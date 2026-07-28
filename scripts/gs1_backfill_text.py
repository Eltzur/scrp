"""One-off: apply gs1_fetch's text normalisation to already-ingested GS1 rows.

The SU10A-1 full sweep landed 22,549 rows *before* brandname /
trade_item_description / group_name were normalised, so historical rows carry
raw HTML entities ('Lord &amp; King', 'vegan&#039;s choice') and stray
whitespace, while anything ingested after the fix is clean. Leaving that split
in place would mean any GROUP BY or join on those columns silently sees two
populations.

This imports `_clean_text` and `_TEXT_COLUMNS` from scraper.gs1_fetch rather
than reimplementing them, so the backfill and the ongoing ingest can never
drift apart.

Idempotent: once clean, a re-run reports 0 rows needing change and writes
nothing. Only the three text columns are touched — fetched_at is deliberately
left alone, since this is not a fetch.

Dry run (default — reports what would change, writes nothing):
    python3 -m scripts.gs1_backfill_text

Apply:
    python3 -m scripts.gs1_backfill_text --apply
"""
import logging

from sqlalchemy import text

from db.db import connect
from scraper.gs1_fetch import _clean_text, _TEXT_COLUMNS

log = logging.getLogger(__name__)

_BATCH = 500


def main():
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Backfill GS1 text normalisation")
    parser.add_argument("--apply", action="store_true",
                        help="write the changes (default: dry run, writes nothing)")
    args = parser.parse_args()

    conn = connect()
    try:
        cols = ", ".join(_TEXT_COLUMNS)
        rows = conn.execute(text(f"SELECT id, {cols} FROM gs1.products")).mappings().all()
        log.info("scanned %d rows", len(rows))

        changed = []
        null_conversions = 0
        for r in rows:
            cleaned = {c: _clean_text(r[c]) for c in _TEXT_COLUMNS}
            if any(cleaned[c] != r[c] for c in _TEXT_COLUMNS):
                changed.append({"id": r["id"], **cleaned})
                # Blank-to-absent is worth calling out separately: it changes
                # what the column *means*, not just how it is formatted.
                if any(cleaned[c] is None and r[c] is not None for c in _TEXT_COLUMNS):
                    null_conversions += 1

        log.info("%d rows need normalisation (%d already clean)",
                 len(changed), len(rows) - len(changed))
        log.info("  of those, %d convert a blank/whitespace-only value to NULL",
                 null_conversions)

        for sample in changed[:5]:
            before = next(r for r in rows if r["id"] == sample["id"])
            for c in _TEXT_COLUMNS:
                if before[c] != sample[c]:
                    log.info("  id=%s %s: %r -> %r", sample["id"], c, before[c], sample[c])

        if not changed:
            log.info("nothing to do.")
            return

        if not args.apply:
            log.info("DRY RUN — nothing written. Re-run with --apply to commit.")
            return

        sets = ", ".join(f"{c} = :{c}" for c in _TEXT_COLUMNS)
        stmt = text(f"UPDATE gs1.products SET {sets} WHERE id = :id")
        for i in range(0, len(changed), _BATCH):
            batch = changed[i:i + _BATCH]
            conn.execute(stmt, batch)
            conn.commit()
            log.info("updated %d/%d", min(i + _BATCH, len(changed)), len(changed))

        log.info("done — %d rows normalised.", len(changed))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
