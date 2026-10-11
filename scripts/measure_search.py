"""Read-only latency + relevance measurement for /search (SU11A-34).

    venv/bin/python3 -m scripts.measure_search --out /tmp/search_measure.json
    venv/bin/python3 -m scripts.measure_search --dry-run

Calls the real endpoint functions in-process - api.routers.search.search and
api.routers.product.product - with the /search defaults the apps use (limit 30,
offset 0, no city / chain filter, group_by=chain). No HTTP. The functions the
endpoint calls are wrapped (not reimplemented) so each stage is timed:

    candidate   find_barcodes_with_relevance (SQL on items)
    sql_shelf   the _PRICE_SQL statement (server time + transfer to the client)
    sql_promo   the _PROMO_ONLY_SQL statement
    py_fetch    the rest of fetch_prices: row -> dict, zero-price and live-store filters
    group       group_by_product (per-chain cheapest, promo effective price)
    rank_page   the rest of the handler: compare filter, sort, slice, _to_model
    serialize   SearchResult.model_dump_json (stands in for FastAPI's serializer)

/search takes NO location: there is no radius, no distance and no near-me in
the search path. The fixed central Tel Aviv point below is used only to report,
in the relevance dump, how far the store behind each cheapest price is.

Safety: every connection is READ ONLY with statement_timeout 30 s (PGOPTIONS,
which also covers the live-store loader's own connection, plus SET TRANSACTION
READ ONLY per run). Never writes. A query that hits the timeout is recorded and
not repeated. Output holds product data only - no user data, no secrets.
Progress goes to stderr; the summary to stdout; everything to --out as JSON.
"""
from __future__ import annotations

import argparse
import gc
import json
import math
import os
import re
import statistics
import sys
import time
from pathlib import Path

RUNS = 3
TIMEOUT_MS = 30_000
LIMIT, OFFSET = 30, 0  # /search defaults; the mobile and web send limit=30 too
TEL_AVIV = (32.0853, 34.7818)  # central Tel Aviv; for the distance column only

QUERIES: list[tuple[str, str]] = [
    *[("single", q) for q in ["חלב", "לחם", "ביצים", "שמן", "מים", "קפה", "שוקולד",
                              "גבינה", "עוף", "אורז", "טחינה", "חומוס"]],
    *[("brand", q) for q in ["תנובה", "אסם", "קוקה קולה", "שטראוס", "עלית"]],
    *[("multi", q) for q in ["חלב תנובה 3%", "שמן זית", "קפה נמס עלית", "שוקולד מילקה",
                             "משקה קולה זירו"]],
    *[("typo", q) for q in ["חלב תנובא", "שוקלד"]],
    *[("english", q) for q in ["coca cola", "milka"]],
    *[("short", q) for q in ["חל", "ק"]],
]
RELEVANCE = ["חלב", "לחם", "שמן", "קפה", "שוקולד", "תנובה", "חלב תנובה 3%", "שמן זית",
             "קוקה קולה", "coca cola", "חלב תנובא", "שוקלד"]
EXPLAIN = ["חלב", "חלב תנובה 3%", "טחינה"]

FUNCTIONS = [
    "api.routers.search.search  (GET /search handler; limit=30 offset=0 city=None chain=None group_by=chain)",
    "  -> db.query.find_barcodes_with_relevance  [candidate]",
    "  -> db.query.fetch_prices -> db.query._fetch_prices_all  [_PRICE_SQL + _PROMO_ONLY_SQL]",
    "     -> db.query.get_liveness  (live-store set, cached 600 s per process; warmed first)",
    "  -> db.query.group_by_product  [group]",
    "api.routers.search.SearchResult.model_dump_json  [serialize]",
    "api.routers.product.product  (GET /product/{barcode}, for the two barcodes)",
    "  -> db.query.fetch_product -> fetch_prices; group_by_product(per_store=True)",
    "EXPLAIN (ANALYZE, BUFFERS) on the captured candidate / shelf / promo-only statements",
    "read-only catalog queries: barcode picks, item sizes, store coordinates, table + index sizes",
]

_PLAN_TIME = re.compile(r"actual time=([\d.]+)\.\.([\d.]+) rows=(\d+) loops=(\d+)")


