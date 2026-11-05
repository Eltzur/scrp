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
        SELECT si.item_code, ic.category_id, si.name_norm, si.chains_live{best}{total}
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


# --------------------------------------------------------------------------- restrictions (SU11A-68)
# The browse predicate as an extra condition on search v2's candidate query
# (search_v2._ranked / _barcode read FROM search_items, unaliased).
_RESTRICT_SQL = (" AND EXISTS (SELECT 1 FROM item_categories ic WHERE ic.item_code = search_items.item_code"
                 f" AND ic.category_id = ANY(CAST(:rc_ids AS text[])) AND {VISIBLE_SQL})")
_LIVE_RESTRICT_SQL = " AND search_items.chains_live >= 1 AND search_items.name_norm <> ''"


def search_restrict(conn: Connection, category_id: str, live: bool = False) -> tuple[str, dict]:
    """(" AND ...", params) for search_v2 / search_filtered: only items with a
    VISIBLE label under the node (tobacco never). live=True adds the browse
    pages' live condition (a name, a live chain). NotFound for an unknown,
    inactive or tobacco id."""
    _node, ids = resolve_node(conn, category_id)
    return _RESTRICT_SQL + (_LIVE_RESTRICT_SQL if live else ""), {"rc_ids": ids}


_VISIBLE_CODES_SQL = f"""
    SELECT ic.item_code FROM item_categories ic
    WHERE ic.category_id = ANY(CAST(:ids AS text[])) AND {VISIBLE_SQL}
"""
VISIBLE_CODES_TTL_S = 600.0
VISIBLE_CODES_MAX = 64
_codes_lock = threading.Lock()
_codes_cache: dict[str, tuple[float, frozenset]] = {}


def visible_codes(conn: Connection, category_id: str) -> frozenset:
    """Every barcode with a visible label under the node (the old /search path
    filters its name matches with it). Cached VISIBLE_CODES_TTL_S per worker;
    labels change only with an import or an admin edit."""
    now = time.monotonic()
    with _codes_lock:
        hit = _codes_cache.get(category_id)
    if hit is not None and now - hit[0] < VISIBLE_CODES_TTL_S:
        return hit[1]
    _node, ids = resolve_node(conn, category_id)
    codes = frozenset(r[0] for r in conn.execute(text(_VISIBLE_CODES_SQL), {"ids": ids}))
    with _codes_lock:
        if len(_codes_cache) >= VISIBLE_CODES_MAX:
            _codes_cache.pop(next(iter(_codes_cache)))
        _codes_cache[category_id] = (now, codes)
    return codes


def reset_codes_cache() -> None:
    with _codes_lock:
        _codes_cache.clear()


# --------------------------------------------------------------------------- dominant category (SU11A-68)
DOMINANT_SHARE = 0.6
DOMINANT_MIN = 4
DOMINANT_CODES_MAX = 60


def dominant_category(conn: Connection, codes: list[str]) -> dict | None:
    """The deepest browsable node that at least DOMINANT_SHARE of the codes
    (and at least DOMINANT_MIN of them) share, counting VISIBLE labels only;
    None when no node qualifies. The search page offers "הצג רק ב<node>"."""
    codes = list(dict.fromkeys(codes))[:DOMINANT_CODES_MAX]
    if len(codes) < DOMINANT_MIN:
        return None
    nodes = cats.tree(conn)["nodes"]
    tob = tobacco_ids(nodes)
    rows = conn.execute(text(
        f"SELECT ic.category_id FROM item_categories ic WHERE ic.item_code = ANY(CAST(:c AS text[])) AND {VISIBLE_SQL}"),
        {"c": codes}).all()
    counts: dict[str, int] = {}
    for (cid,) in rows:
        if cid in tob:
            continue
        for a in _ancestors(nodes, cid):
            counts[a] = counts.get(a, 0) + 1
    need = max(DOMINANT_MIN, DOMINANT_SHARE * len(codes))
    best = None
    for cid, n in counts.items():
        node = nodes.get(cid)
        if n < need or node is None or not node["active"] or cid in tob:
            continue
        if best is None or (node["level"], n) > (best[0]["level"], best[1]):
            best = (node, n)
    if best is None:
        return None
    node, n = best
    return {"id": node["id"], "level": node["level"], "name_he": node["name_he"], "name_en": node["name_en"],
            "share": round(n / len(codes), 2)}


