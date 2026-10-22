"""Filtered search on the v2 path (SU11A-50): /compare, and /search with a city,
chain or group_by=store, without pricing every name match.

The old path (api/routers/search.py _build_result) prices up to OLD_PATH_CAP
(1,000) name matches in the filtered stores before it pages: 1.3-1.4 s for
חלב / במבה in one city, 12 s for /compare?q=חלב without a city, and a 15 s
query_timeout for ים. Here:

  1. Candidates and their order come from search v2 (search_items / lexicon,
     same normalization, pseudo items out, same typo round, v2 relevance):
     db.search_v2.ranked_candidates.
  2. The candidates are walked in rank order in batches (BATCHES, at most
     CEILING in all). Each batch is ONE statement that keeps the items with a
     quote in the filter, until offset + limit + 1 are found:
       - city (and/or chain) filter, and group_by=store: a semi-join on prices
         + promos restricted to the live store set (_STORE_FILTER_SQL; the same
         conditions as fetch_prices: shelf > 0, item_chain_names row, chains
         row, or a promo-only quote);
       - chain filter without a city: search_item_prices rows of those chains
         (precomputed, SU11A-47);
       - /compare without a city: search_item_prices (2+ chains, or one chain
         whose quote is promo-only).
  3. Only the page's items are priced: live through db.query.fetch_prices with
     the request's own city / chain (the old path's SQL, promo pick, liveness,
     ₪0 drop), or from search_item_prices for the precomputed modes, falling
     back to the live fetch per the SU11A-47 rules (other build, missing row,
     ended promo).

Eilat (D2): unchanged in city mode - the old path never drops Eilat quotes, so
city=אילת shows Eilat prices and other cities have no Eilat stores. The
nationwide modes (chain only, /compare without a city) apply D2 like search v2:
search_item_prices was built with it, and the live fallback runs drop_eilat.
group_by=store lists each store's own row and drops nothing (as before).

Counts (deviation, see the SU11A-50 handoff entry): an exact count needs every
candidate filtered. When the walk covered all candidates, total_matches /
comparable_count are exact for the filter (items with a quote there / with 2+
chains there; for group_by=store, store rows). Otherwise they are the
nationwide name-match counts from search_items, as an unfiltered v2 /search
reports them. has_more is exact either way (the walk looks one item past the
page), except past the CEILING-th candidate, where the walk stops: nothing past
it is listed and has_more is false there.

Order (deviation): v2 relevance for every mode, not the old "tier, multi-chain,
cheapest". group_by=store: items in rank order, each item's store rows by
price, then chain, then store.

Anything raised here makes the router answer with the old path (inside a
SAVEPOINT); Unsupported is the expected case (e.g. /compare without a city
while search_item_prices is not usable).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Connection

from db import query as _q
from db import search_v2 as V
from db.query import _PROMO_ONLY_WHERE, fetch_prices, group_by_product, group_by_store

BATCHES = (200, 400, 800, 1600)
CEILING = sum(BATCHES)          # 3,000 candidates walked at most
STREAM_FIRST = 600              # candidate rows in the first fetch (then 4,800: two statements cover 3,000)

NO, YES, MAYBE = 0, 1, 2


class Unsupported(RuntimeError):
    """This request cannot be served here; the router uses the old path."""


@dataclass
class Info:
    """One candidate's quotes in the filter, as the filter statement sees them."""
    chains: set = field(default_factory=set)
    rows: int = 0                  # store rows (shelf + promo-only)
    shelf_chains: set = field(default_factory=set)
    po_chains: set = field(default_factory=set)


@dataclass
class FilteredResult:
    query: str
    total_matches: int
    comparable_count: int
    has_more: bool
    products: list[dict]           # group_by_product / group_by_store dicts, in page order
    corrected_from: str | None = None
    timings_ms: dict = field(default_factory=dict)
    prices_source: str = "live"
    mode: str = ""
    walked: int = 0
    exact_counts: bool = False


# ---------------------------------------------------------------------------
# Filter statements
# ---------------------------------------------------------------------------

