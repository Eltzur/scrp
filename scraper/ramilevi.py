"""Rami Levy price scraper via Cerberus portal (url.retail.publishedprices.co.il)."""
import logging
import re
import time
import urllib3
import xml.etree.ElementTree as ET
from pathlib import Path

from scraper.base import ChainScraper
from db.db import upsert_chain
from scraper.city_names import normalize_city

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
log = logging.getLogger(__name__)

CHAIN_ID = "7290058140886"
BASE_URL  = "https://url.retail.publishedprices.co.il"
USERNAME  = "RamiLevi"

# Rami Levy numeric city codes → canonical city names matching city_names.py
CITY_CODES: dict[int, str] = {
    3000: "ירושלים",
    5000: "תל אביב",
    4000: "חיפה",
    9000: "באר שבע",
    6100: "רמת גן",
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
    9700: "הוד השרון",
    70:   "אשדוד",
    7100: "אשקלון",
    3780: "ביתר עלית",
    3570: "אריאל",
}

_PRICEFULL_RE = re.compile(r"^PriceFull\d{13}-(\d{1,4})-\d{8,12}\.gz$", re.IGNORECASE)


class RamiLeviScraper(ChainScraper):
    CHAIN_ID = CHAIN_ID

    def __init__(self):
        super().__init__()
        self._session.verify = False
        self._csrf = None

    def _login(self) -> None:
        r0 = self._session.get(f"{BASE_URL}/login", timeout=30)
        r0.raise_for_status()
        m = re.search(r'<meta name="csrftoken" content="([^"]+)"', r0.text)
        csrf = m.group(1) if m else ""
        r1 = self._session.post(
            f"{BASE_URL}/login/user",
            data={"username": USERNAME, "password": "", "r": "", "csrftoken": csrf},
            timeout=30,
        )
        r1.raise_for_status()
        m2 = re.search(r'<meta name="csrftoken" content="([^"]+)"', r1.text)
        self._csrf = m2.group(1) if m2 else ""
        log.info("Rami Levy: logged in to Cerberus.")

    def _list_files(self) -> list:
        if not self._csrf:
            self._login()
        r = self._session.post(
            f"{BASE_URL}/file/json/dir",
            data={"sEcho": 1, "iDisplayStart": 0, "iDisplayLength": 2000, "csrftoken": self._csrf},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=30,
        )
        r.raise_for_status()
        time.sleep(self.REQUEST_DELAY)
        return r.json().get("aaData", [])

    def load_stores(self, conn) -> dict:
        upsert_chain(conn, self.CHAIN_ID)
        files = self._list_files()

        stores_files = sorted(
            [f for f in files if f["fname"].lower().startswith("stores")],
            key=lambda f: f["ftime"],
        )
        if not stores_files:
            log.warning("Rami Levy: no Stores file found in listing.")
            return {}

        fname = stores_files[-1]["fname"]
        log.info(f"Rami Levy: loading store metadata from {fname}…")
        r = self._session.get(f"{BASE_URL}/file/d/{fname}", timeout=30)
        r.raise_for_status()
        time.sleep(self.REQUEST_DELAY)

        # Stores XML is UTF-16 encoded with BOM (ff fe), not gzipped
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
            city      = CITY_CODES.get(city_code)
            city_norm = normalize_city(city) if city else None

            conn.execute(
                """
                INSERT INTO stores (chain_id, sub_chain_id, store_id, store_name, city, city_norm, address)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chain_id, sub_chain_id, store_id) DO UPDATE SET
                    store_name = COALESCE(excluded.store_name, store_name),
                    city       = COALESCE(excluded.city, city),
                    city_norm  = COALESCE(excluded.city_norm, city_norm),
                    address    = COALESCE(excluded.address, address)
                """,
                (self.CHAIN_ID, "001", sid, name, city, city_norm, addr),
            )
            seen[sid] = {"store_id": sid, "store_name": name, "city": city, "city_norm": city_norm}

        conn.commit()
        log.info(f"Rami Levy: {len(seen)} stores loaded.")
        return seen

    def build_pricefull_index(self, target_store_ids: set) -> dict:
        files = self._list_files()
        index: dict[str, dict] = {}
        for f in files:
            m = _PRICEFULL_RE.match(f["fname"])
            if not m:
                continue
            sid = m.group(1).zfill(3)
            # Keep only the newest file per store
            if sid not in index or f["ftime"] > index[sid]["ftime"]:
                stem = f["fname"][:-3]  # strip .gz
                index[sid] = {
                    "filename":    stem,
                    "url":         f"{BASE_URL}/file/d/{f['fname']}",
                    "sub_chain_id": "001",
                    "store_id":    sid,
                    "ftime":       f["ftime"],
                }
        log.info(
            f"Rami Levy: PriceFull index built — "
            f"{len(index)} stores available, {len(target_store_ids)} targeted."
        )
        return index

    def _download_gz(self, url: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._session.get(url, stream=True, timeout=60, verify=False) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
        time.sleep(self.REQUEST_DELAY)
        return dest


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    city = sys.argv[1] if len(sys.argv) > 1 else "ירושלים"
    n    = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    keep = "--keep-raw" in sys.argv
    RamiLeviScraper().run(city=city, n_stores=n, keep_raw=keep)
