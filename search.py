"""CLI: search items by name (Hebrew or English) and compare prices across chains.

Usage:
  python -m search <query> [options]

Options:
  --compare          Group by barcode, compare chains (default when 2+ chains loaded)
  --limit N          Max products shown (default 30)
  --city CITY        Filter to stores in this city (Hebrew or English)
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
from scraper.city_names import normalize_city


# ---------------------------------------------------------------------------
# Barcode discovery — barcode-first, name-second architecture
# ---------------------------------------------------------------------------

def _word_clause(words: list[str], table_alias: str = "") -> tuple[str, list]:
    """
    Build SQL WHERE fragment requiring ALL words match (any order, any field).
    Returns (sql_fragment, params_list).
    Each word: (item_name LIKE ? OR manufacturer_name LIKE ?)
    """
    prefix = f"{table_alias}." if table_alias else ""
    clauses = []
    params = []
    for w in words:
        pat = f"%{w}%"
        clauses.append(f"({prefix}item_name LIKE ? OR {prefix}manufacturer_name LIKE ?)")
        params.extend([pat, pat])
    return " AND ".join(clauses), params


def _find_barcodes(conn, words: list[str]) -> list[str]:
    """
    Return all item_codes whose name matches ALL query words in ANY order.
    Searches item_chain_names first (per-chain names), then items (canonical).
    UNION deduplicates.
    """
    if not words:
        return []

    clause, params = _word_clause(words)

    sql = f"""
        SELECT DISTINCT item_code FROM item_chain_names
        WHERE {clause}
        UNION
        SELECT item_code FROM items
        WHERE {clause}
    """
    rows = conn.execute(sql, params + params).fetchall()
    return [r["item_code"] for r in rows]


# ---------------------------------------------------------------------------
# Price fetching
# ---------------------------------------------------------------------------

_PRICE_QUERY = """
SELECT
    icn.item_code,
    icn.item_name,
    icn.manufacturer_name,
    i.unit_of_measure,
    p.item_price,
    p.unit_of_measure_price,
    p.price_update_date,
    c.chain_id,
    c.name        AS chain_name,
    s.store_id,
    s.store_name,
    s.city