# Per (item, chain) in the store set: shelf rows as _PRICE_SQL_CITY joins them
# (prices x stores x item_chain_names x items x chains, shelf > 0) and promo-only
# quotes with _PROMO_ONLY_WHERE. The store set is already the live stores only.
_STORE_FILTER_SQL = f"""
WITH sh AS (
    SELECT p.item_code, s.chain_id, count(*) AS n, true AS shelf
    FROM prices p
    JOIN stores s ON s.id = p.store_fk
    JOIN chains c ON c.chain_id = s.chain_id
    JOIN items  i ON i.item_code = p.item_code
    WHERE p.item_code = ANY(CAST(:codes AS text[]))
      AND p.store_fk  = ANY(CAST(:fks AS int[]))
      AND p.item_price > 0
      AND EXISTS (SELECT 1 FROM item_chain_names icn
                  WHERE icn.item_code = p.item_code AND icn.chain_id = s.chain_id)
    GROUP BY p.item_code, s.chain_id
), po AS (
    SELECT p.item_code, s.chain_id, count(DISTINCT p.store_fk) AS n, false AS shelf
    FROM promos p
    JOIN stores s ON s.id = p.store_fk
    JOIN chains c ON c.chain_id = s.chain_id
    JOIN items  i ON i.item_code = p.item_code
    WHERE p.item_code = ANY(CAST(:codes AS text[]))
      AND p.store_fk  = ANY(CAST(:fks AS int[]))
      AND {_PROMO_ONLY_WHERE}
    GROUP BY p.item_code, s.chain_id
)
SELECT item_code, chain_id, n, shelf FROM sh
UNION ALL
SELECT item_code, chain_id, n, shelf FROM po
"""

_PRE_FILTER_SQL = """
SELECT item_code, chain_id, 1 AS n, (item_price IS NOT NULL) AS shelf
FROM search_item_prices
WHERE item_code = ANY(CAST(:codes AS text[]))
"""


def _infos(rows) -> dict[str, Info]:
    out: dict[str, Info] = {}
    for r in rows:
        inf = out.setdefault(r[0], Info())
        inf.chains.add(r[1])
        inf.rows += int(r[2])
        (inf.shelf_chains if r[3] else inf.po_chains).add(r[1])
    return out


def store_filter(conn: Connection, fks: list[int]):
    def run(codes: list[str]) -> dict[str, Info]:
        # The promo-only part needs its nested-loop anti join (see
        # db.query._fetch_prices_all); an earlier fetch_prices in this
        # transaction may have turned nested loops off.
        conn.execute(text("SET LOCAL enable_nestloop = on"))
        return _infos(conn.execute(text(_STORE_FILTER_SQL), {"codes": codes, "fks": fks}))
    return run


def precomputed_filter(conn: Connection, chains: list[str] | None):
    sql = _PRE_FILTER_SQL + (" AND chain_id = ANY(CAST(:chains AS text[]))" if chains else "")

    def run(codes: list[str]) -> dict[str, Info]:
        params = {"codes": codes, **({"chains": list(chains)} if chains else {})}
        return _infos(conn.execute(text(sql), params))
    return run


def precomputed_ok(conn: Connection) -> bool:
    """search_item_prices exists, is filled and belongs to the live search_items build."""
    try:
        with conn.begin_nested():
            pre = V._prices_built_at(conn)
            return pre is not None and pre == V._built_at(conn)
    except Exception:  # noqa: BLE001 - unreadable = not usable
        return False


def resolve_stores(conn: Connection, city: list[str] | None, chain: list[str] | None) -> list[int]:
    """Live store ids for the filter (all live stores when there is none)."""
    where, params = [], {}
    if city:
        where.append("city_canonical = ANY(CAST(:city AS text[]))")
        params["city"] = list(city)
    if chain:
        where.append("chain_id = ANY(CAST(:chain AS text[]))")
        params["chain"] = list(chain)
    sql = "SELECT id FROM stores" + (" WHERE " + " AND ".join(where) if where else "")
    fks = [r[0] for r in conn.execute(text(sql), params)]
    lv = _q.get_liveness()
    if lv is not None:            # fail open, like fetch_prices
        fks = [f for f in fks if f in lv.live_fks]
    return sorted(fks)


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

def compare_verdict(inf: Info) -> int:
    """/compare's pool rule: 2+ chains, or one chain whose winning quote is promo-only.

    One chain with only promo-only quotes: YES. Only shelf quotes: NO. Both: the
    winner depends on the promo pick - MAYBE, settled by pricing it.
    """
    if len(inf.chains) >= 2:
        return YES
    if not inf.shelf_chains:
        return YES
    return MAYBE if inf.po_chains else NO