# --------------------------------------------------------------------------- one page
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
    q: str | None = None        # the search text used (None = none / ignored)
    corrected_from: str | None = None


TEXT_CAP = 3000                 # text matches considered in a category (v2 candidates)
# "cheapest" in a city prices up to CITY_CHEAPEST_CEILING candidates, walked
# in the nationwide-cheapest order (bench, 7.9M prices, Tel Aviv: a 3,425-item
# category 0.7 s cold vs 1.4 s with 500-row batches; then cached). Every
# production category but D15.C04 (4,479) is under the ceiling, so its order
# is exact; above it (departments) the items past the 4,000 nationally
# cheapest are not considered - documented approximation, total_exact false.
CITY_CHEAPEST_CEILING = 4000
CITY_CHEAPEST_BATCHES = (2000, 4000)
CITY_CACHE_TTL_S = 300.0
CITY_CACHE_MAX = 64

# "cheapest" in a city (SU11A-68): per (item, chain) in the city's live stores,
# the lowest price the card shows - the shelf price, or the promo
# db.query._PROMO_PICK_SQL would pick when it beats the shelf, and for a
# promo-only quote discount_price / min_qty (the _PROMO_ONLY_SQL_CITY pick).
# The same rows as search_filtered.store_filter (shelf > 0, item_chain_names
# row; promo-only per _PROMO_ONLY_WHERE), so the walk keeps the same items.
# The promo part is ONE aggregate per (store, item) instead of the pick's
# per-row LATERAL (1.6-1.8 s -> see the bench in the handoff for a 3,400-item
# walk): the pick's two unit-price forms are each monotone, so their minimum is
#   direct  min(discount_price / min_qty)          min_qty 1-24, price > 0
#   rate    shelf x (1 - max(rate) / 100)          price null / 0, 0 < rate < 100
#                                                  (> 100 = basis points), min_qty <= 1
# and LEAST(shelf, direct, rate) is exactly "the pick when it beats the shelf,
# else the shelf" (LEAST skips NULLs). Tested against fetch_prices.
_RATE = "(CASE WHEN pm.discount_rate > 100 THEN pm.discount_rate / 100.0 ELSE pm.discount_rate END)"
_CITY_PRICE_SQL = f"""
WITH pmx AS (
    SELECT pm.store_fk, pm.item_code,
           min(CASE WHEN pm.min_qty BETWEEN 1 AND 24 AND pm.discount_price > 0
                    THEN pm.discount_price / pm.min_qty END) AS direct,
           max(CASE WHEN (pm.discount_price IS NULL OR pm.discount_price = 0)
                     AND {_RATE} > 0 AND {_RATE} < 100 AND COALESCE(pm.min_qty, 1) <= 1
                    THEN {_RATE} END) AS rate
    FROM promos pm
    WHERE pm.item_code = ANY(CAST(:codes AS text[]))
      AND pm.store_fk  = ANY(CAST(:fks AS int[]))
      AND (pm.promo_end >= NOW() OR pm.promo_end IS NULL)
      AND pm.item_code <> '0000000000000'
    GROUP BY pm.store_fk, pm.item_code
), sh AS (
    SELECT p.item_code, s.chain_id, count(*) AS n, true AS shelf,
           min(LEAST(p.item_price, x.direct, p.item_price * (1 - x.rate / 100.0))) AS best
    FROM prices p
    JOIN stores s ON s.id = p.store_fk
    JOIN chains c ON c.chain_id = s.chain_id
    JOIN items  i ON i.item_code = p.item_code
    LEFT JOIN pmx x ON x.store_fk = p.store_fk AND x.item_code = p.item_code
    WHERE p.item_code = ANY(CAST(:codes AS text[]))
      AND p.store_fk  = ANY(CAST(:fks AS int[]))
      AND p.item_price > 0
      AND EXISTS (SELECT 1 FROM item_chain_names icn
                  WHERE icn.item_code = p.item_code AND icn.chain_id = s.chain_id)
    GROUP BY p.item_code, s.chain_id
), po AS (
    SELECT p.item_code, s.chain_id, count(DISTINCT p.store_fk) AS n, false AS shelf,
           min(p.discount_price / p.min_qty) AS best
    FROM promos p
    JOIN stores s ON s.id = p.store_fk
    JOIN chains c ON c.chain_id = s.chain_id
    JOIN items  i ON i.item_code = p.item_code
    WHERE p.item_code = ANY(CAST(:codes AS text[]))
      AND p.store_fk  = ANY(CAST(:fks AS int[]))
      AND {_q._PROMO_ONLY_WHERE}
    GROUP BY p.item_code, s.chain_id
)
SELECT item_code, chain_id, n, shelf, best FROM sh
UNION ALL
SELECT item_code, chain_id, n, shelf, best FROM po
"""


