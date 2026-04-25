"""One-off script: recompute canonical item names in the database.

Run locally against SQLite:
    python -m scraper.run_canonical

Run against production PostgreSQL:
    DATABASE_URL=postgresql://... python -m scraper.run_canonical
"""
import logging
import sys

from db.db import connect, init_db
from scraper.canonical import update_canonical_names


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    conn = connect()
    init_db(conn)
    summary = update_canonical_names(conn)
    conn.close()
    print(f"\nDone. Processed: {summary['total_processed']}, Updated: {summary['total_updated']}")


if __name__ == "__main__":
    main()