# --------------------------------------------------------------------------- env + db
def _load_env() -> None:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    # libpq applies PGOPTIONS to EVERY connection, including the one
    # db.query._load_liveness opens on its own.
    extra = f"-c default_transaction_read_only=on -c statement_timeout={TIMEOUT_MS}"
    os.environ["PGOPTIONS"] = f"{os.environ.get('PGOPTIONS', '')} {extra}".strip()


def _begin(conn) -> None:
    from sqlalchemy import text
    conn.execute(text("SET TRANSACTION READ ONLY"))
    conn.execute(text(f"SET LOCAL statement_timeout = {TIMEOUT_MS}"))


def _label(sql: str) -> str:
    s = sql.lstrip()
    if s.upper().startswith("SET"):
        return "set"
    if "AS tier" in sql:
        return "candidate"
    if "DISTINCT ON" in sql:
        return "promo_only"
    if "JOIN prices" in sql or "FROM prices p" in sql:
        return "shelf"
    return "other"


class Clock:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.ms: dict[str, float] = {}
        self.n: dict[str, int] = {}
        self.statements: dict[str, tuple] = {}

    def add(self, key: str, ms: float) -> None:
        self.ms[key] = self.ms.get(key, 0.0) + ms


class TimedConn:
    """Stands in for the request's Connection; times each execute() by statement kind.

    psycopg2 buffers the whole result client-side inside execute(), so this is
    server time + transfer + tuple parsing; .mappings().all() runs afterwards and
    is counted by the caller's wrapper.
    """

    def __init__(self, conn, clock: Clock) -> None:
        self._conn, self._clock = conn, clock

    def execute(self, clause, params=None, *a, **kw):
        label = _label(getattr(clause, "text", str(clause)))
        t0 = time.perf_counter()
        res = self._conn.execute(clause, params, *a, **kw)
        self._clock.add(f"sql_{label}", (time.perf_counter() - t0) * 1000)
        if label in ("candidate", "shelf", "promo_only"):
            self._clock.statements[label] = (clause, params)
        return res

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _install_wrappers(clock: Clock):
    """Wrap the functions the handlers call, in the namespaces they call them from."""
    import api.routers.product as P
    import api.routers.search as S
    import db.query as Q

    def timed(name, fn, count=None):
        def w(*a, **kw):
            t0 = time.perf_counter()
            out = fn(*a, **kw)
            clock.add(name, (time.perf_counter() - t0) * 1000)
            if count:
                clock.n[count] = count_of(out)
            return out
        return w

    def count_of(out):
        return len(out[0]) if isinstance(out, tuple) else len(out)

    orig = {
        "find": S.find_barcodes_with_relevance, "fetch": S.fetch_prices,
        "group": S.group_by_product, "raw": Q._fetch_prices_all,
    }

    def find(conn, words):
        t0 = time.perf_counter()
        codes, tiers = orig["find"](conn, words)
        clock.add("candidate", (time.perf_counter() - t0) * 1000)
        clock.n["barcodes"] = len(codes)
        clock.n["tiers"] = {str(t): list(tiers.values()).count(t) for t in sorted(set(tiers.values()))}
        clock.statements["tiers"] = tiers
        return codes, tiers

    S.find_barcodes_with_relevance = find
    S.fetch_prices = timed("price_fetch", orig["fetch"], "price_rows")
    S.group_by_product = timed("group", orig["group"], "products")
    Q._fetch_prices_all = timed("raw_fetch", orig["raw"], "price_rows_raw")
    P.fetch_product = timed("price_fetch", P.fetch_product, "price_rows")
    P.group_by_product = timed("group", P.group_by_product, "products")
    return S, P, Q


# --------------------------------------------------------------------------- measuring
def _stages(clock: Clock, handler_ms: float, ser_ms: float) -> dict:
    ms = clock.ms
    sql_shelf, sql_promo = ms.get("sql_shelf", 0.0), ms.get("sql_promo_only", 0.0)
    fetch = ms.get("price_fetch", 0.0)
    out = {
        "candidate": ms.get("candidate", 0.0),
        "sql_shelf": sql_shelf,
        "sql_promo": sql_promo,
        "py_fetch": max(fetch - sql_shelf - sql_promo - ms.get("sql_set", 0.0), 0.0),
        "group": ms.get("group", 0.0),
        "rank_page": max(handler_ms - ms.get("candidate", 0.0) - fetch - ms.get("group", 0.0), 0.0),
        "serialize": ser_ms,
        "distance": None,  # not in the /search path
    }
    out["total"] = handler_ms + ser_ms
    return {k: (round(v, 1) if v is not None else None) for k, v in out.items()}


