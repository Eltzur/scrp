"""Pure query functions — shared by CLI (search.py) and API (api/routers/).

All functions take an open SQLAlchemy Connection and return plain dicts or lists.
No display logic, no HTTP concerns.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import yaml
from sqlalchemy import text, bindparam
from sqlalchemy.engine import Connection


_ACTIVE_STORES_YAML = Path(__file__).parent.parent / "scraper" / "active_stores.yaml"


# ---------------------------------------------------------------------------
# Barcode discovery
# ---------------------------------------------------------------------------

def _is_meaningful(token: str) -> bool:
    """Return False for tokens that add noise rather than signal to a search."""
    if len(token) < 2:
        return False
    if token.rstrip("%").isdigit():  # pure numbers and percentage values like "3%"
        return False
    return True


def build_word_clause(words: list[str], offset: int = 0, prefix: str = "") -> tuple[str, dict]:
    """
    SQL WHERE fragment requiring ALL meaningful words in item_name OR manufacturer_name.
    Skips tokens that are pure numbers, percentages, or shorter than 2 characters.
    Returns (sql_fragment, params_dict) using SQLAlchemy :named params.
    offset avoids param name collisions when the clause is used twice in a UNION.
    """
    p = f"{prefix}." if prefix else ""
    clauses: list[str] = []
    params: dict[str, str] = {}
    for i, w in enumerate(words, start=offset):
        if not _is_meaningful(w):
            continue
        pat = f"%{w}%"
        clauses.append(f"({p}item_name LIKE :w{i}n OR {p}manufacturer_name LIKE :w{i}m)")
        params[f"w{i}n"] = pat
        params[f"w{i}m"] = pat
    return " AND ".join(clauses), params


def find_barcodes(conn: Connection, words: list[str]) -> list[str]:
    """Return item_codes matching ALL meaningful words in items.item_name / manufacturer_name."""
    if not words:
        return []
    clause, params = build_word_clause(words)
    if not clause:
        return []  # all tokens were filtered out (numbers/percentages/single chars)
    rows = conn.execute(
        text(f"SELECT item_code FROM items WHERE {clause}"),
        params,
    ).mappings().all()
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
WHERE icn.item_code IN :codes
"""


def fetch_prices(
    conn: Connection,
    barcodes: list[str],
    city: list[str] | None = None,
    chain_id: list[str] | None = None,
    store_only: str | None = None,
) -> list[dict]:
    if not barcodes:
        return []
    sql = _PRICE_SQL
    params: dict = {"codes": tuple(barcodes)}
    expanding = [bindparam("codes", expanding=True)]
    if city:
        sql += " AND s.city_canonical IN :city"
        params["city"] = list(city)
        expanding.append(bindparam("city", expanding=True))
    if chain_id:
        sql += " AND c.chain_id IN :chain_id"
        params["chain_id"] = chain_id
        expanding.append(bindparam("chain_id", expanding=True))
    if store_only:
        sql += " AND s.store_id = :store_only"
        params["store_only"] = store_only
    sql += " ORDER BY p.item_price"
    stmt = text(sql).bindparams(*expanding)
    return [dict(r) for r in conn.execute(stmt, params).mappings().all()]


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
        prod["cheapest_price"]       = prod["quotes"][0]["price"]
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
            "chain_id":            r["chain_id"],
            "chain_name":          r["chain_name"],
            "store_id":            r["store_id"],
            "store_name":          r["store_name"],
            "city":                r["city"],
            "address":             r.get("address"),
            "price":               r["item_price"],
            "unit_price":          r["unit_of_measure_price"],
            "unit_of_measure":     r["unit_of_measure"],
            "updated_at":          r["price_update_date"],
            "delta_from_cheapest": 0.0,
        }
        products.append({
            "item_code":            r["item_code"],
            "canonical_name":       r["item_name"],
            "manufacturer":         r["manufacturer_name"],
            "unit_of_measure":      r["unit_of_measure"],
            "is_weighted":          bool(r["is_weighted"]),
            "names_per_chain":      dict(names_per_chain[r["item_code"]]),
            "quotes":               [quote],
            "cheapest_price":       r["item_price"],
            "most_expensive_price": r["item_price"],
            "chains_count":         1,
        })
    return products


# ---------------------------------------------------------------------------
# Catalog queries
# ---------------------------------------------------------------------------

def fetch_chains(conn: Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(text("""
        SELECT
            c.chain_id,
            c.name,
            COUNT(DISTINCT p.item_code) AS total_barcodes,
            COUNT(DISTINCT s.id)        AS total_stores_loaded
        FROM chains c
        LEFT JOIN stores s ON s.chain_id = c.chain_id
        LEFT JOIN prices p ON p.store_fk = s.id
        GROUP BY c.chain_id, c.name
        ORDER BY c.name
    """)).mappings().all()]


