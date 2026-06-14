from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from api.dependencies import get_db
from api.models import HotPromoItem, PromoItem
from db.query import fetch_promos, fetch_promos_bulk, fetch_today_promos, lookup_store_fk

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
def promos_today(conn: Connection = Depends(get_db)):
    """All active promos with discount_pct >= 10 or reward_type=1+1, ordered by discount_pct desc."""
    return fetch_today_promos(conn)


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
