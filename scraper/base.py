"""Shared base class for chain scrapers."""
import abc
import gzip
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from sqlalchemy import text

from db.db import (
    connect, init_db, upsert_chain, upsert_store,
    upsert_item, upsert_item_chain_name, upsert_price,
    bulk_upsert_items, bulk_upsert_item_chain_names, bulk_insert_prices,
    DEFAULT_DB, _pad_store_id,
)
from parser.price_parser import parse_file as parse_price_file
from scraper.city_names import normalize_city

log = logging.getLogger(__name__)
RAW_DIR = Path(__file__).parent.parent / "sample_data" / "raw"


class ChainScraper(abc.ABC):
    CHAIN_ID: str = ""
    REQUEST_DELAY: float = 0.5

    def __init__(self):
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "Mozilla/5.0 (price-comparison-research/1.0)"

    @abc.abstractmethod
    def load_stores(self, conn) -> dict:
        """Populate stores table from chain's source. Return store_id -> metadata."""

    @abc.abstractmethod
    def build_pricefull_index(self, target_store_ids: set) -> dict:
        """Return store_id -> entry dict with keys: filename (no .gz), url, sub_chain_id."""

    def _download_gz(self, url: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._session.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
        time.sleep(self.REQUEST_DELAY)
        return dest

    @staticmethod
    def _decompress(gz_path: Path) -> bytes:
        with gzip.open(gz_path, "rb") as f:
            return f.read()

    def load_prices_for_stores(
        self, store_ids: list, conn, keep_raw: bool = False, replace: bool = True
    ) -> dict:
        target = set(store_ids)
        index = self.build_pricefull_index(target)

        run_at = datetime.now(timezone.utc).isoformat()
        files_attempted = files_loaded = items_inserted = 0

        for sid in store_ids:
            entry = index.get(_pad_store_id(sid))
            if not entry:
                log.warning(f"  No PriceFull found for store {sid} — skipping.")
                continue

            files_attempted += 1
            log.info(f"  Store {sid}: downloading {entry['filename']}...")
            gz_path = RAW_DIR / (entry["filename"] + ".gz")

            try:
                self._download_gz(entry["url"], gz_path)
                data = self._decompress(gz_path)
                if not keep_raw:
                    gz_path.unlink(missing_ok=True)

                RAW_DIR.mkdir(parents=True, exist_ok=True)
                tmp_xml = RAW_DIR / (entry["filename"] + ".xml")
                tmp_xml.write_bytes(data)

                header, items = parse_price_file(tmp_xml)
                tmp_xml.unlink(missing_ok=True)

                chain_id     = header.get("chain_id") or self.CHAIN_ID
                sub_chain_id = header.get("sub_chain_id") or entry.get("sub_chain_id", "001")
                store_id_xml = header.get("store_id") or sid

                upsert_chain(conn, chain_id)
                store_fk = upsert_store(conn, chain_id, sub_chain_id, store_id_xml)

                if replace:
                    # TODO: when price_history table is added, archive rows here before deleting
                    conn.execute(
                        text("DELETE FROM prices WHERE store_fk=:store_fk"),
                        {"store_fk": store_fk},
                    )

                # Filter once; valid items feed all three bulk inserts below.
                valid = [
                    item for item in items
                    if item.get("item_code") and item.get("item_price") is not None
                ]

                # Deduplicate by item_code — source XMLs occasionally emit the same
                # barcode twice. Postgres raises "ON CONFLICT DO UPDATE cannot affect
                # row a second time" when a single INSERT batch contains two rows that
                # target the same conflict key. Last-wins matches ON CONFLICT DO UPDATE
                # semantics; also prevents UNIQUE-constraint violations in replace mode.
                raw_count = len(valid)
                first_seen: dict = {}
                diff_count = 0
                for item in valid:
                    code = item["item_code"]
                    if code in first_seen:
                        prev = first_seen[code]
                        if (item.get("item_price")        != prev.get("item_price") or
                                item.get("item_name")     != prev.get("item_name") or
                                item.get("manufacturer_name") != prev.get("manufacturer_name")):
                            diff_count += 1
                    else:
                        first_seen[code] = item
                valid = list({item["item_code"]: item for item in valid}.values())
                if raw_count != len(valid) and diff_count > 0:
                    log.warning(
                        "Store %s: %d duplicate item_codes (%d with differing values, last-wins)",
                        sid, raw_count - len(valid), diff_count,
                    )

                # Bulk inserts — all three tables in one transaction per store.
                # items/item_chain_names always use ON CONFLICT (never DELETEd).
                # prices skips ON CONFLICT in replace mode (store was just cleared).
                bulk_upsert_items(conn, valid)
                bulk_upsert_item_chain_names(conn, chain_id, valid)
                count = bulk_insert_prices(conn, store_fk, valid, replace=replace)

                conn.commit()
                items_inserted += count
                files_loaded += 1
                log.info(f"    -> {count} items loaded for store {sid}.")

            except Exception as e:
                log.warning(f"  Store {sid} failed: {e}")
                gz_path.unlink(missing_ok=True)

        conn.execute(text("""
            INSERT INTO fetch_runs
               (chain_id, run_at, files_attempted, files_loaded, items_inserted, status)
               VALUES (:chain_id, :run_at, :files_attempted, :files_loaded, :items_inserted, :status)
        """), {
            "chain_id":       self.CHAIN_ID,
            "run_at":         run_at,
            "files_attempted": files_attempted,
            "files_loaded":   files_loaded,
            "items_inserted": items_inserted,
            "status":         "ok" if files_loaded == files_attempted else "partial",
        })
        conn.commit()

        return {
            "files_attempted": files_attempted,
            "files_loaded":    files_loaded,
            "items_inserted":  items_inserted,
        }

    def run(
        self,
        city: str = "ירושלים",
        n_stores: int = 5,
        db_path=None,
        keep_raw: bool = False,
        append: bool = False,
    ):
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        db_path = db_path or DEFAULT_DB
        conn = connect(db_path)
        init_db(conn)

        self.load_stores(conn)

        city_norm = normalize_city(city)
        log.info(f"\nFinding stores with city_norm='{city_norm}'...")

        rows = conn.execute(text(
            "SELECT store_id, sub_chain_id, store_name FROM stores "
            "WHERE chain_id=:chain_id AND city_norm=:city_norm ORDER BY store_id LIMIT :limit"
        ), {"chain_id": self.CHAIN_ID, "city_norm": city_norm, "limit": n_stores}).fetchall()

        if not rows:
            sample = conn.execute(text(
                "SELECT DISTINCT city, city_norm FROM stores "
                "WHERE chain_id=:chain_id AND city IS NOT NULL ORDER BY city_norm LIMIT 15"
            ), {"chain_id": self.CHAIN_ID}).fetchall()
            log.error(
                f"No stores found for '{city}' (norm='{city_norm}'). "
                f"Sample: {[(r[0], r[1]) for r in sample]}"
            )
            conn.close()
            return

        store_ids = [r[0] for r in rows]
        for r in rows:
            log.info(f"  Store {r[0]}: {r[2]}")

        summary = self.load_prices_for_stores(
            store_ids, conn, keep_raw=keep_raw, replace=not append
        )
        conn.close()

        print(f"\n--- Done ---")
        print(f"Files attempted : {summary['files_attempted']}")
        print(f"Files loaded    : {summary['files_loaded']}")
        print(f"Items inserted  : {summary['items_inserted']}")


def _base_cli(scraper_cls):
    """Shared CLI entry point for all chain scrapers."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    city   = next((a for a in sys.argv[1:] if not a.startswith("-")), "ירושלים")
    n      = int(next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "-n"), 5))
    keep   = "--keep-raw" in sys.argv
    append = "--append" in sys.argv
    scraper_cls().run(city=city, n_stores=n, keep_raw=keep, append=append)
