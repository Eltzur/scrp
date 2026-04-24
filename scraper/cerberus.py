"""Shared base class for chains that publish via the Cerberus portal
(url.retail.publishedprices.co.il) — e.g. Rami Levy, Osher Ad.

Login: 2-step CSRF flow
  1. GET /login → extract <meta name="csrftoken"> → POST /login/user
  2. Re-extract CSRF from /file page → use for /file/json/dir calls

Stores XML: UTF-16 encoded, NOT gzipped.
  City field is a numeric government city code — mapped via CITY_CODES.

PriceFull files: both old and new filename formats are handled:
  Old: PriceFull{ChainId}-{StoreId}-{Timestamp12}.gz
  New: PriceFull{ChainId}-{SubChainId}-{StoreId}-{Date8}-{Time6}.gz
"""
import logging
import re
import time
import urllib3
import xml.etree.ElementTree as ET
from pathlib import Path

from sqlalchemy import text

from scraper.base import ChainScraper
from db.db import upsert_chain
from scraper.city_names import normalize_city

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
log = logging.getLogger(__name__)

BASE_URL = "https://url.retail.publishedprices.co.il"

# Israeli government numeric city codes → canonical Hebrew city names.
# Shared across all Cerberus chains (same government system).
CITY_CODES: dict[int, str] = {
    3000: "ירושלים",
    5000: "תל אביב",
    4000: "חיפה",
    9000: "באר שבע",
    6100: "בני ברק",      # government code; some chains label it רמת גן (Ayalon area)
    8600: "רמת גן",
    7400: "נתניה",
    8300: "ראשון לציון",
    7900: "פתח תקווה",
    6900: "כפר סבא",
    8700: "רעננה",
    6400: "הרצליה",
    6600: "חולון",
    6200: "בת ים",
    6500: "חדרה",
    2500: "נשר",
    6300: "גבעתיים",
    6700: "טבריה",
    1015: "מבשרת ציון",
    1165: "מודיעין",
    1200: "מודיעין",
    2610: "בית שמש",
    2640: "ראש העין",
    2660: "יבנה",
    2630: "קריית גת",
    7000: "לוד",
    8500: "רמלה",
    8400: "רחובות",
    7700: "עפולה",
    9100: "נהריה",
    7600: "עכו",
    9200: "בית שאן",
    9300: "זכרון יעקב",
    1031: "שדרות",
    2800: "קריית שמונה",
    2600: "אילת",
    2400: "אור יהודה",
    9500: "קריית ביאליק",
    9600: "קריית ים",
    9700: "הוד השרון",
    70:   "אשדוד",
    7100: "אשקלון",
    3780: "ביתר עלית",
    3570: "אריאל",
    874:  "מגדל העמק",
    2006: "כנות",
    2620: "קריית אונו",
    681:  "גבעת שמואל",
    171:  "פרדסיה",
    195:  "קדימה",
    246:  "נתיבות",
    31:   "אופקים",
}

# Handles both old and new Cerberus PriceFull filename formats.
_PRICEFULL_RE = re.compile(
    r"^PriceFull(\d{13})"   # chain_id
    r"-(\d{1,4})"           # seg2: sub_chain_id (new) or store_id (old)
    r"(?:-(\d{1,4}))?"      # seg3: store_id (new format only, optional)
    r"-(\d{8,12})"          # timestamp or date
    r"(?:-\d{6})?\.gz$",    # optional time component (new format)
    re.IGNORECASE,
)


def _parse_pricefull(fname: str) -> dict | None:
    """
    Parse a PriceFull filename into {sub_chain_id, store_id}.
    Returns None if the filename doesn't match.
    """
    m = _PRICEFULL_RE.match(fname)
    if not m:
        return None
    _chain, seg2, seg3, _ts = m.groups()
    if seg3:
        return {"sub_chain_id": seg2, "store_id": seg3.zfill(3)}
    return {"sub_chain_id": "001", "store_id": seg2.zfill(3)}


