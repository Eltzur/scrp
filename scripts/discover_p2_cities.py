"""
Discover candidate stores for Priority-2 city expansion.

ANALYSIS ONLY — no DB writes, no yaml writes. All DB access is SELECT only.

Usage (from repo root, with DATABASE_URL set):
    python scripts/discover_p2_cities.py
"""
import sys
from pathlib import Path

import yaml
from sqlalchemy import text

# Ensure repo root is on sys.path when run as a plain script.
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.db import connect, _pad_store_id
from scraper.registry import SCRAPERS
from scraper.city_matcher import resolve_city

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ACTIVE_STORES_YAML = Path(__file__).parent.parent / "scraper" / "active_stores.yaml"

# Exact Hebrew strings from city_matcher.CITIES — resolve_city returns these.
TARGET_CITIES: set[str] = {
    "פתח תקווה",
    "חולון",
    "בני ברק",
    "אשקלון",
    "רחובות",
    "בת ים",
    "בית שמש",
    "הרצליה",
    "מודיעין",
}

CONF_ACCEPT  = 0.80   # threshold for ACCEPTED bucket
CONF_LOW_MIN = 0.50   # lower bound for LOW-CONFIDENCE bucket

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_configured() -> dict[str, set[str]]:
    """Return {chain_id: set(padded store_ids)} from active_stores.yaml."""
    config = yaml.safe_load(ACTIVE_STORES_YAML.read_text(encoding="utf-8"))
    return {
        entry["chain_id"]: {_pad_store_id(sid) for sid in entry.get("store_ids", [])}
        for entry in config.get("chains", [])
    }


def print_freshness(conn) -> None:
    """Print most recent successful fetch_runs.run_at per chain."""
    rows = conn.execute(text("""
        SELECT c.name AS chain_name, fr.chain_id, MAX(fr.run_at) AS last_run
        FROM fetch_runs fr
        JOIN chains c ON c.chain_id = fr.chain_id
        WHERE fr.status IN ('ok', 'partial')
        GROUP BY fr.chain_id, c.name
        ORDER BY last_run DESC
    """)).mappings().all()

    overall = max((r["last_run"] for r in rows if r["last_run"]), default="(none)")

    print(SEP)
    print("CATALOG FRESHNESS")
    print("  The stores table is only as current as the last load_stores() run.")
    print(f"  Most recent run overall: {overall}")
    print("-" * 72)
    for r in rows:
        print(f"  {(r['chain_name'] or r['chain_id']):<20}  {r['last_run'] or '(never)'}")
    print(SEP)
    print()


def discover(conn, configured: dict[str, set[str]]) -> tuple[list, list, list]:
    """
    Scan all stores for all chains. Bucket into:
      accepted      — target city, conf >= CONF_ACCEPT,  not already configured
      low_conf      — target city, CONF_LOW_MIN <= conf < CONF_ACCEPT, not configured
      unresolvable  — store_name AND address both null/empty, not already configured
    stores.city is SELECTed for display only and never used as a filter.
    """
    accepted     = []
    low_conf     = []
    unresolvable = []

    for chain_id in SCRAPERS:
        chain_name = CHAIN_NAMES.get(chain_id, chain_id)
        already    = configured.get(chain_id, set())

        rows = conn.execute(text("""
            SELECT store_id, store_name, city, address
            FROM stores
            WHERE chain_id = :chain_id
            ORDER BY store_id
        """), {"chain_id": chain_id}).mappings().all()

        for r in rows:
            sid        = _pad_store_id(r["store_id"])
            store_name = (r["store_name"] or "").strip()
            address    = (r["address"]    or "").strip()
            city_db    = r["city"]  # for display reference only

            if sid in already:
                continue  # already active — skip all buckets

            if not store_name and not address:
                unresolvable.append({
                    "chain_id":   chain_id,
                    "chain_name": chain_name,
                    "store_id":   sid,
                    "city_db":    city_db,
                })
                continue

            city_resolved, conf = resolve_city(store_name, address, chain_id)

            if city_resolved not in TARGET_CITIES:
                continue  # not a target city — not relevant to P2

            rec = {
                "chain_id":      chain_id,
                "chain_name":    chain_name,
                "store_id":      sid,
                "store_name":    store_name,
                "city_resolved": city_resolved,
                "city_db":       city_db,
                "confidence":    conf,
            }

            if conf >= CONF_ACCEPT:
                accepted.append(rec)
            elif conf >= CONF_LOW_MIN:
                low_conf.append(rec)
            # below CONF_LOW_MIN: silently ignore

    return accepted, low_conf, unresolvable


def print_city_chain_table(records: list) -> None:
    """Print records grouped by resolved city then chain name."""
    if not records:
        print("  (none)")
        return

    by_city: dict[str, list] = {}
    for rec in records:
        by_city.setdefault(rec["city_resolved"], []).append(rec)

    for city in sorted(by_city):
        print(f"\n  [{city}]")
        by_chain: dict[str, list] = {}
        for rec in by_city[city]:
            by_chain.setdefault(rec["chain_name"], []).append(rec)
        for chain in sorted(by_chain):
            for rec in sorted(by_chain[chain], key=lambda x: x["store_id"]):
                name_trunc = rec["store_name"][:38]
                city_db    = rec["city_db"] or "(null)"
                print(
                    f"    {rec['chain_name']:<14} {rec['store_id']:<8} "
                    f"{name_trunc:<40}  conf={rec['confidence']:.2f}"
                    f"  db_city={city_db}"
                )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    configured = load_configured()
    conn       = connect()

    print_freshness(conn)

    accepted, low_conf, unresolvable = discover(conn, configured)

    # --- ACCEPTED ---
    print(SEP)
    print(f"ACCEPTED  (conf >= {CONF_ACCEPT:.2f}, target city, not already configured)")
    print(f"  {len(accepted)} candidate store(s)")
    print(SEP)
    print_city_chain_table(accepted)

    # --- LOW-CONFIDENCE ---
    print()
    print(SEP)
    print(f"LOW-CONFIDENCE  ({CONF_LOW_MIN:.2f} <= conf < {CONF_ACCEPT:.2f}, target city, not configured)")
    print(f"  {len(low_conf)} store(s) — manual review recommended")
    print("  Thin cities (Bnei Brak, Beit Shemesh) are where manual rescue matters most.")
    print(SEP)
    print_city_chain_table(low_conf)

    # --- UNRESOLVABLE ---
    print()
    print(SEP)
    print("UNRESOLVABLE  (store_name AND address both null/empty, not already configured)")
    print(f"  {len(unresolvable)} store(s)")
    print(SEP)
    if unresolvable:
        for rec in sorted(unresolvable, key=lambda x: (x["chain_name"], x["store_id"])):
            print(f"  {rec['chain_name']:<14} {rec['store_id']:<8}  db_city={rec['city_db'] or '(null)'}")
    else:
        print("  (none)")

    conn.close()


if __name__ == "__main__":
    main()
