"""Victory scraper — uses laibcatalog.co.il REST API (no auth required)."""
import logging
import sys
import time

from sqlalchemy import text

from scraper.base import ChainScraper
from db.db import upsert_chain
from scraper.city_names import normalize_city

log = logging.getLogger(__name__)

_API_BASE = "https://laibcatalog.co.il"


class VictoryScraper(ChainScraper):
    CHAIN_ID   = "7290696200003"
    CHAIN_NAME = "ויקטורי"

    def load_stores(self, conn) -> dict:
        upsert_chain(conn, self.CHAIN_ID, self.CHAIN_NAME)

        resp = self._session.get(
            f"{_API_BASE}/webapi/api/getbranches",
            params={"edi": self.CHAIN_ID},
            timeout=30,
        )
        resp.raise_for_status()
        time.sleep(self.REQUEST_DELAY)
        branches = resp.json()

        seen = {}
        for b in branches:
            sid  = str(b["number"]).zfill(3)
            name = (b.get("name") or "").strip()
            city_norm = normalize_city(name) if name else None
            conn.execute(text("""
                INSERT INTO stores (chain_id, sub_chain_id, store_id, store_name, city, city_norm)
                VALUES (:chain_id, :sub_chain_id, :store_id, :store_name, :city, :city_norm)
                ON CONFLICT(chain_id, sub_chain_id, store_id) DO UPDATE SET
                    store_name = COALESCE(excluded.store_name, store_name),
                    city       = COALESCE(excluded.city, city),
                    city_norm  = COALESCE(excluded.city_norm, city_norm)
            """), {
                "chain_id": self.CHAIN_ID, "sub_chain_id": "001",
                "store_id": sid, "store_name": name,
                "city": name, "city_norm": city_norm,
            })
            seen[sid] = {"store_id": sid, "store_name": name, "city": name, "city_norm": city_norm}

        conn.commit()
        log.info(f"{self.CHAIN_NAME}: {len(seen)} stores loaded.")
        return seen

    def build_pricefull_index(self, target_store_ids: set) -> dict:
        resp = self._session.get(
            f"{_API_BASE}/webapi/api/getfiles",
            params={"edi": self.CHAIN_ID},
            timeout=30,
        )
        resp.raise_for_status()
        time.sleep(self.REQUEST_DELAY)
        files = resp.json()

        index: dict[str, dict] = {}
        for f in files:
            if f.get("fileType", "").lower() != "pricefull":
                continue
            sid = str(f["branchNumber"]).zfill(3)
            # Keep newest file per store (fileDate: "YYYY-MM-DD HH:MM:SS")
            if sid not in index or f["fileDate"] > index[sid]["fileDate"]:
                fname = f["fileName"]
                index[sid] = {
                    "filename":    fname[:-3] if fname.endswith(".gz") else fname,
                    "url":         f"{_API_BASE}/webapi/{self.CHAIN_ID}/{fname}",
                    "sub_chain_id": "001",
                    "store_id":    sid,
                    "fileDate":    f["fileDate"],
                }

        log.info(
            f"{self.CHAIN_NAME}: PriceFull index built — "
            f"{len(index)} stores available, {len(target_store_ids)} targeted."
        )
        return index


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    city   = next((a for a in sys.argv[1:] if not a.startswith("-")), "תל אביב")
    n      = int(next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "-n"), 5))
    keep   = "--keep-raw" in sys.argv
    append = "--append" in sys.argv
    VictoryScraper().run(city=city, n_stores=n, keep_raw=keep, append=append)
