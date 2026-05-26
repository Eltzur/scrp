"""
One-time cleanup: strip neighborhood/qualifier suffixes from stores.city.

Matches the city column directly against the canonical CITIES set from
city_matcher.py — no resolve_city, no store_name involved.

Logic per store:
  1. city is None/empty           -> skip (no change)
  2. city EXACTLY in CITIES       -> already canonical, skip
  3. city STARTS WITH a CITIES member + space or hyphen
                                  -> strip to longest such prefix (longest-match rule)
  4. none of the above            -> skip (leave column untouched)

Longest-match rule prevents "זכרון יעקב" -> "זכרון":
  "זכרון יעקב" hits step 2 (exact match) -> skipped before any prefix check.
  A hypothetical "זכרון יעקב מרכז" would match both "זכרון" and "זכרון יעקב";
  longest match wins -> "זכרון יעקב".

Dry-run by default -- prints proposed changes, no DB writes.
Pass --apply to commit the UPDATEs.

Usage (from repo root, with DATABASE_URL set):
    python scripts/normalize_store_cities.py           # dry-run
    python scripts/normalize_store_cities.py --apply   # write changes
"""
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.db import connect
from scraper.city_matcher import CITIES
from scraper.city_names import normalize_city

CHAIN_NAMES: dict[str, str] = {
    "7290027600007": "Shufersal",
    "7290058140886": "Rami Levy",
    "7290103152017": "Osher Ad",
    "7290696200003": "Victory",
    "7290803800003": "Yochananof",
    "7290785400000": "Keshet",
    "7290055700007": "Carrefour",
}

SEP = "=" * 72


def _find_canonical_prefix(city: str) -> str | None:
    """Return the longest CITIES member that is a leading prefix of city,
    separated by space or hyphen. Returns None if no such prefix exists."""
    matches = [
        c for c in CITIES
        if city.startswith(c + " ") or city.startswith(c + "-")
    ]
    return max(matches, key=len) if matches else None


def main() -> None:
    apply_mode = "--apply" in sys.argv

    conn = connect()

    rows = conn.execute(text("""
        SELECT id, chain_id, store_id, city
        FROM stores
        ORDER BY chain_id, store_id
    """)).mappings().all()

    changes:           list[dict] = []
    skipped_null:      int        = 0
    skipped_exact:     int        = 0
    skipped_no_prefix: int        = 0

    for r in rows:
        current_city = (r["city"] or "").strip() or None

        # Step 1: null/empty -> skip
        if not current_city:
            skipped_null += 1
            continue

        # Step 2: exact canonical match -> already good, skip
        if current_city in CITIES:
            skipped_exact += 1
            continue

        # Step 3: longest canonical prefix match -> strip suffix
        new_city = _find_canonical_prefix(current_city)
        if new_city is None:
            skipped_no_prefix += 1
            continue

        changes.append({
            "id":            r["id"],
            "chain_id":      r["chain_id"],
            "store_id":      r["store_id"],
            "current_city":  current_city,
            "new_city":      new_city,
            "new_city_norm": normalize_city(new_city),
        })

    # --- Report ---
    mode_label = "APPLY" if apply_mode else "DRY-RUN"
    print(SEP)
    print(f"normalize_store_cities.py -- {mode_label}")
    print(f"  {len(rows)} stores scanned")
    print(f"  {len(changes)} change(s) found (suffix stripped)")
    print(f"  Skipped -- null/empty city:               {skipped_null}")
    print(f"  Skipped -- already exact canonical match: {skipped_exact}")
    print(f"  Skipped -- no canonical prefix found:     {skipped_no_prefix}")
    print(SEP)

    by_chain: dict[str, list] = {}
    for c in changes:
        by_chain.setdefault(c["chain_id"], []).append(c)

    for chain_id in sorted(by_chain):
        chain_name    = CHAIN_NAMES.get(chain_id, chain_id)
        chain_changes = by_chain[chain_id]
        print(f"\n  [{chain_name}]  ({len(chain_changes)} change(s))")
        for c in sorted(chain_changes, key=lambda x: x["store_id"]):
            print(
                f"    store {c['store_id']:<8}  "
                f"current={repr(c['current_city']):<36}  "
                f"canonical={repr(c['new_city'])}"
            )

    print()
    print(SEP)

    if not changes:
        print("Nothing to do.")
        conn.close()
        return

    if apply_mode:
        for c in changes:
            conn.execute(text("""
                UPDATE stores
                SET city=:city, city_norm=:city_norm
                WHERE id=:id
            """), {"city": c["new_city"], "city_norm": c["new_city_norm"], "id": c["id"]})
        conn.commit()
        print(f"Applied {len(changes)} UPDATE(s) -- committed.")
    else:
        print(f"Dry-run complete -- {len(changes)} change(s) pending.")
        print("Re-run with --apply to write to the database.")

    conn.close()


if __name__ == "__main__":
    main()
