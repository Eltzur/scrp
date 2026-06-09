"""Seed prices for a single store — Shufersal only (currently).

Usage:
    python3 -m scripts.seed_one_store <chain_id> <store_id>

Example:
    python3 -m scripts.seed_one_store 7290027600007 844
"""
from __future__ import annotations

import logging
import sys

from sqlalchemy import text

from db.db import (
    connect,
    upsert_chain,
    upsert_store,
    bulk_upsert_items,
    bulk_upsert_item_chain_names,
    bulk_insert_prices,
    _pad_store_id,
)
from parser.price_parser import parse_file as parse_price_file
from scraper.base import RAW_DIR
from scraper.shufersal import ShufersalScraper

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

SHUFERSAL_CHAIN_ID = "7290027600007"


def seed_store(chain_id: str, store_id: str) -> int:
    if chain_id != SHUFERSAL_CHAIN_ID:
        raise NotImplementedError(
            f"seed_one_store only supports Shufersal ({SHUFERSAL_CHAIN_ID}), got {chain_id}"
        )

    padded = _pad_store_id(store_id)
    scraper = ShufersalScraper()

    log.info(f"Building PriceFull index for store {padded}...")
    index = scraper.build_pricefull_index({padded})
    entry = index.get(padded)
    if not entry:
        raise RuntimeError(f"No PriceFull file found for store {padded}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    gz_path = RAW_DIR / (entry["filename"] + ".gz")
    tmp_xml = RAW_DIR / (entry["filename"] + ".xml")

    log.info(f"Downloading {entry['filename']}...")
    scraper._download_gz(entry["url"], gz_path)
    data = scraper._decompress(gz_path)
    gz_path.unlink(missing_ok=True)

    tmp_xml.write_bytes(data)
    header, items = parse_price_file(tmp_xml)
    items = list(items)
    tmp_xml.unlink(missing_ok=True)

    chain_id_xml = header.get("chain_id") or chain_id
    sub_chain_id = header.get("sub_chain_id") or entry.get("sub_chain_id", "001")
    store_id_xml = header.get("store_id") or padded

    valid = [
        item for item in items
        if item.get("item_code") and item.get("item_price") is not None
    ]
    valid = list({item["item_code"]: item for item in valid}.values())

    conn = connect()
    try:
        upsert_chain(conn, chain_id_xml)
        store_fk = upsert_store(conn, chain_id_xml, sub_chain_id, store_id_xml)

        conn.execute(text("DELETE FROM prices WHERE store_fk=:fk"), {"fk": store_fk})

        bulk_upsert_items(conn, valid)
        bulk_upsert_item_chain_names(conn, chain_id_xml, valid)
        count = bulk_insert_prices(conn, store_fk, valid, replace=True)
        conn.commit()
    finally:
        conn.close()

    return count


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python3 -m scripts.seed_one_store <chain_id> <store_id>")
        sys.exit(1)

    chain_id, store_id = sys.argv[1], sys.argv[2]
    count = seed_store(chain_id, store_id)
    print(f"Done — inserted {count} prices for store {store_id}")


if __name__ == "__main__":
    main()