def _city_price_filter(conn: Connection, fks: list[int], best: dict[str, float]):
    """A search_filtered.Walk filter that also records each item's lowest city price in `best`."""
    def run(codes: list[str]):
        conn.execute(text("SET LOCAL enable_nestloop = on"))
        rows = conn.execute(text(_CITY_PRICE_SQL), {"codes": codes, "fks": fks}).all()
        for r in rows:
            if r[4] is not None:
                v = float(r[4])
                best[r[0]] = min(v, best.get(r[0], v))
        return F._infos([r[:4] for r in rows])
    return run


_city_lock = threading.Lock()
_city_cache: dict[tuple, tuple[float, list[str], int]] = {}


def _city_cache_get(key: tuple) -> tuple[list[str], int] | None:
    with _city_lock:
        hit = _city_cache.get(key)
    if hit is not None and time.monotonic() - hit[0] < CITY_CACHE_TTL_S:
        return hit[1], hit[2]
    return None


def _city_cache_put(key: tuple, codes: list[str], walked: int) -> None:
    with _city_lock:
        if len(_city_cache) >= CITY_CACHE_MAX:
            _city_cache.pop(next(iter(_city_cache)))
        _city_cache[key] = (time.monotonic(), codes, walked)


def reset_city_cache() -> None:
    with _city_lock:
        _city_cache.clear()


def clean_q(q: str | None) -> str | None:
    """The search text as db.query.clean_promo_q reads it (SU11A-62 / SU11A-63
    H2): whitespace collapsed; None under 2 characters besides %, _, backslash
    and spaces (no search)."""
    return _q.clean_promo_q(q)


def _text_candidates(conn: Connection, category_id: str, qn: str) -> tuple[list[dict], bool, str | None]:
    """(candidates in v2 relevance order with their tier, complete?, corrected_from):
    search v2's own matcher (search_v2.ranked_candidates: normalisation,
    aliases, barcode, one typo round, LIKE-escaped), restricted to the
    category's visible live items."""
    aliases, _ = V._lexicon(conn)
    ranked, corrected = V.ranked_candidates(conn, qn, aliases, restrict=search_restrict(conn, category_id, live=True))
    rows = ranked.take(min(ranked.total, TEXT_CAP))
    return rows, ranked.total <= TEXT_CAP, corrected


def _sort_key(sort: str, best: dict[str, float] | None = None):
    if sort == "cheapest" and best is not None:
        return lambda r: (best.get(r["item_code"], float("inf")), r["name_norm"], r["item_code"])
    if sort == "name":
        return lambda r: (r["name_norm"], r["item_code"])
    return lambda r: (-int(r["chains_live"]), r["name_norm"], r["item_code"])


