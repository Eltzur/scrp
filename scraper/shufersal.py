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
import gzip
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from lxml import html

from db.db import connect, init_db, upsert_chain, upsert_store, upsert_item, upsert_price, DEFAULT_DB
from parser.price_parser import parse_file as parse_price_file
from scraper.city_names import normalize_city, CITY_VARIANTS

log = logging.getLogger(__name__)

CHAIN_ID      = "7290027600007"
LISTING_BASE  = "http://prices.shufersal.co.il/FileObject/UpdateCategory"
REQUEST_DELAY = 0.5
RAW_DIR       = Path(__file__).parent.parent / "sample_data" / "raw"

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "Mozilla/5.0 (price-comparison-research/1.0)"

# City substrings to scan for in store names.
# Each entry: (canonical_city, [substrings_to_search])
_CITY_HINTS: list[tuple[str, list[str]]] = [
    (canonical, [canonical] + variants)
    for canonical, variants in CITY_VARIANTS.items()
]


# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------

_FILENAME_RE = re.compile(
    r"^[A-Za-z]+"       # file type prefix (PriceFull, Price, Promo…)
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
    Format is typically: 'NNN - BRAND CITY- STREET'
    We strip the trailing street segment (after the last '- ') before searching,
    so '12 - יש בני ברק- ירושלים' correctly yields 'בני ברק', not 'ירושלים'.
    """
    # Normalize non-breaking spaces (U+00A0) to regular spaces before matching
    branch_name = branch_name.replace("\u00a0", "")
    # Strip trailing street segment: "NNN - BRAND CITY- STREET"
    last_dash = branch_name.rfind("- ")
    if last_dash > 5:
        search_text = branch_name[:last_dash].strip()
    else:
        search_text = branch_name
    for canonical, hints in _CITY_HINTS:
        for hint in hints:
            if hint and hint in search_text:
                return canonical
    return None


# ---------------------------------------------------------------------------
# Listing page scraper (raw — returns ALL file types per page)
# ---------------------------------------------------------------------------

def _fetch_raw_page(page: int) -> list[dict]:
    """
    Fetch one listing page (catname ignored server-side).
    Returns all rows: {store_id, sub_chain_id, chain_id, filename, url,
                       updated_at, branch_name, file_type}.
    """
    url = f"{LISTING_BASE}?catname=PriceFull&page={page}&sort=Time&sortdir=DESC"
    resp = _SESSION.get(url, timeout=30)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)

    doc = html.fromstring(resp.text)   # resp.text is already UTF-8 decoded
    rows = []
    for a in doc.cssselect("a[href*='blob.core.windows.net']"):
        href = a.get("href", "")
        filename = href.split("?")[0].rsplit("/", 1)[-1]
        info = parse_filename(filename)
        if not info:
            continue

        file_type = re.match(r"^[A-Za-z]+", filename)
        file_type = file_type.group() if file_type else ""

        # Walk up to <tr>, collect all cell text
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
                # Branch name: "NNN - Hebrew text" pattern
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


# ---------------------------------------------------------------------------
# Store metadata from listing HTML
# ---------------------------------------------------------------------------

def load_stores_from_listing(conn, pages_to_scan: int = 20) -> dict[str, dict]:
    """
    Scan the first N pages of the listing to collect store metadata
    (ID, name, city) from the HTML branch column. Populates the stores table.
    Returns dict: store_id -> metadata.
    """
    upsert_chain(conn, CHAIN_ID)
    seen: dict[str, dict] = {}

    log.info(f"Collecting store metadata from listing (pages 1-{pages_to_scan})…")
    for page in range(1, pages_to_scan + 1):
        log.info(f"  Page {page}/{pages_to_scan}…")
        try:
            rows = _fetch_raw_page(page)
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
                (CHAIN_ID, row["sub_chain_id"], sid,
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
    log.info(f"  Collected {len(seen)} stores.")
    return seen


# ---------------------------------------------------------------------------
# PriceFull index builder (smart stop)
# ---------------------------------------------------------------------------

def build_pricefull_index(
    target_store_ids: set,
    start_page: int = 36,
) -> dict[str, dict]:
    """
    Scan pages starting at start_page for PriceFull files.
    Stops when all target stores are found or pages run out.
    Returns dict: store_id -> {filename, url, …}
    """
    index: dict[str, dict] = {}
    found: set[str] = set()

    log.info(f"Building PriceFull index (starting at page {start_page})…")
    for page in range(start_page, 101):
        log.info(f"  Scanning page {page}…")
        try:
            rows = _fetch_raw_page(page)
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
                index[sid] = row
                if sid in target_store_ids:
                    found.add(sid)

        if found >= target_store_ids:
            log.info(f"  All {len(target_store_ids)} target stores found on page {page}.")
            break

        # If we've gone through 20 pages of PriceFull territory without finishing, stop
        if page >= start_page + 25:
            log.warning(f"  Scanned 25 pages past start, stopping. Found: {found}")
            break

    return index


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _download_gz(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with _SESSION.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
    time.sleep(REQUEST_DELAY)
    return dest


def _decompress_to_bytes(gz_path: Path) -> bytes:
    with gzip.open(gz_path, "rb") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Price loader
# ---------------------------------------------------------------------------

def load_prices_for_stores(
    store_ids: list[str],
    conn,
    keep_raw: bool = False,
    pricefull_start_page: int = 36,
) -> dict:
    """Download and load PriceFull files for the given store_ids."""
    target = set(store_ids)
    index = build_pricefull_index(target, start_page=pricefull_start_page)

    run_at = datetime.now(timezone.utc).isoformat()
    files_attempted = files_loaded = items_inserted = 0

    for sid in store_ids:
        entry = index.get(sid)
        if not entry:
            log.warning(f"  No PriceFull found for store {sid} — skipping.")
            continue

        files_attempted += 1
        log.info(f"  Store {sid}: downloading {entry['filename']}…")
        gz_path = RAW_DIR / (entry["filename"] + ".gz")

        try:
            _download_gz(entry["url"], gz_path)
            data = _decompress_to_bytes(gz_path)
            if not keep_raw:
                gz_path.unlink(missing_ok=True)

            RAW_DIR.mkdir(parents=True, exist_ok=True)
            tmp_xml = RAW_DIR / (entry["filename"] + ".xml")
            tmp_xml.write_bytes(data)

            header, items = parse_price_file(tmp_xml)
            tmp_xml.unlink(missing_ok=True)

            chain_id     = header.get("chain_id") or CHAIN_ID
            sub_chain_id = header.get("sub_chain_id") or entry["sub_chain_id"]
            store_id_xml = header.get("store_id") or sid

            upsert_chain(conn, chain_id)
            store_fk = upsert_store(conn, chain_id, sub_chain_id, store_id_xml)

            count = 0
            for item in items:
                if not item["item_code"] or item["item_price"] is None:
                    continue
                upsert_item(conn, item)
                upsert_price(conn, store_fk, item)
                count += 1
                if count % 500 == 0:
                    conn.commit()

            conn.commit()
            items_inserted += count
            files_loaded += 1
            log.info(f"    -> {count} items loaded for store {sid}.")

        except Exception as e:
            log.warning(f"  Store {sid} failed: {e}")
            gz_path.unlink(missing_ok=True)

    conn.execute(
        """
        INSERT INTO fetch_runs
            (chain_id, run_at, files_attempted, files_loaded, items_inserted, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (CHAIN_ID, run_at, files_attempted, files_loaded, items_inserted,
         "ok" if files_loaded == files_attempted else "partial"),
    )
    conn.commit()

    return {
        "files_attempted": files_attempted,
        "files_loaded":    files_loaded,
        "items_inserted":  items_inserted,
    }


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run(city: str = "ירושלים", n_stores: int = 5, db_path=None, keep_raw: bool = False):
    """Load stores from listing HTML, pick N stores in city, load their PriceFull data."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db_path = db_path or DEFAULT_DB

    conn = connect(db_path)
    init_db(conn)

    # Scan enough pages to cover all Price files and most store IDs
    load_stores_from_listing(conn, pages_to_scan=18)

    city_norm = normalize_city(city)
    log.info(f"\nFinding stores with city_norm='{city_norm}'…")

    rows = conn.execute(
        "SELECT store_id, sub_chain_id, store_name FROM stores WHERE city_norm = ? ORDER BY store_id LIMIT ?",
        (city_norm, n_stores),
    ).fetchall()

    if not rows:
        sample = conn.execute(
            "SELECT DISTINCT city, city_norm FROM stores WHERE city IS NOT NULL ORDER BY city_norm LIMIT 15"
        ).fetchall()
        log.error(
            f"No stores found for '{city}' (norm='{city_norm}'). "
            f"Sample of available cities: {[(r['city'], r['city_norm']) for r in sample]}"
        )
        conn.close()
        return

    store_ids = [r["store_id"] for r in rows]
    for r in rows:
        log.info(f"  Store {r['store_id']}: {r['store_name']}")

    summary = load_prices_for_stores(store_ids, conn, keep_raw=keep_raw)
    conn.close()

    print(f"\n--- Done ---")
    print(f"Files attempted : {summary['files_attempted']}")
    print(f"Files loaded    : {summary['files_loaded']}")
    print(f"Items inserted  : {summary['items_inserted']}")


if __name__ == "__main__":
    import sys
    city  = sys.argv[1] if len(sys.argv) > 1 else "ירושלים"
    n     = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    keep  = "--keep-raw" in sys.argv
    run(city=city, n_stores=n, keep_raw=keep)
