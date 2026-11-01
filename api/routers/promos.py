from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from api import categories as cats
from api.dependencies import get_db
from api.models import FlatPromoItem, GroupedPromoItem, HotPromoItem, PromoItem
from db.promo_curation import get_curation
from db.query import (
    fetch_flat_promos, fetch_grouped_promos, fetch_promo_chains, fetch_promo_cities,
    fetch_promoted_promos, fetch_promos, fetch_promos_bulk, fetch_today_promos, lookup_store_fk,
)

# SU11A-60: a list read with no chain, category, search text or branch scans
# every active promo; the web no longer asks for it, so such a call gets at most
# UNFILTERED_CAP rows in all (offset + limit).
UNFILTERED_CAP = 100

router = APIRouter(tags=["Promos"])


class _StoreRef(BaseModel):
    chain_id: str
    store_id: str


class _PromoBulkRequest(BaseModel):
    stores: list[_StoreRef]


@router.post(
    "/promos/bulk",
    response_model=dict[str, list[PromoItem]],
    summary="Active promos for many stores in one request",
)
def promos_bulk(
    body: _PromoBulkRequest,
    conn: Connection = Depends(get_db),
):
    pairs = [(s.chain_id, s.store_id) for s in body.stores]
    return fetch_promos_bulk(conn, pairs)


@router.get(
    "/promos/today",
    response_model=list[HotPromoItem],
    summary="Hot deals — active promos with ≥10% discount or 1+1",
)
def promos_today(
    city:     Optional[str] = Query(None, description="Filter by city_canonical"),
    chain_id: Optional[str] = Query(None, description="Filter by chain_id"),
    conn: Connection = Depends(get_db),
):
    """SU11A-58: admin pins first, hidden promotions left out (db/promo_curation.py)."""
    cur = get_curation(conn)
    return fetch_today_promos(conn, city=city, chain_id=chain_id, curation=cur)


@router.get(
    "/promos/grouped",
    response_model=list[GroupedPromoItem],
    summary="Per-branch promos for the chain → city → branch view",
)
def promos_grouped(
    chain:  Optional[str] = Query(None, description="Filter by chain_id"),
    city:   Optional[str] = Query(None, description="Filter by city_canonical"),
    branch: Optional[int] = Query(None, description="Filter to one branch by stores.id (store_fk)"),
    bands:  Optional[str] = Query(None, description="CSV of discount bands: 0-10,11-25,26-50,51-75,76-99. Lower bound exclusive, upper inclusive — so 0% and 100% match no band"),
    promo_type: Optional[str] = Query(None, description="CSV of shape classes: gift,bundle,fixed,discount,basket"),
    q:      Optional[str] = Query(None, description="Search product name (substring) or exact item_code"),
    ending_within_hours: Optional[int] = Query(None, ge=1, description="Only promos ending within N hours"),
    sort:   str           = Query("discount", pattern="^(discount|savings|ending)$", description="Row order WITHIN each branch"),
    limit:  int           = Query(500, ge=1, le=5000, description="Max rows returned"),
    offset: int           = Query(0, ge=0, description="Pagination offset"),
    category: Optional[str] = Query(None, max_length=32, description="SU11A-60: category node id (/categories/tree); items labelled under it. Low-confidence labels count at department level only"),
    conn: Connection = Depends(get_db),
):
    """
    Active promos ordered chain → city → branch, then by `sort` within each
    branch. Flat rows; the frontend groups them. Not deduplicated: the same
    item_code appears once per branch on purpose.

    `discount_price` is the raw bundle total — compare `unit_price` against
    `shelf_price`, never `discount_price`.

    Two kinds of row come back, distinguished by `promo_kind`:
      * `unit`   — has a per-unit price, so unit_price / discount_pct / savings
                   are populated.
      * `basket` — a conditional or spend-threshold deal with no derivable unit
                   price (including rows whose min_qty is a spend figure rather
                   than a count). unit_price, discount_pct and savings are NULL;
                   read promo_description and min_purchase_amount instead.
                   A `bands` filter excludes these by construction, since they
                   have no percentage to band.

    SU11A-58: promotions an admin pinned lead each branch (pinned / sponsored
    on the row; sponsored = the card shows "ממומן"), hidden ones are left out.
    Display only: search, compare and basket prices never read the curation.

    SU11A-60: `category`; without chain, category, q and branch at most
    UNFILTERED_CAP rows in all.
    """
    cur = get_curation(conn)
    args = _filters(conn, chain, city, branch, bands, promo_type, q, ending_within_hours, sort, category)
    if args is None:
        return []
    limit = _capped(args, limit, offset)
    if limit == 0:
        return []
    return fetch_grouped_promos(conn, curation=cur, limit=limit, offset=offset, **args)


def _csv(v: str | None) -> list[str] | None:
    return [x.strip() for x in v.split(",") if x.strip()] if v else None


