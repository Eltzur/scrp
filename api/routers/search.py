from __future__ import annotations
import logging
import os
import time
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.models import (SearchResult, SearchResultV2, ProductWithPrices, Product, PriceQuote,
                        SuggestResponse, SuggestItem)
from api.dependencies import get_db
from api.response_cache import ResponseCache
from db import search_filtered, search_v2
from db.query import find_barcodes_with_relevance, fetch_prices, group_by_product, group_by_store
from db.search_norm import normalize

router = APIRouter(tags=["Search"])
log = logging.getLogger(__name__)


def _build_result(
    query: str,
    conn: Connection,
    limit: int,
    offset: int,
    city: list[str] | None,
    chain_id: list[str] | None,
    compare_only: bool,
    group_by: Literal["chain", "store"] = "chain",
) -> SearchResult:
    words    = query.split()
    barcodes, tiers = find_barcodes_with_relevance(conn, words)
    if not barcodes:
        return SearchResult(query=query, total_matches=0, comparable_count=0, has_more=False, items=[])

    # SU11A-49 (F-01): price at most OLD_PATH_CAP candidates. A short query
    # matched ~30K barcodes and priced all of them before paging.
    n_candidates = len(barcodes)
    capped = n_candidates > OLD_PATH_CAP
    if capped:
        barcodes = cap_candidates(conn, barcodes, tiers)

    rows = fetch_prices(conn, barcodes, city=city, chain_id=chain_id)

    if group_by == "store":
        all_products = group_by_store(rows)
        total = len(all_products)
        page  = all_products[offset : offset + limit]
        items = [_to_model(p) for p in page]
        return SearchResult(
            query=query,
            total_matches=n_candidates if capped else total,
            comparable_count=0,
            has_more=(offset + len(items)) < total,
            items=items,
        )

    by_item  = group_by_product(rows)
    multi    = {c: p for c, p in by_item.items() if p["chains_count"] >= 2}
    single   = {c: p for c, p in by_item.items() if p["chains_count"] == 1}

    # Relevance is the PRIMARY key; the previous ordering is nested underneath
    # it rather than replaced — multi-chain still outranks single-chain, and
    # cheapest still wins, but only among items of equal relevance.
    # item_code is a final deterministic tie-break: without it, equal-priced
    # items ordered arbitrarily and offset pages could overlap between requests
    # (test_search_has_more_and_pagination was already failing on main).
    # A single-source promo-only product (no shelf price anywhere — every quote
    # is a promo) is not a cross-chain comparison, but it IS real savings info
    # that compare mode (the default view) would otherwise hide entirely, since
    # its chains_count is 1. Surface those specifically; ordinary single-chain
    # shelf products stay filtered in compare mode as before (SU10A-6).
    def _is_promo_only(p: dict) -> bool:
        return bool(p["quotes"]) and all(q["promo_kind"] == "promo_only" for q in p["quotes"])

    pool = [(c, p) for c, p in multi.items()]
    if compare_only:
        pool += [(c, p) for c, p in single.items() if _is_promo_only(p)]
    else:
        pool += [(c, p) for c, p in single.items()]

    ordered = [
        p for _, p in sorted(pool, key=lambda cp: (
            tiers.get(cp[0], 3),                        # 1. relevance tier
            0 if cp[1]["chains_count"] >= 2 else 1,     # 2. multi-chain first
            cp[1]["cheapest_price"] or 0,               # 3. cheapest first
            cp[0],                                      # 4. deterministic
        ))
    ]

    total = len(ordered)
    page  = ordered[offset : offset + limit]
    items = [_to_model(p) for p in page]

    return SearchResult(
        query=query,
        # Capped: the name-match count (the true number of matching products;
        # some may have no price in the filtered stores). comparable_count and
        # the pages cover the priced OLD_PATH_CAP only - nothing past them.
        total_matches=n_candidates if capped else len(by_item),
        comparable_count=len(multi),
        has_more=(offset + len(items)) < total,
        items=items,
    )


