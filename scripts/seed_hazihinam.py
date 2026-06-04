"""One-off seed: copy HaziHinam online-store (103) PriceFull to all physical stores.

Store 103 is the online delivery store and publishes a full PriceFull that
represents the whole chain's catalog. Physical stores (201-217) don't publish
their own PriceFull files. This script seeds all physical stores from store 103's
PriceFull so that the daily Price (delta) cron can then apply incremental updates.

Usage (on server):
  cd ~/scrp && source venv/bin/activate && source .env
  python3 -m scripts.seed_hazihinam
"""
import logging
import sys
from datetime import datetime, timezone

from sqlalchemy import text

from scraper.hazihinam import HaziHinamScraper
from scraper.base import RAW_DIR
from db.db import (
    connect,
    bulk_upsert_items,
    bulk_upsert_item_chain_names,
    bulk_insert_prices,
    _pad_store_id,
)
from parser.price_parser import parse_file as parse_price_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

CHAIN_ID = "7290700100008"
SOURCE_STORE = "103"
PHYSICAL_STORES = ["201", "202", "203", "204", "205", "206", "207", "208", "209", "210", "217"]


def main() -> None:
    conn = connect()
    scraper = HaziHinamScraper()

    # -----------------------------------------------------------------------
    # Step 1: fetch PriceFull index for online store 103
    # -----------------------------------------------------------------------
    log.info(f"Fetching PriceFull index for source store {SOURCE_STORE}...")
    index = scraper.build_pricefull_index({SOURCE_STORE})
    entry = index.get(_pad_store_id(SOURCE_STORE))
    if not entry:
        log.error(f"No PriceFull found for store {SOURCE_STORE}. Aborting.")
        conn.close()
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Step 2: download and parse the file
    # -----------------------------------------------------------------------
    gz_path = RAW_DIR / (entry["filename"] + ".gz")
    log.info(f"Downloading {entry['filename']}...")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    scraper._download_gz(entry["url"], gz_path)
    data = scraper._decompress(gz_path)
    gz_path.unlink(missing_ok=True)

    tmp_xml = RAW_DIR / (entry["filename"] + ".xml")
    tmp_xml.write_bytes(data)
    header, items = parse_price_file(tmp_xml)
    items = list(items)
    tmp_xml.unlink(missing_ok=True)

    chain_id_hdr = header.get("chain_id") or CHAIN_ID
    log.info(f"Parsed {len(items)} raw items from store {SOURCE_STORE}.")

    # Filter and deduplicate — same logic as base._process_store.
    valid = [
        item for item in items
        if item.get("item_code") and item.get("item_price") is not None
    ]
    valid = list({item["item_code"]: item for item in valid}.values())
    log.info(f"{len(valid)} valid items after filter+dedup.")

    # Upsert item catalog once (chain-level, not per-store).
    bulk_upsert_items(conn, valid)
    bulk_upsert_item_chain_names(conn, chain_id_hdr, valid)
    conn.commit()
    log.info("Item catalog upserted.")

    # -----------------------------------------------------------------------
    # Step 3: copy prices to each physical store
    # -----------------------------------------------------------------------
    run_at = datetime.now(timezone.utc).isoformat()
    total_inserted = 0

    for sid in PHYSICAL_STORES:
        padded = _pad_store_id(sid)
        row = conn.execute(
            text("SELECT id FROM stores WHERE chain_id=:cid AND store_id=:sid"),
            {"cid": CHAIN_ID, "sid": padded},
        ).fetchone()
        if not row:
            log.warning(f"  Store {sid}: not found in stores table — skipping.")
            continue
        store_fk = row[0]

        conn.execute(
            text("DELETE FROM prices WHERE store_fk=:fk"),
            {"fk": store_fk},
        )
        count = bulk_insert_prices(conn, store_fk, valid, replace=True)
        conn.commit()
        total_inserted += count
        log.info(f"  Store {sid} (fk={store_fk}): {count} prices inserted.")

    # -----------------------------------------------------------------------
    # Step 4: record the seed run in fetch_runs
    # -----------------------------------------------------------------------
    conn.execute(text("""
        INSERT INTO fetch_runs
            (chain_id, run_at, files_attempted, files_loaded, items_inserted, status)
        VALUES (:chain_id, :run_at, 1, 1, :items_inserted, 'seeded_from_103')
    """), {
        "chain_id": CHAIN_ID,
        "run_at": run_at,
        "items_inserted": total_inserted,
    })
    conn.commit()

    log.info(
        f"Seed complete. {len(PHYSICAL_STORES)} stores seeded, "
        f"{total_inserted} total price rows inserted."
    )
    conn.close()


if __name__ == "__main__":
    main()
