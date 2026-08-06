"""Base scraper for chains published via the bina-projects portal
(e.g. kingstore.binaprojects.com). Multiple Israeli chains share this
platform.

Portal contract (3 JSON endpoints, all POST):
  - {BASE}/Select_Store.aspx  (empty body)
      -> [{"Kod": <int>, "Nm": <str>}]
  - {BASE}/MainIO_Hok.aspx  (form: WStore="", WDate="", WFileType="4")
      -> list of file objects with FileNm, Store, DateFile.
      WFileType: 1=StoresFull, 2=Price (delta), 3=Promo (delta),
      4=PriceFull, 5=PromoFull. 6+ return nothing. Each returns full
      history (~1000 files).
      Order is not reliable — use the 12-digit YYYYMMDDHHMM stamp
      embedded in FileNm for newest-per-store selection.
  - {BASE}/Download.aspx?FileNm=<name>  (empty body)
      -> [{"SPath": "<full .gz url>"}]  (always a list, take [0])

Adding a new bina-projects chain = 4-line subclass (BASE_URL, CHAIN_NAME,
CHAIN_ID).
"""
import gzip
import io
import logging
import re
import time
import zipfile

from sqlalchemy import text

from scraper.base import ChainScraper
from scraper.cerberus import CITY_CODES
from parser.price_parser import parse_promo_file_flat
from db.db import upsert_chain
from scraper.city_names import normalize_city, city_override
from scraper.city_matcher import resolve_city

log = logging.getLogger(__name__)