# ---------------------------------------------------------------------------
# Old-path candidate cap (SU11A-49, F-01)
# ---------------------------------------------------------------------------
# The old path (/compare, and /search with city / chain / group_by=store /
# engine=v1) prices every name match before paging. A two-letter query matched
# ~30K of 171K barcodes against the 7.8M-row prices table, anonymously. Above
# OLD_PATH_CAP candidates only the best OLD_PATH_CAP are priced, chosen by the
# same price-neutral order search v2 uses (search_v2.rank_key over
# search_items: relevance tier, 2+ chains, popularity, chains, shorter name,
# item_code), with this path's own tiers. Items not in search_items (no live
# quote at the last build) come after every live one. If search_items is
# missing, the order is tier then item_code.
#
# Effect: total_matches is still the full match count, the pages within the
# cap are exactly as before (same order keys, same has_more), and there are no
# results past item OLD_PATH_CAP (has_more turns false there).

OLD_PATH_CAP = 1000

_RANK_SQL = text("""
    SELECT item_code, name_norm, chains_live, popularity
    FROM search_items
    WHERE item_code = ANY(CAST(:codes AS text[]))
""")


def cap_candidates(conn: Connection, codes: list[str], tiers: dict[str, int],
                   cap: int = OLD_PATH_CAP) -> list[str]:
    """The best `cap` of `codes` (all of them when there are not more)."""
    if len(codes) <= cap:
        return codes
    try:
        # SAVEPOINT: a missing search_items must not abort the request.
        with conn.begin_nested():
            info = {r["item_code"]: dict(r)
                    for r in conn.execute(_RANK_SQL, {"codes": list(codes)}).mappings()}
    except Exception as exc:  # noqa: BLE001 - fall back to the plain order
        log.warning("old-path cap: search_items rank unavailable (%s)", type(exc).__name__)
        info = None

    def key(code: str) -> tuple:
        tier = tiers.get(code, 3)
        r = info.get(code) if info else None
        if r is None:
            return (1, tier, code)
        return (0, *search_v2.rank_key(r, tier))

    return sorted(codes, key=key)[:cap]


def _to_model(p: dict) -> ProductWithPrices:
    product = Product(
        item_code=p["item_code"],
        canonical_name=p["canonical_name"],
        manufacturer=p["manufacturer"],
        unit_of_measure=p["unit_of_measure"],
        is_weighted=p["is_weighted"],
        names_per_chain=p["names_per_chain"],
    )
    quotes = [
        PriceQuote(
            chain_id=q["chain_id"],
            chain_name=q["chain_name"],
            store_id=q["store_id"],
            store_name=q["store_name"],
            city=q["city"],
            price=q["price"],
            unit_price=q["unit_price"],
            unit_of_measure=q["unit_of_measure"],
            updated_at=q["updated_at"],
            delta_from_cheapest=q["delta_from_cheapest"],
            is_promo=q.get("is_promo", False),
            promo_kind=q.get("promo_kind", "shelf"),
            shelf_price=q.get("shelf_price"),
            promo_price=q.get("promo_price"),
            promo_min_qty=q.get("promo_min_qty"),
            promo_description=q.get("promo_description"),
            promo_end=q.get("promo_end"),
            store_fk=q.get("store_fk"),
        )
        for q in p["quotes"]
    ]
    return ProductWithPrices(
        product=product,
        quotes=quotes,
        cheapest_price=p["cheapest_price"],
        most_expensive_price=p["most_expensive_price"],
        chains_count=p["chains_count"],
    )


