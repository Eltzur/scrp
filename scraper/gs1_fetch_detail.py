"""Fetch per-product GS1 detail records into gs1.products.full_content (phase 2a).

The list endpoint used by gs1_fetch.py returns catalogue metadata only. The
per-product detail endpoint additionally returns Kashrut certification,
ingredients, coded allergens, a nutritional-values table, dimensions and
logistics data. This backfills that into the full_content JSONB column that the
SU10A-1 migration reserved.

SCOPE: only products already matched to an item (active GS1 row whose GTIN
appears in items). Detail data for products nobody sells is a wasted call.

WHAT GETS STORED: the complete response element — i.e. product_info PLUS
media_assets / private_data / multi_pack. So the JSON path is
    full_content -> 'product_info' -> 'Kashrut'
not full_content -> 'Kashrut'.
This is a deliberate superset of "store product_info": media_assets lists the
product's imagery, and discarding it would mean re-fetching all ~11.5k products
when the image work starts. Cheap to flatten later; expensive to re-fetch.

RATE LIMIT: GS1's API docs are a PDF we cannot text-extract, so no documented
limit was confirmed. Defaults to a conservative 3 req/sec, tunable with --rps.
Any X-RateLimit-* response headers are logged on the first call.

Dry run against a small sample (fetches, parses, writes NOTHING):
    python3 -m scraper.gs1_fetch_detail --dry-run --limit 15

Full backfill:
    python3 -m scraper.gs1_fetch_detail

Re-fetch products that already have full_content:
    python3 -m scraper.gs1_fetch_detail --refresh
"""
import json
import logging
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from sqlalchemy import text

from db.db import connect

log = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

_DETAIL_URL = "https://retailer.gs1ildigital.org/external/product/{product_code}.json?hq=1"

# Same closed-set active status the enrichment uses.
_ACTIVE_STATUS = "פעיל"

# Conservative default — no documented limit was confirmed (see module docstring).
_DEFAULT_RPS = 3.0

_HTTP_TIMEOUT = 45
_COMMIT_EVERY = 100
_MAX_ATTEMPTS = 2

# One active GS1 row per GTIN (newest wins, id breaks ties), restricted to GTINs
# that actually appear in items.
_TARGET_SQL = """
    WITH ranked AS (
        SELECT p.id, p.product_code, p.gtin, p.full_content,
               ROW_NUMBER() OVER (
                   PARTITION BY p.gtin
                   ORDER BY p.modification_timestamp DESC NULLS LAST, p.id DESC
               ) AS rn
        FROM gs1.products p
        WHERE p.product_status = :active AND p.gtin IS NOT NULL
    )
    SELECT DISTINCT r.id, r.product_code
    FROM ranked r
    JOIN items i ON i.item_code = r.gtin
    WHERE r.rn = 1
      AND (:refresh OR r.full_content IS NULL)
    ORDER BY r.product_code
"""

_STORE_SQL = text("""
    UPDATE gs1.products
    SET full_content = CAST(:payload AS jsonb),
        full_content_fetched_at = now()
    WHERE id = :id
""")


def _fetch_one(session: requests.Session, product_code: str, log_headers: bool = False):
    """Return the parsed detail element, or None on failure."""
    url = _DETAIL_URL.format(product_code=product_code)
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            r = session.get(url, timeout=_HTTP_TIMEOUT)
            if log_headers:
                rl = {k: v for k, v in r.headers.items() if "ratelimit" in k.lower()
                      or "retry-after" in k.lower()}
                log.info("rate-limit headers on first call: %s", rl or "(none advertised)")
            r.raise_for_status()
            data = r.json()
            # Same doubly-wrapped shape as the list endpoint: a list of one.
            if isinstance(data, list):
                if not data:
                    log.warning("%s: empty list response", product_code)
                    return None
                data = data[0]
            if not isinstance(data, dict) or "product_info" not in data:
                log.warning("%s: unexpected shape, keys=%s", product_code,
                            sorted(data) if isinstance(data, dict) else type(data).__name__)
                return None
            return data
        except Exception as exc:
            if attempt < _MAX_ATTEMPTS:
                time.sleep(1.0 * attempt)
                continue
            log.warning("%s: failed after %d attempts — %s", product_code, attempt, exc)
            return None


def run(dry_run: bool = False, limit: int | None = None, refresh: bool = False,
        rps: float = _DEFAULT_RPS) -> dict:
    """Backfill full_content. Returns {targets, fetched, failed, seconds}."""
    from scraper.gs1_fetch import _credentials

    user, password = _credentials()
    session = requests.Session()
    session.auth = (user, password)

    conn = connect()
    t0 = time.monotonic()
    fetched = failed = 0
    try:
        rows = conn.execute(text(_TARGET_SQL),
                            {"active": _ACTIVE_STATUS, "refresh": refresh}).mappings().all()
        targets = list(rows)
        if limit:
            targets = targets[:limit]

        log.info("targets: %s%s", f"{len(targets):,}",
                 f" (limited from {len(rows):,})" if limit else "")
        log.info("rate:    %.1f req/sec%s", rps, "  [DRY RUN — no writes]" if dry_run else "")
        if not targets:
            return {"targets": 0, "fetched": 0, "failed": 0, "seconds": 0.0}

        min_interval = 1.0 / rps if rps > 0 else 0.0
        next_at = time.monotonic()
        pending = 0

        for n, tgt in enumerate(targets, 1):
            now = time.monotonic()
            if now < next_at:
                time.sleep(next_at - now)
            next_at = time.monotonic() + min_interval

            data = _fetch_one(session, tgt["product_code"], log_headers=(n == 1))
            if data is None:
                failed += 1
                continue
            fetched += 1

            if not dry_run:
                conn.execute(_STORE_SQL, {
                    "payload": json.dumps(data, ensure_ascii=False),
                    "id": tgt["id"],
                })
                pending += 1
                if pending >= _COMMIT_EVERY:
                    conn.commit()
                    pending = 0

            if n % 200 == 0 or n == len(targets):
                rate = n / max(time.monotonic() - t0, 0.001)
                log.info("  %s/%s  ok=%s failed=%s  (%.1f/s)",
                         f"{n:,}", f"{len(targets):,}", f"{fetched:,}", f"{failed:,}", rate)

        if not dry_run and pending:
            conn.commit()

        elapsed = time.monotonic() - t0
        log.info("DONE — fetched=%s failed=%s of %s in %.0fs",
                 f"{fetched:,}", f"{failed:,}", f"{len(targets):,}", elapsed)
        return {"targets": len(targets), "fetched": fetched, "failed": failed,
                "seconds": elapsed}
    finally:
        conn.close()


def main():
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Fetch GS1 per-product detail into full_content")
    parser.add_argument("--dry-run", action="store_true", help="fetch and parse but write nothing")
    parser.add_argument("--limit", type=int, help="only process the first N targets")
    parser.add_argument("--refresh", action="store_true",
                        help="re-fetch products that already have full_content")
    parser.add_argument("--rps", type=float, default=_DEFAULT_RPS,
                        help=f"requests per second (default {_DEFAULT_RPS})")
    args = parser.parse_args()
    run(dry_run=args.dry_run, limit=args.limit, refresh=args.refresh, rps=args.rps)


if __name__ == "__main__":
    main()