def _is_promo_only(p: dict) -> bool:
    return bool(p["quotes"]) and all(q["promo_kind"] == "promo_only" for q in p["quotes"])


def compare_ok(p: dict) -> bool:
    return p["chains_count"] >= 2 or _is_promo_only(p)


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------

class Walk:
    """Ranked candidates -> the ones with quotes in the filter, in rank order."""

    def __init__(self, ranked: V.Ranked, filt, verdict, weight=lambda inf: 1, ceiling: int | None = None,
                 batches: tuple | None = None):
        self.ranked, self.filt, self.verdict, self.weight = ranked, filt, verdict, weight
        self.ceiling = CEILING if ceiling is None else ceiling
        self.batches = BATCHES if batches is None else batches
        self.walked = 0
        self.items: list[list] = []      # [candidate, info, state]
        self.any_items = 0               # candidates with any quote in the filter
        self.multi_items = 0             # ... in 2+ chains
        self.done = False                # no candidate left, or the ceiling reached
        self.exhausted = False           # every candidate was walked
        self.queries = 0
        self._b = 0

    def size(self) -> int:
        return sum(self.weight(it[1]) for it in self.items)

    def step(self) -> None:
        if self.done:
            return
        n = self.batches[min(self._b, len(self.batches) - 1)]
        n = min(n, self.ceiling - self.walked)
        self._b += 1
        batch = self.ranked.take(self.walked + n)[self.walked:] if n > 0 else []
        if not batch:
            self.done = True
            self.exhausted = self.walked >= self.ranked.total
            return
        infos = self.filt([c["item_code"] for c in batch])
        self.queries += 1
        self.walked += len(batch)
        for c in batch:
            inf = infos.get(c["item_code"])
            if inf is None or not inf.chains:
                continue
            self.any_items += 1
            self.multi_items += len(inf.chains) >= 2
            st = self.verdict(inf)
            if st != NO:
                self.items.append([c, inf, st])
        if self.walked >= self.ranked.total:
            self.done = self.exhausted = True
        elif self.walked >= self.ceiling:
            self.done = True

    def ensure(self, need: int) -> None:
        while not self.done and self.size() < need:
            self.step()

    def maybes(self, upto: int) -> list[list]:
        out, acc = [], 0
        for it in self.items:
            if acc >= upto:
                break
            if it[2] == MAYBE:
                out.append(it)
            acc += self.weight(it[1])
        return out

    def settle(self, decided: dict[str, bool]) -> None:
        keep = []
        for it in self.items:
            code = it[0]["item_code"]
            if it[2] == MAYBE and code in decided:
                if not decided[code]:
                    continue
                it[2] = YES
            keep.append(it)
        self.items = keep


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(conn: Connection, q: str, *, limit: int, offset: int, city: list[str] | None = None,
        chain: list[str] | None = None, group_by: str = "chain", compare_only: bool = False) -> FilteredResult:
    """The filtered answer. Raises Unsupported / V2Unavailable / anything -> old path."""
    t = {"start": time.perf_counter()}

    def lap(name: str) -> None:
        now = time.perf_counter()
        t[name] = round((now - t.pop("_last", t["start"])) * 1000, 1)
        t["_last"] = now

    V.check_ready(conn)
    aliases, eilat_fks = V._lexicon(conn)
    by_store = group_by == "store"
    if compare_only and (chain or by_store):
        raise Unsupported("compare has no chain / store grouping")

    if not city and not by_store and (chain or compare_only):
        if not precomputed_ok(conn):
            if compare_only:
                raise Unsupported("search_item_prices not usable for a nationwide compare")
            mode = "chain-live"
        else:
            mode = "national-precomputed" if compare_only else "chain-precomputed"
    else:
        mode = "stores"

    empty = FilteredResult(query=q, total_matches=0, comparable_count=0, has_more=False, products=[],
                           mode=mode, exact_counts=True)
    if len(V.normalize(q).replace(" ", "")) < 2:
        return empty

    ranked, corrected_from = V.ranked_candidates(conn, q, aliases, first_limit=STREAM_FIRST)
    lap("candidates")
    if not ranked.total:
        return empty

    fks: list[int] = []
    if mode in ("stores", "chain-live"):
        fks = resolve_stores(conn, city, chain)
        if not fks:
            return empty
        filt = store_filter(conn, fks)
    else:
        filt = precomputed_filter(conn, chain if mode == "chain-precomputed" else None)
    verdict = compare_verdict if compare_only else (lambda inf: YES)
    weight = (lambda inf: inf.rows) if by_store else (lambda inf: 1)
    walk = Walk(ranked, filt, verdict, weight)

    need = offset + limit + 1
    live_city = city if mode == "stores" else None
    live_chain = chain
    while True:
        walk.ensure(need)
        maybes = walk.maybes(need)
        if not maybes:
            break
        codes = [it[0]["item_code"] for it in maybes]
        priced = group_by_product(fetch_prices(conn, codes, city=live_city, chain_id=live_chain, page=True))
        walk.settle({c: c in priced and compare_ok(priced[c]) for c in codes})
    lap("filter")

    products, source, has_more = _page(conn, walk, mode, offset, limit, by_store, compare_only,
                                       live_city, live_chain, eilat_fks)
    lap("prices")
    t.pop("_last", None)
    t["total"] = round((time.perf_counter() - t.pop("start")) * 1000, 1)

    if walk.exhausted:
        total = walk.size() if by_store else walk.any_items
        comparable = 0 if by_store else walk.multi_items
    else:
        total, comparable = ranked.total, (0 if by_store else ranked.comparable)
    return FilteredResult(query=q, total_matches=total, comparable_count=comparable, has_more=has_more,
                          products=products, corrected_from=corrected_from, timings_ms=t,
                          prices_source=source, mode=mode, walked=walk.walked, exact_counts=walk.exhausted)


