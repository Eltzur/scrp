"""Pure query functions — shared by CLI (search.py) and API (api/routers/).

All functions take an open sqlite3.Connection and return plain dicts or lists.
No display logic, no HTTP concerns.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from scraper.city_names import normalize_city


# ---------------------------------------------------------------------------
# Barcode discovery
# ---------------------------------------------------------------------------

def build_word_clause(words: list[str], prefix: str = "") -> tuple[str, list]:
    """
    SQL WHERE fragment that requires ALL words to appear in item_name OR
    manufacturer_name (any order, substring match).
    Returns (fragment, params).
    """
    p = f"{prefix}." if prefix else ""
    clauses, params = [], []
    for w in words:
        pat = f"%{w}%"
        clauses.append(f"({p}item_name LIKE ? OR {p}manufacturer_name LIKE ?)")
        params.extend([pat, pat])
    return " AND ".join(clauses), params


def find_barcodes(conn: sqlite3.Connection, words: list[str]) -> list[str]:
    """Return item_codes matching ALL words across item_chain_names ∪ items."""
    if not words:
        return []
    clause, params = build_word_clause(words)
    rows = conn.execute(
        f"""
        SELECT DISTINCT item_code FROM item_chain_names WHERE {clause}
        UNION
        SELECT item_code FROM items WHERE {clause}
        """,
        params + params,
    ).fetchall()
    return [r["item_code"] for r in rows]


# ---------------------------------------------------------------------------
# Price rows (raw, one row per store × barcode)
# ---------------------------------------------------------------------------

_PRICE_SQL = """
SELECT
    icn.item_code,
    icn.item_name,
    icn.manufacturer_name,
    i.unit_of_measure,
    i.is_weighted,
    i.item_type,
    i.quantity,
    i.unit_qty,
    p.item_price,
    p.unit_of_measure_price,
    p.price_update_date,
    c.chain_id,
    c.name        AS chain_name,
    s.store_id,
    s.store_name,
    s.city,
    s.address
