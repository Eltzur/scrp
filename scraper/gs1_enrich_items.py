"""Enrich items.item_name from the GS1 catalog, matched on GTIN.

Joins `items.item_code` to `gs1.products.gtin`, restricted to ACTIVE GS1
products, and writes the GS1 trade_item_description over the chain-derived name,
stamping name_source='gs1'.

GS1 is the highest-priority name source: it is the manufacturer's own
description, whereas the canonical name is a majority vote over retailer
strings. scraper/canonical.py is guarded to never overwrite a row this script
owns.

Where one GTIN matches several active GS1 rows, the most recently modified wins
(ties broken by id, so the choice is deterministic).

Deliberately does NOT touch product_image_url: the GS1 list response carries no
image data at all — `content` is empty in every row sampled — and the
per-product detail/image endpoints are untested. That is a separate, later task.

Dry run (default — reports, writes nothing):
    python3 -m scraper.gs1_enrich_items

Apply:
    python3 -m scraper.gs1_enrich_items --apply
"""
import logging
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

from db.db import connect

log = logging.getLogger(__name__)

# Load the repo-root .env ourselves — `source .env` sets shell variables but does
# NOT export them to a python3 child, so relying on the caller yields a bare
# "DATABASE_URL environment variable is not set!". Same reasoning as gs1_fetch.py.
# override=False so an already-exported value still wins.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

# GS1 product_status is a closed set of three Hebrew values:
#   פעיל (active) / מבוטל (cancelled) / נבדק (under review).
# Only active products may name a customer-facing item.
_ACTIVE_STATUS = "פעיל"  # 'פעיל'

_SAMPLE_SIZE = 20

# Numeric size / weight / pack-count token: digits followed by a Hebrew unit.
# Longest alternatives first so 'גרם' wins over 'גר' over 'ג'. Trailing group
# forces a boundary so the unit is not matched inside a longer word.
# Passed to Postgres as a bind parameter, not inlined, so it needs no SQL
# quote-doubling.
_SIZE_TOKEN_RE = r"""(\d+(?:[.,]\d+)?)\s*(גרם|גר|ק"ג|קג|קילו|מ"ל|מ״ל|מל|ליטר|ליט|יחידות|יח|ס"מ|סמ|מ"ג|מג|ג)(\s|$|[.,)`'"])"""

# Skip any row whose CHAIN name carries a size token the GS1 description drops
# (e.g. 'אגוזי קשיו טבעיים 220 גר' -> 'קשיו טבעי'). ~1,238 rows.
#
# Note this is a conservative choice about the *display string* only: the number
# still lives in items.quantity, which is populated on 99.9% of these rows, so
# the size is not actually lost to the app. Retained anyway because the name is
# what a user reads.
_SIZE_SAFE = """
    NOT EXISTS (
        SELECT 1
        FROM regexp_matches(i.item_name, :size_re, 'g') AS m
        WHERE position(m[1] IN r.trade_item_description) = 0
    )
"""

# One active GS1 row per GTIN: newest modification_timestamp wins, id breaks
# ties so repeated runs pick the same row. Rows with no description are excluded
# outright — writing a NULL over a real chain name would be a regression.
_RANKED_CTE = """
    WITH ranked AS (
        SELECT p.gtin,
               p.gln,
               p.trade_item_description,
               p.modification_timestamp,
               ROW_NUMBER() OVER (
                   PARTITION BY p.gtin
                   ORDER BY p.modification_timestamp DESC NULLS LAST, p.id DESC
               ) AS rn
        FROM gs1.products p
        WHERE p.product_status = :active
          AND p.gtin IS NOT NULL
          AND p.trade_item_description IS NOT NULL
    )
"""


