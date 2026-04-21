from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, Depends, Query
import sqlite3

from api.models import SearchResult, ProductWithPrices, Product, PriceQuote
from api.dependencies import get_db
from db.query import find_barcodes, fetch_prices, group_by_product, group_by_store

router = APIRouter(tags=["Search"])


def _build_result(
    query: str,
    conn: sqlite3.Connection,
    limit: int,
    offset: int,
    city: str | None,
    chain_id: str | None,
    compare_only: bool,
    group_by: Literal["chain", "store"] = "chain",
) -> SearchResult:
    words    = query.split()
    barcodes = find_barcodes(conn, words)
    if not barcodes:
        return SearchResult(query=query, total_matches=0, comparable_count=0, has_more=False, items=[])

    rows = fetch_prices(conn, barcodes, city=city, chain_id=chain_id)

    if group_by == "store":
        all_products = group_by_store(rows)
        total = len(all_products)
        page  = all_products[offset : offset + limit]
        items = [_to_model(p) for p in page]
        return SearchResult(
            query=query,
            total_matches=total,
            comparable_count=0,
            has_more=(offset + len(items)) < total,
            items=items,
        )

    by_item  = group_by_product(rows)
    multi    = {c: p for c, p in by_item.items() if p["chains_count"] >= 2}
    single   = {c: p for c, p in by_item.items() if p["chains_count"] == 1}

    ordered = (
        sorted(multi.values(),  key=lambda p: p["cheapest_price"] or 0) +
        ([] if compare_only else sorted(single.values(), key=lambda p: p["cheapest_price"] or 0))
    )

    total = len(ordered)
    page  = ordered[offset : offset + limit]
    items = [_to_model(p) for p in page]

    return SearchResult(
        query=query,
        total_matches=len(by_item),
        comparable_count=len(multi),
        has_more=(offset + len(items)) < total,
        items=items,
    )


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
    city:     str | None    = Query(None, description="Filter to stores in this city"),
    chain:    str | None    = Query(None, description="Filter to one chain_id"),
    group_by: Literal["chain", "store"] = Query("chain", description="Group results by chain or individual store"),
    conn:     sqlite3.Connection = Depends(get_db),
):
    """
    Search for products by Hebrew or English name. Multi-word queries match ALL words
    in any order. Returns multi-chain products first, then single-chain.
    Supports pagination via offset. group_by=store returns one row per store.
    """
    return _build_result(q, conn, limit, offset, city, chain, compare_only=False, group_by=group_by)


@router.get("/compare", response_model=SearchResult, summary="Cross-chain price comparison")
def compare(
    q:      str           = Query(..., min_length=1, max_length=200, description="Product name or manufacturer"),
    limit:  int           = Query(30, ge=1, le=100, description="Max products returned"),
    offset: int           = Query(0, ge=0, description="Pagination offset"),
    city:   str | None    = Query(None, description="Filter to stores in this city"),
    conn:   sqlite3.Connection = Depends(get_db),
):
    """
    Like /search but returns ONLY products available in 2+ chains, with
    delta_from_cheapest on each quote showing how much more expensive vs the cheapest chain.
    """
    return _build_result(q, conn, limit, offset, city, chain_id=None, compare_only=True)
