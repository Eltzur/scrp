"""Shared base class for chain scrapers."""
import abc
import gzip
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests
from sqlalchemy import text

from db.db import (
    connect, init_db, upsert_chain, upsert_store,
    upsert_item, upsert_item_chain_name, upsert_price,
    bulk_upsert_items, bulk_upsert_item_chain_names, bulk_insert_prices,
    bulk_insert_promos,
    _pad_store_id,
)
from parser.price_parser import parse_file as parse_price_file, parse_promo_file
from scraper.city_names import normalize_city

log = logging.getLogger(__name__)
RAW_DIR = Path(__file__).parent.parent / "sample_data" / "raw"


class ChainScraper(abc.ABC):
    CHAIN_ID: str = ""
    REQUEST_DELAY: float = 0.5
    STORE_WORKERS: int = 4

    def __init__(self):
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "Mozilla/5.0 (price-comparison-research/1.0)"

    @abc.abstractmethod
    def load_stores(self, conn) -> dict:
        """Populate stores table from chain's source. Return store_id -> metadata."""

    @abc.abstractmethod
    def build_pricefull_index(self, target_store_ids: set) -> dict:
        """Return store_id -> entry dict with keys: filename (no .gz), url, sub_chain_id."""

    def build_price_index(self, target_store_ids: set) -> dict:
        """Return store_id -> entry dict for Price (delta) files. Override per chain."""
        raise NotImplementedError

    def build_promo_index(self, target_store_ids: set) -> dict:
        """Return store_id -> entry dict for Promo files. Override per chain."""
        raise NotImplementedError

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

    def _process_store(
        self, sid: str, entry, store_id_to_fk: dict,
        keep_raw: bool, replace: bool, delta: bool,
        run_at: str, fetch_run_id: int,
    ) -> dict:
        """Process one store in its own DB connection. Writes fetch_store_runs immediately.

        Returns {"attempted": 0/1, "files_loaded": 0/1, "items_inserted": N}.
        """
        padded = _pad_store_id(sid)
        fk = store_id_to_fk.get(padded)

        if entry is None:
            if delta:
                log.info(f"  No Price delta for store {sid} — falling back to PriceFull")
                pf_index = self.build_pricefull_index({padded})
                entry = pf_index.get(padded)
                if entry:
                    delta = False
                    replace = True
            if entry is None:
                log.warning(f"  No {'Price' if delta else 'PriceFull'} found for store {sid} — skipping.")
                if fk is not None:
                    wconn = connect()
                    try:
                        wconn.execute(text(
                            "INSERT INTO fetch_store_runs"
                            " (fetch_run_id, chain_id, store_fk, store_id, run_at,"
                            "  files_loaded, items_inserted, status)"
                            " VALUES (:frid, :cid, :sfk, :sid, :rat, 0, 0, 'no_file')"
                        ), {"frid": fetch_run_id, "cid": self.CHAIN_ID,
                            "sfk": fk, "sid": padded, "rat": run_at})
                        wconn.commit()
                    finally:
                        wconn.close()
                else:
                    log.warning(f"  Store {sid}: not in stores table, omitting fetch_store_runs row.")
                return {"attempted": 0, "files_loaded": 0, "items_inserted": 0}

        log.info(f"  Store {sid}: downloading {entry['filename']}...")
        gz_path = RAW_DIR / (entry["filename"] + ".gz")
        wconn = connect()
        try:
            self._download_gz(entry["url"], gz_path)
            data = self._decompress(gz_path)
            if not keep_raw:
                gz_path.unlink(missing_ok=True)

            RAW_DIR.mkdir(parents=True, exist_ok=True)
            tmp_xml = RAW_DIR / (entry["filename"] + ".xml")
            tmp_xml.write_bytes(data)

            header, items = parse_price_file(tmp_xml)
            items = list(items)
            tmp_xml.unlink(missing_ok=True)

            chain_id     = header.get("chain_id") or self.CHAIN_ID
            sub_chain_id = header.get("sub_chain_id") or entry.get("sub_chain_id", "001")
            store_id_xml = header.get("store_id") or sid

            upsert_chain(wconn, chain_id)
            store_fk = upsert_store(wconn, chain_id, sub_chain_id, store_id_xml)

            if replace and not delta:
                # TODO: when price_history table is added, archive rows here before deleting
                wconn.execute(
                    text("DELETE FROM prices WHERE store_fk=:store_fk"),
                    {"store_fk": store_fk},
                )

            # Delta mode: split items by ItemStatus before filtering.
            # removed_codes = items with status '0' (delisted); valid = active items.
            if delta:
                removed_codes = list({
                    str(item["item_code"]) for item in items
                    if item.get("item_code") and str(item.get("item_status", "")) == "0"
                })
                valid = [
                    item for item in items
                    if item.get("item_code")
                    and str(item.get("item_status", "")) != "0"
                    and item.get("item_price") is not None
                ]
            else:
                removed_codes = []
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
            # prices: in replace mode the store was just cleared (no ON CONFLICT needed);
            #         in delta mode we need ON CONFLICT DO UPDATE (store NOT cleared).
            bulk_upsert_items(wconn, valid)
            bulk_upsert_item_chain_names(wconn, chain_id, valid)
            count = bulk_insert_prices(wconn, store_fk, valid, replace=(replace and not delta))

            if delta and removed_codes:
                for i in range(0, len(removed_codes), 1000):
                    batch = removed_codes[i:i + 1000]
                    del_params = {f"d{j}": code for j, code in enumerate(batch)}
                    del_params["store_fk"] = store_fk
                    wconn.execute(text(
                        "DELETE FROM prices WHERE store_fk=:store_fk"
                        f" AND item_code IN ({','.join(f':d{j}' for j in range(len(batch)))})"
                    ), del_params)
                log.info(f"    -> {len(removed_codes)} prices removed for store {sid}.")

            wconn.execute(text(
                "INSERT INTO fetch_store_runs"
                " (fetch_run_id, chain_id, store_fk, store_id, run_at,"
                "  files_loaded, items_inserted, status)"
                " VALUES (:frid, :cid, :sfk, :sid, :rat, 1, :ii, 'loaded')"
            ), {"frid": fetch_run_id, "cid": self.CHAIN_ID,
                "sfk": store_fk, "sid": padded, "rat": run_at, "ii": count})
            wconn.commit()
            log.info(f"    -> {count} items loaded for store {sid}.")

            # Promo ingestion — best-effort, does not affect price loading result
            try:
                promo_idx = self.build_promo_index({padded})
                promo_entry = promo_idx.get(padded)
                if promo_entry:
                    gz_p = RAW_DIR / (promo_entry["filename"] + ".gz")
                    self._download_gz(promo_entry["url"], gz_p)
                    promo_data = self._decompress(gz_p)
                    if not keep_raw:
                        gz_p.unlink(missing_ok=True)
                    tmp_p = RAW_DIR / (promo_entry["filename"] + ".xml")
                    tmp_p.write_bytes(promo_data)
                    _, promo_items = parse_promo_file(tmp_p)
                    promo_items = list(promo_items)
                    tmp_p.unlink(missing_ok=True)
                    wconn.execute(text("DELETE FROM promos WHERE store_fk=:fk"), {"fk": store_fk})
                    n_promos = bulk_insert_promos(wconn, store_fk, promo_items)
                    wconn.commit()
                    log.info(f"    -> {n_promos} promos loaded for store {sid}.")
            except NotImplementedError:
                pass
            except Exception as e:
                log.warning(f"  Store {sid}: promo ingestion failed: {e}")
                try:
                    wconn.rollback()
                except Exception:
                    pass

            return {"attempted": 1, "files_loaded": 1, "items_inserted": count}

        except Exception as e:
            log.warning(f"  Store {sid} failed: {e}")
            gz_path.unlink(missing_ok=True)
            try:
                wconn.rollback()
                if fk is not None:
                    wconn.execute(text(
                        "INSERT INTO fetch_store_runs"
                        " (fetch_run_id, chain_id, store_fk, store_id, run_at,"
                        "  files_loaded, items_inserted, status)"
                        " VALUES (:frid, :cid, :sfk, :sid, :rat, 0, 0, 'error')"
                    ), {"frid": fetch_run_id, "cid": self.CHAIN_ID,
                        "sfk": fk, "sid": padded, "rat": run_at})
                    wconn.commit()
                else:
                    log.warning(f"  Store {sid}: not in stores table, omitting fetch_store_runs row.")
            except Exception:
                pass
            return {"attempted": 1, "files_loaded": 0, "items_inserted": 0}

        finally:
            wconn.close()

    def load_prices_for_stores(
        self, store_ids: list, conn, keep_raw: bool = False, replace: bool = True,
        delta: bool = False,
    ) -> dict:
        target = set(store_ids)
        index = self.build_price_index(target) if delta else self.build_pricefull_index(target)

        run_at = datetime.now(timezone.utc).isoformat()

        # Batch lookup — read-only dict, safely shared across worker threads.
        store_id_to_fk: dict[str, int] = {
            _pad_store_id(r[1]): r[0]
            for r in conn.execute(
                text("SELECT id, store_id FROM stores WHERE chain_id=:chain_id"),
                {"chain_id": self.CHAIN_ID},
            ).fetchall()
        }

        # Insert fetch_runs upfront so workers can reference it for fetch_store_runs FK.
        fetch_run_id = conn.execute(text("""
            INSERT INTO fetch_runs
               (chain_id, run_at, files_attempted, files_loaded, items_inserted, status)
               VALUES (:chain_id, :run_at, 0, 0, 0, 'running')
            RETURNING id
        """), {"chain_id": self.CHAIN_ID, "run_at": run_at}).scalar()
        conn.commit()

        with ThreadPoolExecutor(max_workers=self.STORE_WORKERS) as executor:
            futures = [
                executor.submit(
                    self._process_store,
                    sid, index.get(_pad_store_id(sid)), store_id_to_fk,
                    keep_raw, replace, delta, run_at, fetch_run_id,
                )
                for sid in store_ids
            ]
            results = [f.result() for f in futures]

        files_attempted = sum(r["attempted"] for r in results)
        files_loaded    = sum(r["files_loaded"] for r in results)
        items_inserted  = sum(r["items_inserted"] for r in results)

        conn.execute(text("""
            UPDATE fetch_runs
            SET files_attempted=:fa, files_loaded=:fl, items_inserted=:ii, status=:s
            WHERE id=:id
        """), {
            "fa": files_attempted, "fl": files_loaded, "ii": items_inserted,
            "s": "ok" if files_loaded == files_attempted else "partial",
            "id": fetch_run_id,
        })
        conn.commit()

        return {
            "files_attempted": files_attempted,
            "files_loaded":    files_loaded,
            "items_inserted":  items_inserted,
            "fetch_run_id":    fetch_run_id,
        }

    def run(
        self,
        city: str = "ירושלים",
        n_stores: int = 5,
        keep_raw: bool = False,
        append: bool = False,
    ):
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        conn = connect()
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
