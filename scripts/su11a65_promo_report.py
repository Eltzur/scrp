"""SU11A-65 read-only report for the runbook (docs/admin/su11a65_runbook.md):

  1. indexes: the su11a65 trigram indexes, valid or not, and their size;
  2. timings: /promos/list search in Tel Aviv and in all cities (3x each), and
     whether the plan reads idx_promos_description_trgm (EXPLAIN, no ANALYZE);
  3. why each of the top 15 rows for a term matched (description / name /
     barcode, category boost): the SU11A-62 חומוס finding (lentils, peas);
  4. gift coupons on the promo lists (db/query.py _GIFT_COUPON_SQL): rows,
     promotions, cards, per chain, 10 examples, plus free units WITHOUT a
     coupon (unchanged, for context). Reads every active promo once (~1 min).

Read-only: the session is READ ONLY with a statement_timeout. No user data is
read or printed. Run it at a quiet time.

Server:
    ulimit -v 2000000
    set -a; source .env; set +a
    venv/bin/python3 -m scripts.su11a65_promo_report              # all parts
    venv/bin/python3 -m scripts.su11a65_promo_report --no-gifts   # skip part 4 (the full read)
"""
from __future__ import annotations

import argparse
import re
import time

from sqlalchemy import event, text

from api import categories as cats
from db.db import connect
from db.promo_curation import get_curation
from db.query import count_gift_coupons, fetch_flat_promos

TLV = "תל אביב-יפו"
TIMEOUT = "120s"
INDEXES = ("idx_promos_description_trgm", "idx_items_name_trgm")


def indexes(conn) -> None:
    rows = conn.execute(text("""
        SELECT c.relname, i.indisvalid, pg_size_pretty(pg_relation_size(c.oid)) AS size
        FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
        WHERE c.relname = ANY(:n) ORDER BY c.relname"""), {"n": list(INDEXES)}).all()
    print("\n== indexes")
    found = {r.relname: r for r in rows}
    for n in INDEXES:
        r = found.get(n)
        print(f"  {n}: " + ("MISSING" if r is None else f"valid={r.indisvalid} size={r.size}"))


def timings(conn, terms: list[str]) -> None:
    cur = get_curation(conn)
    print("\n== timings (ms, 3x; 30 rows a page)")
    for term in terms:
        s = cats.promo_search(conn, term)
        for label, city in (("list-city-q", TLV), ("list-all-q", None)):
            ms = []
            for _ in range(3):
                t0 = time.monotonic()
                fetch_flat_promos(conn, curation=cur, q=s, city=city, limit=30, offset=0)
                ms.append(round((time.monotonic() - t0) * 1000))
                conn.rollback()
            print(f"  {label} {term}: {ms}")
    # the plan of the last statement shape, without running it
    seen: list = []
    eng = conn.engine

    def cap(_c, _cur, statement, parameters, _ctx, _many):
        seen.append((statement, parameters))

    event.listen(eng, "before_cursor_execute", cap)
    try:
        fetch_flat_promos(conn, curation=cur, q=cats.promo_search(conn, terms[0]), city=TLV, limit=30, offset=0)
    finally:
        event.remove(eng, "before_cursor_execute", cap)
    stmt, params = seen[-1]
    raw = conn.connection.driver_connection.cursor()
    raw.execute("EXPLAIN " + stmt, params)
    plan = "\n".join(r[0] for r in raw.fetchall())
    conn.rollback()
    print(f"  plan reads idx_promos_description_trgm: {'yes' if 'idx_promos_description_trgm' in plan else 'NO'}")


def why(conn, term: str, city: str | None, n: int = 15) -> None:
    """How each of the top n rows matched the term."""
    s = cats.promo_search(conn, term)
    rows = fetch_flat_promos(conn, curation=get_curation(conn), q=s, city=city, limit=n, offset=0)
    boosted = set()
    if s and s.boost_ids and rows:
        boosted = {r[0] for r in conn.execute(text(
            "SELECT item_code FROM item_categories WHERE item_code = ANY(:c) AND category_id = ANY(:k)"
            " AND (confidence <> 'low' OR category_id = ANY(:low))"),
            {"c": [r["item_code"] for r in rows], "k": list(s.boost_ids), "low": list(s.boost_low_ids)})}
    conn.rollback()
    q = term.casefold()
    print(f"\n== why: {term} / {city or 'כל הערים'}  (boost categories: {', '.join(s.boost_ids) if s else '-'})")
    for k, r in enumerate(rows, 1):
        name, desc = r.get("product_name") or "", r.get("promo_description") or ""
        how = [w for w, ok in (("description", q in desc.casefold()), ("name", q in name.casefold()),
                               ("barcode", r["item_code"] == term)) if ok]
        flag = "" if how else "   <-- NO TEXT MATCH"
        print(f"  {k:>2}. {name} | {'+'.join(how) or '-'}{' +boost' if r['item_code'] in boosted else ''}"
              f" | desc: {re.sub(r'\s+', ' ', desc)[:120]}{flag}")


def gifts(conn) -> None:
    t0 = time.monotonic()
    out = count_gift_coupons(conn, examples=10)
    conn.rollback()
    print(f"\n== gift coupons ({time.monotonic() - t0:.1f} s)")
    for k, v in out["counts"].items():
        print(f"  {k}: {v}")
    print(" by chain:")
    for r in out["by_chain"]:
        print(f"  {r['chain_name'] or r['chain_id']}: {r['rows']} rows, {r['promotions']} promotions")
    print(" examples:")
    for r in out["examples"]:
        shelf = "-" if r.get("shelf_price") is None else f"{float(r['shelf_price']):.2f}"
        qty = "-" if r.get("min_qty") is None else f"{float(r['min_qty']):g}"
        print(f"  {r.get('chain_name') or r['chain_id']} | {r['item_code']} | {r.get('product_name') or ''}"
              f" | shelf {shelf} | min_qty {qty} | {(r.get('promo_description') or '')[:60]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--terms", nargs="*", default=["שמנת", "חומוס"])
    ap.add_argument("--no-gifts", action="store_true", help="skip part 4 (the full read)")
    a = ap.parse_args()
    with connect() as conn:
        conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
        conn.execute(text(f"SET statement_timeout = '{TIMEOUT}'"))
        conn.commit()
        indexes(conn)
        conn.rollback()
        timings(conn, a.terms)
        why(conn, "חומוס", TLV)
        if not a.no_gifts:
            gifts(conn)


if __name__ == "__main__":
    main()
