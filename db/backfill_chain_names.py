"""One-time backfill: populate item_chain_names from existing prices data.

Since items has only one canonical name per barcode, shared barcodes get the
same name for both chains. Per-chain names will be written correctly on the
next scraper run.
"""
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
from db.db import connect, init_db, DEFAULT_DB


def backfill(db_path: Path = DEFAULT_DB) -> None:
    conn = connect(db_path)
    init_db(conn)  # creates item_chain_names table if missing

    before = conn.execute("SELECT COUNT(*) FROM item_chain_names").fetchone()[0]

    conn.execute("""
        INSERT OR IGNORE INTO item_chain_names (item_code, chain_id, item_name, manufacturer_name)
        SELECT DISTINCT p.item_code, s.chain_id, i.item_name, i.manufacturer_name
        FROM prices p
        JOIN stores s ON s.id        = p.store_fk
        JOIN items  i ON i.item_code = p.item_code
    """)
    conn.commit()

    after = conn.execute("SELECT COUNT(*) FROM item_chain_names").fetchone()[0]

    # Per-chain breakdown
    rows = conn.execute("""
        SELECT c.name, icn.chain_id, COUNT(*) as n
        FROM item_chain_names icn
        JOIN chains c ON c.chain_id = icn.chain_id
        GROUP BY icn.chain_id
    """).fetchall()

    print(f"item_chain_names: {before} rows before → {after} rows after backfill")
    for r in rows:
        label = r["name"] if r["name"] else r["chain_id"]
        print(f"  {label}: {r['n']:,} rows")

    conn.close()


if __name__ == "__main__":
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    backfill(db)