class BinaProjectsScraper(ChainScraper):
    """Base class for chains served by the bina-projects portal."""

    BASE_URL:   str  = ""
    CHAIN_NAME: str  = ""
    CITY_CODES: dict = CITY_CODES

    # bina-projects promo files are the flat variant: no <Group>, items as
    # <Item>, discount fields on <Promotion>. The shared parser returns zero
    # rows on them, which is why these chains had no promos before SU10A-5.
    PROMO_PARSER = staticmethod(parse_promo_file_flat)

    def __init__(self):
        super().__init__()
        self._session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

    # ------------------------------------------------------------------
    # Decompression — bina-projects files use ZIP despite the .gz name
    # ------------------------------------------------------------------

    @staticmethod
    def _decompress(gz_path):
        raw = gz_path.read_bytes()
        if raw[:2] == b'\x1f\x8b':            # gzip magic
            return gzip.decompress(raw)
        if raw[:2] == b'PK':                  # zip magic
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                names = z.namelist()
                if not names:
                    raise ValueError("empty zip archive")
                # bina-projects zips contain a single XML file
                return z.read(names[0])
        raise ValueError(f"unknown archive format, magic={raw[:4]!r}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post_json(self, url: str, data: dict, params: dict | None = None) -> list | dict:
        """POST to a bina-projects endpoint and return parsed JSON.
        Returns [] on any failure — non-fatal, caller checks for empty."""
        try:
            r = self._session.post(url, data=data, params=params, timeout=30)
            r.raise_for_status()
            time.sleep(self.REQUEST_DELAY)
            return r.json()
        except Exception as exc:
            log.warning(f"{self.CHAIN_NAME}: POST {url} failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Store metadata
    # ------------------------------------------------------------------

    def load_stores(self, conn) -> dict:
        upsert_chain(conn, self.CHAIN_ID, self.CHAIN_NAME)
        stores = self._post_json(f"{self.BASE_URL}/Select_Store.aspx", {})
        if not stores:
            log.warning(f"{self.CHAIN_NAME}: no stores returned from Select_Store.")
            return {}

        seen: dict[str, dict] = {}
        for s in stores:
            try:
                sid = str(int(s.get("Kod", 0))).zfill(3)
            except (ValueError, TypeError):
                continue
            name = (s.get("Nm") or "").strip()

            # bina-projects Select_Store has no numeric city code — skip CITY_CODES lookup.
            # Mirror cerberus city-resolution order: override → resolve_city fallback.
            city = city_override(self.CHAIN_ID, sid)
            if not city:
                guess, conf = resolve_city(name, "", self.CHAIN_ID)
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
                "chain_id": self.CHAIN_ID, "sub_chain_id": "001", "store_id": sid,
                "store_name": name, "city": city, "city_norm": city_norm, "address": "",
            })
            seen[sid] = {
                "store_id": sid, "store_name": name,
                "city": city, "city_norm": city_norm,
            }

        conn.commit()
        log.info(f"{self.CHAIN_NAME}: {len(seen)} stores loaded.")
        return seen

    # ------------------------------------------------------------------
    # PriceFull index
    # ------------------------------------------------------------------

    def build_pricefull_index(self, target_store_ids: set) -> dict:
        return self._build_file_index(target_store_ids, "4", "PriceFull")

    def build_price_index(self, target_store_ids: set) -> dict:
        """Daily Price (delta) index. WFileType=2 on the same MainIO_Hok endpoint.

        Its existence is what puts these chains in DELTA_CHAINS — the base
        class calls this instead of build_pricefull_index when delta is on.
        The "Price" prefix cannot collide with "PriceFull": the pattern in
        _build_file_index requires the chain id immediately after the prefix.
        """
        return self._build_file_index(target_store_ids, "2", "Price")

    def build_promo_index(self, target_store_ids: set) -> dict:
        """Daily Promo (delta) index. WFileType=3 on the same MainIO_Hok endpoint.

        Same newest-per-store selection as prices — only the file type and
        prefix differ, so the two share _build_file_index rather than keeping
        two copies of the Download.aspx resolution logic in sync.
        """
        return self._build_file_index(target_store_ids, "3", "Promo")

    def _build_file_index(self, target_store_ids: set, wfiletype: str, prefix: str) -> dict:
        files = self._post_json(f"{self.BASE_URL}/MainIO_Hok.aspx", {
            "WStore": "", "WDate": "", "WFileType": wfiletype,
        })
        if not files:
            log.warning(f"{self.CHAIN_NAME}: no {prefix} files returned from MainIO_Hok.")
            return {}

        # King Store's portal changed its filename scheme Aug 2026 (SU10A-7):
        #   old: {prefix}{chain}-{store}-{YYYYMMDDHHMM}.gz            (2 segments)
        #   new: {prefix}{chain}-{subchain}-{store}-{YYYYMMDD}-{HHMMSS}.gz  (4 segments)
        # Shefa + Shuk Hayir still publish the old form, so BOTH must be accepted.
        pat_old = re.compile(
            rf"^{prefix}{re.escape(self.CHAIN_ID)}-(\d+)-(\d{{12}})\.gz$",
            re.IGNORECASE,
        )
        pat_new = re.compile(
            rf"^{prefix}{re.escape(self.CHAIN_ID)}-\d+-(\d+)-(\d{{8}})-(\d{{6}})\.gz$",
            re.IGNORECASE,
        )

        # Pass 1: newest-per-store using the 12-digit YYYYMMDDHHMM stamp in
        # the filename. DateFile ("HH:MM DD/MM/YYYY") does NOT sort correctly
        # across days — the embedded stamp does.
        newest: dict[str, tuple[str, str]] = {}  # sid -> (FileNm, stamp)
        for f in files:
            fname = f.get("FileNm", "")
            m = pat_old.match(fname)
            if m:
                sid   = str(int(m.group(1))).zfill(3)
                stamp = m.group(2)                    # 12-digit YYYYMMDDHHMM
            else:
                m = pat_new.match(fname)
                if not m:
                    continue
                sid   = str(int(m.group(1))).zfill(3) # store is the 2nd numeric segment now
                stamp = m.group(2) + m.group(3)       # YYYYMMDD + HHMMSS = 14-digit, sorts correctly
            if sid not in newest or stamp > newest[sid][1]:
                newest[sid] = (fname, stamp)

        # Pass 2: resolve download URL for each winning file that is targeted.
        # One Download.aspx call per targeted store (not all ~1000 files).
        index: dict[str, dict] = {}
        for sid, (fname, stamp) in newest.items():
            if sid not in target_store_ids:
                continue
            result = self._post_json(
                f"{self.BASE_URL}/Download.aspx",
                {},
                params={"FileNm": fname},
            )
            if not result or not isinstance(result, list):
                log.warning(f"{self.CHAIN_NAME}: Download.aspx returned no result for {fname}")
                continue
            spath = result[0].get("SPath", "")
            if not spath:
                log.warning(f"{self.CHAIN_NAME}: empty SPath for {fname}")
                continue
            fname_no_gz = fname[:-3] if fname.endswith(".gz") else fname
            index[sid] = {
                "filename":     fname_no_gz,
                "url":          spath,
                "sub_chain_id": "001",
                "store_id":     sid,
                "modified":     stamp,
            }

        log.info(
            f"{self.CHAIN_NAME}: {prefix} index built — "
            f"{len(index)} stores available, {len(target_store_ids)} targeted."
        )
        return index
