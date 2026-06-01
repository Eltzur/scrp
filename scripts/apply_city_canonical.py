"""Apply city_canonical values from review CSV to the stores table (9d-8).

Reads data/city_canonical_review.csv, skips rows with no proposed_canonical,
and UPDATEs stores.city_canonical in a single transaction.
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from db.db import get_engine

CSV_PATH = ROOT / "data" / "city_canonical_review.csv"

# Belt-and-suspenders: these stores report גבעת אולגה but belong to חדרה.
_HARDCODED = {
    194: "חדרה",
    282: "חדרה",
}


def main() -> None:
    if not CSV_PATH.exists():
        print(f"ERROR: {CSV_PATH} not found.")
        sys.exit(1)

    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    updates = []
    skipped = 0

    for row in rows:
        try:
            store_pk = int(row["store_id"])
        except (ValueError, KeyError):
            skipped += 1
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

    print(f"Updated: {len(updates)}")
    print(f"Skipped: {skipped}")


if __name__ == "__main__":
    main()
