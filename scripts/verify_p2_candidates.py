"""
Verify P2 candidate stores can publish PriceFull files.

ANALYSIS ONLY — no DB writes, no yaml writes. Reads DB for store metadata (SELECT only).

Usage (from repo root, with DATABASE_URL set):
    python scripts/verify_p2_candidates.py

Shufersal timing note: PriceFull files appear in the listing by ~08:00 IDT and
persist all day. Evening results are reliable. Only runs before 08:00 IDT risk
false NO_FILE for Shufersal stores.
"""
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.db import connect, _pad_store_id
from scraper.city_matcher import resolve_city
from scraper.registry import SCRAPERS

# ---------------------------------------------------------------------------
# Candidates — hard-coded from P2 discovery output (60 stores)
# ---------------------------------------------------------------------------

CANDIDATES: dict[str, list[str]] = {
    "7290055700007": ["002", "065", "033", "3680", "183", "067", "191", "4120", "4150", "062", "2540", "2750", "3600", "2190", "2740"],
    "7290103152017": ["022", "016", "011", "010"],
    "7290058140886": ["035", "056", "049", "071", "016", "045", "050", "010", "034", "725", "726", "041"],
    "7290027600007": ["014", "181", "209", "606", "219", "295", "611", "199", "018", "123", "119", "105", "290"],
    "7290696200003": ["052", "095", "014", "076", "039", "060", "051", "083"],
    "7290803800003": ["034", "041", "029", "073", "017", "018", "031"],
    "7290785400000": ["020"],
}

CHAIN_NAMES: dict[str, str] = {
    "7290027600007": "Shufersal",
    "7290058140886": "Rami Levy",
    "7290103152017": "Osher Ad",
    "7290696200003": "Victory",
    "7290803800003": "Yochananof",
    "7290785400000": "Keshet",
    "7290055700007": "Carrefour",
}

SHUFERSAL_ID = "7290027600007"
SEP = "=" * 72


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_store_meta(conn, chain_id: str) -> dict[str, dict]:
    """Return {padded_store_id: {store_name, address, city_db}} for a chain."""
    rows = conn.execute(text("""
        SELECT store_id, store_name, address, city
        FROM stores
        WHERE chain_id = :chain_id
    """), {"chain_id": chain_id}).mappings().all()
    return {
        _pad_store_id(r["store_id"]): {
            "store_name": (r["store_name"] or "").strip(),
            "address":    (r["address"]    or "").strip(),
            "city_db":    r["city"],
        }
        for r in rows
    }


def verify_chain(chain_id: str, candidate_ids: list[str], conn) -> list[dict]:
    """Instantiate the scraper, call build_pricefull_index, return per-store results."""
    padded     = [_pad_store_id(sid) for sid in candidate_ids]
    store_meta = load_store_meta(conn, chain_id)

    scraper_cls = SCRAPERS[chain_id]
    scraper     = scraper_cls()
    index       = scraper.build_pricefull_index(set(padded))

    results = []
    for sid in padded:
        meta       = store_meta.get(sid, {})
        store_name = meta.get("store_name", "")
        address    = meta.get("address", "")
        city_db    = meta.get("city_db")

        city_resolved, conf = resolve_city(store_name, address, chain_id)

        results.append({
            "chain_id":      chain_id,
            "store_id":      sid,
            "store_name":    store_name,
            "city_resolved": city_resolved,
            "city_db":       city_db,
            "confidence":    conf,
            "status":        "PASS" if sid in index else "NO_FILE",
        })

    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_chain_block(chain_name: str, chain_id: str, results: list[dict]) -> None:
    n_pass    = sum(1 for r in results if r["status"] == "PASS")
    n_no_file = sum(1 for r in results if r["status"] == "NO_FILE")

    print(SEP)
    print(f"{chain_name}  —  {n_pass} PASS / {n_no_file} NO_FILE")

    if chain_id == SHUFERSAL_ID:
        print("  [Shufersal] Files appear by ~08:00 IDT and persist all day.")
        print("  Evening results are reliable. Only pre-08:00 runs risk false NO_FILE.")

    print()

    # Group by resolved city (None → "(unresolved)")
    by_city: dict[str, list] = {}
    for r in results:
        key = r["city_resolved"] or "(unresolved)"
        by_city.setdefault(key, []).append(r)

    for city in sorted(by_city):
        print(f"  [{city}]")
        for r in sorted(by_city[city], key=lambda x: x["store_id"]):
            tag        = "PASS   " if r["status"] == "PASS" else "NO_FILE"
            name_trunc = r["store_name"][:38]
            conf_str   = f"conf={r['confidence']:.2f}"
            db_city    = r["city_db"] or "(null)"
            print(
                f"    {tag}  {r['store_id']:<8}  {name_trunc:<40}  "
                f"{conf_str}  db_city={db_city}"
            )
    print()


def print_summary(all_results: list[dict]) -> None:
    print(SEP)
    print("SUMMARY")
    print(SEP)
    print(f"  {'Chain':<16}  {'Candidates':>10}  {'PASS':>6}  {'NO_FILE':>8}")
    print(f"  {'-'*16}  {'-'*10}  {'-'*6}  {'-'*8}")

    total_cand = total_pass = total_no_file = 0
    for chain_id in CANDIDATES:
        chain_name = CHAIN_NAMES.get(chain_id, chain_id)
        chain_res  = [r for r in all_results if r["chain_id"] == chain_id]
        n_cand     = len(CANDIDATES[chain_id])
        n_pass     = sum(1 for r in chain_res if r["status"] == "PASS")
        n_no_file  = sum(1 for r in chain_res if r["status"] == "NO_FILE")
        total_cand    += n_cand
        total_pass    += n_pass
        total_no_file += n_no_file
        print(f"  {chain_name:<16}  {n_cand:>10}  {n_pass:>6}  {n_no_file:>8}")

    print(f"  {'':->16}  {'':->10}  {'':->6}  {'':->8}")
    print(f"  {'TOTAL':<16}  {total_cand:>10}  {total_pass:>6}  {total_no_file:>8}")
    print(SEP)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    conn     = connect()
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    total_stores = sum(len(v) for v in CANDIDATES.values())
    print(SEP)
    print(f"P2 CANDIDATE VERIFICATION  —  {run_time}")
    print(f"  {total_stores} stores across {len(CANDIDATES)} chains")
    print(SEP)
    print()

    all_results: list[dict] = []

    for chain_id, candidate_ids in CANDIDATES.items():
        chain_name = CHAIN_NAMES.get(chain_id, chain_id)
        print(f"Checking {chain_name} ({len(candidate_ids)} stores)...", flush=True)
        results = verify_chain(chain_id, candidate_ids, conn)
        all_results.extend(results)
        print_chain_block(chain_name, chain_id, results)

    print_summary(all_results)
    conn.close()


if __name__ == "__main__":
    main()