_BEST_SQL = f"""
    SELECT sp.item_code, min({_EFFECTIVE}) AS best FROM search_item_prices sp
    WHERE sp.item_code = ANY(CAST(:codes AS text[])){{chain}}
    GROUP BY sp.item_code
"""
_PRE_KEEP_SQL = """
    SELECT DISTINCT sp.item_code FROM search_item_prices sp
    WHERE sp.item_code = ANY(CAST(:codes AS text[])){chain}{promo}
"""


def items_page(conn: Connection, category_id: str, *, city: str | None = None, chain: str | None = None,
               sort: str = "popular", on_promo: bool = False, limit: int = 30, offset: int = 0,
               q: str | None = None) -> Page:
    t0 = time.perf_counter()
    node, ids = resolve_node(conn, category_id)
    V.check_ready(conn)
    precomputed = F.precomputed_ok(conn)
    base = {"ids": ids, **({"chain": chain} if chain else {})}
    _aliases, eilat_fks = V._lexicon(conn)
    qn = clean_q(q)
    tm: dict = {}
    corrected = None
    chain_sp = " AND sp.chain_id = :chain" if chain else ""

    def lap(name: str) -> None:
        tm[name] = round((time.perf_counter() - t0) * 1000 - sum(tm.values()), 1)

    if not qn and not city and precomputed:
        # SU11A-67 fast path: filtered, ordered and paged in one statement
        rows = [dict(r) for r in conn.execute(text(_candidates_sql(
            precomputed=True, sort=sort, chain=chain, on_promo=on_promo, paged=True)),
            {**base, "limit": limit + 1, "offset": offset}).mappings()]
        lap("candidates")
        has_more = len(rows) > limit
        rows = rows[:limit]
        if rows:
            total = int(rows[0]["total"])
        else:
            total = int(conn.execute(text("SELECT count(*) FROM (" + _candidates_sql(
                precomputed=True, sort="name", chain=chain, on_promo=on_promo, paged=False) + ") x"), base).scalar())
        cat_of = {r["item_code"]: r["category_id"] for r in rows}
        products, source = _price_nationwide(conn, list(cat_of), chain, eilat_fks)
        return _done(node, total, True, has_more, products, cat_of, "precomputed", source, tm, t0, qn, corrected)

    # The full candidate list, in the requested order.
    if qn:
        text_rows, complete, corrected = _text_candidates(conn, category_id, qn)
        codes = [r["item_code"] for r in text_rows]
        cat_of = {r[0]: r[1] for r in conn.execute(text(
            "SELECT item_code, category_id FROM item_categories WHERE item_code = ANY(CAST(:c AS text[]))"),
            {"c": codes})} if codes else {}
        best = None
        if sort == "cheapest" and precomputed and codes:
            best = {r[0]: float(r[1]) for r in conn.execute(text(_BEST_SQL.format(chain=chain_sp)),
                                                           {"codes": codes, **base}) if r[1] is not None}
        key = _sort_key(sort, best if best is not None else ({} if sort == "cheapest" else None))
        cands = sorted(({"item_code": r["item_code"], "name_norm": r["name_norm"], "chains_live": r["chains_live"],
                         "tier": r.get("tier", 0), "category_id": cat_of.get(r["item_code"])} for r in text_rows),
                       key=lambda r: (r["tier"], *key(r)))
    else:
        complete = True
        cands = [dict(r) for r in conn.execute(text(_candidates_sql(
            precomputed=precomputed, sort=sort, chain=chain if precomputed else None,
            on_promo=False, paged=False)), base).mappings()]
        cat_of = {r["item_code"]: r["category_id"] for r in cands}
    lap("candidates")

    if not city and precomputed:
        # q without a city: the build's quotes filter (chain / on_promo), then page
        if (chain or on_promo) and cands:
            promo = f" AND {_PROMO_LIVE}" if on_promo else ""
            keep = {r[0] for r in conn.execute(text(_PRE_KEEP_SQL.format(chain=chain_sp, promo=promo)),
                                               {"codes": [c["item_code"] for c in cands], **base})}
            cands = [c for c in cands if c["item_code"] in keep]
        page = cands[offset:offset + limit]
        products, source = _price_nationwide(conn, [c["item_code"] for c in page], chain, eilat_fks)
        return _done(node, len(cands), complete, len(cands) > offset + limit, products, cat_of, "precomputed-q",
                     source, tm, t0, qn, corrected)

    # a city, or no usable search_item_prices: the walk over live stores
    mode = "stores" if city else "stores-national"
    fks = F.resolve_stores(conn, [city] if city else None, [chain] if chain else None)
    products, has_more, total, exact = [], False, 0, complete
    if fks and cands:
        if sort == "cheapest" and city:
            mode = "stores-cheapest"
            codes, walked = _city_cheapest(conn, category_id, city, chain, on_promo, qn, cands, fks)
            lap("filter")
            page_codes = codes[offset:offset + limit]
            has_more = len(codes) > offset + limit
            exact = complete and walked >= len(cands)
            total = len(codes) if exact else len(cands)
        else:
            filt = F.store_filter(conn, fks)
            if on_promo:
                filt = _promo_filter(conn, fks, filt)
            walk = F.Walk(_List(cands), filt, lambda inf: F.YES)
            walk.ensure(offset + limit + 1)
            lap("filter")
            page_codes = [it[0]["item_code"] for it in walk.items[offset:offset + limit]]
            has_more = len(walk.items) > offset + limit
            exact = complete and walk.exhausted
            total = walk.any_items if exact else len(cands)
        if page_codes:
            by_item = _q.group_by_product(_q.fetch_prices(
                conn, page_codes, city=[city] if city else None, chain_id=[chain] if chain else None, page=True))
            products = [by_item[c] for c in page_codes if c in by_item]
    return _done(node, total, exact, has_more, products, cat_of, mode, "live", tm, t0, qn, corrected)


