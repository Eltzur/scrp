"""Hazi Hinam scraper — חצי חינם.

Portal listing: https://shop.hazi-hinam.co.il/Prices?d=YYYY-MM-DD&t=PriceFull|Price
Download base: https://hazihinamprod01.blob.core.windows.net/regulatories/{filename}.gz
No auth required.

Store list is hardcoded from the StoresFull XML (store 103 = online delivery, excluded).
Filename format: PriceFull{ChainId}-{SubChainId}-{StoreId}-{Timestamp}.gz
"""
import logging
from datetime import date

from lxml import html
from sqlalchemy import text

from scraper.base import ChainScraper
from db.db import upsert_chain, _pad_store_id

log = logging.getLogger(__name__)

CHAIN_ID     = "7290700100008"
CHAIN_NAME   = "חצי חינם"
LISTING_BASE = "https://shop.hazi-hinam.co.il/Prices"

# Store 103 (StoreType=2, online delivery) is deliberately excluded.
_STORES: list[tuple[str, str, str]] = [
    ("201", "כל בו חצי חינם הכשרת הישוב", "ראשון לציון"),
    ("202", "כל בו חצי חינם כישור",        "חולון"),
    ("203", "כל בו חצי חינם רחובות",        "רחובות"),
    ("204", "כל בו חצי חינם מרכבה",         "חולון"),
    ("205", "כל בו חצי חינם לחי",           "ראשון לציון"),
    ("206", "כל בו חצי חינם שרונים",        "הוד השרון"),
    ("207", "תוצרת חקלאית ירקות לחי",       "ראשון לציון"),
    ("208", "תוצרת חקלאית שוק ראשון",       "ראשון לציון"),
    ("209", "כל בו חצי חינם אם המושבות",    "פתח תקווה"),
    ("210", "תוצרת חקלאית ירקות שרונים",    "הוד השרון"),
    ("217", "תוצרת חקלאית מרכבה ירקות",     "חולון"),
]


class HaziHinamScraper(ChainScraper):
    CHAIN_ID     = CHAIN_ID
    STORE_WORKERS = 4

    def load_stores(self, conn) -> dict:
        upsert_chain(conn, self.CHAIN_ID, CHAIN_NAME)
        seen: dict[str, dict] = {}
        for sid, name, city in _STORES:
            conn.execute(text("""
                INSERT INTO stores (chain_id, sub_chain_id, store_id, store_name, city)
                VALUES (:chain_id, :sub_chain_id, :store_id, :store_name, :city)
                ON CONFLICT(chain_id, sub_chain_id, store_id) DO UPDATE SET
                    store_name = COALESCE(excluded.store_name, stores.store_name),
                    city       = COALESCE(excluded.city, stores.city)
            """), {
                "chain_id": self.CHAIN_ID, "sub_chain_id": "000",
                "store_id": sid, "store_name": name, "city": city,
            })
            seen[sid] = {"store_id": sid, "store_name": name, "city": city}
        conn.commit()
        log.info(f"{CHAIN_NAME}: {len(seen)} stores upserted.")
        return seen

    def _fetch_listing(self, file_type: str) -> list[dict]:
        """Fetch today's portal listing page and return blob URL entries."""
        today = date.today().isoformat()
        url = f"{LISTING_BASE}?d={today}&t={file_type}"
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        doc = html.fromstring(resp.content)
        entries = []
        for href in doc.xpath('//a[contains(@href, "blob.core.windows.net")]/@href'):
            fname = href.rsplit("/", 1)[-1]
            if fname.endswith(".gz"):
                fname = fname[:-3]
            entries.append({"filename": fname, "url": href})
        return entries

    def build_pricefull_index(self, target_store_ids: set) -> dict:
        entries = self._fetch_listing("PriceFull")
        index: dict[str, dict] = {}
        prefix = f"PriceFull{self.CHAIN_ID}"
        for e in entries:
            fname = e["filename"]
            if not fname.startswith(prefix):
                continue
            parts = fname.split("-")
            if len(parts) < 3:
                continue
            sid = _pad_store_id(parts[2])
            if sid not in target_store_ids:
                continue
            # Keep latest file per store — filename timestamp sorts lexicographically.
            if sid not in index or fname > index[sid]["filename"]:
                index[sid] = {"filename": fname, "url": e["url"], "sub_chain_id": "000"}
        log.info(
            f"{CHAIN_NAME}: PriceFull index built — "
            f"{len(index)} stores available, {len(target_store_ids)} targeted."
        )
        return index

    def build_price_index(self, target_store_ids: set) -> dict:
        entries = self._fetch_listing("Price")
        index: dict[str, dict] = {}
        prefix      = f"Price{self.CHAIN_ID}"
        full_prefix = f"PriceFull{self.CHAIN_ID}"
        for e in entries:
            fname = e["filename"]
            if not fname.startswith(prefix) or fname.startswith(full_prefix):
                continue
            parts = fname.split("-")
            if len(parts) < 3:
                continue
            sid = _pad_store_id(parts[2])
            if sid not in target_store_ids:
                continue
            if sid not in index or fname > index[sid]["filename"]:
                index[sid] = {"filename": fname, "url": e["url"], "sub_chain_id": "000"}
        log.info(
            f"{CHAIN_NAME}: Price (delta) index built — "
            f"{len(index)} stores available, {len(target_store_ids)} targeted."
        )
        return index