def run(apply: bool = False, sample_size: int = _SAMPLE_SIZE) -> dict:
    """Compute the enrichment set, and write it when `apply` is set.

    Returns the stats mapping plus 'updated' — rows actually written (0 on a dry
    run). `sample_size=0` suppresses the before/after dump, which is just noise
    in a cron log.
    """
    conn = connect()
    try:
        params = {"active": _ACTIVE_STATUS, "size_re": _SIZE_TOKEN_RE}

        total_items = conn.execute(text("SELECT count(*) FROM items")).scalar()
        gs1_total = conn.execute(text("SELECT count(*) FROM gs1.products")).scalar()
        gs1_active = conn.execute(text(
            "SELECT count(*) FROM gs1.products WHERE product_status = :active"
        ), params).scalar()
        gs1_usable = conn.execute(text("""
            SELECT count(DISTINCT gtin) FROM gs1.products
            WHERE product_status = :active AND gtin IS NOT NULL
              AND trade_item_description IS NOT NULL
        """), params).scalar()

        log.info("items total                      : %s", f"{total_items:,}")
        log.info("gs1.products total               : %s", f"{gs1_total:,}")
        log.info("  active (%s)                  : %s", _ACTIVE_STATUS, f"{gs1_active:,}")
        log.info("  distinct usable GTINs          : %s", f"{gs1_usable:,}")

        stats = conn.execute(text(_RANKED_CTE + f"""
            SELECT count(*)                                                          AS matched,
                   count(*) FILTER (WHERE i.item_name IS DISTINCT FROM r.trade_item_description) AS name_would_change,
                   count(*) FILTER (WHERE i.item_name IS DISTINCT FROM r.trade_item_description
                                      AND {_SIZE_SAFE})                              AS will_update,
                   count(*) FILTER (WHERE i.item_name IS DISTINCT FROM r.trade_item_description
                                      AND NOT ({_SIZE_SAFE}))                        AS skipped_size_loss,
                   count(*) FILTER (WHERE i.name_source = 'gs1')                     AS already_gs1
            FROM items i
            JOIN ranked r ON r.gtin = i.item_code AND r.rn = 1
        """), params).mappings().one()

        matched = stats["matched"]
        pct = matched / total_items * 100 if total_items else 0
        log.info("")
        log.info("MATCHED items (item_code = active GS1 gtin) : %s  (%.2f%% of items)",
                 f"{matched:,}", pct)
        log.info("  of which the name would change           : %s", f"{stats['name_would_change']:,}")
        log.info("  SKIPPED — chain name has a size the GS1   : %s", f"{stats['skipped_size_loss']:,}")
        log.info("            name drops (guarded)")
        log.info("  WILL UPDATE                              : %s", f"{stats['will_update']:,}")
        log.info("  already name_source='gs1'                : %s", f"{stats['already_gs1']:,}")

        # RANDOM() rather than ORDER BY item_code: sorting by code groups the
        # sample under one GTIN prefix, i.e. one manufacturer, which makes the
        # sample look far more uniform than the catalogue actually is.
        if sample_size:
            samples = conn.execute(text(_RANKED_CTE + f"""
                SELECT i.item_code, i.name_source, r.gln,
                       i.item_name              AS old_name,
                       r.trade_item_description AS new_name
                FROM items i
                JOIN ranked r ON r.gtin = i.item_code AND r.rn = 1
                WHERE i.item_name IS DISTINCT FROM r.trade_item_description
                  AND {_SIZE_SAFE}
                ORDER BY RANDOM()
                LIMIT {sample_size}
            """), params).mappings().all()

            log.info("")
            log.info("--- random sample before/after (%d rows, %d distinct suppliers) ---",
                     len(samples), len({s["gln"] for s in samples}))
            for s in samples:
                log.info("  %s [src=%s gln=%s]", s["item_code"], s["name_source"], s["gln"])
                log.info("      old: %s", s["old_name"])
                log.info("      new: %s", s["new_name"])

        if not apply:
            log.info("")
            log.info("DRY RUN — nothing written. Re-run with --apply to commit.")
            return {**stats, "updated": 0}

        result = conn.execute(text(_RANKED_CTE + f"""
            UPDATE items i
            SET item_name = r.trade_item_description,
                name_source = 'gs1'
            FROM ranked r
            WHERE r.gtin = i.item_code
              AND r.rn = 1
              AND (i.item_name  IS DISTINCT FROM r.trade_item_description
                   OR i.name_source IS DISTINCT FROM 'gs1')
              AND {_SIZE_SAFE}
        """), params)
        conn.commit()
        log.info("")
        log.info("APPLIED — %s items updated.", f"{result.rowcount:,}")
        return {**stats, "updated": result.rowcount}
    finally:
        conn.close()


def main():
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Enrich items.item_name from the GS1 catalog")
    parser.add_argument("--apply", action="store_true",
                        help="write the changes (default: dry run, writes nothing)")
    args = parser.parse_args()
    run(apply=args.apply)


if __name__ == "__main__":
    main()
