"""CLI: search items by name (Hebrew or English) and print prices."""
import io
import sys
import sqlite3
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from db.db import connect, DEFAULT_DB


QUERY = """
SELECT
    i.item_code,
    i.item_name,
    i.manufacturer_name,
    i.unit_of_measure,
    p.item_price,
    p.unit_of_measure_price,
    p.price_update_date,
    c.chain_id,
    c.name   AS chain_name,
    s.store_id
FROM items i
JOIN prices  p ON p.item_code = i.item_code
JOIN stores  s ON s.id        = p.store_fk
JOIN chains  c ON c.chain_id  = s.chain_id
WHERE i.item_name LIKE ? OR i.manufacturer_name LIKE ?
ORDER BY p.item_price
"""


def search(query: str, db_path: Path = DEFAULT_DB) -> None:
    if not db_path.exists():
        print(f"Database not found: {db_path}  (run load.py first)")
        sys.exit(1)

    conn = connect(db_path)
    pattern = f"%{query}%"
    rows = conn.execute(QUERY, (pattern, pattern)).fetchall()
    conn.close()

    if not rows:
        print(f'No results for "{query}"')
        return

    print(f'{"CODE":<14} {"PRICE":>7}  {"UNIT PRICE":>14}  {"UPDATED":<17}  {"CHAIN":<15}  {"STORE":<6}  NAME')
    print("-" * 115)
    for r in rows:
        chain_label = r["chain_name"] if r["chain_name"] else r["chain_id"]
        unit = (
            f'{r["unit_of_measure_price"]:.2f}/{r["unit_of_measure"]}'
            if r["unit_of_measure_price"] else ""
        )
        print(
            f'{r["item_code"]:<14} '
            f'{r["item_price"]:>7.2f}  '
            f'{unit:>14}  '
            f'{(r["price_update_date"] or ""):<17}  '
            f'{chain_label:<15}  '
            f'{r["store_id"]:<6}  '
            f'{r["item_name"]}'
        )
    print(f"\n{len(rows)} result(s)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python search.py <query> [db_file]")
        sys.exit(1)
    q  = sys.argv[1]
    db = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_DB
    search(q, db)
