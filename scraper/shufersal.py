"""Shufersal price scraper.

Key discovery: prices.shufersal.co.il returns one global time-sorted listing
regardless of the `catname` URL param. Layout (newest-first, ~April 2026):
  pages  1-15 : Price files  (8 PM daily, old filename format)
  pages 16-35 : Promo files  (8 PM daily)
  pages 36+   : PriceFull, PromoFull (3 AM daily, new filename format)

Store metadata (name, city) is extracted directly from the HTML branch column
(e.g. "357 - דיל קדימה לב השרון") since StoresFull files are not reliably
present in the listing.
"""
import logging
import re
import time
from pathlib import Path
from typing import Optional

from lxml import html

from scraper.base import ChainScraper
from db.db import upsert_chain
from scraper.city_names import normalize_city, CITY_VARIANTS

log = logging.getLogger(__name__)

CHAIN_ID     = "7290027600007"
LISTING_BASE = "http://prices.shufersal.co.il/FileObject/UpdateCategory"

_CITY_HINTS: list[tuple[str, list[str]]] = [
    (canonical, [canonical] + variants)
    for canonical, variants in CITY_VARIANTS.items()
]

_FILENAME_RE = re.compile(
    r"^[A-Za-z]+"       # file type prefix
    r"(\d{13})"         # chain id (13 digits)
    r"-(\d{1,4})"       # seg2: sub-chain OR store-id (old format)
    r"(?:-(\d{1,4}))?"  # seg3: store-id (new format, optional)
    r"-(\d{8,12})"      # timestamp / date
)


def parse_filename(filename: str) -> dict:
    name = Path(filename).stem
    m = _FILENAME_RE.match(name)
    if not m:
        return {}
    chain_id, seg2, seg3, _ts = m.groups()
    if seg3:
        return {"chain_id": chain_id, "sub_chain_id": seg2, "store_id": seg3}
    return {"chain_id": chain_id, "sub_chain_id": "001", "store_id": seg2}


def _city_from_branch_name(branch_name: str) -> Optional[str]:
    """
    Detect canonical city from a branch label like '2 - שלי ירושלים- אגרון'.
    Strips trailing street segment (after the last '- ') before searching,
    so '12 - יש בני ברק- ירושלים' yields 'בני ברק', not 'ירושלים'.
    """
    branch_name = branch_name.replace("\u00a0", "")
    last_dash = branch_name.rfind("- ")
    search_text = branch_name[:last_dash].strip() if last_dash > 5 else branch_name
    for canonical, hints in _CITY_HINTS:
        for hint in hints:
            if hint and hint in search_text:
                return canonical
    return None


class ShufersalScraper(ChainScraper):
    CHAIN_ID = CHAIN_ID

    def _fetch_raw_page(self, page: int) -> list:
        url = f"{LISTING_BASE}?catname=PriceFull&page={page}&sort=Time&sortdir=DESC"
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        time.sleep(self.REQUEST_DELAY)

        doc = html.fromstring(resp.text)
        rows = []
        for a in doc.cssselect("a[href*='blob.core.windows.net']"):
            href = a.get("href", "")
            filename = href.split("?")[0].rsplit("/", 1)[-1]
            info = parse_filename(filename)
            if not info:
                continue

            file_type = re.match(r"^[A-Za-z]+", filename)
            file_type = file_type.group() if file_type else ""

            tr = a.getparent()
            while tr is not None and tr.tag != "tr":
                tr = tr.getparent()
            updated_at = None
            branch_name = ""
            if tr is not None:
                cells = [td.text_content().strip() for td in tr]
                for cell in cells:
                    if re.match(r"\d{1,2}/\d{1,2}/\d{4}", cell):
                        updated_at = cell
                    if re.match(r"^\d+\s*[-–]\s*\S", cell):
                        branch_name = cell

            rows.append({
                **info,
                "filename":    filename,
                "url":         href,
                "updated_at":  updated_at,
                "branch_name": branch_name,
                "file_type":   file_type,
            })
        return rows

    def load_stores(self, conn, pages_to_scan: int = 18) -> dict:
        upsert_chain(conn, self.CHAIN_ID, "שופרסל")
        seen: dict[str, dict] = {}

        log.info(f"Shufersal: collecting store metadata (pages 1-{pages_to_scan})…")
        for page in range(1, pages_to_scan + 1):
            log.info(f"  Page {page}/{pages_to_scan}…")
            try:
                rows = self._fetch_raw_page(page)
            except Exception as e:
                log.warning(f"  Page {page} failed: {e}")
                continue

            for row in rows:
                sid = row["store_id"]
                if sid in seen:
                    continue
                city = _city_from_branch_name(row["branch_name"])
                city_norm = normalize_city(city) if city else None
                conn.execute(
                    """
                    INSERT INTO stores (chain_id, sub_chain_id, store_id, store_name, city, city_norm)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chain_id, sub_chain_id, store_id) DO UPDATE SET
                        store_name = COALESCE(excluded.store_name, store_name),
                        city       = COALESCE(excluded.city, city),
                        city_norm  = COALESCE(excluded.city_norm, city_norm)
                    """,
                    (self.CHAIN_ID, row["sub_chain_id"], sid,
                     row["branch_name"], city, city_norm),
                )
                seen[sid] = {
                    "store_id":    sid,
                    "store_name":  row["branch_name"],
                    "city":        city,
                    "city_norm":   city_norm,
                    "sub_chain_id": row["sub_chain_id"],
                }

        conn.commit()
        log.info(f"Shufersal: {len(seen)} stores collected.")
        return seen

    def build_pricefull_index(self, target_store_ids: set, start_page: int = 36) -> dict:
        index: dict[str, dict] = {}
        found: set[str] = set()

        log.info(f"Shufersal: building PriceFull index (from page {start_page})…")
        for page in range(start_page, 101):
            log.info(f"  Scanning page {page}…")
            try:
                rows = self._fetch_raw_page(page)
            except Exception as e:
                log.warning(f"  Page {page} failed: {e}")
                continue

            if not rows:
                log.info(f"  Empty page {page} — stopping.")
                break

            for row in rows:
                if row["file_type"] != "PriceFull":
                    continue
                sid = row["store_id"]
                if sid not in index:
                    # Strip .gz so base class can add it back consistently
                    fname = row["filename"]
                    if fname.endswith(".gz"):
                        fname = fname[:-3]
                    index[sid] = {
                        **row,
                        "filename": fname,
                    }
                    if sid in target_store_ids:
                        found.add(sid)

            if found >= target_store_ids:
                log.info(f"  All {len(target_store_ids)} target stores found on page {page}.")
                break

            if page >= start_page + 25:
                log.warning(f"  Scanned 25 pages past start, stopping. Found: {found}")
                break

        return index


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    city = sys.argv[1] if len(sys.argv) > 1 else "ירושלים"
    n    = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    keep = "--keep-raw" in sys.argv
    ShufersalScraper().run(city=city, n_stores=n, keep_raw=keep)
