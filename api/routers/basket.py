"""Basket comparison endpoint — compares a shopping list across all chains."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from api.dependencies import get_db
from db.query import fetch_prices
from scraper.city_names import normalize_city

router = APIRouter(prefix="/basket", tags=["Basket"])

ITEM_LIMIT = 25


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class BasketItem(BaseModel):
    item_code: str
    quantity: int = Field(1, ge=1)


class BasketRequest(BaseModel):
    items:     list[BasketItem]
    chain_ids: list[str] | None = None  # null = all chains
    cities:    list[str] | None = None  # null = all cities
    # Restrict pricing to these branches (stores.id). Used by mobile's
    # "nearby branches only" toggle.
    #
    # IN THE BODY, NEVER A QUERY PARAMETER. gunicorn and nginx both log full
    # request paths, so a store list in the URL would be written to disk on
    # every request — and a list of branches near someone is a location
    # disclosure by another name. The body is not logged.
    #
    # Absent (the default) means today's behaviour exactly, unchanged.
    store_fks: list[int] | None = Field(
        None, max_length=300,
        description="Optional stores.id allow-list; absent = all branches",
    )


class BasketBreakdownItem(BaseModel):
    item_code:  str
    item_name:  str | None
    price:      float | None
    quantity:   int
    subtotal:   float | None
    found:      bool


class BasketChainResult(BaseModel):
    chain_id:      str
    chain_name:    str | None
    total_price:   float
    items_found:   int
    items_missing: int
    breakdown:     list[BasketBreakdownItem]


class BasketResponse(BaseModel):
    chains:          list[BasketChainResult]
    winner_chain_id: str | None
    item_limit:      int
    items_requested: int


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/compare", response_model=BasketResponse, summary="Compare basket across chains")
def compare_basket(body: BasketRequest, conn: Connection = Depends(get_db)):
    """
    Given a list of barcodes + quantities, returns the total cost at each chain
    along with which items each chain stocks. Chains are sorted by items found
    (desc) then total price (asc). First chain in the list is the winner.
    Free tier: max 25 items.
    """
    if len(body.items) > ITEM_LIMIT:
        raise HTTPException(
            status_code=402,
            detail="סל של יותר מ-25 פריטים זמין למנויים בלבד",
        )

    barcodes  = [i.item_code for i in body.items]
    qty_map   = {i.item_code: i.quantity for i in body.items}

    # Fetch all prices for requested barcodes (unfiltered — we filter below)
    rows = fetch_prices(conn, barcodes)

    # Apply chain filter
    if body.chain_ids:
        chain_set = set(body.chain_ids)
        rows = [r for r in rows if r["chain_id"] in chain_set]

    # Apply branch allow-list. Deliberately before the city filter: it is the
    # narrowest of the three and cheapest to apply first.
    if body.store_fks:
        allowed = set(body.store_fks)
        rows = [r for r in rows if r.get("store_fk") in allowed]

    # Apply city filter (normalise both sides)
    if body.cities:
        norm_cities = {normalize_city(c) for c in body.cities if c}
        rows = [
            r for r in rows
            if r.get("city") and normalize_city(r["city"]) in norm_cities
        ]

    # Best price per (chain_id, item_code) — fetch_prices already sorts by price asc
    best: dict[tuple[str, str], dict] = {}
    chain_meta: dict[str, str | None] = {}   # chain_id → chain_name
    item_names: dict[str, str | None] = {}   # item_code → any available name

    for r in rows:
        key = (r["chain_id"], r["item_code"])
        # The basket prices from the SHELF by design. A promo-only quote has no
        # shelf price (item_price None) and float(None) was a 500 whenever it
        # was a chain's only row for an item (SU10S-26); it counts as missing
        # at that chain. A ₪0 shelf price is "no price" too: fetch_prices already
        # drops those, and this guard keeps a ₪0 from ever lowering a total.
        item_names.setdefault(r["item_code"], r.get("item_name"))
        if r["item_price"] is None or r["item_price"] <= 0:
            continue
        if key not in best:
            best[key] = r
        chain_meta.setdefault(r["chain_id"], r.get("chain_name"))

    # Build per-chain results
    chain_results: list[BasketChainResult] = []

    for chain_id, chain_name in chain_meta.items():
        breakdown: list[BasketBreakdownItem] = []
        total_price = 0.0
        found_count = 0

        for basket_item in body.items:
            code = basket_item.item_code
            qty  = basket_item.quantity
            row  = best.get((chain_id, code))

            if row:
                price    = float(row["item_price"])
                subtotal = round(price * qty, 4)
                total_price += subtotal
                found_count += 1
                breakdown.append(BasketBreakdownItem(
                    item_code=code,
                    item_name=row.get("item_name"),
                    price=price,
                    quantity=qty,
                    subtotal=round(subtotal, 2),
                    found=True,
                ))
            else:
                breakdown.append(BasketBreakdownItem(
                    item_code=code,
                    item_name=item_names.get(code),
                    price=None,
                    quantity=qty,
                    subtotal=None,
                    found=False,
                ))

        chain_results.append(BasketChainResult(
            chain_id=chain_id,
            chain_name=chain_name,
            total_price=round(total_price, 2),
            items_found=found_count,
            items_missing=len(body.items) - found_count,
            breakdown=breakdown,
        ))

    # Sort: most items found first, cheapest total as tiebreaker
    chain_results.sort(key=lambda c: (-c.items_found, c.total_price))

    winner = chain_results[0].chain_id if chain_results else None

    return BasketResponse(
        chains=chain_results,
        winner_chain_id=winner,
        item_limit=ITEM_LIMIT,
        items_requested=len(body.items),
    )