def _is_timeout(exc: Exception) -> bool:
    return "statement timeout" in str(exc).lower() or "QueryCanceled" in type(getattr(exc, "orig", exc)).__name__


def measure(kind: str, q: str, S, P, clock: Clock, connect, runs: int, barcode_lookup: bool = False) -> dict:
    rec: dict = {"kind": kind, "query": q, "endpoint": "/product/{barcode}" if barcode_lookup else "/search",
                 "runs": [], "flags": []}
    last = None
    for i in range(runs):
        clock.reset()
        conn = connect()
        try:
            _begin(conn)
            tc = TimedConn(conn, clock)
            t0 = time.perf_counter()
            if barcode_lookup:
                result = P.product(barcode=q, conn=tc)
            else:
                result = S.search(q=q, limit=LIMIT, offset=OFFSET, city=None, chain=None,
                                  group_by="chain", conn=tc)
            t1 = time.perf_counter()
            body = result.model_dump_json()
            t2 = time.perf_counter()
        except Exception as exc:  # noqa: BLE001 - recorded, then the next query
            conn.rollback()
            conn.close()
            name = "statement_timeout" if _is_timeout(exc) else type(exc).__name__
            rec["runs"].append({"error": name})
            rec["flags"].append(f"run {i + 1}: {name}")
            break  # never repeat a query that timed out or failed
        conn.rollback()
        conn.close()
        run = {"stages_ms": _stages(clock, (t1 - t0) * 1000, (t2 - t1) * 1000),
               "barcodes": clock.n.get("barcodes"), "tiers": clock.n.get("tiers"),
               "price_rows_raw": clock.n.get("price_rows_raw"), "price_rows": clock.n.get("price_rows"),
               "products": clock.n.get("products"), "response_bytes": len(body)}
        if barcode_lookup:
            run["returned"] = len(result.quotes)
        else:
            run.update(returned=len(result.items), total_matches=result.total_matches,
                       comparable_count=result.comparable_count, has_more=result.has_more)
        rec["runs"].append(run)
        last = (result, dict(clock.statements))
        del body
        gc.collect()

    ok = [r for r in rec["runs"] if "error" not in r]
    if ok:
        totals = [r["stages_ms"]["total"] for r in ok]
        rec["total_min_ms"] = round(min(totals), 1)
        rec["total_median_ms"] = round(statistics.median(totals), 1)
        rec["stages_median_ms"] = {
            k: (round(statistics.median([r["stages_ms"][k] for r in ok]), 1)
                if ok[0]["stages_ms"][k] is not None else None)
            for k in ok[0]["stages_ms"]}
        if not barcode_lookup and ok[-1]["returned"] == 0:
            rec["flags"].append("ZERO RESULTS")
    return rec, last


# --------------------------------------------------------------------------- relevance
def _km(a, b) -> float | None:
    if None in (*a, *b):
        return None
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return round(6371 * 2 * math.asin(math.sqrt(h)), 1)


def relevance_top10(conn, result, tiers: dict) -> list[dict]:
    from sqlalchemy import bindparam, text
    items = result.items[:10]
    if not items:
        return []
    codes = [it.product.item_code for it in items]
    fks = [it.quotes[0].store_fk for it in items if it.quotes and it.quotes[0].store_fk is not None]
    sizes = {r.item_code: r for r in conn.execute(text(
        "SELECT item_code, quantity, unit_qty FROM items WHERE item_code IN :c"
    ).bindparams(bindparam("c", expanding=True)), {"c": codes})}
    pos = {}
    if fks:
        pos = {r.id: (r.lat, r.lon) for r in conn.execute(text(
            "SELECT id, lat, lon FROM stores WHERE id IN :f"
        ).bindparams(bindparam("f", expanding=True)), {"f": fks})}
    out = []
    for rank, it in enumerate(items, 1):
        p, q0 = it.product, (it.quotes[0] if it.quotes else None)
        sz = sizes.get(p.item_code)
        size = " ".join(str(x) for x in (sz.quantity if sz else None, sz.unit_qty if sz else None) if x not in (None, ""))
        out.append({
            "rank": rank, "item_code": p.item_code, "name": p.canonical_name, "brand": p.manufacturer,
            "size": size or None, "tier": tiers.get(p.item_code), "chains": it.chains_count,
            "lowest_price": it.cheapest_price,
            "cheapest_at": f"{q0.chain_name} / {q0.store_name} / {q0.city}" if q0 else None,
            "cheapest_km_from_tel_aviv": _km(TEL_AVIV, pos.get(q0.store_fk, (None, None))) if q0 else None,
        })
    return out