def _filters(conn, chain, city, branch, bands, promo_type, q, ending_within_hours, sort, category) -> dict | None:
    """The shared filter arguments; None = an unknown category (nothing matches)."""
    cat = None
    if category:
        cat = cats.promo_filter(conn, category)
        if cat is None:
            return None
    return dict(chain_id=chain, city=city, branch=branch, bands=_csv(bands), promo_types=_csv(promo_type),
                q=q, ending_within_hours=ending_within_hours, sort=sort, category=cat)


def _capped(args: dict, limit: int, offset: int) -> int:
    if args["chain_id"] or args["category"] or args["q"] or args["branch"] is not None:
        return limit
    return max(0, min(limit, UNFILTERED_CAP - offset))


_FILTER_DOC = dict(
    chain=Query(None, description="Filter by chain_id"),
    city=Query(None, description="Filter by city_canonical"),
    bands=Query(None, description="CSV of discount bands, as /promos/grouped"),
    promo_type=Query(None, description="CSV of shape classes, as /promos/grouped"),
    q=Query(None, description="Product name (substring) or exact item_code"),
    category=Query(None, max_length=32, description="Category node id, as /promos/grouped"),
)


@router.get(
    "/promos/list",
    response_model=list[FlatPromoItem],
    summary="Promos across chains, one card per chain + product + promotion (SU11A-60)",
)
def promos_list(
    chain:  Optional[str] = _FILTER_DOC["chain"],
    city:   Optional[str] = _FILTER_DOC["city"],
    bands:  Optional[str] = _FILTER_DOC["bands"],
    promo_type: Optional[str] = _FILTER_DOC["promo_type"],
    q:      Optional[str] = _FILTER_DOC["q"],
    category: Optional[str] = _FILTER_DOC["category"],
    ending_within_hours: Optional[int] = Query(None, ge=1, description="Only promos ending within N hours"),
    sort:   str = Query("discount", pattern="^(discount|savings|ending)$", description="Order across chains"),
    limit:  int = Query(30, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, le=10000, description="Rows already shown"),
    conn: Connection = Depends(get_db),
):
    """The promos page's flat list (no chain chosen): each row is the best
    branch of a (chain, product, promotion) by `sort`, with branch_count.
    Hidden promotions are left out; pins are not lifted (see /promos/promoted)
    but carry pinned / sponsored. Same cap as /promos/grouped when unfiltered."""
    cur = get_curation(conn)
    args = _filters(conn, chain, city, None, bands, promo_type, q, ending_within_hours, sort, category)
    if args is None:
        return []
    limit = _capped(args, limit, offset)
    if limit == 0:
        return []
    args.pop("branch")
    return fetch_flat_promos(conn, curation=cur, limit=limit, offset=offset, **args)


@router.get(
    "/promos/promoted",
    response_model=list[FlatPromoItem],
    summary="מבצעים מקודמים: the active pins matching the filters (SU11A-60)",
)
def promos_promoted(
    chain:  Optional[str] = _FILTER_DOC["chain"],
    city:   Optional[str] = _FILTER_DOC["city"],
    bands:  Optional[str] = _FILTER_DOC["bands"],
    promo_type: Optional[str] = _FILTER_DOC["promo_type"],
    q:      Optional[str] = _FILTER_DOC["q"],
    category: Optional[str] = _FILTER_DOC["category"],
    ending_within_hours: Optional[int] = Query(None, ge=1, description="Only promos ending within N hours"),
    conn: Connection = Depends(get_db),
):
    """At most 10 pinned promotions, in pin rank order, across chains: one row
    per promotion (its best item and branch by discount) with branch_count in
    the city and item_count. sponsored = show ממומן. Empty when nothing
    matches. Display only: no price reads the curation."""
    cur = get_curation(conn)
    if not cur.pins:
        return []
    args = _filters(conn, chain, city, None, bands, promo_type, q, ending_within_hours, "discount", category)
    if args is None:
        return []
    args.pop("branch")
    return fetch_promoted_promos(conn, curation=cur, **args)


@router.get("/promos/cities", response_model=list[str], summary="Cities with active promos")
def promo_cities(conn: Connection = Depends(get_db)):
    return fetch_promo_cities(conn)


@router.get("/promos/chains", summary="Chains with active promos")
def promo_chains(conn: Connection = Depends(get_db)):
    return fetch_promo_chains(conn)


@router.get(
    "/promos/store/{chain_id}/{store_id}",
    response_model=list[PromoItem],
    summary="Active promos for a store by chain_id + store_id",
)
def promos_by_store(
    chain_id: str,
    store_id: str,
    conn: Connection = Depends(get_db),
):
    fk = lookup_store_fk(conn, chain_id, store_id)
    if fk is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return fetch_promos(conn, fk)


@router.get(
    "/promos/{store_fk}",
    response_model=list[PromoItem],
    summary="Active promos for a store by stores.id (FK)",
)
def promos_by_fk(
    store_fk: int,
    conn: Connection = Depends(get_db),
):
    return fetch_promos(conn, store_fk)
