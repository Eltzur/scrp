"""Shufersal price scraper.

Store metadata (name, city) is extracted directly from the HTML branch column
(e.g. "357 - דיל קדימה לב השרון") since StoresFull files are not reliably
present in the listing.

PriceFull discovery uses a direct per-store query:
  GET /FileObject/UpdateCategory?catID=0&storeId={N}&sort=Time&sortdir=DESC
Returns the newest PriceFull file for the given store in one request.
"""
import logging
import re
import time
from pathlib import Path
from typing import Optional

from lxml import html
from sqlalchemy import text

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
        return {"chain_id": chain_id, "sub_chain_id": seg2, "store_id": seg3.zfill(3)}
    return {"chain_id": chain_id, "sub_chain_id": "001", "store_id": seg2.zfill(3)}


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

    def _fetch_url(self, url: str) -> list:
        resp = self._session.get(url, timeout=60)
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

    def _fetch_raw_page(self, page: int) -> list:
        url = f"{LISTING_BASE}?catname=PriceFull&page={page}&sort=Time&sortdir=DESC"
        return self._fetch_url(url)

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
                conn.execute(text("""
                    INSERT INTO stores (chain_id, sub_chain_id, store_id, store_name, city, city_norm)
                    VALUES (:chain_id, :sub_chain_id, :store_id, :store_name, :city, :city_norm)
                    ON CONFLICT(chain_id, sub_chain_id, store_id) DO UPDATE SET
                        store_name = COALESCE(excluded.store_name, stores.store_name),
                        city       = COALESCE(excluded.city, stores.city),
                        city_norm  = COALESCE(excluded.city_norm, stores.city_norm)
                    """), {
                    "chain_id": self.CHAIN_ID, "sub_chain_id": row["sub_chain_id"],
                    "store_id": sid, "store_name": row["branch_name"],
                    "city": city, "city_norm": city_norm,
                })
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

    def build_pricefull_index(self, target_store_ids: set,
                              start_page: int | None = None) -> dict:
        # start_page retained for call-site compatibility; no longer used.
        index: dict[str, dict] = {}
        log.info(f"Shufersal: fetching PriceFull for {len(target_store_ids)} stores…")
        for store_id in sorted(target_store_ids):
            url = (f"{LISTING_BASE}?catID=0&storeId={int(store_id)}"
                   f"&sort=Time&sortdir=DESC")
            try:
                rows = self._fetch_url(url)
            except Exception as e:
                log.warning(f"Shufersal store {store_id}: fetch failed: {e}")
                continue
            pf_rows = [r for r in rows if r["file_type"] == "PriceFull"]
            if not pf_rows:
                log.warning(f"Shufersal store {store_id}: no PriceFull file found")
                continue
            best = max(pf_rows, key=lambda r: r["filename"])
            fname = best["filename"]
            if fname.endswith(".gz"):
                fname = fname[:-3]
            sid = parse_filename(best["filename"]).get("store_id", store_id)
            index[sid] = {**best, "filename": fname}
        return index


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    city = sys.argv[1] if len(sys.argv) > 1 else "ירושלים"
    n    = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    keep = "--keep-raw" in sys.argv
    ShufersalScraper().run(city=city, n_stores=n, keep_raw=keep)