# --------------------------------------------------------------------------- explain
def _explain_clause(clause):
    from sqlalchemy import bindparam, text
    e = text("EXPLAIN (ANALYZE, BUFFERS) " + clause.text)
    expanding = [b.key for b in clause._bindparams.values() if b.expanding]
    return e.bindparams(*[bindparam(k, expanding=True) for k in expanding]) if expanding else e


def _plan_summary(lines: list[str]) -> dict:
    nodes = []
    for ln in lines:
        m = _PLAN_TIME.search(ln)
        if not m:
            continue
        indent = ln.index("->") if "->" in ln else -1
        name = ln.split("->", 1)[-1].split("  (")[0].strip() if "->" in ln else ln.split("  (")[0].strip()
        nodes.append({"indent": indent, "name": name,
                      "incl_ms": float(m.group(2)) * int(m.group(4)), "rows": int(m.group(3))})
    for i, n in enumerate(nodes):  # exclusive = inclusive - direct children
        child_ms, j = 0.0, i + 1
        child_indent = None
        while j < len(nodes) and nodes[j]["indent"] > n["indent"]:
            if child_indent is None:
                child_indent = nodes[j]["indent"]
            if nodes[j]["indent"] == child_indent:
                child_ms += nodes[j]["incl_ms"]
            j += 1
        n["excl_ms"] = max(n["incl_ms"] - child_ms, 0.0)
    exe = next((ln for ln in lines if ln.startswith("Execution Time")), None)
    big = max(nodes, key=lambda n: n["excl_ms"]) if nodes else None
    return {"top_node": lines[0].split("  (")[0].strip() if lines else None,
            "execution_time": exe.split(":", 1)[1].strip() if exe else None,
            "planning_time": next((ln.split(":", 1)[1].strip() for ln in lines if ln.startswith("Planning Time")), None),
            "biggest_node": (f"{big['name']} ~{big['excl_ms']:.0f} ms self, rows={big['rows']} "
                             "(approx.; parallel workers counted by loops)") if big else None}


def explain(connect, statements: dict) -> dict:
    out = {}
    for label in ("candidate", "shelf", "promo_only"):
        if label not in statements:
            out[label] = {"error": "statement not captured (zero candidates or failed run)"}
            continue
        clause, params = statements[label]
        conn = connect()
        try:
            _begin(conn)
            lines = [r[0] for r in conn.execute(_explain_clause(clause), params)]
            out[label] = {"summary": _plan_summary(lines), "plan": lines}
        except Exception as exc:  # noqa: BLE001
            out[label] = {"error": "statement_timeout" if _is_timeout(exc) else type(exc).__name__}
        finally:
            conn.rollback()
            conn.close()
    return out


# --------------------------------------------------------------------------- catalog facts
def pick_barcodes(conn) -> dict:
    from sqlalchemy import text
    popular = conn.execute(text("""
        SELECT item_code, count(*) AS chains FROM item_chain_names
        WHERE item_code ~ '^729[0-9]{10}$'
        GROUP BY item_code ORDER BY chains DESC, item_code LIMIT 1
    """)).first()
    rare = conn.execute(text("""
        SELECT icn.item_code, count(*) AS chains FROM item_chain_names icn
        WHERE icn.item_code ~ '^729[0-9]{10}$'
        GROUP BY icn.item_code
        HAVING count(*) = 1
           AND (SELECT count(*) FROM prices p WHERE p.item_code = icn.item_code) BETWEEN 1 AND 3
        ORDER BY icn.item_code LIMIT 1
    """)).first()
    out = {}
    for key, row in (("popular", popular), ("rare", rare)):
        if row:
            n = conn.execute(text("SELECT count(*) FROM prices WHERE item_code = :c"), {"c": row.item_code}).scalar()
            name = conn.execute(text("SELECT item_name FROM items WHERE item_code = :c"), {"c": row.item_code}).scalar()
            out[key] = {"item_code": row.item_code, "chains": row.chains, "price_rows": n, "name": name}
    return out


