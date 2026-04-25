"""Enrich items table with OpenFoodFacts data (Hebrew names + product images).

For each barcode, queries two sources in order:
  1. https://world.openfoodfacts.org/api/v0/product/{barcode}.json
  2. https://il.openfoodfacts.org/api/v0/product/{barcode}.json (Israeli mirror, better Hebrew)

Best result wins: Hebrew name from either source takes priority.

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

_OFF_WORLD = "https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
_OFF_IL    = "https://il.openfoodfacts.org/api/v0/product/{barcode}.json"
_USER_AGENT = "IsraeliPriceComparison/1.0 (research; github.com/Eltzur/scrp)"


def _query(session: requests.Session, url: str) -> dict | None:
    """Fetch one OFF URL. Returns product dict or None."""
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != 1:
            return None
        return data.get("product") or None
    except Exception as e:
        log.debug(f"OFF request failed ({url}): {e}")
        return None


def _fetch_off(session: requests.Session, barcode: str, skip_il: bool = False) -> dict | None:
    """
    Query world then (optionally) IL mirror. Merge results, preferring Hebrew name.
    Returns a synthetic product dict with the best available data, or None if not found.
    """
    world = _query(session, _OFF_WORLD.format(barcode=barcode))
    time.sleep(0.5)
    if skip_il:
        il = None
    else:
        il = _query(session, _OFF_IL.format(barcode=barcode))
        time.sleep(0.5)

    if not world and not il:
        return None

    def _get(p, *keys):
        for k in keys:
            v = (p or {}).get(k, "")
            if v and str(v).strip():
                return str(v).strip()
        return ""

    # Prefer Hebrew name from either source
    name_he = _get(world, "product_name_he") or _get(il, "product_name_he")
    name_en = (
        _get(world, "product_name_en", "product_name") or
        _get(il,    "product_name_en", "product_name")
    )
    image = (
        _get(world, "image_front_url", "image_url") or
        _get(il,    "image_front_url", "image_url")
    )

    return {"product_name_he": name_he, "product_name_en": name_en, "image_front_url": image}


def fetch_off(
    conn,
    limit: int | None = None,
    offset: int = 0,
    israel_only: bool = False,
    skip_il: bool = False,
) -> dict:
    """
    Enrich items table with OpenFoodFacts data.
    Returns summary dict with keys: found_hebrew, found_english, not_found, images_added.
    """
    rows = conn.execute(text("SELECT item_code FROM items ORDER BY RANDOM()")).fetchall()
    if israel_only:
        rows = [r for r in rows if str(r[0]).startswith("729")]
    if offset:
        rows = rows[offset:]
    if limit is not None:
        rows = rows[:limit]
    total = len(rows)
    flags = []
    if israel_only:
        flags.append("israel-only")
    if offset:
        flags.append(f"offset={offset}")
    if limit:
        flags.append(f"limit={limit}")
    if skip_il:
        flags.append("skip-il-mirror")
    suffix = f" ({', '.join(flags)})" if flags else ""
    log.info(f"Fetching OpenFoodFacts data for {total} barcodes{suffix}...")

    session = requests.Session()
    session.headers["User-Agent"] = _USER_AGENT

    found_hebrew = found_english = not_found = images_added = 0
    pending = 0

    for i, (barcode,) in enumerate(rows, start=1):
        product = _fetch_off(session, barcode, skip_il=skip_il)

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
    import argparse
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    parser = argparse.ArgumentParser(description="Enrich items with OpenFoodFacts data")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Process only N barcodes after offset (default: all)")
    parser.add_argument("--offset", type=int, default=0, metavar="N",
                        help="Skip the first N barcodes before starting (default: 0)")
    parser.add_argument("--israel-only", action="store_true",
                        help="Only process barcodes starting with '729' (Israeli EAN prefix)")
    parser.add_argument("--skip-il-mirror", action="store_true",
                        help="Skip the IL mirror query, use world.openfoodfacts.org only")
    args = parser.parse_args()

    conn = connect()
    init_db(conn)
    summary = fetch_off(
        conn,
        limit=args.limit,
        offset=args.offset,
        israel_only=args.israel_only,
        skip_il=args.skip_il_mirror,
    )
    conn.close()
    print(f"\nDone: {summary}")


if __name__ == "__main__":
    main()
