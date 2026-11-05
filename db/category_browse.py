"""Category browse pages (SU11A-67, design docs/catalog/su11a66_categories_browse_design.md).

GET /categories/browse-tree and GET /categories/{id}/items (api/routers/categories.py).

VISIBILITY (Dude, 5 Nov 2026) - one predicate for every browse page
(department, category, sub-category), VISIBLE_SQL / is_visible below:
    manual (any confidence), gs1 high / medium, rule high / medium, ai high.
NOT shown: ai medium, and every low-confidence label of any source. The
SU11A-57 display rule for the promos page and the product dialog
(api/categories.public_path, db.query.CategoryFilter) is NOT this rule and is
unchanged.

LIVE: a search_items row of the current build that is not a pseudo row
(coupons, service rows), has a name, and is sold by at least one live chain -
the items search v2 can return.

LINKED: a category or sub-category is linked from the tree only with at least
MIN_LINKED visible live items (computed per build). A department is always
listed. Its page still answers below the threshold.

TOBACCO (D10.C05 and below): never in the tree, its page is 404 here, and the
D10 department page leaves it out. Tobacco items stay in normal search.

Paths (never a per-request scan of prices):
  * no city: one statement over item_categories x search_items, filtered /
    sorted with search_item_prices (the SU11A-47 per-chain quotes of the
    build), paged in SQL; the page is priced from search_item_prices with the
    live fallback of db.search_filtered (SU11A-50).
  * a city: the category's visible items in the requested order are the
    candidates of the db.search_filtered walk (batches 200 / 400 / 800 / 1,600,
    at most 3,000 candidates), checked against the city's live stores
    (search_filtered.store_filter); only the page is priced live
    (db.query.fetch_prices). total is exact once the walk covered every
    candidate, else the category's visible count (total_exact false).
Sorts: popular (chains_live desc, then name), cheapest (the lowest effective
price of the build: min over chains of LEAST(shelf, promo); in a city the
candidates walk in that order, so it is "cheapest nationwide" among the items
the city has), name. on_promo: no city - the build's winning quote of some chain
(of the chain, with chain) carries a promo still in force; a city - the item has
an in-force promo at one of the city's live stores (of the chain).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Connection

from api import categories as cats
from db import query as _q
from db import search_filtered as F
from db import search_v2 as V

log = logging.getLogger(__name__)

MIN_LINKED = 5
TOBACCO = "D10.C05"
SORTS = ("popular", "cheapest", "name")
LIMIT_MAX = 60
OFFSET_MAX = 2000
STAMP_TTL_S = 60.0        # how often the build stamp is re-read for the tree cache
TREE_MAX_AGE_S = 6 * 3600.0

# --------------------------------------------------------------------------- the predicate
# The ONE visibility rule (see the module docstring). `ic` = item_categories.
VISIBLE_SQL = ("(ic.source = 'manual'"
               " OR (ic.source IN ('gs1', 'rule') AND ic.confidence IN ('high', 'medium'))"
               " OR (ic.source = 'ai' AND ic.confidence = 'high'))")
# `si` = search_items: what search v2 can return.
LIVE_SQL = "(NOT si.is_pseudo AND si.chains_live >= 1 AND si.name_norm <> '')"


def is_visible(source: str | None, confidence: str | None) -> bool:
    """VISIBLE_SQL in Python."""
    if source == "manual":
        return True
    if source in ("gs1", "rule"):
        return confidence in ("high", "medium")
    return source == "ai" and confidence == "high"


class NotFound(LookupError):
    """Unknown, inactive or tobacco node."""


# --------------------------------------------------------------------------- the tree
def tobacco_ids(nodes: dict) -> set[str]:
    return cats._subtree(nodes, TOBACCO) if TOBACCO in nodes else set()


def _ancestors(nodes: dict, cid: str) -> list[str]:
    out, cur, seen = [], cid, set()
    while cur and cur in nodes and cur not in seen:
        seen.add(cur)
        out.append(cur)
        cur = nodes[cur]["parent_id"]
    return out


_COUNTS_SQL = f"""
    SELECT ic.category_id, count(*) AS n
    FROM item_categories ic JOIN search_items si ON si.item_code = ic.item_code
    WHERE {VISIBLE_SQL} AND {LIVE_SQL}
    GROUP BY ic.category_id