def table_facts(conn) -> dict:
    from sqlalchemy import text
    tables = ("items", "item_chain_names", "prices", "stores", "promos", "chains")
    sizes = [dict(r._mapping) for r in conn.execute(text("""
        SELECT c.relname AS table, c.reltuples::bigint AS est_rows,
               pg_relation_size(c.oid) AS heap_bytes, pg_indexes_size(c.oid) AS index_bytes,
               pg_total_relation_size(c.oid) AS total_bytes
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = ANY(:t)
        ORDER BY c.relname
    """), {"t": list(tables)})]
    for s in sizes:  # exact counts only where they are cheap; prices stays an estimate
        if s["table"] in ("items", "stores", "chains", "item_chain_names"):
            s["exact_rows"] = conn.execute(text(f'SELECT count(*) FROM "{s["table"]}"')).scalar()
    indexes = [dict(r._mapping) for r in conn.execute(text("""
        SELECT tablename AS table, indexname AS index, indexdef AS definition,
               pg_relation_size(format('%I.%I', schemaname, indexname)::regclass) AS bytes
        FROM pg_indexes WHERE schemaname = 'public' AND tablename = ANY(:t)
        ORDER BY tablename, indexname
    """), {"t": list(tables)})]
    ext = [dict(r._mapping) for r in conn.execute(text("SELECT extname, extversion FROM pg_extension ORDER BY 1"))]
    settings = [dict(r._mapping) for r in conn.execute(text("""
        SELECT name, setting, unit FROM pg_settings WHERE name IN
        ('shared_buffers','work_mem','effective_cache_size','max_parallel_workers_per_gather',
         'random_page_cost','jit','server_version')
    """))]
    return {"tables": sizes, "indexes": indexes, "extensions": ext, "settings": settings,
            "note": "prices row count is pg_class.reltuples (estimate); an exact count would scan the whole table"}


# --------------------------------------------------------------------------- output
def _mb(b) -> str:
    return f"{b / 1048576:,.0f} MB" if b is not None else "?"


