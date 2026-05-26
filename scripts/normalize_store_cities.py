"""
One-time cleanup: normalize stores.city to canonical Hebrew city names.

Dry-run by default — prints proposed changes, no DB writes.
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
from scraper.city_matcher import resolve_city
from scraper.city_names import normalize_city

CONF_THRESHOLD = 0.80

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


def main() -> None:
    apply_mode = "--apply" in sys.argv

    conn = connect()

    rows = conn.execute(text("""
        SELECT id, chain_id, store_id, store_name, address, city
        FROM stores
        ORDER BY chain_id, store_id
    """)).mappings().all()

    changes:             list[dict] = []
    skipped_low_conf:    int        = 0
    skipped_no_change:   int        = 0

    for r in rows:
        store_name   = (r["store_name"] or "").strip()
        address      = (r["address"]    or "").strip()
        current_city = r["city"]

        new_city, conf = resolve_city(store_name, address, r["chain_id"])

        if conf < CONF_THRESHOLD:
            skipped_low_conf += 1
            continue

        if new_city == current_city:
            skipped_no_change += 1
            continue

        changes.append({
            "id":            r["id"],
            "chain_id":      r["chain_id"],
            "store_id":      r["store_id"],
            "current_city":  current_city,
            "new_city":      new_city,
            "new_city_norm": normalize_city(new_city),
            "conf":          conf,
        })

    # --- Report ---
    mode_label = "APPLY" if apply_mode else "DRY-RUN"
    print(SEP)
    print(f"normalize_store_cities.py — {mode_label}")
    print(f"  {len(rows)} stores scanned")
    print(f"  {len(changes)} change(s) found")
    print(f"  Skipped — already canonical or no resolve result: {skipped_no_change}")
    print(f"  Skipped — below confidence threshold ({CONF_THRESHOLD:.2f}):  {skipped_low_conf}")
    print(SEP)

    by_chain: dict[str, list] = {}
    for c in changes:
        by_chain.setdefault(c["chain_id"], []).append(c)

    for chain_id in sorted(by_chain):
        chain_name = CHAIN_NAMES.get(chain_id, chain_id)
        chain_changes = by_chain[chain_id]
        print(f"\n  [{chain_name}]  ({len(chain_changes)} change(s))")
        for c in sorted(chain_changes, key=lambda x: x["store_id"]):
            print(
                f"    store {c['store_id']:<8}  "
                f"current={repr(c['current_city']):<36}  "
                f"canonical={repr(c['new_city']):<26}  "
                f"conf={c['conf']:.2f}"
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
        print(f"Applied {len(changes)} UPDATE(s) — committed.")
    else:
        print(f"Dry-run complete — {len(changes)} change(s) pending.")
        print("Re-run with --apply to write to the database.")

    conn.close()


if __name__ == "__main__":
    main()
