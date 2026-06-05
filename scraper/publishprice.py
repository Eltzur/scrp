"""Base scraper for chains published via the U-CODE PublishPrice portal.

Portal pattern (e.g. https://prices.carrefour.co.il/):
- Public HTTP, no authentication.
- File listing embedded in the second-to-last <script> tag as two JS variables:
    const path = '20260511';
    const files = [{"name":"PriceFull...", "size":..., "modified":"..."}, ...]
- Download URL: {base_url}/{path}/{filename}
- Stores XML: UTF-16 LE encoded, same gov-city-code system as Cerberus.
- PriceFull files: gzipped, same XML format as all other Israeli chains.

Adding a new PublishPrice chain = ~6-line subclass (CHAIN_ID, SITE_INFIX, CHAIN_NAME).
"""
import json
import logging
import re
import time
import xml.etree.ElementTree as ET

import requests
from sqlalchemy import text

from scraper.base import ChainScraper
from scraper.cerberus import CITY_CODES  # same government city-code system
from db.db import upsert_chain
from scraper.city_names import normalize_city, city_override
from scraper.city_matcher import resolve_city

log = logging.getLogger(__name__)


class PublishPriceScraper(ChainScraper):
    """Base class for chains published via the PublishPrice / U-CODE portal."""

    SITE_INFIX: str = ""   # override in subclass, e.g. "carrefour"
    CHAIN_NAME: str = ""
    CITY_CODES: dict = CITY_CODES

    @property
    def _base_url(self) -> str:
        return f"https://prices.{self.SITE_INFIX}.co.il"

    def _get_file_listing(self) -> tuple[str, list[dict]]:
        """
        Fetch the portal page and extract (path, files) from the embedded JS.
        Results are cached for the lifetime of this scraper instance so that
        load_stores and build_pricefull_index share one HTTP round-trip.
        """
        if hasattr(self, '_listing_cache'):
            return self._listing_cache  # type: ignore[return-value]

        log.info(f"{self.CHAIN_NAME}: fetching file listing from {self._base_url}/")
        # The PublishPrice portal (prices.carrefour.co.il) intermittently
        # connect-times-out. Retry with backoff so a single transient failure
        # doesn't lose the whole chain for the day. After all attempts fail the
        # exception still propagates — the chain is correctly marked errored.
        attempts = 3
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                r = self._session.get(self._base_url + "/", timeout=30)
                r.raise_for_status()
                break
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < attempts:
                    backoff = 5 * attempt  # 5s, then 10s
                    log.warning(
                        f"{self.CHAIN_NAME}: listing fetch attempt {attempt}/{attempts} "
                        f"failed ({exc.__class__.__name__}); retrying in {backoff}s…"
                    )
                    time.sleep(backoff)
        else:
            raise RuntimeError(
                f"{self.CHAIN_NAME}: file listing fetch failed after {attempts} attempts"
            ) from last_exc
        time.sleep(self.REQUEST_DELAY)

        # The portal hard-codes file metadata in the second-to-last <script> block
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL)
        script_text = next(
            (s for s in reversed(scripts) if 'const files' in s), None
        )
        if not script_text:
            raise ValueError(f"{self.CHAIN_NAME}: file listing not found in portal page")

        path = script_text.split("const path = '")[1].split("'")[0]
        files_raw = script_text.split('const files = ')[1].split('\n')[0].rstrip(';')
        files: list[dict] = json.loads(files_raw)

        log.info(f"{self.CHAIN_NAME}: listing date={path}, {len(files)} files total.")
        self._listing_cache = (path, files)
        return path, files

    # ------------------------------------------------------------------
    # Store metadata
    # ------------------------------------------------------------------

    def load_stores(self, conn) -> dict:
        upsert_chain(conn, self.CHAIN_ID, self.CHAIN_NAME)
        path, files = self._get_file_listing()

        stores_file = next(
            (f for f in files
             if f['name'].startswith('Stores') and f['name'].endswith('.xml')),
            None,
        )
        if not stores_file:
            log.warning(f"{self.CHAIN_NAME}: no Stores XML found in listing.")
            return {}

        url = f"{self._base_url}/{path}/{stores_file['name']}"
        log.info(f"{self.CHAIN_NAME}: loading store metadata from {stores_file['name']}…")
        r = self._session.get(url, timeout=30)
        r.raise_for_status()
        time.sleep(self.REQUEST_DELAY)

        content = r.content.decode('utf-16', errors='replace')
        root = ET.fromstring(content)

        seen: dict[str, dict] = {}
        for store in root.iter('Store'):
            raw_sid = (store.findtext('StoreID') or store.findtext('StoreId') or '').strip()
            if not raw_sid:
                continue
            try:
                sid = str(int(raw_sid)).zfill(3)  # canonical: zero-padded 3-digit
            except ValueError:
                continue

            name = (store.findtext('StoreName') or '').strip()
            addr = (store.findtext('Address')   or '').strip()
            try:
                city_code = int((store.findtext('City') or '0').strip())
            except ValueError:
                city_code = 0
            city = city_override(self.CHAIN_ID, sid)
            if not city:
                city = self.CITY_CODES.get(city_code)
            if not city:
                guess, conf = resolve_city(name, addr, self.CHAIN_ID)
                if conf >= 0.80:
                    city = guess
            city_norm = normalize_city(city) if city else None

            conn.execute(text("""
                INSERT INTO stores
                    (chain_id, sub_chain_id, store_id, store_name, city, city_norm, address)
                VALUES (:chain_id, :sub_chain_id, :store_id, :store_name, :city, :city_norm, :address)
                ON CONFLICT(chain_id, sub_chain_id, store_id) DO UPDATE SET
                    store_name = COALESCE(excluded.store_name, stores.store_name),
                    city       = COALESCE(excluded.city, stores.city),
                    city_norm  = COALESCE(excluded.city_norm, stores.city_norm),
                    address    = COALESCE(excluded.address, stores.address)
            """), {
                'chain_id': self.CHAIN_ID, 'sub_chain_id': '001', 'store_id': sid,
                'store_name': name, 'city': city, 'city_norm': city_norm, 'address': addr,
            })
            seen[sid] = {'store_id': sid, 'store_name': name, 'city': city, 'city_norm': city_norm}

        conn.commit()
        log.info(f"{self.CHAIN_NAME}: {len(seen)} stores loaded.")
        return seen

    # ------------------------------------------------------------------
    # PriceFull index
    # ------------------------------------------------------------------

    def build_pricefull_index(self, target_store_ids: set) -> dict:
        path, files = self._get_file_listing()
        index: dict[str, dict] = {}

        pattern = re.compile(
            rf'PriceFull{re.escape(self.CHAIN_ID)}-\d+-(\d+)-',
            re.IGNORECASE,
        )
        for f in files:
            m = pattern.match(f['name'])
            if not m:
                continue
            sid = str(int(m.group(1))).zfill(3)  # canonical: zero-padded 3-digit
            # Keep the most recently published file per store.
            # modified format is "HH:MM DD-MM-YYYY" — sorts correctly for same-day.
            if sid not in index or f['modified'] > index[sid]['modified']:
                fname = f['name']
                fname_no_gz = fname[:-3] if fname.endswith('.gz') else fname
                index[sid] = {
                    'filename':     fname_no_gz,
                    'url':          f"{self._base_url}/{path}/{fname}",
                    'sub_chain_id': '001',
                    'store_id':     sid,
                    'modified':     f['modified'],
                }

        log.info(
            f"{self.CHAIN_NAME}: PriceFull index built — "
            f"{len(index)} stores available, {len(target_store_ids)} targeted."
        )
        return index
