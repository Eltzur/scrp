"""Pure query functions — shared by CLI (search.py) and API (api/routers/).

All functions take an open SQLAlchemy Connection and return plain dicts or lists.
No display logic, no HTTP concerns.
"""
from __future__ import annotations

import re
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
    # A percentage is a product attribute (fat content, alcohol, cocoa), not
    # noise: "חלב 3%" must narrow to 3% milk. Only bare integers are noise.
    if token.endswith("%"):
        return True
    if token.isdigit():
        return False
    return True


def _like_escape(s: str) -> str:
    r"""Escape LIKE wildcards so a literal % or _ in a search word matches itself.

    Without this, now that "3%" survives _is_meaningful, the pattern "%3%%"
    would make the trailing % a wildcard — matching "300 גרם" and defeating the
    whole point of keeping the token. Paired with ESCAPE '\' on every LIKE.
    """
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
        pat = f"%{_like_escape(w)}%"
        clauses.append(
            f"({p}item_name LIKE :w{i}n ESCAPE '\\' "
            f"OR {p}manufacturer_name LIKE :w{i}m ESCAPE '\\')"
        )
        params[f"w{i}n"] = pat
        params[f"w{i}m"] = pat
    return " AND ".join(clauses), params


def find_barcodes_with_relevance(
    conn: Connection, words: list[str]
) -> tuple[list[str], dict[str, int]]:
    """Match item_codes AND score each one's relevance to the search.

    Returns (item_codes, {item_code: tier}). Tier is judged on the FIRST
    meaningful word only — that is the word the user led with, so it carries the
    intent; later words act as filters, which the WHERE clause already applies.

        0  item_name starts with the word      ("חלב 3%"        for "חלב")
        1  whole word elsewhere in item_name   ("משקה חלב סויה")
        2  substring anywhere in item_name     ("שוקולד במילוי חלבה" — mid-word)
        3  matched on manufacturer_name only; item_name lacks the word entirely

    Tier 1 uses a \\y regex word boundary rather than space-splitting, so a word
    followed by a comma or parenthesis still counts as a whole word.
    """
    if not words:
        return [], {}
    clause, params = build_word_clause(words)
    if not clause:
        return [], {}  # all tokens were filtered out (bare numbers / single chars)

    first = next((w for w in words if _is_meaningful(w)), None)
    if first is None:
        return [], {}

    esc = _like_escape(first)
    rx = re.escape(first)  # keeps a user-typed regex metacharacter literal
    params = {
        **params,
        # Tier 0 needs a trailing word boundary, NOT a bare LIKE 'word%':
        # 'חלב%' also matches חלבה (halva), so a halva snack outranked actual
        # milk for the query חלב. Caught in manual verification.
        "rel_start": rf"^{rx}\y",
        "rel_word": rf"\y{rx}\y",
        "rel_any": f"%{esc}%",
    }

    rows = conn.execute(text(f"""
        SELECT item_code,
               CASE
                   WHEN item_name ~ :rel_start              THEN 0
                   WHEN item_name ~ :rel_word               THEN 1
                   WHEN item_name LIKE :rel_any ESCAPE '\\' THEN 2
                   ELSE 3
               END AS tier
        FROM items
        WHERE {clause}
    """), params).mappings().all()

    return [r["item_code"] for r in rows], {r["item_code"]: r["tier"] for r in rows}


def find_barcodes(conn: Connection, words: list[str]) -> list[str]:
    """Return item_codes matching ALL meaningful words in items.item_name / manufacturer_name."""
    codes, _ = find_barcodes_with_relevance(conn, words)
    return codes


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

