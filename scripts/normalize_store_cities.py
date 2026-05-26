"""
One-time cleanup: strip neighborhood/qualifier suffixes from stores.city.

Scope: ONLY accepts changes where the resolved canonical city is a leading
token of the current city string — i.e. we are stripping a suffix off the
SAME city, never replacing one city with a different city.

  VALID:   "חולון קוגל"  → "חולון"   (qualifier suffix stripped)
  VALID:   "אשקלון מרכז" → "אשקלון"  (qualifier suffix stripped)
  INVALID: "חולון"       → "אילת"    (different city — rejected)
  INVALID: "בני ברק"     → "רמת גן"  (different city — rejected)
  INVALID: None          → anything  (no existing city to strip from — rejected)

Spelling normalizations (e.g. קריית→קרית) are a DIFFERENT operation and
belong in normalize_city's CITY_VARIANTS table — NOT handled here.

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


def _is_suffix_strip(current_city: str | None, new_city: str | None) -> bool:
    """True only when new_city is a complete leading token of current_city.

    Requires current_city to be non-empty (None → False).
    Requires current_city to be strictly longer than new_city (equal → False,
    handled upstream by the no-change check).
    The separator after new_city must be a space or hyphen — prevents partial
    word matches (e.g. "חולון" is NOT a leading token of "חולוניה").
    """
    if not current_city or not new_city:
        return False
    return (
        current_city.startswith(new_city + " ") or
        current_city.startswith(new_city + "-")
    )


def main() -> None:
    apply_mode = "--apply" in sys.argv

    conn = connect()

    rows = conn.execute(text("""
        SELECT id, chain_id, store_id, store_name, address, city
        FROM stores
        ORDER BY chain_id, store_id
    """)).mappings().all()

    changes:                  list[dict] = []
    skipped_low_conf:         int        = 0
    skipped_no_change:        int        = 0
    skipped_not_suffix_strip: int        = 0

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

        # GUARD: only accept pure suffix-strips — never swap one city for another.
        if not _is_suffix_strip(current_city, new_city):
            skipped_not_suffix_strip += 1
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
    print(f"  {len(changes)} change(s) accepted (suffix-strip, conf >= {CONF_THRESHOLD:.2f})")
    print(f"  Skipped — already canonical or resolver returned None: {skipped_no_change}")
    print(f"  Skipped — below confidence threshold ({CONF_THRESHOLD:.2f}):        {skipped_low_conf}")
    print(f"  Skipped — not a suffix-strip (city-swap rejected):        {skipped_not_suffix_strip}")
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
