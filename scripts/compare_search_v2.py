"""Read-only comparison of search v2 against the old /search (SU11A-36).

    venv/bin/python3 -m scripts.compare_search_v2 --out /tmp/search_v2_compare.json
    venv/bin/python3 -m scripts.compare_search_v2 --dry-run
    venv/bin/python3 -m scripts.compare_search_v2 --check-precomputed 300
    venv/bin/python3 -m scripts.compare_search_v2 --filtered [--out /tmp/search_filtered_compare.json]

--filtered (SU11A-50): the filtered v2 path (db/search_filtered.py) against the
old path, in-process, independent of SEARCH_V2_FILTERED. Read-only, like the
rest of this script.
  1. Candidate step (the Ranked stream): for the 12 standard queries, the top 10
     from the stream vs the full SU11A-36 ranking (must be identical), and the
     candidate-step time of both.
  2. /compare in a city: חלב לחם במבה שוקולד קפה ים x רמת גן, בני ברק, ירושלים,
     אילת (limit 20). Old path ONCE per pair (it is the heavy one), new path 3
     times (min / median). Overlap of the two first-20 lists, items only in
     one of them, and PRICE MISMATCHES: every new page item that the old path
     also priced must have the identical product JSON (must be 0). "not in
     reference" = new items the old path did not price (it stops at its
     1,000-candidate cap; the new walk goes to 3,000). Eilat check:
     city=אילת shows only Eilat quotes.
  3. Chain filter (/search?chain=, three chains) and /compare without a city
     (two queries): the reference is the live fetch with the Eilat rule over
     all chains, then the chain filter (what search v2 shows nationwide); the
     old path does not apply the Eilat rule, so it is not the reference here.
     Old path timed once. Eilat check: no Eilat quote on an item that has a
     quote elsewhere.
  Go/no-go (runbook step d): 0 price mismatches, 0 stream differences, new p50
  <= 400 ms, no error / timeout in the new path, Eilat checks pass.

--check-precomputed N (SU11A-47): N random live, non-pseudo items, in pages of
30: the page's products from search_item_prices vs from the live fetch
(fetch_prices + Eilat rule), both through group_by_product and the API's
_to_model, compared as JSON. Prints every mismatch with the first differing
field, and the pages search_item_prices could not serve (stale build, ended
promo, item missing - the API takes the live fetch for those). Same read-only
connections as the rest of this script.

Runs both engines in-process, with what the apps send (limit 30, offset 0, no
city / chain filter, group_by=chain). No HTTP, independent of SEARCH_V2:
    old  api.routers.search._build_result  (unchanged old path)
    v2   db.search_v2.run                  (+ the router's _to_model for the page)

Queries: the 30 /search queries of scripts/measure_search.py (28 texts + the
popular and rare barcodes) plus Milka, דג and a 12-digit UPC-A barcode (the
others the SU11A-36 spec lists - milka, coca cola, חלב תנובא, חל, ק - are
already among the 30). Per query: v2 latency (3 runs, min/median), old latency
(3 runs, 1 run when the old path matches more than 2000 barcodes),
total_matches and comparable_count old vs v2, top-10 overlap. Then the v2 top
10 for 12 queries, the coupon pseudo-items that left the old top 10, and how
many top-10 results had an Eilat cheapest price before vs after.

Safety: every connection READ ONLY (PGOPTIONS default_transaction_read_only,
also covering the liveness loader's own connection, plus SET TRANSACTION READ
ONLY) with statement_timeout 60 s. A query that fails or times out is recorded
and not repeated. Product data only - no user data, no secrets. Progress to
stderr, summary to stdout, everything to --out as JSON.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = 3
OLD_SINGLE_RUN_ABOVE = 2000   # barcodes; the old path is run once above this
TIMEOUT_MS = 60_000
LIMIT, OFFSET = 30, 0
EXTRA = ["milka", "Milka", "coca cola", "חלב תנובא", "<upc-a>", "חל", "ק", "דג"]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _load_env() -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    extra = f"-c default_transaction_read_only=on -c statement_timeout={TIMEOUT_MS}"
    os.environ["PGOPTIONS"] = f"{os.environ.get('PGOPTIONS', '')} {extra}".strip()


class ReadOnly:
    """A fresh READ ONLY connection per run; always rolled back and closed."""

    def __enter__(self):
        from sqlalchemy import text
        from db.db import connect
        self.conn = connect()
        self.conn.execute(text("SET TRANSACTION READ ONLY"))
        self.conn.execute(text(f"SET LOCAL statement_timeout = {TIMEOUT_MS}"))
        return self.conn

    def __exit__(self, *exc):
        self.conn.rollback()
        self.conn.close()
        return False


def _err(exc: Exception) -> str:
    s = str(exc).lower()
    return "statement_timeout" if "statement timeout" in s or "canceling statement" in s else type(exc).__name__


def _ms(xs: list[float]) -> dict:
    return {"min": round(min(xs), 1), "median": round(statistics.median(xs), 1), "runs": len(xs)} if xs else {}


def run_old(S, q: str, runs: int) -> tuple[dict, object | None]:
    times, last, err = [], None, None
    for _ in range(runs):
        try:
            with ReadOnly() as conn:
                t0 = time.perf_counter()
                last = S._build_result(q, conn, LIMIT, OFFSET, None, None, compare_only=False, group_by="chain")
                times.append((time.perf_counter() - t0) * 1000)
        except Exception as exc:  # noqa: BLE001 - recorded, never repeated
            err = _err(exc)
            break
        gc.collect()
    return {"ms": _ms(times), "error": err}, last


def run_v2(V, q: str, runs: int) -> tuple[dict, object | None]:
    times, last, err = [], None, None
    for _ in range(runs):
        try:
            with ReadOnly() as conn:
                t0 = time.perf_counter()
                last = V.run(conn, q, limit=LIMIT, offset=OFFSET)
                times.append((time.perf_counter() - t0) * 1000)
        except Exception as exc:  # noqa: BLE001
            err = f"{_err(exc)}: {exc}" if isinstance(exc, V.V2Unavailable) else _err(exc)
            break
    return {"ms": _ms(times), "error": err, "stages_ms": getattr(last, "timings_ms", None)}, last


def _first_diff(a, b, path: str = "") -> str:
    """Path and values of the first difference between two JSON values."""
    if type(a) is not type(b):
        return f"{path or '/'}: {a!r} != {b!r}"
    if isinstance(a, dict):
        for k in list(dict.fromkeys([*a, *b])):
            if k not in a or k not in b:
                return f"{path}/{k}: only in {'precomputed' if k in a else 'live'}"
            if a[k] != b[k]:
                return _first_diff(a[k], b[k], f"{path}/{k}")
        return f"{path}: key order differs: {list(a)} != {list(b)}"
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: {len(a)} entries != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return _first_diff(x, y, f"{path}[{i}]")
    return f"{path or '/'}: {a!r} != {b!r}"


def check_precomputed(n: int, out: str | None) -> int:
    """--check-precomputed: precomputed vs live page prices for n random items."""
    import api.routers.search as S
    import db.query as Q
    import db.search_v2 as V
    from sqlalchemy import text

    started = time.perf_counter()
    Q.get_liveness()
    with ReadOnly() as conn:
        stamps = conn.execute(text(
            "SELECT (SELECT built_at FROM search_items LIMIT 1), "
            "CASE WHEN to_regclass('public.search_item_prices') IS NULL THEN NULL "
            "ELSE (SELECT built_at FROM search_item_prices LIMIT 1) END")).one()
        codes = [r[0] for r in conn.execute(text(
            "SELECT item_code FROM search_items WHERE NOT is_pseudo ORDER BY random() LIMIT :n"), {"n": n})]
        eilat = frozenset(r[0] for r in conn.execute(
            text("SELECT id FROM stores WHERE city_canonical = :c"), {"c": V.EILAT}))
        pre_rows = conn.execute(text("SELECT count(*) FROM search_item_prices")).scalar() \
            if stamps[1] is not None else 0
    print(f"search_items built_at {stamps[0]}; search_item_prices built_at {stamps[1]} ({pre_rows} rows)")
    if stamps[1] is None or stamps[0] != stamps[1]:
        print("STOP: search_item_prices is missing, empty or from another build - the API would not use it")
        return 2

    def as_json(products: dict, page: list[str]) -> dict[str, dict]:
        return {c: json.loads(S._to_model(products[c]).model_dump_json()) for c in page if c in products}

    checked, mismatches, unusable, ms_pre, ms_live = 0, [], [], [], []
    for i in range(0, len(codes), 30):
        page = codes[i:i + 30]
        V._cache.built_at = V._cache.prices_built_at = None
        with ReadOnly() as conn:
            t0 = time.perf_counter()
            rows = V._precomputed_rows(conn, page)
            ms_pre.append((time.perf_counter() - t0) * 1000)
            t0 = time.perf_counter()
            live = as_json(Q.group_by_product(V.drop_eilat(Q.fetch_prices(conn, page), eilat)), page)
            ms_live.append((time.perf_counter() - t0) * 1000)
            if rows is None:   # find which items, one by one
                good = []
                for c in page:
                    r1 = V._precomputed_rows(conn, [c])
                    if r1 is None:
                        unusable.append(c)
                    else:
                        good.extend(r1)
                rows = good
        pre = as_json(Q.group_by_product(rows), page)
        for c in page:
            if c in unusable:
                continue
            checked += 1
            if pre.get(c) != live.get(c):
                mismatches.append({"item_code": c, "diff": _first_diff(pre.get(c), live.get(c))})
        log(f"{min(i + 30, len(codes))}/{len(codes)}: {len(mismatches)} mismatches, {len(unusable)} not served")

    rep = {"session": "SU11A-47", "mode": "check-precomputed", "items": len(codes), "checked": checked,
           "mismatches": mismatches, "not_served_by_precomputed": unusable,
           "page_ms": {"precomputed": _ms(ms_pre), "live": _ms(ms_live)},
           "elapsed_s": round(time.perf_counter() - started, 1)}
    print(f"\n=== SU11A-47 precomputed vs live page prices (read-only) ===")
    print(f"items {len(codes)}; compared {checked}; MISMATCHES {len(mismatches)}; "
          f"not served by search_item_prices (API uses the live fetch): {len(unusable)}")
    for m in mismatches[:30]:
        print(f"  {m['item_code']}: {m['diff']}")
    if unusable:
        print(f"  not served: {', '.join(unusable[:30])}")
    print(f"page of 30, ms min/median: precomputed {rep['page_ms']['precomputed']} | live {rep['page_ms']['live']}")
    print(f"elapsed {rep['elapsed_s']} s")
    if out:
        Path(out).write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"JSON: {out}")
    return 1 if mismatches else 0


FILTERED_QUERIES = ["חלב", "לחם", "במבה", "שוקולד", "קפה", "ים"]
FILTERED_CITIES = ["רמת גן", "בני ברק", "ירושלים", "אילת"]
FILTERED_LIMIT = 20


def _timed(fn, runs: int) -> tuple[dict, object | None, str | None]:
    times, last, err = [], None, None
    for _ in range(runs):
        try:
            with ReadOnly() as conn:
                t0 = time.perf_counter()
                last = fn(conn)
                times.append((time.perf_counter() - t0) * 1000)
        except Exception as exc:  # noqa: BLE001 - recorded, never repeated
            err = _err(exc)
            break
        gc.collect()
    return _ms(times), last, err


def filtered(out: str | None, runs: int) -> int:
    """--filtered: the SU11A-50 filtered v2 path against the old path (read-only)."""
    import api.routers.search as S
    import db.query as Q
    import db.search_filtered as F
    import db.search_v2 as V
    from db.search_norm import normalize, tokenize
    from scripts.measure_search import RELEVANCE
    from sqlalchemy import text

    started = time.perf_counter()
    Q.get_liveness()
    with ReadOnly() as conn:
        V.check_ready(conn)
        aliases, eilat = V._lexicon(conn)
        chains = [r[0] for r in conn.execute(text("""
            SELECT s.chain_id FROM stores s GROUP BY s.chain_id ORDER BY count(*) DESC LIMIT 3"""))]
        pre_ok = F.precomputed_ok(conn)
    rep: dict = {"session": "SU11A-50", "mode": "filtered", "precomputed_usable": pre_ok, "stream": [],
                 "city": [], "nationwide": []}

    def j(p) -> dict:
        return json.loads(S._to_model(p).model_dump_json())

    # 1. the candidate stream against the full ranking
    stream_diffs = 0
    for q in RELEVANCE:
        qn = normalize(q)
        groups = V.apply_aliases(tokenize(qn), aliases)
        with ReadOnly() as conn:
            t0 = time.perf_counter()
            full = V.rank(V._candidates(conn, groups), groups, qn)
            old_ms = (time.perf_counter() - t0) * 1000
        ms, r, err = _timed(lambda c: V._ranked(c, groups, qn).take(10), runs)
        same = err is None and [x["item_code"] for x in r] == [x["item_code"] for x in full[:10]]
        stream_diffs += not same
        rep["stream"].append({"query": q, "matches": len(full), "old_ms": round(old_ms, 1), "new_ms": ms,
                              "same_top10": same, "error": err})
        log(f"stream {q}: {len(full)} matches, same top 10: {same}")

    def check(mode, q, f, old_fn, new_fn, ref_fn=None):
        log(f"{mode} {q} {f or ''}")
        new_ms, new, new_err = _timed(new_fn, runs)
        old_ms, old, old_err = _timed(old_fn, 1)
        rec = {"mode": mode, "query": q, "filter": f, "new_ms": new_ms, "old_ms": old_ms,
               "new_error": new_err, "old_error": old_err}
        if new is None:
            return rec
        rec.update(new_mode=new.mode, walked=new.walked, total=new.total_matches, has_more=new.has_more,
                   stages_ms={k: v for k, v in new.timings_ms.items() if k != "total"})
        new_codes = [p["item_code"] for p in new.products]
        old_codes = [it.product.item_code for it in old.items[:FILTERED_LIMIT]] if old else []
        rec["overlap_first20"] = len(set(new_codes) & set(old_codes))
        rec["only_old"] = [c for c in old_codes if c not in new_codes]
        rec["only_new"] = [c for c in new_codes if c not in old_codes]
        if ref_fn is not None:
            with ReadOnly() as conn:
                ref = ref_fn(conn, new_codes)
        elif old is not None:
            ref = {it.product.item_code: json.loads(it.model_dump_json()) for it in old.items}
        else:
            ref = {}
        mism = [c for p, c in zip(new.products, new_codes) if c in ref and j(p) != ref[c]]
        rec["price_mismatches"] = [{"item_code": c, "diff": _first_diff(
            j(next(p for p in new.products if p["item_code"] == c)), ref[c])} for c in mism]
        rec["not_in_reference"] = [c for c in new_codes if c not in ref]
        quotes = [qt for p in new.products for qt in p["quotes"]]
        if f == V.EILAT:
            rec["eilat_ok"] = all(qt["store_fk"] in eilat for qt in quotes)
        elif mode != "city":
            rec["eilat_ok"] = all(not ({qt["store_fk"] for qt in p["quotes"]} & eilat)
                                  or {qt["store_fk"] for qt in p["quotes"]} <= eilat for p in new.products)
        return rec

    # 2. /compare in a city: the old path is the reference
    for q in FILTERED_QUERIES:
        for city in FILTERED_CITIES:
            rep["city"].append(check(
                "city", q, city,
                lambda c, q=q, city=city: S._build_result(q, c, 1000, 0, [city], None, compare_only=True),
                lambda c, q=q, city=city: F.run(c, q, limit=FILTERED_LIMIT, offset=0, city=[city],
                                                compare_only=True)))

    # 3. nationwide modes: the live fetch with the Eilat rule over all chains is the reference
    def reference(chain):
        def ref(conn, codes):
            rows = V.drop_eilat(Q.fetch_prices(conn, codes), eilat, None)
            if chain:
                rows = [r for r in rows if r["chain_id"] in chain]
            g = Q.group_by_product(rows)
            return {c: j(g[c]) for c in codes if c in g}
        return ref

    for q in ("חלב", "שוקולד"):
        for ch in chains:
            rep["nationwide"].append(check(
                "chain", q, ch,
                lambda c, q=q, ch=ch: S._build_result(q, c, FILTERED_LIMIT, 0, None, [ch], compare_only=False),
                lambda c, q=q, ch=ch: F.run(c, q, limit=FILTERED_LIMIT, offset=0, chain=[ch]),
                reference([ch])))
    for q in ("חלב", "במבה"):
        rep["nationwide"].append(check(
            "compare", q, None,
            lambda c, q=q: S._build_result(q, c, FILTERED_LIMIT, 0, None, None, compare_only=True),
            lambda c, q=q: F.run(c, q, limit=FILTERED_LIMIT, offset=0, compare_only=True),
            reference(None)))

    rows = rep["city"] + rep["nationwide"]
    meds = sorted(r["new_ms"]["median"] for r in rows if r.get("new_ms"))
    p50 = meds[len(meds) // 2] if meds else None
    n_mism = sum(len(r.get("price_mismatches", [])) for r in rows)
    new_errors = [f"{r['mode']} {r['query']} {r['filter'] or ''}: {r['new_error']}" for r in rows if r["new_error"]]
    eilat_bad = [f"{r['mode']} {r['query']} {r['filter'] or ''}" for r in rows if r.get("eilat_ok") is False]
    rep["summary"] = {"stream_differences": stream_diffs, "price_mismatches": n_mism, "new_p50_ms": p50,
                      "new_errors": new_errors, "eilat_failures": eilat_bad,
                      "go": stream_diffs == 0 and n_mism == 0 and p50 is not None and p50 <= 400
                      and not new_errors and not eilat_bad}
    rep["elapsed_s"] = round(time.perf_counter() - started, 1)

    p = print
    p("\n=== SU11A-50 filtered v2 path vs old path (read-only) ===")
    p(f"search_item_prices usable: {pre_ok}")
    p("\n-- 1. candidate stream vs full ranking (12 standard queries) --")
    p("query | matches | old ms (all rows + rank) | new ms min/med | same top 10")
    for r in rep["stream"]:
        m = r["new_ms"]
        p(f"{r['query']} | {r['matches']} | {r['old_ms']:.0f} | "
          f"{m.get('min', 0):.0f}/{m.get('median', 0):.0f} | {r['same_top10']}{' ' + r['error'] if r['error'] else ''}")

    def line(r):
        nm, om = r.get("new_ms") or {}, r.get("old_ms") or {}
        errs = "; ".join(x for x in (r["new_error"] and f"new: {r['new_error']}", r["old_error"] and f"old: {r['old_error']}") if x)
        return (f"{r['mode']} | {r['query']} | {r['filter'] or '-'} | "
                f"{nm.get('min', 0):.0f}/{nm.get('median', 0):.0f} | {om.get('min', 0):.0f} | "
                f"{r.get('stages_ms', '')} | {r.get('walked', '')} | {r.get('overlap_first20', '')} | "
                f"{len(r.get('only_old', []))}/{len(r.get('only_new', []))} | {len(r.get('price_mismatches', []))} | "
                f"{len(r.get('not_in_reference', []))} | {r.get('eilat_ok', '')} | {errs}")
    hdr = ("mode | query | filter | new ms min/med | old ms | new stages | walked | overlap first 20 | "
           "only old/new | PRICE MISMATCHES | not in reference | eilat ok | errors")
    p("\n-- 2. /compare in a city (reference: the old path) --")
    p(hdr)
    for r in rep["city"]:
        p(line(r))
    p("\n-- 3. chain filter and /compare without a city (reference: live fetch + Eilat rule over all chains) --")
    p(hdr)
    for r in rep["nationwide"]:
        p(line(r))
    for r in rows:
        for m in r.get("price_mismatches", [])[:5]:
            p(f"  mismatch {r['mode']} {r['query']} {r['filter'] or ''}: {m['item_code']} {m['diff']}")
    sm = rep["summary"]
    p(f"\nSUMMARY: stream differences {sm['stream_differences']} | price mismatches {sm['price_mismatches']} | "
      f"new p50 {sm['new_p50_ms']} ms | new errors {len(sm['new_errors'])} | Eilat failures {len(sm['eilat_failures'])}")
    for e in sm["new_errors"] + sm["eilat_failures"]:
        p(f"  {e}")
    p("GO" if sm["go"] else "NO-GO")
    p(f"elapsed {rep['elapsed_s']} s")
    if out:
        Path(out).write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        p(f"JSON: {out}")
    return 0 if sm["go"] else 1


def pick_upc(conn, popular: str | None) -> tuple[str | None, str]:
    from sqlalchemy import text
    if popular and len(popular) == 13 and popular.startswith("0"):
        return popular[1:], f"UPC-A form of the popular barcode {popular}"
    row = conn.execute(text("""
        SELECT item_code FROM search_items
        WHERE item_code ~ '^0[0-9]{12}$' AND NOT is_pseudo
        ORDER BY chains_live DESC, item_code LIMIT 1
    """)).first()
    if not row:
        return None, "no live 13-digit barcode starting with 0 - UPC-A case skipped"
    return row[0][1:], (f"the popular barcode {popular} starts with 7 and has no UPC-A form; "
                        f"used {row[0]} (most chains among 0-prefixed EAN-13) as 12 digits")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="/tmp/search_v2_compare.json")
    ap.add_argument("--runs", type=int, default=RUNS)
    ap.add_argument("--dry-run", action="store_true", help="list the queries; no database")
    ap.add_argument("--check-precomputed", type=int, metavar="N", default=None,
                    help="SU11A-47: compare search_item_prices with the live fetch for N random items")
    ap.add_argument("--filtered", action="store_true",
                    help="SU11A-50: the filtered v2 path (/compare, city / chain filters) vs the old path")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(ROOT))
    if args.check_precomputed is not None:
        _load_env()
        out = args.out if args.out != ap.get_default("out") else None
        return check_precomputed(max(1, args.check_precomputed), out)
    if args.filtered:
        if args.dry_run:
            print(f"queries: {' | '.join(FILTERED_QUERIES)} x cities: {' | '.join(FILTERED_CITIES)} (/compare, "
                  f"limit {FILTERED_LIMIT}); chain filter for the 3 largest chains x חלב, שוקולד; "
                  f"/compare without a city x חלב, במבה; stream check on the 12 standard queries")
            print(f"runs: new {args.runs}, old 1; READ ONLY, statement_timeout {TIMEOUT_MS} ms")
            return 0
        _load_env()
        out = args.out if args.out != ap.get_default("out") else None
        return filtered(out, args.runs)
    from scripts.measure_search import QUERIES, RELEVANCE

    texts = [q for _, q in QUERIES]
    if args.dry_run:
        print("queries: " + " | ".join(texts + ["<popular barcode>", "<rare barcode>"] +
                                       [q for q in EXTRA if q not in texts]))
        print(f"top-10 dump for: {', '.join(RELEVANCE)}")
        print(f"runs: v2 {args.runs}; old {args.runs} (1 above {OLD_SINGLE_RUN_ABOVE} barcodes); "
              f"READ ONLY, statement_timeout {TIMEOUT_MS} ms")
        return 0

    _load_env()
    import api.routers.search as S
    import db.query as Q
    import db.search_v2 as V
    from sqlalchemy import bindparam, text
    from scripts.measure_search import pick_barcodes

    started = time.perf_counter()
    Q.get_liveness()
    with ReadOnly() as conn:
        bc = pick_barcodes(conn)
        upc, upc_note = pick_upc(conn, bc.get("popular", {}).get("item_code"))
        built = conn.execute(text("SELECT max(built_at), count(*), count(*) FILTER (WHERE is_pseudo) "
                                  "FROM search_items")).one()
        eilat = frozenset(r[0] for r in conn.execute(
            text("SELECT id FROM stores WHERE city_canonical = :c"), {"c": V.EILAT}))
    plan = list(texts)
    for k in ("popular", "rare"):
        if k in bc:
            plan.append(bc[k]["item_code"])
    for q in EXTRA:
        q = upc if q == "<upc-a>" else q
        if q and q not in plan:
            plan.append(q)

    with ReadOnly() as conn:  # warm the per-process v2 caches, like a running worker
        try:
            V.run(conn, "חלב", limit=1)
        except Exception as exc:  # noqa: BLE001
            log(f"v2 warm-up failed: {_err(exc)}: {exc}")

    rep: dict = {"session": "SU11A-36", "built_at": str(built[0]), "search_items_rows": built[1],
                 "pseudo_rows": built[2], "eilat_stores": len(eilat), "barcodes": bc, "upc_note": upc_note,
                 "queries": [], "top10": {}, "pseudo_left_top10": {}}
    eilat_before = eilat_after = 0
    for n, q in enumerate(plan, 1):
        log(f"[{n}/{len(plan)}] {q}")
        with ReadOnly() as conn:
            words = q.split()
            n_old = len(Q.find_barcodes_with_relevance(conn, words)[0]) if words else 0
        v2rec, v2 = run_v2(V, q, args.runs)
        oldrec, old = run_old(S, q, 1 if n_old > OLD_SINGLE_RUN_ABOVE else args.runs)
        old_top = [it.product.item_code for it in old.items[:10]] if old else []
        v2_top = [p["item_code"] for p in v2.products[:10]] if v2 else []
        rec = {"query": q, "old_barcodes": n_old, "v2": v2rec, "old": oldrec,
               "total_matches": {"old": old.total_matches if old else None, "v2": v2.total_matches if v2 else None},
               "comparable": {"old": old.comparable_count if old else None,
                              "v2": v2.comparable_count if v2 else None},
               "corrected_from": v2.corrected_from if v2 else None,
               "top10_overlap": len(set(old_top) & set(v2_top)) if old and v2 else None}
        if old and v2:
            ob = sum(1 for it in old.items[:10] if it.quotes and it.quotes[0].store_fk in eilat)
            ab = sum(1 for p in v2.products[:10] if p["quotes"] and p["quotes"][0].get("store_fk") in eilat)
            rec["eilat_cheapest_top10"] = {"old": ob, "v2": ab}
            eilat_before += ob
            eilat_after += ab
            gone = [c for c in old_top if c not in v2_top]
            if gone:
                with ReadOnly() as conn:
                    pseudo = {r[0] for r in conn.execute(text(
                        "SELECT item_code FROM search_items WHERE is_pseudo AND item_code IN :c"
                    ).bindparams(bindparam("c", expanding=True)), {"c": gone})}
                left = [f"{it.product.item_code} | {it.product.canonical_name} | {it.cheapest_price}"
                        for it in old.items[:10] if it.product.item_code in pseudo]
                if left:
                    rep["pseudo_left_top10"][q] = left
        if v2 and q in RELEVANCE:
            names = {p["item_code"]: p for p in v2.products}
            rep["top10"][q] = [
                {"rank": i, "item_code": c["item_code"],
                 "name": (names.get(c["item_code"]) or {}).get("canonical_name") or c["name_norm"],
                 "manufacturer": (names.get(c["item_code"]) or {}).get("manufacturer") or c["manufacturer_norm"],
                 "chains": c["chains_live"], "popularity": c["popularity"], "tier": c["tier"]}
                for i, c in enumerate(v2.ranked_page[:10], 1)]
        rep["queries"].append(rec)
        del old, v2
        gc.collect()
    rep["eilat_cheapest_top10_total"] = {"old": eilat_before, "v2": eilat_after}
    rep["elapsed_s"] = round(time.perf_counter() - started, 1)
    Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print_summary(rep, args.out)
    return 0


def print_summary(rep: dict, out: str) -> None:
    p = print
    p("\n=== SU11A-36 search v2 vs old /search (read-only) ===")
    p(f"search_items: {rep['search_items_rows']} rows ({rep['pseudo_rows']} pseudo), built {rep['built_at']}; "
      f"Eilat stores {rep['eilat_stores']}")
    p(f"UPC-A: {rep['upc_note']}")
    p("\nquery | old codes | v2 ms min/med | old ms min/med (runs) | total old/v2 | comparable old/v2 | "
      "top10 overlap | corrected_from | errors")

    def ms(r):
        m = r["ms"]
        return f"{m['min']:.0f}/{m['median']:.0f}" + (f" ({m['runs']})" if m.get("runs") else "") if m else "-"
    for r in rep["queries"]:
        errs = "; ".join(f"{k}: {r[k]['error']}" for k in ("v2", "old") if r[k]["error"])
        p(f"{r['query']} | {r['old_barcodes']} | {ms(r['v2'])} | {ms(r['old'])} | "
          f"{r['total_matches']['old']}/{r['total_matches']['v2']} | "
          f"{r['comparable']['old']}/{r['comparable']['v2']} | {r['top10_overlap']} | "
          f"{r['corrected_from'] or ''} | {errs}")
    p("\n--- v2 top 10: name | manufacturer | chains | popularity | tier ---")
    for q, rows in rep["top10"].items():
        p(f"\n[{q}]")
        for x in rows or []:
            p(f"  {x['rank']:>2}. {x['name']} | {x['manufacturer']} | {x['chains']} | {x['popularity']} | {x['tier']}")
        if not rows:
            p("  (no results)")
    p("\n--- coupon pseudo-items that left the old top 10 (code | name | old cheapest) ---")
    for q, rows in rep["pseudo_left_top10"].items():
        p(f"[{q}]")
        for x in rows:
            p(f"  {x}")
    if not rep["pseudo_left_top10"]:
        p("  (none)")
    e = rep["eilat_cheapest_top10_total"]
    p(f"\ntop-10 results whose cheapest quote is an Eilat store, summed over all queries: "
      f"old {e['old']}, v2 {e['v2']}")
    p(f"\nelapsed {rep['elapsed_s']} s; full JSON: {out}")


if __name__ == "__main__":
    sys.exit(main())