def fetch_stores(
    conn: Connection,
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
    params: dict = {}
    if chain_id:
        sql += " AND s.chain_id = :chain_id"
        params["chain_id"] = chain_id
    if city:
        sql += " AND s.city_canonical = :city"
        params["city"] = city
    sql += " ORDER BY c.name, s.store_id"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def fetch_cities(conn: Connection) -> list[dict]:
    """Cities that have actual price data, with coverage stats. Dialect-agnostic."""
    rows = conn.execute(text("""
        SELECT
            s.city_canonical,
            COUNT(DISTINCT s.chain_id) AS chain_count,
            COUNT(DISTINCT s.id)       AS store_count,
            COUNT(p.id)                AS price_count
        FROM stores s
        JOIN prices p ON p.store_fk = s.id
        WHERE s.city_canonical IS NOT NULL
        GROUP BY s.city_canonical
        ORDER BY s.city_canonical
    """)).mappings().all()

    # Fetch chain_ids per city separately (avoids GROUP_CONCAT vs STRING_AGG dialect split)
    chain_rows = conn.execute(text("""
        SELECT DISTINCT s.city_canonical, s.chain_id
        FROM stores s
        JOIN prices p ON p.store_fk = s.id
        WHERE s.city_canonical IS NOT NULL
    """)).mappings().all()

    city_chains: dict[str, list[str]] = {}
    for r in chain_rows:
        city_chains.setdefault(r["city_canonical"], []).append(r["chain_id"])

    return [
        {
            "city":        r["city_canonical"],
            "chain_count": r["chain_count"],
            "store_count": r["store_count"],
            "price_count": r["price_count"],
            "chain_ids":   city_chains.get(r["city_canonical"], []),
        }
        for r in rows
    ]


def fetch_stats(conn: Connection) -> dict:
    chains_count = conn.execute(text("SELECT COUNT(*) FROM chains")).scalar()
    stores_count = conn.execute(text(
        "SELECT COUNT(DISTINCT id) FROM stores WHERE id IN (SELECT store_fk FROM prices)"
    )).scalar()
    items_count  = conn.execute(text("SELECT COUNT(*) FROM items")).scalar()
    prices_count = conn.execute(text("SELECT COUNT(*) FROM prices")).scalar()

    last_fetch: dict[str, str | None] = {}
    for r in conn.execute(text("""
        SELECT c.name, fr.run_at
        FROM fetch_runs fr
        JOIN chains c ON c.chain_id = fr.chain_id
        WHERE fr.status IN ('ok', 'partial')
          AND fr.run_at = (
              SELECT MAX(fr2.run_at) FROM fetch_runs fr2
              WHERE fr2.chain_id = fr.chain_id
          )
        ORDER BY c.name
    """)).mappings().all():
        last_fetch[r["name"] or ""] = r["run_at"]

    return {
        "chains_count":         chains_count,
        "stores_count":         stores_count,
        "items_count":          items_count,
        "prices_count":         prices_count,
        "last_fetch_per_chain": last_fetch,
    }


def fetch_product(conn: Connection, barcode: str) -> list[dict]:
    """All price rows for a single barcode across all stores."""
    return fetch_prices(conn, [barcode])


def fetch_coverage(conn: Connection) -> dict:
    """
    Per-chain 72h coverage using fetch_store_runs.
    Denominator is the configured store count from active_stores.yaml — chains
    that never ran at all appear as 0/0/0% rather than being invisible.
    Sorted by coverage_pct ascending (worst first).
    """
    config = yaml.safe_load(_ACTIVE_STORES_YAML.read_text(encoding="utf-8"))
    configured: dict[str, int] = {
        entry["chain_id"]: len(entry.get("store_ids", []))
        for entry in config.get("chains", [])
    }

    all_chain_names: dict[str, str | None] = {
        r["chain_id"]: r["name"]
        for r in conn.execute(text("SELECT chain_id, name FROM chains")).mappings().all()
    }

    view_by_chain: dict[str, dict] = {
        r["chain_id"]: dict(r)
        for r in conn.execute(text("""
            SELECT
                v.chain_id,
                c.name          AS chain_name,
                v.stores_loaded_72h,
                v.stores_seen_72h
            FROM v_store_coverage_72h v
            JOIN chains c ON c.chain_id = v.chain_id
        """)).mappings().all()
    }

    result = []
    for chain_id, n_configured in configured.items():
        v = view_by_chain.get(chain_id)
        loaded = v["stores_loaded_72h"] if v else 0
        seen   = v["stores_seen_72h"]   if v else 0
        name   = (v["chain_name"] if v else None) or all_chain_names.get(chain_id)
        pct    = round(loaded / n_configured * 100, 1) if n_configured else 0.0
        result.append({
            "chain_id":          chain_id,
            "chain_name":        name,
            "stores_configured": n_configured,
            "stores_loaded_72h": loaded,
            "stores_seen_72h":   seen,
            "coverage_pct":      pct,
        })

    result.sort(key=lambda x: x["coverage_pct"])
    return {"chains": result}


def fetch_freshness(conn: Connection) -> dict:
    """
    Per-chain: most recent run where files_loaded > 0.
    oldest_last_loaded_at: earliest such timestamp across chains that have data.
    Chains with no successful load have last_loaded_at=None (sorted last).
    """
    rows = conn.execute(text("""
        SELECT
            c.name        AS chain_name,
            MAX(fr.run_at) AS last_loaded_at
        FROM chains c
        LEFT JOIN fetch_runs fr
               ON fr.chain_id = c.chain_id AND fr.files_loaded > 0
        GROUP BY c.chain_id, c.name
    """)).mappings().all()

    chains = [
        {"chain_name": r["chain_name"], "last_loaded_at": r["last_loaded_at"]}
        for r in rows
    ]
    # Newest data first; chains with no data (None) last.
    # Key: (1, date) for chains with data, (0, "") for None; reverse=True gives newest first, NULLs last.
    chains.sort(
        key=lambda x: (0 if x["last_loaded_at"] is None else 1, x["last_loaded_at"] or ""),
        reverse=True,
    )

    oldest = min((c["last_loaded_at"] for c in chains if c["last_loaded_at"]), default=None)

    return {"oldest_last_loaded_at": oldest, "chains": chains}
