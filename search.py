"""CLI: search items by name (Hebrew or English) and print prices.

Usage:
  python search.py <query> [options]

Options:
  --limit N          Max results (default 30)
  --compare          Group by barcode, show price per chain with delta
  --store-only ID    Filter to a single store_id
  --db FILE          Path to prices.db
"""
import io
import sys
import argparse
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from db.db import connect, DEFAULT_DB

_BASE_QUERY = """
SELECT
    i.item_code,
    i.item_name,
    i.manufacturer_name,
    i.unit_of_measure,
    p.item_price,
    p.unit_of_measure_price,
    p.price_update_date,
    c.chain_id,
    c.name        AS chain_name,
    s.store_id,
    s.store_name,
    s.city
FROM items i
JOIN prices  p ON p.item_code = i.item_code
JOIN stores  s ON s.id        = p.store_fk
JOIN chains  c ON c.chain_id  = s.chain_id
WHERE (i.item_name LIKE ? OR i.manufacturer_name LIKE ?)
"""


def _unit_str(r) -> str:
    if r["unit_of_measure_price"] and r["unit_of_measure"]:
        return f'{r["unit_of_measure_price"]:.2f}/{r["unit_of_measure"]}'
    return ""


def _store_label(r) -> str:
    return r["store_name"] if r["store_name"] else r["store_id"]


def _chain_label(r) -> str:
    return r["chain_name"] if r["chain_name"] else r["chain_id"]


def search_plain(rows, limit: int) -> None:
    """Default view: one row per store-item, sorted by price, limited."""
    # Deduplicate: cheapest price per (item_code, store_id)
    seen: dict[tuple, dict] = {}
    for r in rows:
        key = (r["item_code"], r["store_id"])
        if key not in seen or r["item_price"] < seen[key]["item_price"]:
            seen[key] = dict(r)

    results = sorted(seen.values(), key=lambda r: r["item_price"])[:limit]
    if not results:
        return

    print(f'{"CODE":<14} {"PRICE":>7}  {"UNIT PRICE":>14}  {"CHAIN":<12}  {"STORE":<28}  {"CITY":<15}  NAME')
    print("-" * 130)
    for r in results:
        print(
            f'{r["item_code"]:<14} '
            f'{r["item_price"]:>7.2f}  '
            f'{_unit_str(r):>14}  '
            f'{_chain_label(r):<12}  '
            f'{_store_label(r):<28}  '
            f'{(r["city"] or ""):<15}  '
            f'{r["item_name"]}'
        )
    print(f"\n{len(results)} result(s) shown (--limit {limit})")


def search_compare(rows, limit: int) -> None:
    """Compare mode: group by barcode, show cheapest price per chain, with delta."""
    # Best price per (item_code, chain_id)
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r["item_code"], r["chain_id"])
        if key not in best or r["item_price"] < best[key]["item_price"]:
            best[key] = dict(r)

    # Group by item_code
    by_item: dict[str, list] = defaultdict(list)
    for (code, _chain), r in best.items():
        by_item[code].append(r)

    # Only keep items available in 2+ chains, sort by min price
    multi = {code: sorted(entries, key=lambda r: r["item_price"])
             for code, entries in by_item.items()
             if len(entries) >= 2}
    # Sort groups by min price, then alphabetically for ties
    groups = sorted(multi.items(), key=lambda kv: kv[1][0]["item_price"])[:limit]

    if not groups:
        # Fallback: show all items (single-chain too), no delta
        all_groups = sorted(by_item.items(), key=lambda kv: kv[1][0]["item_price"])[:limit]
        print("(No items found in 2+ chains — showing all matches)\n")
        groups = all_groups

    print(f'{"CODE":<14}  NAME  /  CHAIN → PRICE  (delta vs cheapest)')
    print("-" * 90)
    shown = 0
    for code, entries in groups:
        cheapest = entries[0]["item_price"]
        name = entries[0]["item_name"]
        print(f'{code:<14}  {name}')
        for r in entries:
            delta = r["item_price"] - cheapest
            delta_str = f"+{delta:.2f}" if delta > 0 else "  —  "
            city = r["city"] or ""
            print(
                f'{"":16}  {_chain_label(r):<14}  '
                f'{r["item_price"]:>7.2f}  {delta_str}  '
                f'({_store_label(r)}, {city})'
            )
        shown += 1
    print(f"\n{shown} item(s) shown (--limit {limit})")


def search(query: str, db_path: Path, limit: int, compare: bool, store_only: str | None) -> None:
    if not db_path.exists():
        print(f"Database not found: {db_path}  (run scraper first)")
        sys.exit(1)

    conn = connect(db_path)
    pattern = f"%{query}%"

    sql = _BASE_QUERY
    params: list = [pattern, pattern]

    if store_only:
        sql += " AND s.store_id = ?"
        params.append(store_only)

    sql += " ORDER BY p.item_price"

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    if not rows:
        print(f'No results for "{query}"')
        return

    if compare:
        search_compare(rows, limit)
    else:
        search_plain(rows, limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search supermarket prices")
    parser.add_argument("query", help="Product name or manufacturer (Hebrew or English)")
    parser.add_argument("--limit", type=int, default=30, metavar="N", help="Max results (default 30)")
    parser.add_argument("--compare", action="store_true", help="Group by barcode, compare chains")
    parser.add_argument("--store-only", metavar="STORE_ID", help="Filter to one store")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, metavar="FILE", help="DB path")
    args = parser.parse_args()

    search(args.query, args.db, args.limit, args.compare, args.store_only)


if __name__ == "__main__":
    main()