class CerberusScraper(ChainScraper):
    """Base class for chains served by the Cerberus portal."""

    USERNAME:   str = ""          # override in subclass
    CHAIN_NAME: str = ""          # Hebrew name for upsert_chain
    CITY_CODES: dict = CITY_CODES # can override per subclass if needed

    def __init__(self):
        super().__init__()
        self._session.verify = False
        self._csrf: str | None = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _login(self) -> None:
        r0 = self._session.get(f"{BASE_URL}/login", timeout=30)
        r0.raise_for_status()
        m = re.search(r'<meta name="csrftoken" content="([^"]+)"', r0.text)
        csrf = m.group(1) if m else ""
        r1 = self._session.post(
            f"{BASE_URL}/login/user",
            data={"username": self.USERNAME, "password": "", "r": "", "csrftoken": csrf},
            timeout=30,
        )
        r1.raise_for_status()
        m2 = re.search(r'<meta name="csrftoken" content="([^"]+)"', r1.text)
        self._csrf = m2.group(1) if m2 else ""
        log.info(f"{self.CHAIN_NAME}: logged in to Cerberus as '{self.USERNAME}'.")

    def _list_files(self) -> list:
        if not self._csrf:
            self._login()
        r = self._session.post(
            f"{BASE_URL}/file/json/dir",
            data={
                "sEcho": 1, "iDisplayStart": 0,
                "iDisplayLength": 2000, "csrftoken": self._csrf,
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=30,
        )
        r.raise_for_status()
        time.sleep(self.REQUEST_DELAY)
        return r.json().get("aaData", [])

    # ------------------------------------------------------------------
    # Download (authenticated — session cookie required)
    # ------------------------------------------------------------------

    def _download_gz(self, url: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._session.get(url, stream=True, timeout=60, verify=False) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
        time.sleep(self.REQUEST_DELAY)
        return dest

    # ------------------------------------------------------------------
    # Store metadata
    # ------------------------------------------------------------------

    def load_stores(self, conn) -> dict:
        upsert_chain(conn, self.CHAIN_ID, self.CHAIN_NAME)
        files = self._list_files()

        stores_files = sorted(
            [f for f in files if f["fname"].lower().startswith("stores")],
            key=lambda f: f["ftime"],
        )
        if not stores_files:
            log.warning(f"{self.CHAIN_NAME}: no Stores file found in listing.")
            return {}

        fname = stores_files[-1]["fname"]
        log.info(f"{self.CHAIN_NAME}: loading store metadata from {fname}…")
        r = self._session.get(f"{BASE_URL}/file/d/{fname}", timeout=30)
        r.raise_for_status()
        time.sleep(self.REQUEST_DELAY)

        # Stores XML is UTF-16 with BOM (ff fe), not gzipped
        content = r.content.decode("utf-16", errors="replace")
        root = ET.fromstring(content)

        seen = {}
        for store in root.iter("Store"):
            sid  = (store.findtext("StoreID")   or "").strip().zfill(3)
            name = (store.findtext("StoreName") or "").strip()
            addr = (store.findtext("Address")   or "").strip()
            try:
                city_code = int((store.findtext("City") or "0").strip())
            except ValueError:
                city_code = 0
            city      = self.CITY_CODES.get(city_code)
            city_norm = normalize_city(city) if city else None

            conn.execute(text("""
                INSERT INTO stores
                    (chain_id, sub_chain_id, store_id, store_name, city, city_norm, address)
                VALUES (:chain_id, :sub_chain_id, :store_id, :store_name, :city, :city_norm, :address)
                ON CONFLICT(chain_id, sub_chain_id, store_id) DO UPDATE SET
                    store_name = COALESCE(excluded.store_name, store_name),
                    city       = COALESCE(excluded.city, city),
                    city_norm  = COALESCE(excluded.city_norm, city_norm),
                    address    = COALESCE(excluded.address, address)
                """), {
                "chain_id": self.CHAIN_ID, "sub_chain_id": "001", "store_id": sid,
                "store_name": name, "city": city, "city_norm": city_norm, "address": addr,
            })
            seen[sid] = {
                "store_id": sid, "store_name": name,
                "city": city, "city_norm": city_norm,
            }

        conn.commit()
        log.info(f"{self.CHAIN_NAME}: {len(seen)} stores loaded.")
        return seen

    # ------------------------------------------------------------------
    # PriceFull index (handles old and new filename formats)
    # ------------------------------------------------------------------

    def build_pricefull_index(self, target_store_ids: set) -> dict:
        files = self._list_files()
        index: dict[str, dict] = {}

        for f in files:
            fname = f["fname"]
            parsed = _parse_pricefull(fname)
            if not parsed:
                continue
            sid = parsed["store_id"]
            # Keep only the newest file per store (ftime is "MM/DD/YYYY HH:MM" — sorts correctly)
            if sid not in index or f["ftime"] > index[sid]["ftime"]:
                index[sid] = {
                    "filename":    fname[:-3],  # strip .gz for base class convention
                    "url":         f"{BASE_URL}/file/d/{fname}",
                    "sub_chain_id": parsed["sub_chain_id"],
                    "store_id":    sid,
                    "ftime":       f["ftime"],
                }

        log.info(
            f"{self.CHAIN_NAME}: PriceFull index built — "
            f"{len(index)} stores available, {len(target_store_ids)} targeted."
        )
        return index
