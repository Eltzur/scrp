"""One-off migration: normalize Carrefour store_id padding in the DB.

The PublishPrice scraper previously indexed Format-A filenames incorrectly,
producing store_id values like '0002' instead of the canonical '002'.  This
script finds those rows and either:
  - merges them into the already-existing canonical row (re-pointing prices),
  - or renames them in-place when no canonical row exists yet.

Usage:
    python3 -m scripts.fix_carrefour_padding [--dry-run]
"""
from __future__ import annotations

import sys

from sqlalchemy import text

from db.db import connect

CHAIN_ID = "7290055700007"


def run(dry_run: bool = False) -> None:
    conn = connect()
    try:
        _run(conn, dry_run)
    finally:
        conn.close()


def _run(conn, dry_run: bool) -> None:
    tag = "[DRY RUN] " if dry_run else ""

    # Find all stores whose store_id is longer than 3 chars (over-padded).
    rows = conn.execute(text("""
        SELECT id, sub_chain_id, store_id
        FROM stores
        WHERE chain_id = :chain_id
          AND length(store_id) > 3
        ORDER BY store_id
    """), {"chain_id": CHAIN_ID}).mappings().all()

    if not rows:
        print("No over-padded Carrefour store rows found — nothing to do.")
        return

    merged = []
    renamed = []

    for row in rows:
        src_fk   = row["id"]
        src_sid  = row["store_id"]
        sub      = row["sub_chain_id"]
        canon    = str(int(src_sid)).zfill(3)

        # Check whether the canonical row already exists.
        target = conn.execute(text("""
            SELECT id FROM stores
            WHERE chain_id = :chain_id
              AND sub_chain_id = :sub_chain_id
              AND store_id = :store_id
        """), {"chain_id": CHAIN_ID, "sub_chain_id": sub, "store_id": canon}).fetchone()

        if target:
            target_fk = target[0]
            price_count = conn.execute(text(
                "SELECT COUNT(*) FROM prices WHERE store_fk = :fk"
            ), {"fk": src_fk}).scalar()

            print(f"{tag}MERGE  {src_sid} (id={src_fk}, {price_count} prices)"
                  f" → {canon} (id={target_fk})")

            if not dry_run:
                # Re-point prices to the canonical store row.
                # ON CONFLICT: if (target_fk, item_code) already exists, keep target's row.
                conn.execute(text("""
                    INSERT INTO prices (store_fk, item_code, price_update_date,
                                        item_price, unit_of_measure_price,
                                        allow_discount, item_status)
                    SELECT :target_fk, item_code, price_update_date,
                           item_price, unit_of_measure_price,
                           allow_discount, item_status
                    FROM prices
                    WHERE store_fk = :src_fk
                    ON CONFLICT (store_fk, item_code) DO NOTHING
                """), {"target_fk": target_fk, "src_fk": src_fk})

                conn.execute(text(
                    "DELETE FROM prices WHERE store_fk = :fk"
                ), {"fk": src_fk})

                conn.execute(text(
                    "DELETE FROM stores WHERE id = :fk"
                ), {"fk": src_fk})

            merged.append((src_sid, canon))

        else:
            print(f"{tag}RENAME {src_sid} (id={src_fk}) → {canon}")

            if not dry_run:
                conn.execute(text("""
                    UPDATE stores SET store_id = :canon
                    WHERE id = :fk
                """), {"canon": canon, "fk": src_fk})

            renamed.append((src_sid, canon))

    if not dry_run:
        conn.commit()

    print()
    print(f"Summary: {len(merged)} merged, {len(renamed)} renamed"
          + (" (dry run — no changes written)" if dry_run else "."))


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    run(dry_run=dry_run)


if __name__ == "__main__":
    main()