"""


def build_tree(nodes: dict, label_counts: dict[str, int]) -> dict:
    """Pure: the browse tree from the taxonomy and per-node visible counts.
    A label counts for its node and every ancestor (a label on an inactive node
    still counts for its active ancestors); tobacco counts nowhere."""
    tob = tobacco_ids(nodes)
    counts: dict[str, int] = {}
    for cid, n in label_counts.items():
        if cid in tob or cid not in nodes:
            continue
        for a in _ancestors(nodes, cid):
            counts[a] = counts.get(a, 0) + int(n)
    kids: dict[str | None, list[dict]] = {}
    for n in nodes.values():
        if n["active"] and n["id"] not in tob:
            kids.setdefault(n["parent_id"], []).append(n)

    def node(n: dict) -> dict:
        children = [node(c) for c in kids.get(n["id"], [])]
        out = {"id": n["id"], "level": n["level"], "name_he": n["name_he"], "name_en": n["name_en"],
               "count": counts.get(n["id"], 0)}
        if n["level"] > 1:
            out["linked"] = out["count"] >= MIN_LINKED
        out["children"] = [c for c in children if c["linked"]]
        return out

    unlinked: dict[str, dict] = {}

    def collect(n: dict, raw: dict) -> None:
        for c in kids.get(raw["id"], []):
            full = node(c)
            if not full["linked"]:
                unlinked[c["id"]] = full
            collect(full, c)

    depts = []
    for n in kids.get(None, []):
        if n["level"] == 1:
            d = node(n)
            collect(d, n)
            depts.append(d)
    return {"min_linked": MIN_LINKED, "departments": depts,
            "total": sum(d["count"] for d in depts), "_unlinked": unlinked}


@dataclass
class _TreeCache:
    key: object = None
    checked_at: float = float("-inf")
    built_at: float = float("-inf")
    value: dict | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


_tree_cache = _TreeCache()


def _stamp(conn: Connection) -> object:
    """The build stamp and the taxonomy version: the tree cache key."""
    return (V.built_stamp(conn), cats.tree(conn)["version"])


def browse_tree(conn: Connection) -> dict:
    """Cached per worker until the search build stamp (or the taxonomy
    version) changes - re-read at most every STAMP_TTL_S - or TREE_MAX_AGE_S
    passes. A failed refresh serves the last value; a cold worker raises."""
    c, now = _tree_cache, time.monotonic()
    if c.value is not None and now - c.checked_at < STAMP_TTL_S and now - c.built_at < TREE_MAX_AGE_S:
        return c.value
    with c.lock:
        try:
            key = _stamp(conn)
            c.checked_at = now
            if c.value is not None and key == c.key and now - c.built_at < TREE_MAX_AGE_S:
                return c.value
            counts = {r[0]: int(r[1]) for r in conn.execute(text(_COUNTS_SQL))}
            value = build_tree(cats.tree(conn)["nodes"], counts)
            value["built_at"] = key[0].isoformat() if key[0] is not None else None
            c.key, c.value, c.built_at = key, value, now
            return value
        except Exception as exc:
            if c.value is None:
                raise
            conn.rollback()
            c.checked_at = now
            log.warning("/categories/browse-tree: serving the cached tree (%s)", type(exc).__name__)
            return c.value


def reset_cache() -> None:
    global _tree_cache
    _tree_cache = _TreeCache()


def tree_node(conn: Connection, category_id: str) -> dict | None:
    """The node as /categories/browse-tree lists it (count, linked children),
    found even when it is not linked; None for tobacco / unknown ids."""
    def find(ns: list[dict]) -> dict | None:
        for n in ns:
            if n["id"] == category_id:
                return n
            hit = find(n["children"]) if category_id.startswith(n["id"] + ".") else None
            if hit is not None:
                return hit
        return None
    hit = find(browse_tree(conn)["departments"])
    if hit is not None:
        return hit
    # an unlinked category / sub-category: not under its parent's children
    tree = browse_tree(conn)
    return tree.get("_unlinked", {}).get(category_id)


# --------------------------------------------------------------------------- one page
def resolve_node(conn: Connection, category_id: str) -> tuple[dict, list[str]]:
    """(node, ids of its subtree without tobacco). NotFound for an unknown,
    inactive or tobacco id."""
    nodes = cats.tree(conn)["nodes"]
    n = nodes.get(category_id)
    tob = tobacco_ids(nodes)
    if n is None or not n["active"] or category_id in tob:
        raise NotFound(category_id)
    return n, sorted(cats._subtree(nodes, category_id) - tob)


_EFFECTIVE = "LEAST(sp.item_price, sp.promo_unit_price)"
_PROMO_LIVE = "(sp.promo_unit_price IS NOT NULL AND (sp.promo_end IS NULL OR CAST(sp.promo_end AS timestamp) >= NOW()))"


def _order(sort: str, cheapest_ok: bool) -> str:
    if sort == "cheapest" and cheapest_ok:
        return "best ASC NULLS LAST, si.name_norm, si.item_code"
    if sort == "name":
        return "si.name_norm, si.item_code"
    return "si.chains_live DESC, si.name_norm, si.item_code"


def _candidates_sql(*, precomputed: bool, sort: str, chain: str | None, on_promo: bool, paged: bool) -> str:
    """The category's visible live items, filtered and ordered. With precomputed
    (search_item_prices of this build) the chain / on_promo filters and the
    cheapest order use it; paged adds count(*) OVER () and LIMIT / OFFSET."""
    chain_sp = " AND sp.chain_id = :chain" if chain else ""
    where = [f"ic.category_id = ANY(CAST(:ids AS text[]))", VISIBLE_SQL, LIVE_SQL]
    if precomputed and chain:
        where.append(f"EXISTS (SELECT 1 FROM search_item_prices sp WHERE sp.item_code = si.item_code{chain_sp})")
    if precomputed and on_promo:
        where.append(f"EXISTS (SELECT 1 FROM search_item_prices sp WHERE sp.item_code = si.item_code{chain_sp}"
                     f" AND {_PROMO_LIVE})")
    best = ""
    if precomputed and sort == "cheapest":
        best = (f", (SELECT min({_EFFECTIVE}) FROM search_item_prices sp"
                f" WHERE sp.item_code = si.item_code{chain_sp}) AS best")
    total = ", count(*) OVER () AS total" if paged else ""
    tail = " LIMIT :limit OFFSET :offset" if paged else ""
    return f"""
        SELECT si.item_code, ic.category_id{best}{total}
        FROM item_categories ic JOIN search_items si ON si.item_code = ic.item_code
        WHERE {' AND '.join(where)}
        ORDER BY {_order(sort, precomputed)}{tail}"""


class _List:
    """The candidate list as db.search_filtered.Walk reads it (take / total)."""

    def __init__(self, rows: list[dict]):
        self.rows, self.total = rows, len(rows)

    def take(self, n: int) -> list[dict]:
        return self.rows[:n]


_PROMO_AT_STORES_SQL = """
    SELECT DISTINCT p.item_code FROM promos p
    WHERE p.item_code = ANY(CAST(:codes AS text[])) AND p.store_fk = ANY(CAST(:fks AS int[]))
      AND (p.promo_end >= NOW() OR p.promo_end IS NULL)
