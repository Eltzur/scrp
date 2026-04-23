from fastapi import APIRouter, Depends, Query
from sqlalchemy.engine import Connection
from api.models import ChainSummary, Store, CityInfo
from api.dependencies import get_db
from db.query import fetch_chains, fetch_stores, fetch_cities

router = APIRouter(tags=["Catalog"])


@router.get("/chains", response_model=list[ChainSummary], summary="All loaded chains")
def chains(conn: Connection = Depends(get_db)):
    """Returns one entry per chain in the database with barcode and store counts."""
    return fetch_chains(conn)


@router.get("/stores", response_model=list[Store], summary="Store branches")
def stores(
    chain: str | None = Query(None, description="Filter by chain_id"),
    city:  str | None = Query(None, description="Filter by city (Hebrew or English)"),
    conn: Connection = Depends(get_db),
):
    """
    List supermarket branches. Filter by chain and/or city.
    Only returns stores that have at least store metadata loaded.
    """
    return fetch_stores(conn, chain_id=chain, city=city)


@router.get("/cities", response_model=list[CityInfo], summary="Cities with price data")
def cities(conn: Connection = Depends(get_db)):
    """Cities that have actual price data loaded, with chain/store/price counts."""
    return fetch_cities(conn)