@router.get("/search", response_model=SearchResult, summary="Search products by name")
def search(
    q:        str           = Query(..., min_length=1, max_length=200, description="Product name or manufacturer (multi-word AND)"),
    limit:    int           = Query(30, ge=1, le=100, description="Max products returned"),
    offset:   int           = Query(0, ge=0, description="Pagination offset"),
    city:     list[str] | None   = Query(None, description="Filter to stores in these cities (repeat param for multiple)"),
    chain:    list[str] | None   = Query(None, description="Filter to chain_ids (repeat param for multiple)"),
    group_by: Literal["chain", "store"] = Query("chain", description="Group results by chain or individual store"),
    engine:   str | None = Query(None, description="Search engine: 'v2' (used when SEARCH_V2=test or on) or 'v1' (forces the old engine); other values are ignored"),
    conn:     Connection = Depends(get_db),
    request:  Request = None,
    response: Response = None,
):
    """
    Search for products by Hebrew or English name. Multi-word queries match ALL words
    in any order. Returns multi-chain products first, then single-chain.
    Supports pagination via offset. group_by=store returns one row per store.
    """
    t0 = time.perf_counter()
    if _use_v2(_v2_mode(), engine, city, chain, group_by):
        v2 = _search_v2(q, conn, limit, offset, city, _signed_in(request))
        if v2 is not None:
            return v2
    elif (city or chain or group_by != "chain") and _use_filtered(_filtered_mode(), engine):
        fr = _search_filtered(q, conn, limit, offset, city, chain, group_by, compare_only=False)
        if fr is not None:
            return fr
    result = _build_result(q, conn, limit, offset, city, chain, compare_only=False, group_by=group_by)
    if response is not None:
        response.headers["Server-Timing"] = f"total;dur={_ms(t0)}"
    return result


# ---------------------------------------------------------------------------
# Search v2 switch (SU11A-36)
# ---------------------------------------------------------------------------
# SEARCH_V2 (from the API's systemd EnvironmentFile; read per request):
#   off  (default, also when unset or unknown) - never v2; /search is unchanged
#   test - v2 only when the request says engine=v2
#   on   - v2 whenever the request has no city and no chain filter and
#          group_by=chain (what the mobile app sends); engine=v1 forces the old path
# Requests with a city / chain filter or group_by=store, and /compare, are not
# SEARCH_V2's: they follow SEARCH_V2_FILTERED (SU11A-50, below).
# Rollback: set SEARCH_V2=off and restart scrp-api.

def _v2_mode() -> str:
    mode = (os.environ.get("SEARCH_V2") or "off").strip().lower()
    return mode if mode in ("off", "test", "on") else "off"


def _use_v2(mode: str, engine: str | None, city, chain, group_by: str) -> bool:
    if mode == "off" or city or chain or group_by != "chain":
        return False
    if mode == "test":
        return engine == "v2"
    return engine != "v1"


# ---------------------------------------------------------------------------
# Filtered search on the v2 path (SU11A-50)
# ---------------------------------------------------------------------------
# SEARCH_V2_FILTERED (scrp-api EnvironmentFile; read per request):
#   off  (default, also when unset or unknown) - /compare and filtered /search
#        use the old path, exactly as before
#   test - the filtered v2 path only when the request says engine=v2
#   on   - every /compare, and every /search with a city / chain filter or
#          group_by=store; engine=v1 forces the old path
# The unfiltered /search keeps following SEARCH_V2. The filtered path
# (db/search_filtered.py) runs in a SAVEPOINT; any error or timeout there logs a
# warning (exception type only, never the query) and the old path answers.
# Rollback: SEARCH_V2_FILTERED=off and restart scrp-api.

def _filtered_mode() -> str:
    mode = (os.environ.get("SEARCH_V2_FILTERED") or "off").strip().lower()
    return mode if mode in ("off", "test", "on") else "off"


def _use_filtered(mode: str, engine: str | None) -> bool:
    if mode == "off" or engine == "v1":
        return False
    if mode == "test":
        return engine == "v2"
    return True