def print_summary(report: dict) -> None:
    p = print
    p("\n=== SU11A-34 search measurement (read-only) ===")
    p(f"runs per query: {report['runs']}, limit={LIMIT}, offset={OFFSET}, no city/chain; "
      f"liveness warm-up {report['liveness_warmup_ms']} ms")
    bc = report["barcodes"]
    for k, v in bc.items():
        p(f"barcode {k}: {v['item_code']} chains={v['chains']} price_rows={v['price_rows']} name={v['name']}")
    p("\nquery | endpoint | codes | rows raw/kept | cand | sql_shelf | sql_promo | py_fetch | group | rank_page | ser | total min/med ms | returned | flags")
    for r in report["queries"]:
        ok = [x for x in r["runs"] if "error" not in x]
        st = r.get("stages_median_ms") or {}
        last = ok[-1] if ok else {}
        g = lambda k: "-" if st.get(k) is None else f"{st[k]:.0f}"
        p(f"{r['query']} | {r['endpoint']} | {last.get('barcodes', '-')} | "
          f"{last.get('price_rows_raw', '-')}/{last.get('price_rows', '-')} | {g('candidate')} | {g('sql_shelf')} | "
          f"{g('sql_promo')} | {g('py_fetch')} | {g('group')} | {g('rank_page')} | {g('serialize')} | "
          f"{r.get('total_min_ms', '-')}/{r.get('total_median_ms', '-')} | {last.get('returned', '-')} | "
          f"{'; '.join(r['flags']) or ''}")
    p("\n--- relevance: top 10 as /search returns them (km = cheapest store from central Tel Aviv) ---")
    for q, rows in report["relevance"].items():
        p(f"\n[{q}]")
        if not rows:
            p("  (no results)")
        for x in rows:
            p(f"  {x['rank']:>2}. {x['name']} | {x['brand']} | {x['size'] or '-'} | tier {x['tier']} | "
              f"{x['chains']} chains | {x['lowest_price']} | {x['cheapest_km_from_tel_aviv']} km")
    p("\n--- EXPLAIN (ANALYZE, BUFFERS) summaries (full plans in the JSON) ---")
    for q, plans in report["explain"].items():
        for label, e in plans.items():
            if "error" in e:
                p(f"[{q}] {label}: {e['error']}")
            else:
                s = e["summary"]
                p(f"[{q}] {label}: top={s['top_node']} | exec {s['execution_time']} | biggest: {s['biggest_node']}")
    p("\n--- table sizes ---")
    for t in report["tables"]["tables"]:
        p(f"{t['table']}: rows {t.get('exact_rows', str(t['est_rows']) + ' (est)')}, heap {_mb(t['heap_bytes'])}, "
          f"indexes {_mb(t['index_bytes'])}, total {_mb(t['total_bytes'])}")
    for i in report["tables"]["indexes"]:
        if i["table"] in ("prices", "items", "item_chain_names"):
            p(f"  {i['table']}.{i['index']} {_mb(i['bytes'])}: {i['definition']}")
    p("extensions: " + ", ".join(f"{e['extname']} {e['extversion']}" for e in report["tables"]["extensions"]))
    p("settings: " + ", ".join(f"{s['name']}={s['setting']}{s['unit'] or ''}" for s in report["tables"]["settings"]))
    p(f"\nelapsed {report['elapsed_s']} s; full JSON: {report['out']}")


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="/tmp/search_measure.json", help="JSON output path")
    ap.add_argument("--runs", type=int, default=RUNS, help="runs per query (default 3)")
    ap.add_argument("--dry-run", action="store_true", help="list queries and functions; no database")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # Hebrew on any console
        stream.reconfigure(encoding="utf-8")

    if args.dry_run:
        print("queries (kind, text):")
        for k, q in QUERIES:
            print(f"  {k:8} {q}")
        print("  barcode  <popular, picked read-only from item_chain_names>  (/search and /product)")
        print("  barcode  <rare, picked read-only from item_chain_names>     (/search and /product)")
        print(f"relevance dump (top 10): {', '.join(RELEVANCE)}")
        print(f"EXPLAIN (ANALYZE, BUFFERS): {', '.join(EXPLAIN)}")
        print(f"runs per query: {args.runs}; statement_timeout {TIMEOUT_MS} ms; READ ONLY transactions")
        print("functions:")
        for f in FUNCTIONS:
            print(f"  {f}")
        return 0

    _load_env()
    from db.db import connect

    clock = Clock()
    S, P, Q = _install_wrappers(clock)
    started = time.perf_counter()
    report: dict = {"session": "SU11A-34", "runs": args.runs, "limit": LIMIT, "offset": OFFSET,
                    "tel_aviv": TEL_AVIV, "out": args.out, "queries": [], "relevance": {}, "explain": {}}

    t0 = time.perf_counter()
    Q.get_liveness()  # what a warm gunicorn worker has cached
    report["liveness_warmup_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    conn = connect()
    try:
        _begin(conn)
        report["barcodes"] = pick_barcodes(conn)
    finally:
        conn.rollback()
        conn.close()

    plan = list(QUERIES)
    for key in ("popular", "rare"):
        if key in report["barcodes"]:
            code = report["barcodes"][key]["item_code"]
            plan += [(f"barcode-{key}", code), (f"barcode-{key}-lookup", code)]

    for n, (kind, q) in enumerate(plan, 1):
        print(f"[{n}/{len(plan)}] {kind}: {q}", file=sys.stderr, flush=True)
        rec, last = measure(kind, q, S, P, clock, connect, args.runs, barcode_lookup=kind.endswith("-lookup"))
        report["queries"].append(rec)
        if last and q in RELEVANCE and not kind.endswith("-lookup"):
            conn = connect()
            try:
                _begin(conn)
                report["relevance"][q] = relevance_top10(conn, last[0], last[1].get("tiers", {}))
            finally:
                conn.rollback()
                conn.close()
        elif q in RELEVANCE:
            report["relevance"][q] = []
        if q in EXPLAIN and kind in ("single", "multi"):
            print(f"    explain: {q}", file=sys.stderr, flush=True)
            report["explain"][q] = explain(connect, last[1] if last else {})
        del last
        gc.collect()

    conn = connect()
    try:
        _begin(conn)
        report["tables"] = table_facts(conn)
    finally:
        conn.rollback()
        conn.close()

    report["elapsed_s"] = round(time.perf_counter() - started, 1)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print_summary(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