def _page(conn, walk: Walk, mode: str, offset: int, limit: int, by_store: bool, compare_only: bool,
          live_city, live_chain, eilat_fks) -> tuple[list[dict], str, bool]:
    """(products, prices source, has_more) for the page."""
    if by_store:
        return _store_page(conn, walk, offset, limit, live_city, live_chain)

    page = walk.items[offset:offset + limit]
    has_more = len(walk.items) > offset + limit
    codes = [it[0]["item_code"] for it in page]
    if not codes:
        return [], "live", has_more
    rows, source = None, "live"
    if mode in ("chain-precomputed", "national-precomputed"):
        rows = V._try_precomputed(conn, codes)
        if rows is not None:
            source = "precomputed"
            if live_chain:
                keep = set(live_chain)
                rows = [r for r in rows if r["chain_id"] in keep]
    if rows is None:
        if mode == "stores":
            rows = fetch_prices(conn, codes, city=live_city, chain_id=live_chain, page=True)
        else:
            # Nationwide: the Eilat rule over ALL chains, as search_item_prices
            # was built, then the chain filter - so this fallback and the
            # precomputed rows agree.
            rows = V.drop_eilat(fetch_prices(conn, codes, page=True), eilat_fks, None)
            if live_chain:
                keep = set(live_chain)
                rows = [r for r in rows if r["chain_id"] in keep]
    by_item = group_by_product(rows)
    products = [by_item[c] for c in codes if c in by_item]
    if compare_only:
        products = [p for p in products if compare_ok(p)]
    return products, source, has_more


def _store_page(conn, walk: Walk, offset: int, limit: int, live_city, live_chain):
    """group_by=store: rows [offset, offset + limit) of the items' store rows in rank order."""
    acc, start, picked = 0, None, []
    for it in walk.items:
        n = it[1].rows
        if acc + n > offset and acc < offset + limit:
            if start is None:
                start = acc
            picked.append(it[0]["item_code"])
        acc += n
        if acc >= offset + limit:
            break
    has_more = walk.size() > offset + limit
    if not picked:
        return [], "live", has_more
    rank_of = {c: i for i, c in enumerate(picked)}
    rows = fetch_prices(conn, picked, city=live_city, chain_id=live_chain, page=True)
    entries = group_by_store(rows)
    entries.sort(key=lambda p: (rank_of[p["item_code"]], p["cheapest_price"],
                                p["quotes"][0]["chain_id"], str(p["quotes"][0]["store_id"])))
    lo = offset - start
    return entries[lo:lo + limit], "live", has_more
