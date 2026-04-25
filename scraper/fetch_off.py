"""Enrich items table with OpenFoodFacts data (Hebrew names + product images).

For each barcode in the items table, queries:
  https://world.openfoodfacts.org/api/v0/product/{barcode}.json

Name source priority:
  'off_hebrew'  — Hebrew name found → update item_name + image
  'off_english' — No Hebrew, English found → keep item_name, update image only
  (unchanged)   — Not found or no useful data

Rate limit: 1 request/second (polite to OFF servers).
Commit every 100 rows, log progress every 500 barcodes.

Run locally:
    python -m scraper.fetch_off

Run against production:
    DATABASE_URL=postgresql://... python -m scraper.fetch_off
"""
import logging
import sys
import time
import io

import requests
from sqlalchemy import text

from db.db import connect, init_db

log = logging.getLogger(__name__)

_OFF_URL = "https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
_USER_AGENT = "IsraeliPriceComparison/1.0 (research; github.com/Eltzur/scrp)"


def _fetch_off(session: requests.Session, barcode: str) -> dict | None:
    """Query OFF for one barcode. Returns parsed product dict or None."""
    try:
        resp = session.get(
            _OFF_URL.format(barcode=barcode),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != 1:
            return None
        return data.get("product") or None
    except Exception as e:
        log.debug(f"OFF request failed for {barcode}: {e}")
        return None


def fetch_off(conn) -> dict:
    """
    Enrich items table with OpenFoodFacts data.
    Returns summary dict with keys: found_hebrew, found_english, not_found, images_added.
    """
    rows = conn.execute(text("SELECT item_code FROM items ORDER BY item_code")).fetchall()
    total = len(rows)
    log.info(f"Fetching OpenFoodFacts data for {total} barcodes...")

    session = requests.Session()
    session.headers["User-Agent"] = _USER_AGENT

    found_hebrew = found_english = not_found = images_added = 0
    pending = 0

    for i, (barcode,) in enumerate(rows, start=1):
        product = _fetch_off(session, barcode)
        time.sleep(1.0)

        if product is None:
            not_found += 1
        else:
            name_he  = (product.get("product_name_he") or "").strip()
            name_en  = (product.get("product_name_en") or product.get("product_name") or "").strip()
            image    = (product.get("image_front_url") or product.get("image_url") or "").strip() or None

            if name_he:
                conn.execute(text("""
                    UPDATE items
                    SET item_name         = :name,
                        product_image_url = COALESCE(:image, product_image_url),
                        name_source       = 'off_hebrew'
                    WHERE item_code = :code
                """), {"name": name_he, "image": image, "code": barcode})
                found_hebrew += 1
                if image:
                    images_added += 1
            elif name_en:
                conn.execute(text("""
                    UPDATE items
                    SET product_image_url = COALESCE(:image, product_image_url),
                        name_source       = 'off_english'
                    WHERE item_code = :code
                """), {"image": image, "code": barcode})
                found_english += 1
                if image:
                    images_added += 1
            else:
                not_found += 1

        pending += 1
        if pending >= 100:
            conn.commit()
            pending = 0

        if i % 500 == 0:
            log.info(
                f"  {i}/{total} — he:{found_hebrew} en:{found_english} "
                f"not_found:{not_found} images:{images_added}"
            )

    if pending:
        conn.commit()

    summary = {
        "found_hebrew":  found_hebrew,
        "found_english": found_english,
        "not_found":     not_found,
        "images_added":  images_added,
    }
    log.info(
        f"OFF enrichment complete: {found_hebrew} Hebrew names, "
        f"{found_english} English/image-only, {not_found} not found, "
        f"{images_added} images added."
    )
    return summary


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    conn = connect()
    init_db(conn)
    summary = fetch_off(conn)
    conn.close()
    print(f"\nDone: {summary}")


if __name__ == "__main__":
    main()