# City-filtered variant: starts from prices so Postgres can BitmapAnd on
# idx_prices_store_fk + idx_prices_item_code instead of doing 6K nested-loop
# index scans across all stores.  store_fks is a pre-fetched int[] array.
_PRICE_SQL_CITY = """
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
FROM prices p
JOIN stores  s   ON s.id           = p.store_fk
JOIN item_chain_names icn
                ON icn.item_code   = p.item_code
               AND icn.chain_id    = s.chain_id
JOIN items   i   ON i.item_code    = p.item_code
JOIN chains  c   ON c.chain_id     = s.chain_id
WHERE p.store_fk  = ANY(:store_fks)
  AND p.item_code = ANY(:codes)
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

    if city:
        # Pre-fetch the store PKs for the requested cities (fast bitmap scan on
        # idx_stores_city_canonical).  Passing both arrays as bound parameters
        # lets Postgres use BitmapAnd(idx_prices_store_fk, idx_prices_item_code),
        # which is ~4x faster than the default nested-loop plan.
        store_fks: list[int] = [
            r[0] for r in conn.execute(
                text("SELECT id FROM stores WHERE city_canonical = ANY(:city)"),
                {"city": list(city)},
            ).fetchall()
        ]
        if not store_fks:
            return []

        # Disable nested loops for this transaction so the planner uses
        # BitmapAnd rather than repeating 6K index scans across all stores.
        conn.execute(text("SET LOCAL enable_nestloop = off"))

        sql: str = _PRICE_SQL_CITY
        params: dict = {"store_fks": store_fks, "codes": list(barcodes)}
        if chain_id:
            sql += " AND s.chain_id = ANY(:chain_id)"
            params["chain_id"] = list(chain_id)
        if store_only:
            sql += " AND s.store_id = :store_only"
            params["store_only"] = store_only
        sql += " ORDER BY p.item_price"
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]

    # No city filter: original query with expandable IN clause.
    sql = _PRICE_SQL
    params = {"codes": tuple(barcodes)}
    expanding = [bindparam("codes", expanding=True)]
    if chain_id:
        sql += " AND c.chain_id IN :chain_id"
        params["chain_id"] = chain_id
        expanding.append(bindparam("chain_id", expanding=True))
    if store_only:
        sql += " AND s.store_id = :store_only"
        params["store_only"] = store_only
    sql += " ORDER BY p.item_price"
    return [dict(r) for r in conn.execute(text(sql).bindparams(*expanding), params).mappings().all()]


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
    """Cities from stores table only — no prices JOIN."""
    rows = conn.execute(text("""
        SELECT
            city_canonical,
            COUNT(DISTINCT chain_id) AS chain_count,
            COUNT(DISTINCT id)       AS store_count
        FROM stores
        WHERE city_canonical IS NOT NULL
        GROUP BY city_canonical
        ORDER BY city_canonical
    """)).mappings().all()

    # Fetch chain_ids per city separately (avoids GROUP_CONCAT vs STRING_AGG dialect split)
    chain_rows = conn.execute(text("""
        SELECT DISTINCT city_canonical, chain_id
        FROM stores
        WHERE city_canonical IS NOT NULL
    """)).mappings().all()

    city_chains: dict[str, list[str]] = {}
    for r in chain_rows:
        city_chains.setdefault(r["city_canonical"], []).append(r["chain_id"])

    return [
        {
            "city":        r["city_canonical"],
            "chain_count": r["chain_count"],
            "store_count": r["store_count"],
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


# ---------------------------------------------------------------------------
# Promos
# ---------------------------------------------------------------------------

def lookup_store_fk(conn: Connection, chain_id: str, store_id: str) -> int | None:
    """Return stores.id for (chain_id, store_id), or None if not found."""
    row = conn.execute(text("""
        SELECT id FROM stores
        WHERE chain_id = :chain_id AND store_id = :store_id
        LIMIT 1
    """), {"chain_id": chain_id, "store_id": store_id}).fetchone()
    return row[0] if row else None


def fetch_promos(conn: Connection, store_fk: int) -> list[dict]:
    """Return active promos for a store (promo_end >= NOW() or no end date)."""
    rows = conn.execute(text("""
        SELECT
            item_code, promo_id, promo_description, promo_type,
            allow_multiple_discounts, min_qty, reward_type,
            discount_rate, discount_price, min_purchase_amount,
            to_char(promo_start, 'YYYY-MM-DD"T"HH24:MI:SS') AS promo_start,
            to_char(promo_end,   'YYYY-MM-DD"T"HH24:MI:SS') AS promo_end
        FROM promos
        WHERE store_fk = :store_fk
          AND (promo_end >= NOW() OR promo_end IS NULL)
        ORDER BY item_code, promo_id
    """), {"store_fk": store_fk}).mappings().all()
    return [dict(r) for r in rows]


def fetch_promos_bulk(
    conn: Connection,
    pairs: list[tuple[str, str]],
) -> dict[str, list[dict]]:
    """Return active promos for many stores in one query.

    pairs: list of (chain_id, store_id).
    Returns dict keyed by "chain_id/store_id" → list of promo dicts.
    """
    if not pairs:
        return {}

    placeholders = []
    params: dict = {}
    for i, (chain_id, store_id) in enumerate(pairs):
        placeholders.append(f"(:c{i}, :s{i})")
        params[f"c{i}"] = chain_id
        params[f"s{i}"] = store_id

    rows = conn.execute(text(f"""
        SELECT
            s.chain_id, s.store_id,
            p.item_code, p.promo_id, p.promo_description, p.promo_type,
            p.allow_multiple_discounts, p.min_qty, p.reward_type,
            p.discount_rate, p.discount_price, p.min_purchase_amount,
            to_char(p.promo_start, 'YYYY-MM-DD"T"HH24:MI:SS') AS promo_start,
            to_char(p.promo_end,   'YYYY-MM-DD"T"HH24:MI:SS') AS promo_end,
            CASE
                -- Single-item discount: discount_price is the per-item price
                WHEN p.discount_price IS NOT NULL
                 AND COALESCE(p.min_qty, 1) <= 1
                 AND pr.item_price > 0
                 AND p.discount_price < pr.item_price
                THEN ROUND(((pr.item_price - p.discount_price)
                             / pr.item_price * 100)::numeric, 1)
                -- Bundle deal: discount_price is the total for min_qty items
                WHEN p.discount_price IS NOT NULL
                 AND p.min_qty > 1
                 AND pr.item_price > 0
                 AND (p.discount_price / p.min_qty) < pr.item_price
                THEN ROUND(((pr.item_price - (p.discount_price / p.min_qty))
                             / pr.item_price * 100)::numeric, 1)
                ELSE NULL
            END AS discount_pct
        FROM promos p
        JOIN stores s ON s.id = p.store_fk
        LEFT JOIN prices pr ON pr.store_fk = p.store_fk AND pr.item_code = p.item_code
        WHERE (s.chain_id, s.store_id) IN ({', '.join(placeholders)})
          AND (p.promo_end >= NOW() OR p.promo_end IS NULL)
        ORDER BY s.chain_id, s.store_id, p.item_code
    """), params).mappings().all()

    result: dict[str, list[dict]] = {}
    for row in rows:
        key = f"{row['chain_id']}/{row['store_id']}"
        promo = {k: v for k, v in row.items() if k not in ("chain_id", "store_id")}
        result.setdefault(key, []).append(promo)
    return result


_ONLINE_STORE_FILTER = """
    AND NOT (s.store_name ILIKE '%online%'
          OR s.store_name ILIKE '%אונליין%'
          OR s.store_name ILIKE '%אינטרנט%')
