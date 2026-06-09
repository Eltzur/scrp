"""Victory scraper — uses laibcatalog.co.il REST API (no auth required)."""
import logging
import sys
import time

from sqlalchemy import text

from scraper.base import ChainScraper
from db.db import upsert_chain
from scraper.city_names import normalize_city, city_override
from scraper.city_matcher import resolve_city

log = logging.getLogger(__name__)

_API_BASE = "https://laibcatalog.co.il/webapi"


class VictoryScraper(ChainScraper):
    CHAIN_ID   = "7290696200003"
    CHAIN_NAME = "ויקטורי"

    def load_stores(self, conn) -> dict:
        upsert_chain(conn, self.CHAIN_ID, self.CHAIN_NAME)

        for attempt in range(1, 4):
            try:
                resp = self._session.get(
                    f"{_API_BASE}/api/getbranches",
                    params={"edi": self.CHAIN_ID},
                    timeout=30,
                )
                resp.raise_for_status()
                branches = resp.json()
                break
            except Exception as e:
                log.warning(f"{self.CHAIN_NAME}: getbranches attempt {attempt}/3 failed: {e}")
                if attempt == 3:
                    raise
                time.sleep(10)
        time.sleep(self.REQUEST_DELAY)

        seen = {}
        for b in branches:
            sid  = str(b["number"]).zfill(3)
            name = (b.get("name") or "").strip()
            city = city_override(self.CHAIN_ID, sid)
            if not city:
                guess, conf = resolve_city(name, "", self.CHAIN_ID)
                city = guess if conf >= 0.80 else name
            city_norm = normalize_city(city) if city else None
            conn.execute(text("""
                INSERT INTO stores (chain_id, sub_chain_id, store_id, store_name, city, city_norm)
                VALUES (:chain_id, :sub_chain_id, :store_id, :store_name, :city, :city_norm)
                ON CONFLICT(chain_id, sub_chain_id, store_id) DO UPDATE SET
                    store_name = COALESCE(excluded.store_name, stores.store_name),
                    city       = COALESCE(excluded.city, stores.city),
                    city_norm  = COALESCE(excluded.city_norm, stores.city_norm)
            """), {
                "chain_id": self.CHAIN_ID, "sub_chain_id": "001",
                "store_id": sid, "store_name": name,
                "city": city, "city_norm": city_norm,
            })
            seen[sid] = {"store_id": sid, "store_name": name, "city": city, "city_norm": city_norm}

        conn.commit()
        log.info(f"{self.CHAIN_NAME}: {len(seen)} stores loaded.")
        return seen

    def _build_file_index(self, file_type: str, target_store_ids: set) -> dict:
        """Fetch getfiles, filter by file_type, return latest-per-store index."""
        for attempt in range(1, 4):
            try:
                resp = self._session.get(
                    f"{_API_BASE}/api/getfiles",
                    params={"edi": self.CHAIN_ID},
                    timeout=30,
                )
                resp.raise_for_status()
                files = resp.json()
                break
            except Exception as e:
                log.warning(f"{self.CHAIN_NAME}: getfiles attempt {attempt}/3 failed: {e}")
                if attempt == 3:
                    raise
                time.sleep(10)
        time.sleep(self.REQUEST_DELAY)

        index: dict[str, dict] = {}
        for f in files:
            if f.get("fileType", "").lower() != file_type:
                continue
            sid = str(f["branchNumber"]).zfill(3)
            if sid not in index or f["fileDate"] > index[sid]["fileDate"]:
                fname = f["fileName"]
                index[sid] = {
                    "filename":     fname[:-3] if fname.endswith(".gz") else fname,
                    "url":          f"{_API_BASE}/{self.CHAIN_ID}/{fname}",
                    "sub_chain_id": "001",
                    "store_id":     sid,
                    "fileDate":     f["fileDate"],
                }

        log.info(
            f"{self.CHAIN_NAME}: {file_type} index built — "
            f"{len(index)} stores available, {len(target_store_ids)} targeted."
        )
        return index

    def build_pricefull_index(self, target_store_ids: set) -> dict:
        return self._build_file_index("pricefull", target_store_ids)

    def build_price_index(self, target_store_ids: set) -> dict:
        return self._build_file_index("price", target_store_ids)

    def build_promo_index(self, target_store_ids: set) -> dict:
        return self._build_file_index("promo", target_store_ids)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    city   = next((a for a in sys.argv[1:] if not a.startswith("-")), "תל אביב")
    n      = int(next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "-n"), 5))
    keep   = "--keep-raw" in sys.argv
    append = "--append" in sys.argv
    VictoryScraper().run(city=city, n_stores=n, keep_raw=keep, append=append)