"""


def _promo_filter(conn: Connection, fks: list[int], inner):
    def run(codes: list[str]):
        infos = inner(codes)
        if not infos:
            return infos
        keep = {r[0] for r in conn.execute(text(_PROMO_AT_STORES_SQL), {"codes": list(infos), "fks": fks})}
        return {c: inf for c, inf in infos.items() if c in keep}
    return run


@dataclass
class Page:
    node: dict
    total: int
    total_exact: bool
    has_more: bool
    products: list[dict]        # db.query.group_by_product dicts, in page order, + "category_id"
    mode: str
    prices_source: str = "live"
    timings_ms: dict = field(default_factory=dict)


def items_page(conn: Connection, category_id: str, *, city: str | None = None, chain: str | None = None,
               sort: str = "popular", on_promo: bool = False, limit: int = 30, offset: int = 0) -> Page:
    t0 = time.perf_counter()
    node, ids = resolve_node(conn, category_id)
    V.check_ready(conn)
    precomputed = F.precomputed_ok(conn)
    base = {"ids": ids, **({"chain": chain} if chain else {})}
    _aliases, eilat_fks = V._lexicon(conn)
    tm: dict = {}

    if not city and precomputed:
        mode = "precomputed"
        rows = [dict(r) for r in conn.execute(text(_candidates_sql(
            precomputed=True, sort=sort, chain=chain, on_promo=on_promo, paged=True)),
            {**base, "limit": limit + 1, "offset": offset}).mappings()]
        tm["candidates"] = round((time.perf_counter() - t0) * 1000, 1)
        has_more = len(rows) > limit
        rows = rows[:limit]
        if rows:
            total, exact = int(rows[0]["total"]), True
        else:
            total = int(conn.execute(text(f"SELECT count(*) FROM ({_candidates_sql(precomputed=True, sort='name', chain=chain, on_promo=on_promo, paged=False)}) x"), base).scalar())
            exact = True
        cat_of = {r["item_code"]: r["category_id"] for r in rows}
        codes = list(cat_of)
        products, source = _price_nationwide(conn, codes, chain, eilat_fks)
    else:
        # a city, or no usable search_item_prices: the walk over live stores
        mode = "stores" if city else "stores-national"
        cands = [dict(r) for r in conn.execute(text(_candidates_sql(
            precomputed=precomputed, sort=sort, chain=chain if precomputed else None,
            on_promo=False, paged=False)), base).mappings()]
        tm["candidates"] = round((time.perf_counter() - t0) * 1000, 1)
        cat_of = {r["item_code"]: r["category_id"] for r in cands}
        fks = F.resolve_stores(conn, [city] if city else None, [chain] if chain else None)
        products, has_more, total, exact, source = [], False, 0, True, "live"
        if fks and cands:
            filt = F.store_filter(conn, fks)
            if on_promo:
                filt = _promo_filter(conn, fks, filt)
            walk = F.Walk(_List(cands), filt, lambda inf: F.YES)
            walk.ensure(offset + limit + 1)
            tm["filter"] = round((time.perf_counter() - t0) * 1000 - tm["candidates"], 1)
            page = walk.items[offset:offset + limit]
            has_more = len(walk.items) > offset + limit
            codes = [it[0]["item_code"] for it in page]
            if codes:
                by_item = _q.group_by_product(_q.fetch_prices(
                    conn, codes, city=[city] if city else None, chain_id=[chain] if chain else None, page=True))
                products = [by_item[c] for c in codes if c in by_item]
            exact = walk.exhausted
            total = walk.any_items if exact else len(cands)
    for p in products:
        p["category_id"] = cat_of.get(p["item_code"])
    tm["total"] = round((time.perf_counter() - t0) * 1000, 1)
    return Page(node=node, total=total, total_exact=exact, has_more=has_more, products=products,
                mode=mode, prices_source=source, timings_ms=tm)


def _price_nationwide(conn: Connection, codes: list[str], chain: str | None, eilat_fks) -> tuple[list[dict], str]:
    """The page's products as an unfiltered v2 /search prices them (search_filtered._page)."""
    if not codes:
        return [], "precomputed"
    rows, source = V._try_precomputed(conn, codes), "precomputed"
    if rows is None:
        source = "live"
        rows = V.drop_eilat(_q.fetch_prices(conn, codes, page=True), eilat_fks, None)
    if chain:
        rows = [r for r in rows if r["chain_id"] == chain]
    by_item = _q.group_by_product(rows)
    return [by_item[c] for c in codes if c in by_item], source