""".strip()


def fetch_today_promos(
    conn: Connection,
    limit: int = 200,
    city: str | None = None,
    chain_id: str | None = None,
) -> list[dict]:
    """Return today's hot deals — deduplicated by (item_code, chain_id).

    Caps discount_pct at 99, excludes orphaned rows and online/virtual stores.
    """
    params: dict = {"limit": limit}
    city_clause = ""
    chain_clause = ""
    if city:
        city_clause = "AND s.city_canonical = :city"
        params["city"] = city
    if chain_id:
        chain_clause = "AND s.chain_id = :chain_id"
        params["chain_id"] = chain_id

    rows = conn.execute(text(f"""
        WITH promo_data AS (
            SELECT
                p.item_code,
                p.promo_description,
                p.reward_type,
                p.discount_price,
                p.min_qty,
                to_char(p.promo_end, 'YYYY-MM-DD"T"HH24:MI:SS') AS promo_end,
                s.chain_id,
                c.name           AS chain_name,
                s.store_name,
                s.city_canonical AS city,
                pr.item_price,
                CASE
                    WHEN p.discount_price IS NOT NULL
                     AND COALESCE(p.min_qty, 1) <= 1
                     AND pr.item_price > 0
                     AND p.discount_price < pr.item_price
                    THEN LEAST(ROUND(((pr.item_price - p.discount_price)
                                      / pr.item_price * 100)::numeric, 1), 99.0)
                    WHEN p.discount_price IS NOT NULL
                     AND p.min_qty > 1
                     AND pr.item_price > 0
                     AND (p.discount_price / p.min_qty) < pr.item_price
                    THEN LEAST(ROUND(((pr.item_price - (p.discount_price / p.min_qty))
                                      / pr.item_price * 100)::numeric, 1), 99.0)
                    ELSE NULL
                END AS discount_pct
            FROM promos p
            JOIN stores s ON s.id = p.store_fk
            JOIN chains c ON c.chain_id = s.chain_id
            LEFT JOIN prices pr ON pr.store_fk = p.store_fk AND pr.item_code = p.item_code
            WHERE (p.promo_end >= NOW() OR p.promo_end IS NULL)
              AND c.name IS NOT NULL
              {_ONLINE_STORE_FILTER}
              {city_clause}
              {chain_clause}
        ),
        deduped AS (
            SELECT DISTINCT ON (item_code, chain_id) *
            FROM promo_data
            WHERE (discount_pct >= 10 AND discount_pct <= 99)
               OR (reward_type = 1 AND ROUND(COALESCE(min_qty, 0)::numeric) = 2)
            ORDER BY item_code, chain_id, discount_pct DESC NULLS LAST
        )
        SELECT *
        FROM deduped
        ORDER BY discount_pct DESC NULLS LAST
        LIMIT :limit
    """), params).mappings().all()
    return [dict(r) for r in rows]


def fetch_promo_cities(conn: Connection) -> list[str]:
    """Distinct cities that have active qualifying promos."""
    rows = conn.execute(text(f"""
        SELECT DISTINCT s.city_canonical
        FROM promos p
        JOIN stores s ON s.id = p.store_fk
        JOIN chains c ON c.chain_id = s.chain_id
        LEFT JOIN prices pr ON pr.store_fk = p.store_fk AND pr.item_code = p.item_code
        WHERE (p.promo_end >= NOW() OR p.promo_end IS NULL)
          AND c.name IS NOT NULL
          AND s.city_canonical IS NOT NULL
          {_ONLINE_STORE_FILTER}
        ORDER BY s.city_canonical
    """)).fetchall()
    return [r[0] for r in rows]


def fetch_promo_chains(conn: Connection) -> list[dict]:
    """Distinct chains that have active qualifying promos."""
    rows = conn.execute(text(f"""
        SELECT DISTINCT s.chain_id, c.name
        FROM promos p
        JOIN stores s ON s.id = p.store_fk
        JOIN chains c ON c.chain_id = s.chain_id
        WHERE (p.promo_end >= NOW() OR p.promo_end IS NULL)
          AND c.name IS NOT NULL
          {_ONLINE_STORE_FILTER}
        ORDER BY c.name
    """)).mappings().all()
    return [dict(r) for r in rows]
