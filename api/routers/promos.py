from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from api.dependencies import get_db
from api.models import GroupedPromoItem, HotPromoItem, PromoItem
from db.query import (
    fetch_grouped_promos, fetch_promo_chains, fetch_promo_cities,
    fetch_promos, fetch_promos_bulk, fetch_today_promos, lookup_store_fk,
)

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
    return fetch_today_promos(conn, city=city, chain_id=chain_id)


@router.get(
    "/promos/grouped",
    response_model=list[GroupedPromoItem],
    summary="Per-branch promos for the chain → city → branch view",
)
def promos_grouped(
    chain:  Optional[str] = Query(None, description="Filter by chain_id"),
    city:   Optional[str] = Query(None, description="Filter by city_canonical"),
    limit:  int           = Query(500, ge=1, le=5000, description="Max rows returned"),
    offset: int           = Query(0, ge=0, description="Pagination offset"),
    conn: Connection = Depends(get_db),
):
    """
    Every active promo with a derivable per-unit price, ordered
    chain → city → branch → discount desc. Flat rows; the frontend groups them.

    Not deduplicated: the same item_code appears once per branch on purpose.
    `discount_price` is the raw bundle total — compare `unit_price` against
    `shelf_price`, never `discount_price`. Rows whose min_qty is a spend
    threshold rather than a count (Rami Levy publishes agorot there) yield no
    unit price and are omitted from this view; they remain in the promos table.
    """
    return fetch_grouped_promos(conn, chain_id=chain, city=city, limit=limit, offset=offset)


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