FROM item_chain_names icn
JOIN items   i ON i.item_code  = icn.item_code
JOIN prices  p ON p.item_code  = icn.item_code
JOIN stores  s ON s.id         = p.store_fk AND s.chain_id = icn.chain_id
JOIN chains  c ON c.chain_id   = icn.chain_id
WHERE icn.item_code IN ({ph})
"""


def fetch_prices(
    conn: sqlite3.Connection,
    barcodes: list[str],
    city: str | None = None,
    chain_id: str | None = None,
    store_only: str | None = None,
) -> list[dict]:
    if not barcodes:
        return []
    ph = ",".join("?" * len(barcodes))
    sql = _PRICE_SQL.format(ph=ph)
    params: list = list(barcodes)
    if city:
        sql += " AND s.city_norm = ?"
        params.append(normalize_city(city))
    if chain_id:
        sql += " AND c.chain_id = ?"
        params.append(chain_id)
    if store_only:
        sql += " AND s.store_id = ?"
        params.append(store_only)
    sql += " ORDER BY p.item_price"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ---------------------------------------------------------------------------
# Product grouping (used by both search and compare)
# ---------------------------------------------------------------------------

def group_by_product(rows: list[dict]) -> dict[str, dict]:
    """
    Group raw price rows by item_code.
    Returns dict: item_code → {
        "item_code", "canonical_name", "manufacturer", "unit_of_measure",
        "is_weighted", "names_per_chain": {chain_id: name},
        "quotes": [{chain_id, chain_name, store_id, store_name, city,
                    address, price, unit_price, unit_of_measure, updated_at}],
        "cheapest_price", "most_expensive_price", "chains_count"
    }
    """
    # Best price per (item_code, chain_id) — cheapest store per chain
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r["item_code"], r["chain_id"])
        if key not in best or r["item_price"] < best[key]["item_price"]:
            best[key] = r

    # Collect all per-chain names per barcode
    names_per_chain: dict[str, dict[str, str]] = defaultdict(dict)
    for r in rows:
        if r["item_name"]:
            names_per_chain[r["item_code"]][r["chain_id"]] = r["item_name"]

    # Build product groups
    by_item: dict[str, dict] = {}
    for (code, _chain), r in best.items():
        if code not in by_item:
            by_item[code] = {
                "item_code":        code,
                "canonical_name":   r["item_name"],
                "manufacturer":     r["manufacturer_name"],
                "unit_of_measure":  r["unit_of_measure"],
                "is_weighted":      bool(r["is_weighted"]),
                "names_per_chain":  dict(names_per_chain[code]),
                "quotes":           [],
            }
        by_item[code]["quotes"].append({
            "chain_id":        r["chain_id"],
            "chain_name":      r["chain_name"],
            "store_id":        r["store_id"],
            "store_name":      r["store_name"],
            "city":            r["city"],
            "address":         r.get("address"),
            "price":           r["item_price"],
            "unit_price":      r["unit_of_measure_price"],
            "unit_of_measure": r["unit_of_measure"],
            "updated_at":      r["price_update_date"],
        })

    # Sort quotes cheapest-first, compute deltas and summary stats
    for prod in by_item.values():
        prod["quotes"].sort(key=lambda q: q["price"])
        cheapest = prod["quotes"][0]["price"]
        for q in prod["quotes"]:
            q["delta_from_cheapest"] = round(q["price"] - cheapest, 4)
        prod["cheapest_price"]      = prod["quotes"][0]["price"]
        prod["most_expensive_price"] = prod["quotes"][-1]["price"]
        prod["chains_count"]         = len({q["chain_id"] for q in prod["quotes"]})

    return by_item


# ---------------------------------------------------------------------------
# Store-level grouping (one ProductWithPrices per store, no deduplication)
# ---------------------------------------------------------------------------

def group_by_store(rows: list[dict]) -> list[dict]:
    """
    Return one entry per (item_code, store) — no chain deduplication.
    Each entry is a ProductWithPrices-shaped dict with a single quote.
    """
    products = []
    names_per_chain: dict[str, dict[str, str]] = defaultdict(dict)
    for r in rows:
        if r["item_name"]:
            names_per_chain[r["item_code"]][r["chain_id"]] = r["item_name"]

    for r in rows:
        quote = {
            "chain_id":        r["chain_id"],
            "chain_name":      r["chain_name"],
            "store_id":        r["store_id"],
            "store_name":      r["store_name"],
            "city":            r["city"],
            "address":         r.get("address"),
            "price":           r["item_price"],
            "unit_price":      r["unit_of_measure_price"],
            "unit_of_measure": r["unit_of_measure"],
            "updated_at":      r["price_update_date"],
            "delta_from_cheapest": 0.0,
        }
        products.append({
            "item_code":          r["item_code"],
            "canonical_name":     r["item_name"],
            "manufacturer":       r["manufacturer_name"],
            "unit_of_measure":    r["unit_of_measure"],
            "is_weighted":        bool(r["is_weighted"]),
            "names_per_chain":    dict(names_per_chain[r["item_code"]]),
            "quotes":             [quote],
            "cheapest_price":     r["item_price"],
            "most_expensive_price": r["item_price"],
            "chains_count":       1,
        })
    return products


# ---------------------------------------------------------------------------
# Catalog queries
# ---------------------------------------------------------------------------

def fetch_chains(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("""
        SELECT
            c.chain_id,
            c.name,
            COUNT(DISTINCT p.item_code) AS total_barcodes,
            COUNT(DISTINCT s.id)        AS total_stores_loaded
        FROM chains c
        LEFT JOIN stores s ON s.chain_id = c.chain_id
        LEFT JOIN prices p ON p.store_fk = s.id
        GROUP BY c.chain_id
        ORDER BY c.name
    """).fetchall()]


def fetch_stores(
    conn: sqlite3.Connection,
    chain_id: str | None = None,
    city: str | None = None,
) -> list[dict]:
    sql = """
        SELECT s.store_id, s.chain_id, c.name AS chain_name,
               s.store_name, s.city, s.address
        FROM stores s
        JOIN chains c ON c.chain_id = s.chain_id
        WHERE 1=1
    """
    params: list = []
    if chain_id:
        sql += " AND s.chain_id = ?"
        params.append(chain_id)
    if city:
        sql += " AND s.city_norm = ?"
        params.append(normalize_city(city))
    sql += " ORDER BY c.name, s.store_id"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def fetch_cities(conn: sqlite3.Connection) -> list[dict]:
    """Cities that have actual price data, with coverage stats."""
    rows = conn.execute("""
        SELECT
            s.city,
            COUNT(DISTINCT s.chain_id)  AS chain_count,
            COUNT(DISTINCT s.id)        AS store_count,
            COUNT(p.id)                 AS price_count,
            GROUP_CONCAT(DISTINCT s.chain_id) AS chain_ids_csv
        FROM stores s
        JOIN prices p ON p.store_fk = s.id
        WHERE s.city IS NOT NULL
        GROUP BY s.city
        ORDER BY s.city
    """).fetchall()
    result = []
    for r in rows:
        result.append({
            "city":        r["city"],
            "chain_count": r["chain_count"],
            "store_count": r["store_count"],
            "price_count": r["price_count"],
            "chain_ids":   r["chain_ids_csv"].split(",") if r["chain_ids_csv"] else [],
        })
    return result


def fetch_stats(conn: sqlite3.Connection) -> dict:
    chains_count = conn.execute("SELECT COUNT(*) FROM chains").fetchone()[0]
    stores_count = conn.execute(
        "SELECT COUNT(DISTINCT id) FROM stores WHERE id IN (SELECT store_fk FROM prices)"
    ).fetchone()[0]
    items_count  = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    prices_count = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]

    last_fetch = {}
    for r in conn.execute("""
        SELECT c.name, fr.run_at
        FROM fetch_runs fr
        JOIN chains c ON c.chain_id = fr.chain_id
        WHERE fr.status IN ('ok', 'partial')
          AND fr.run_at = (
              SELECT MAX(fr2.run_at) FROM fetch_runs fr2
              WHERE fr2.chain_id = fr.chain_id
          )
        ORDER BY c.name
    """).fetchall():
        last_fetch[r["name"] or r[0]] = r["run_at"]

    return {
        "chains_count":        chains_count,
        "stores_count":        stores_count,
        "items_count":         items_count,
        "prices_count":        prices_count,
        "last_fetch_per_chain": last_fetch,
    }


def fetch_product(conn: sqlite3.Connection, barcode: str) -> list[dict]:
    """All price rows for a single barcode across all stores."""
    return fetch_prices(conn, [barcode])
