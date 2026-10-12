"""Read-only comparison of search v2 against the old /search (SU11A-36).

    venv/bin/python3 -m scripts.compare_search_v2 --out /tmp/search_v2_compare.json
    venv/bin/python3 -m scripts.compare_search_v2 --dry-run

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
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(ROOT))
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
