from fastapi import APIRouter, Depends, Query
import sqlite3
from api.models import ChainSummary, Store
from api.dependencies import get_db
from db.query import fetch_chains, fetch_stores, fetch_cities

router = APIRouter(tags=["Catalog"])


@router.get("/chains", response_model=list[ChainSummary], summary="All loaded chains")
def chains(conn: sqlite3.Connection = Depends(get_db)):
    """Returns one entry per chain in the database with barcode and store counts."""
    return fetch_chains(conn)


@router.get("/stores", response_model=list[Store], summary="Store branches")
def stores(
    chain: str | None = Query(None, description="Filter by chain_id"),
    city:  str | None = Query(None, description="Filter by city (Hebrew or English)"),
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    List supermarket branches. Filter by chain and/or city.
    Only returns stores that have at least store metadata loaded.
    """
    return fetch_stores(conn, chain_id=chain, city=city)


@router.get("/cities", response_model=list[str], summary="Cities with data")
def cities(conn: sqlite3.Connection = Depends(get_db)):
    """Distinct city names we have store data for, sorted alphabetically."""
    return fetch_cities(conn)
