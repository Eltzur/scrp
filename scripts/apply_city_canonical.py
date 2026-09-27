"""Apply city_canonical values from review CSV to the stores table (9d-8).

Reads data/city_canonical_review.csv, skips rows with no proposed_canonical,
and UPDATEs stores.city_canonical in a single transaction.

TWO MODES:

  (no flags)            the original full apply: EVERY CSV row is written,
                        including blanks-over-values and DELETE actions.
                        SU10S-16 found this would erase 80 curated cities.

  --targeted [--apply]  SU10S-17. Only FILLS a NULL, and only for stores that
                        are SERVING (hold prices) and LIVE (db/query.py
                        live_store_clause - loaded within 3 days of their
                        chain's latest load). Never changes or blanks an
                        existing city; DELETE actions are ignored. Prints the
                        diff and writes nothing unless --apply is given.

                        Dead or non-serving stores are left NULL on purpose: a
                        city makes a store eligible for the Sunday geocoder,
                        which would put it in /stores/coordinates (SU10S-14).

THE CSV's `store_id` COLUMN HOLDS stores.id (THE PRIMARY KEY), not the chain's
store_id (build_city_canonical.py writes "store_id": store_pk). Joining it on
the chain store_id produces plausible-looking garbage (SU10S-16 follow-up).
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from db.db import get_engine
from db.query import live_store_clause

CSV_PATH = ROOT / "data" / "city_canonical_review.csv"

# Belt-and-suspenders: these stores report גבעת אולגה but belong to חדרה.
_HARDCODED = {
    194: "חדרה",
    282: "חדרה",
}


def _read_csv() -> list[dict]:
    if not CSV_PATH.exists():
        print(f"ERROR: {CSV_PATH} not found.")
        sys.exit(1)
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def targeted(apply: bool) -> None:
    """Fill NULL city_canonical for serving + live stores only. See module doc."""
    proposals: dict[int, dict] = {}
    for row in _read_csv():
        if row.get("action", "").strip().upper() == "DELETE":
            continue
        try:
            store_pk = int(row["store_id"])  # stores.id - see module doc
        except (ValueError, KeyError):
            continue
        canonical = _HARDCODED.get(store_pk) or row.get("proposed_canonical", "").strip()
        if canonical:
            proposals[store_pk] = {**row, "canonical": canonical}

    with get_engine().begin() as conn:
        live_sql, live_params = live_store_clause(conn)
        eligible = conn.execute(text(f"""
            SELECT s.id, s.chain_id, s.store_id, s.store_name, s.city
            FROM stores s
            WHERE s.id = ANY(:ids)
              AND s.city_canonical IS NULL
              AND EXISTS (SELECT 1 FROM prices p WHERE p.store_fk = s.id)
              {live_sql}
            ORDER BY s.chain_id, s.id
        """), {"ids": list(proposals), **live_params}).mappings().all()

        print(f"CSV proposals with a value: {len(proposals)}")
        print(f"eligible (NULL now, serving, live): {len(eligible)}")
        for r in eligible:
            pr = proposals[r["id"]]
            print(f"  FILL id={r['id']} chain={r['chain_id']} store_id={r['store_id']} "
                  f"'{r['store_name']}' raw='{r['city']}' -> '{pr['canonical']}' "
                  f"[{pr.get('match_layer', '')} {pr.get('confidence', '')}]")

        if not apply:
            print("DRY RUN - nothing written. Re-run with --apply.")
            return

        n = 0
        for r in eligible:
            # The IS NULL re-check makes overwriting impossible even if the row
            # changed between the SELECT above and here.
            n += conn.execute(text(
                "UPDATE stores SET city_canonical = :c WHERE id = :pk AND city_canonical IS NULL"
            ), {"c": proposals[r["id"]]["canonical"], "pk": r["id"]}).rowcount
        print(f"Filled: {n}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--targeted", action="store_true",
                    help="fill NULLs for serving+live stores only (SU10S-17)")
    ap.add_argument("--apply", action="store_true", help="with --targeted: write (default is dry run)")
    args = ap.parse_args()
    if args.targeted:
        targeted(args.apply)
        return
    if args.apply:
        ap.error("--apply is only meaningful with --targeted")

    rows = _read_csv()

    updates = []
    deletes = []
    skipped = 0

    for row in rows:
        try:
            store_pk = int(row["store_id"])
        except (ValueError, KeyError):
            skipped += 1
            continue

        action = row.get("action", "").strip().upper()

        if action == "DELETE":
            deletes.append(store_pk)
            continue

        canonical = _HARDCODED.get(store_pk) or row.get("proposed_canonical", "").strip()
        if not canonical:
            skipped += 1
            continue

        updates.append({"pk": store_pk, "canonical": canonical})

    with get_engine().begin() as conn:
        for rec in updates:
            conn.execute(
                text("UPDATE stores SET city_canonical = :canonical WHERE id = :pk"),
                rec,
            )
        for pk in deletes:
            conn.execute(text("DELETE FROM prices WHERE store_fk = :pk"), {"pk": pk})
            conn.execute(text("DELETE FROM fetch_store_runs WHERE store_fk = :pk"), {"pk": pk})
            conn.execute(text("DELETE FROM stores WHERE id = :pk"), {"pk": pk})

    print(f"Updated: {len(updates)}")
    print(f"Deleted: {len(deletes)}")
    print(f"Skipped: {skipped}")


if __name__ == "__main__":
    main()