def _search_filtered(q: str, conn: Connection, limit: int, offset: int, city, chain,
                     group_by: str, compare_only: bool) -> Response | None:
    """The filtered v2 answer, or None (the caller then uses the old path).

    /search answers carry engine="v2" and corrected_from like an unfiltered v2
    answer; /compare answers keep /compare's exact fields. No Cache-Control:
    the prices are live, as on the old path.
    """
    t0 = time.perf_counter()
    try:
        with conn.begin_nested():
            r = search_filtered.run(conn, q, limit=limit, offset=offset, city=city, chain=chain,
                                    group_by=group_by, compare_only=compare_only)
    except search_filtered.Unsupported as exc:
        log.info("filtered search not available here, using the old path: %s", exc)
        return None
    except search_v2.V2Unavailable as exc:
        log.warning("filtered search unavailable, using the old path: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 - never a 500; never log the query (no traceback: it carries the SQL parameters)
        log.warning("filtered search failed, using the old path: %s", type(exc).__name__)
        return None
    fields = dict(query=r.query, total_matches=r.total_matches, comparable_count=r.comparable_count,
                  has_more=r.has_more, items=[_to_model(p) for p in r.products])
    if compare_only:
        body = SearchResult(**fields).model_dump_json().encode()
    else:
        body = SearchResultV2(**fields, corrected_from=r.corrected_from).model_dump_json().encode()
    tm = r.timings_ms
    timing = (f"candidates;dur={tm.get('candidates', 0)}, filter;dur={tm.get('filter', 0)}, "
              f"prices;dur={tm.get('prices', 0)};desc={r.prices_source}, total;dur={_ms(t0)}")
    return Response(content=body, media_type="application/json", headers={"Server-Timing": timing})


# ---------------------------------------------------------------------------
# Response cache, Server-Timing, Cache-Control (SU11A-47)
# ---------------------------------------------------------------------------
# v2 /search (no city / chain filter, group_by=chain - every v2 request) and
# /suggest answers are cached per worker (api/response_cache.py) and sent with
# Cache-Control: public, max-age=300. A request with an Authorization header
# gets no Cache-Control at all, as before (the SU11A-44 rule: nothing a signed-in
# client receives is marked shareable). Server-Timing carries durations only,
# never the query text.

CACHE_CONTROL = "public, max-age=300"
_cache = ResponseCache()


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def _signed_in(request: Request | None) -> bool:
    return request is not None and "authorization" in request.headers


def _json(body: bytes, timing: str, signed_in: bool) -> Response:
    headers = {"Server-Timing": timing}
    if not signed_in:
        headers["Cache-Control"] = CACHE_CONTROL
    return Response(content=body, media_type="application/json", headers=headers)


def _search_v2(q: str, conn: Connection, limit: int, offset: int, city,
               signed_in: bool = False) -> Response | None:
    """The v2 answer, or None after logging why (the caller then uses the old path).

    Runs inside a SAVEPOINT: a failed v2 statement would otherwise abort the
    request's transaction and take the fallback down with it.
    """
    t0 = time.perf_counter()
    try:
        key = ("search", normalize(q), limit, offset, "chain")
        with conn.begin_nested():
            stamp = search_v2.built_stamp(conn)
            hit = _cache.get(key, stamp, q) if not city else None
            if hit is not None:
                return _json(hit, f"cache;desc=hit, total;dur={_ms(t0)}", signed_in)
            r = search_v2.run(conn, q, limit=limit, offset=offset, city=city)
        result = SearchResultV2(
            query=r.query,
            total_matches=r.total_matches,
            comparable_count=r.comparable_count,
            has_more=r.has_more,
            items=[_to_model(p) for p in r.products],
            corrected_from=r.corrected_from,
        )
        # Returned as a Response so FastAPI does not filter it down to the
        # SearchResult response_model (which would drop engine/corrected_from).
        body = result.model_dump_json().encode()
        if not city:
            _cache.put(key, stamp, q, body, exact_only=r.corrected_from is not None)
        tm = r.timings_ms
        timing = (f"candidates;dur={round(tm.get('candidates', 0) + tm.get('rank', 0), 1)}, "
                  f"prices;dur={tm.get('prices', 0)};desc={r.prices_source}, total;dur={_ms(t0)}")
        return _json(body, timing, signed_in)
    except search_v2.V2Unavailable as exc:
        log.warning("search v2 unavailable, using the old search: %s", exc)
    except Exception as exc:  # noqa: BLE001 - v2 must never turn into a 500
        log.warning("search v2 failed, using the old search: %s", type(exc).__name__, exc_info=True)
    return None


@router.get("/suggest", response_model=SuggestResponse, summary="Type-ahead suggestions (no prices)")
def suggest(
    q:       str = Query("", max_length=200, description="What has been typed so far"),
    limit:   int = Query(8, ge=1, le=search_v2.SUGGEST_MAX, description="Max suggestions (default 8, max 10)"),
    conn:    Connection = Depends(get_db),
    request: Request = None,
):
    """
    Type-ahead for the search box: terms (completing the last word), brands, and
    products (kind=product carries item_code: open it; brand / term: search for
    text). Anonymous, no prices: reads search_items and search_lexicon only.
    Same normalization and typo correction as /search. 8-14 digits answer that
    barcode's product, if it is a live item. Fewer than 1 character: no items.
    """
    t0 = time.perf_counter()
    signed_in = _signed_in(request)
    empty = SuggestResponse(query=q).model_dump_json(exclude_none=True).encode()
    q_norm = normalize(q)
    if not q_norm:
        return _json(empty, f"total;dur={_ms(t0)}", signed_in)
    key = ("suggest", q_norm, limit, 0, "")
    try:
        with conn.begin_nested():
            stamp = search_v2.built_stamp(conn)
            hit = _cache.get(key, stamp, q)
            if hit is not None:
                return _json(hit, f"cache;desc=hit, total;dur={_ms(t0)}", signed_in)
            s = search_v2.suggest(conn, q, limit=limit)
    except search_v2.V2Unavailable as exc:
        log.warning("suggest unavailable: %s", exc)
        return Response(content=empty, media_type="application/json",
                        headers={"Server-Timing": f"total;dur={_ms(t0)}"})
    except Exception as exc:  # noqa: BLE001 - a broken type-ahead must not break the search box
        log.warning("suggest failed: %s", type(exc).__name__, exc_info=True)
        return Response(content=empty, media_type="application/json",
                        headers={"Server-Timing": f"total;dur={_ms(t0)}"})
    body = SuggestResponse(query=q, corrected_from=s.corrected_from,
                           items=[SuggestItem(**i) for i in s.items]).model_dump_json(exclude_none=True).encode()
    _cache.put(key, stamp, q, body, exact_only=s.corrected_from is not None)
    return _json(body, f"candidates;dur={s.timings_ms.get('total', 0)}, total;dur={_ms(t0)}", signed_in)


@router.get("/compare", response_model=SearchResult, summary="Cross-chain price comparison")
def compare(
    q:      str           = Query(..., min_length=1, max_length=200, description="Product name or manufacturer"),
    limit:  int           = Query(30, ge=1, le=100, description="Max products returned"),
    offset: int           = Query(0, ge=0, description="Pagination offset"),
    city:   list[str] | None  = Query(None, description="Filter to stores in these cities (repeat param for multiple)"),
    engine: str | None = Query(None, description="'v2' (used when SEARCH_V2_FILTERED=test or on) or 'v1' (forces the old path); other values are ignored"),
    conn:   Connection = Depends(get_db),
    response: Response = None,
):
    """
    Like /search but returns ONLY products available in 2+ chains, with
    delta_from_cheapest on each quote showing how much more expensive vs the cheapest chain.
    """
    t0 = time.perf_counter()
    if _use_filtered(_filtered_mode(), engine):
        fr = _search_filtered(q, conn, limit, offset, city, None, "chain", compare_only=True)
        if fr is not None:
            return fr
    result = _build_result(q, conn, limit, offset, city, chain_id=None, compare_only=True)
    if response is not None:
        response.headers["Server-Timing"] = f"total;dur={_ms(t0)}"
    return result
