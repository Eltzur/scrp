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
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lxml import html
from sqlalchemy import text

from scraper.base import ChainScraper, RAW_DIR
from db.db import (
    upsert_chain, upsert_store,
    bulk_upsert_items, bulk_upsert_item_chain_names, bulk_insert_prices,
    _pad_store_id,
)
from parser.price_parser import parse_file as parse_price_file
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

    def build_price_index(self, target_store_ids: set) -> dict:
        """Fetch Price (delta) file index for each target store (catID=1)."""
        index: dict[str, dict] = {}
        log.info(f"Shufersal: fetching Price (delta) for {len(target_store_ids)} stores…")
        for store_id in sorted(target_store_ids):
            url = (f"{LISTING_BASE}?catID=1&storeId={int(store_id)}"
                   f"&sort=Time&sortdir=DESC")
            try:
                rows = self._fetch_url(url)
            except Exception as e:
                log.warning(f"Shufersal store {store_id}: fetch failed: {e}")
                continue
            p_rows = [r for r in rows if r["file_type"] == "Price"]
            if not p_rows:
                log.warning(f"Shufersal store {store_id}: no Price file found")
                continue
            best = max(p_rows, key=lambda r: r["filename"])
            fname = best["filename"]
            if fname.endswith(".gz"):
                fname = fname[:-3]
            sid = parse_filename(best["filename"]).get("store_id", store_id)
            index[sid] = {**best, "filename": fname}
        return index

    def fetch_price_entry(self, store_id: str) -> dict | None:
        """Fetch a fresh signed Azure URL for one store's Price (delta) file on demand."""
        url = (f"{LISTING_BASE}?catID=1&storeId={int(store_id)}"
               f"&sort=Time&sortdir=DESC")
        try:
            rows = self._fetch_url(url)
        except Exception as e:
            log.warning(f"Shufersal store {store_id}: fetch failed: {e}")
            return None
        p_rows = [r for r in rows if r["file_type"] == "Price"]
        if not p_rows:
            log.warning(f"Shufersal store {store_id}: no Price file found")
            return None
        best = max(p_rows, key=lambda r: r["filename"])
        fname = best["filename"]
        if fname.endswith(".gz"):
            fname = fname[:-3]
        return {**best, "filename": fname}

    def fetch_pricefull_entry(self, store_id: str) -> dict | None:
        """Fetch a fresh signed Azure URL for one store on demand.

        Avoids pre-fetching all URLs upfront (they expire in ~30 min), which
        caused 403s when cron ran chains in parallel and Shufersal downloads
        started late. Called immediately before each store's download.
        """
        url = (f"{LISTING_BASE}?catID=0&storeId={int(store_id)}"
               f"&sort=Time&sortdir=DESC")
        try:
            rows = self._fetch_url(url)
        except Exception as e:
            log.warning(f"Shufersal store {store_id}: fetch failed: {e}")
            return None
        pf_rows = [r for r in rows if r["file_type"] == "PriceFull"]
        if not pf_rows:
            log.warning(f"Shufersal store {store_id}: no PriceFull file found")
            return None
        best = max(pf_rows, key=lambda r: r["filename"])
        fname = best["filename"]
        if fname.endswith(".gz"):
            fname = fname[:-3]
        return {**best, "filename": fname}

    def load_prices_for_stores(
        self, store_ids: list, conn, keep_raw: bool = False, replace: bool = True,
        delta: bool = False,
    ) -> dict:
        """Override: fetch each store's signed URL lazily, right before download."""
        run_at = datetime.now(timezone.utc).isoformat()
        files_attempted = files_loaded = items_inserted = 0

        store_id_to_fk: dict[str, int] = {
            _pad_store_id(r[1]): r[0]
            for r in conn.execute(
                text("SELECT id, store_id FROM stores WHERE chain_id=:chain_id"),
                {"chain_id": self.CHAIN_ID},
            ).fetchall()
        }
        store_results: list[dict] = []

        for sid in store_ids:
            entry = (self.fetch_price_entry(_pad_store_id(sid)) if delta
                     else self.fetch_pricefull_entry(_pad_store_id(sid)))
            if not entry:
                log.warning(f"  No {'Price' if delta else 'PriceFull'} found for store {sid} — skipping.")
                fk = store_id_to_fk.get(_pad_store_id(sid))
                if fk is not None:
                    store_results.append({
                        "chain_id": self.CHAIN_ID, "store_fk": fk, "store_id": _pad_store_id(sid),
                        "files_loaded": 0, "items_inserted": 0, "status": "no_file",
                    })
                else:
                    log.warning(f"  Store {sid}: not in stores table, omitting fetch_store_runs row.")
                continue

            files_attempted += 1
            log.info(f"  Store {sid}: downloading {entry['filename']}...")
            gz_path = RAW_DIR / (entry["filename"] + ".gz")

            try:
                self._download_gz(entry["url"], gz_path)
                data = self._decompress(gz_path)
                if not keep_raw:
                    gz_path.unlink(missing_ok=True)

                RAW_DIR.mkdir(parents=True, exist_ok=True)
                tmp_xml = RAW_DIR / (entry["filename"] + ".xml")
                tmp_xml.write_bytes(data)

                header, items = parse_price_file(tmp_xml)
                tmp_xml.unlink(missing_ok=True)

                chain_id     = header.get("chain_id") or self.CHAIN_ID
                sub_chain_id = header.get("sub_chain_id") or entry.get("sub_chain_id", "001")
                store_id_xml = header.get("store_id") or sid

                upsert_chain(conn, chain_id)
                store_fk = upsert_store(conn, chain_id, sub_chain_id, store_id_xml)

                if replace and not delta:
                    conn.execute(
                        text("DELETE FROM prices WHERE store_fk=:store_fk"),
                        {"store_fk": store_fk},
                    )

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

                raw_count = len(valid)
                first_seen: dict = {}
                diff_count = 0
                for item in valid:
                    code = item["item_code"]
                    if code in first_seen:
                        prev = first_seen[code]
                        if (item.get("item_price")            != prev.get("item_price") or
                                item.get("item_name")         != prev.get("item_name") or
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

                bulk_upsert_items(conn, valid)
                bulk_upsert_item_chain_names(conn, chain_id, valid)
                count = bulk_insert_prices(conn, store_fk, valid, replace=(replace and not delta))

                if delta and removed_codes:
                    for i in range(0, len(removed_codes), 1000):
                        batch = removed_codes[i:i + 1000]
                        del_params = {f"d{j}": code for j, code in enumerate(batch)}
                        del_params["store_fk"] = store_fk
                        conn.execute(text(
                            "DELETE FROM prices WHERE store_fk=:store_fk"
                            f" AND item_code IN ({','.join(f':d{j}' for j in range(len(batch)))})"
                        ), del_params)
                    log.info(f"    -> {len(removed_codes)} prices removed for store {sid}.")

                conn.commit()
                items_inserted += count
                files_loaded += 1
                log.info(f"    -> {count} items loaded for store {sid}.")
                store_results.append({
                    "chain_id": self.CHAIN_ID, "store_fk": store_fk, "store_id": _pad_store_id(sid),
                    "files_loaded": 1, "items_inserted": count, "status": "loaded",
                })

            except Exception as e:
                log.warning(f"  Store {sid} failed: {e}")
                gz_path.unlink(missing_ok=True)
                fk = store_id_to_fk.get(_pad_store_id(sid))
                if fk is not None:
                    store_results.append({
                        "chain_id": self.CHAIN_ID, "store_fk": fk, "store_id": _pad_store_id(sid),
                        "files_loaded": 0, "items_inserted": 0, "status": "error",
                    })
                else:
                    log.warning(f"  Store {sid}: not in stores table, omitting fetch_store_runs row.")

        fetch_run_id = conn.execute(text("""
            INSERT INTO fetch_runs
               (chain_id, run_at, files_attempted, files_loaded, items_inserted, status)
               VALUES (:chain_id, :run_at, :files_attempted, :files_loaded, :items_inserted, :status)
            RETURNING id
        """), {
            "chain_id":        self.CHAIN_ID,
            "run_at":          run_at,
            "files_attempted": files_attempted,
            "files_loaded":    files_loaded,
            "items_inserted":  items_inserted,
            "status":          "ok" if files_loaded == files_attempted else "partial",
        }).scalar()
        conn.commit()

        if store_results and fetch_run_id is not None:
            placeholders, params = [], {}
            for j, sr in enumerate(store_results):
                placeholders.append(
                    f"(:s{j}0,:s{j}1,:s{j}2,:s{j}3,:s{j}4,:s{j}5,:s{j}6,:s{j}7)"
                )
                params.update({
                    f"s{j}0": fetch_run_id,
                    f"s{j}1": sr["chain_id"],
                    f"s{j}2": sr["store_fk"],
                    f"s{j}3": sr["store_id"],
                    f"s{j}4": run_at,
                    f"s{j}5": sr["files_loaded"],
                    f"s{j}6": sr["items_inserted"],
                    f"s{j}7": sr["status"],
                })
            conn.execute(text(
                "INSERT INTO fetch_store_runs"
                " (fetch_run_id, chain_id, store_fk, store_id, run_at,"
                "  files_loaded, items_inserted, status)"
                f" VALUES {','.join(placeholders)}"
            ), params)
            conn.commit()

        return {
            "files_attempted": files_attempted,
            "files_loaded":    files_loaded,
            "items_inserted":  items_inserted,
        }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    city = sys.argv[1] if len(sys.argv) > 1 else "ירושלים"
    n    = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    keep = "--keep-raw" in sys.argv
    ShufersalScraper().run(city=city, n_stores=n, keep_raw=keep)