def _city_cheapest(conn: Connection, category_id: str, city: str, chain: str | None, on_promo: bool,
                   qn: str | None, cands: list[dict], fks: list[int]) -> tuple[list[str], int]:
    """(the city's items ordered by their lowest city price, candidates walked).
    Walks up to CITY_CHEAPEST_CEILING candidates (in the nationwide-cheapest
    order, so a capped walk keeps the likely cheapest) and sorts what the city
    has by the price the card shows; text relevance stays first with q.
    Cached CITY_CACHE_TTL_S per worker, so "טען עוד" pages reuse one walk."""
    key = (category_id, city, chain, on_promo, qn, V.built_stamp(conn), len(cands))
    hit = _city_cache_get(key)
    if hit is not None:
        return hit
    best: dict[str, float] = {}
    filt = _city_price_filter(conn, fks, best)
    if on_promo:
        filt = _promo_filter(conn, fks, filt)
    walk = F.Walk(_List(cands), filt, lambda inf: F.YES, ceiling=CITY_CHEAPEST_CEILING,
                  batches=CITY_CHEAPEST_BATCHES)
    walk.ensure(10 ** 9)
    rows = [it[0] for it in walk.items]
    rows.sort(key=lambda r: (r.get("tier", 0) if qn else 0, best.get(r["item_code"], float("inf")),
                             r.get("name_norm") or "", r["item_code"]))
    codes = [r["item_code"] for r in rows]
    _city_cache_put(key, codes, walk.walked)
    return codes, walk.walked


def _done(node, total, exact, has_more, products, cat_of, mode, source, tm, t0, qn, corrected) -> Page:
    for p in products:
        p["category_id"] = cat_of.get(p["item_code"])
    tm["total"] = round((time.perf_counter() - t0) * 1000, 1)
    return Page(node=node, total=total, total_exact=exact, has_more=has_more, products=products,
                mode=mode, prices_source=source, timings_ms=tm, q=qn, corrected_from=corrected)


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