FROM item_chain_names icn
JOIN items   i ON i.item_code  = icn.item_code
JOIN prices  p ON p.item_code  = icn.item_code
JOIN stores  s ON s.id         = p.store_fk AND s.chain_id = icn.chain_id
JOIN chains  c ON c.chain_id   = icn.chain_id
WHERE icn.item_code IN ({placeholders})
"""


def _fetch_prices(conn, barcodes: list[str], city: str | None, store_only: str | None) -> list:
    if not barcodes:
        return []

    placeholders = ",".join("?" * len(barcodes))
    sql = _PRICE_QUERY.format(placeholders=placeholders)
    params: list = list(barcodes)

    if city:
        city_norm = normalize_city(city)
        sql += " AND s.city_norm = ?"
        params.append(city_norm)

    if store_only:
        sql += " AND s.store_id = ?"
        params.append(store_only)

    sql += " ORDER BY p.item_price"
    return conn.execute(sql, params).fetchall()


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _unit_str(r) -> str:
    if r["unit_of_measure_price"] and r["unit_of_measure"]:
        return f'{r["unit_of_measure_price"]:.2f}/{r["unit_of_measure"]}'
    return ""


def _store_label(r) -> str:
    return r["store_name"] if r["store_name"] else r["store_id"]


def _chain_label(r) -> str:
    return r["chain_name"] if r["chain_name"] else r["chain_id"]


# ---------------------------------------------------------------------------
# Plain view
# ---------------------------------------------------------------------------

def search_plain(rows: list, limit: int) -> None:
    # Cheapest price per (item_code, store_id)
    seen: dict[tuple, dict] = {}
    for r in rows:
        key = (r["item_code"], r["store_id"])
        if key not in seen or r["item_price"] < seen[key]["item_price"]:
            seen[key] = dict(r)

    results = sorted(seen.values(), key=lambda r: r["item_price"])[:limit]
    if not results:
        print("No results.")
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


# ---------------------------------------------------------------------------
# Compare view
# ---------------------------------------------------------------------------

def search_compare(rows: list, limit: int) -> None:
    # Best price per (item_code, chain_id)
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r["item_code"], r["chain_id"])
        if key not in best or r["item_price"] < best[key]["item_price"]:
            best[key] = dict(r)

    # Group by item_code → list of chain entries sorted cheapest first
    by_item: dict[str, list] = defaultdict(list)
    for (code, _), r in best.items():
        by_item[code].append(r)
    for entries in by_item.values():
        entries.sort(key=lambda r: r["item_price"])

    multi  = {c: e for c, e in by_item.items() if len(e) >= 2}
    single = {c: e for c, e in by_item.items() if len(e) == 1}

    total   = len(by_item)
    n_multi = len(multi)
    print(f"Found {total} product(s). {n_multi} available in 2+ chains.\n")

    if not by_item:
        print("No results.")
        return

    shown = 0
    groups = (
        sorted(multi.items(),  key=lambda kv: kv[1][0]["item_price"]) +
        sorted(single.items(), key=lambda kv: kv[1][0]["item_price"])
    )

    print(f'{"CODE":<14}  NAME  /  CHAIN  →  PRICE  (vs cheapest)')
    print("-" * 95)

    for code, entries in groups[:limit]:
        cheapest   = entries[0]["item_price"]
        name       = entries[0]["item_name"] or code
        n_chains   = len(entries)
        badge      = f"[{n_chains} chains]" if n_chains >= 2 else f"[{_chain_label(entries[0])} only]"
        print(f'{code:<14}  {name}  {badge}')
        for r in entries:
            delta     = r["item_price"] - cheapest
            delta_str = f"+{delta:.2f}" if delta > 0 else "cheapest"
            city      = r["city"] or ""
            print(
                f'{"":16}  {_chain_label(r):<14}  '
                f'{r["item_price"]:>7.2f}  ({delta_str})  '
                f'{_store_label(r)}, {city}'
            )
        shown += 1

    if shown < total:
        remaining = total - shown
        print(f"\n  ... {remaining} more product(s) not shown (increase --limit)")
    print(f"\n{shown} product(s) shown.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def search(
    query: str,
    db_path: Path,
    limit: int,
    compare: bool,
    city: str | None,
    store_only: str | None,
) -> None:
    if not db_path.exists():
        print(f"Database not found: {db_path}  (run scraper first)")
        sys.exit(1)

    if store_only and compare:
        print("Note: --store-only + --compare is a single store; showing plain output instead.\n")
        compare = False

    words = query.split()
    conn  = connect(db_path)

    barcodes = _find_barcodes(conn, words)
    if not barcodes:
        print(f'No results for "{query}"')
        conn.close()
        return

    rows = _fetch_prices(conn, barcodes, city, store_only)
    conn.close()

    if not rows:
        scope = f" in city '{city}'" if city else ""
        scope += f" store '{store_only}'" if store_only else ""
        print(f'Barcodes matched but no prices found{scope}.')
        return

    if compare:
        search_compare(rows, limit)
    else:
        search_plain(rows, limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search supermarket prices")
    parser.add_argument("query",
        help="Product name or manufacturer (Hebrew or English, multi-word AND)")
    parser.add_argument("--compare", action="store_true",
        help="Group by barcode, compare chains side-by-side")
    parser.add_argument("--limit", type=int, default=30, metavar="N",
        help="Max products shown (default 30)")
    parser.add_argument("--city", metavar="CITY",
        help="Filter to stores in this city")
    parser.add_argument("--store-only", metavar="STORE_ID",
        help="Filter to one store (disables --compare)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, metavar="FILE",
        help="Path to prices.db")
    args = parser.parse_args()

    search(args.query, args.db, args.limit, args.compare, args.city, args.store_only)


if __name__ == "__main__":
    main()
