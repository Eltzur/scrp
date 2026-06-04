"""Single-chain runner — mirrors cron_main's DB/yaml setup for one chain.

Usage:
    python -m scripts.run_one <chain_id> [--yaml active|scheduled]

Options:
    --yaml active      Read from scraper/active_stores.yaml (default)
    --yaml scheduled   Read from scraper/scheduled_stores.yaml
"""
import argparse
import logging
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import connect, init_db
from scraper.registry import get_scraper, uses_delta

SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"
YAML_FILES = {
    "active":    SCRAPER_DIR / "active_stores.yaml",
    "scheduled": SCRAPER_DIR / "scheduled_stores.yaml",
}


def main():
    parser = argparse.ArgumentParser(description="Run scraper for a single chain.")
    parser.add_argument("chain_id", help="13-digit chain ID")
    parser.add_argument(
        "--yaml",
        choices=["active", "scheduled"],
        default="active",
        help="Which store list to use (default: active)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force PriceFull even for delta chains",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger(__name__)

    # Load yaml — same pattern as cron_main
    yaml_path = YAML_FILES[args.yaml]
    config = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    chains = config.get("chains", [])

    entry = next((c for c in chains if c["chain_id"] == args.chain_id), None)
    if entry is None:
        print(f"ERROR: chain_id {args.chain_id!r} not found in {yaml_path.name}.")
        print(f"Available chain_ids: {[c['chain_id'] for c in chains]}")
        sys.exit(1)

    store_ids = entry.get("store_ids")
    if not store_ids:
        print(f"ERROR: no store_ids listed for chain {args.chain_id} in {yaml_path.name}.")
        sys.exit(1)

    # Get scraper — same registry as cron_main
    scraper = get_scraper(args.chain_id)
    if scraper is None:
        print(f"ERROR: no scraper registered for chain_id {args.chain_id!r}.")
        print("Add it to scraper/registry.py first.")
        sys.exit(1)

    # Open DB — same as cron_main
    conn = connect()
    init_db(conn)

    log.info(f"[{args.chain_id}] yaml={yaml_path.name}, {len(store_ids)} stores")

    t_start = time.monotonic()

    log.info(f"[{args.chain_id}] Loading store metadata...")
    scraper.load_stores(conn)

    log.info(f"[{args.chain_id}] Scraping {len(store_ids)} stores: {store_ids}")
    delta = uses_delta(args.chain_id) and not args.full
    summary = scraper.load_prices_for_stores(store_ids, conn, replace=True, delta=delta)

    conn.close()
    elapsed = time.monotonic() - t_start

    print()
    print(f"--- Done ({elapsed:.0f}s) ---")
    print(f"Chain          : {args.chain_id}")
    print(f"Yaml           : {yaml_path.name}")
    print(f"Stores targeted: {len(store_ids)}")
    print(f"Files attempted: {summary['files_attempted']}")
    print(f"Files loaded   : {summary['files_loaded']}")
    print(f"Items inserted : {summary['items_inserted']}")


if __name__ == "__main__":
    main()
