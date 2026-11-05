"""SU11A-62 read-only report for the runbook (docs/admin/su11a62_runbook.md):

  1. before / after top-10 of the promos page search (/promos/list) for a few
     terms, in Tel Aviv and in all cities. "before" is the pre-SU11A-62 list
     (product name / barcode match, sorted by discount, no cleanup: legacy=True
     in db/query.py); "after" is the new list (relevance, category boost,
     cleanup), exactly as the endpoint builds it.
  2. how many promo-list rows each cleanup rule removes (no discount, coupon /
     threshold), over every active promo at live branches, with 10 examples each.

Read-only: the session is READ ONLY with a statement_timeout. No user data is
read or printed. Part 2 reads every active promo row (the scan the endpoints
no longer do): run it at a quiet time.

Server:
    ulimit -v 2000000
    set -a; source .env; set +a
    venv/bin/python3 -m scripts.su11a62_promo_report            # both parts
    venv/bin/python3 -m scripts.su11a62_promo_report --no-cleanup
"""
from __future__ import annotations

import argparse
import time

from sqlalchemy import text

from api import categories as cats
from db.db import connect
from db.promo_curation import get_curation
from db.query import count_promo_list_cleanup, fetch_flat_promos

TERMS = ["שמנת", "חלב", "במבה", "קפה", "חומוס"]
TLV = "תל אביב-יפו"
TIMEOUT = "120s"


def _line(k: int, r: dict) -> str:
    pct = "-" if r.get("discount_pct") is None else f"{float(r['discount_pct']):.0f}%"
    return (f"  {k:>2}. {r.get('chain_name') or r['chain_id']} | {r.get('product_name') or r['item_code']}"
            f" | {pct} | {(r.get('promo_description') or '')[:40]}")


def top10(conn, term: str, city: str | None) -> None:
    cur = get_curation(conn)
    t0 = time.monotonic()
    before = fetch_flat_promos(conn, curation=cur, q=term, city=city, limit=10, offset=0, legacy=True)
    t1 = time.monotonic()
    after = fetch_flat_promos(conn, curation=cur, q=cats.promo_search(conn, term), city=city, limit=10, offset=0)
    t2 = time.monotonic()
    print(f"\n== {term} / {city or 'כל הערים'}   (before {t1 - t0:.1f} s, after {t2 - t1:.1f} s)")
    print(" before:")
    for k, r in enumerate(before, 1):
        print(_line(k, r))
    print(" after:")
    for k, r in enumerate(after, 1):
        print(_line(k, r))


def cleanup(conn) -> None:
    t0 = time.monotonic()
    out = count_promo_list_cleanup(conn, examples=10)
    print(f"\n== cleanup ({time.monotonic() - t0:.1f} s)")
    for k, v in out["counts"].items():
        print(f"  {k}: {v}")
    for rule, rows in out["examples"].items():
        print(f" examples: {rule}")
        for r in rows:
            shelf = "-" if r.get("shelf_price") is None else f"{float(r['shelf_price']):.2f}"
            unit = "-" if r.get("unit_price") is None else f"{float(r['unit_price']):.2f}"
            print(f"  {r.get('chain_name') or r['chain_id']} | {r['item_code']} | {r.get('product_name') or ''}"
                  f" | shelf {shelf} unit {unit} | {r.get('promo_kind')} | {(r.get('promo_description') or '')[:50]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--terms", nargs="*", default=TERMS)
    ap.add_argument("--no-cleanup", action="store_true", help="skip part 2 (the full scan)")
    a = ap.parse_args()
    with connect() as conn:
        conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
        conn.execute(text(f"SET statement_timeout = '{TIMEOUT}'"))
        conn.commit()
        for term in a.terms:
            for city in (TLV, None):
                top10(conn, term, city)
                conn.rollback()
        if not a.no_cleanup:
            cleanup(conn)
            conn.rollback()


if __name__ == "__main__":
    main()
