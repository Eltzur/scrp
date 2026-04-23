import re
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.engine import Connection

from api.models import ProductWithPrices, Product, PriceQuote
from api.dependencies import get_db
from db.query import fetch_product, group_by_product
from api.routers.search import _to_model

router = APIRouter(tags=["Product"])

_BARCODE_RE = re.compile(r"^\d{8,14}$")


@router.get(
    "/product/{barcode}",
    response_model=ProductWithPrices,
    summary="All prices for one barcode",
)
def product(
    barcode: str = Path(description="EAN/barcode — 8 to 14 digits"),
    conn: Connection = Depends(get_db),
):
    """
    Fetch every price quote across all stores for a single barcode.
    Returns 404 if the barcode is not found in any chain.
    Returns 400 if the barcode format is invalid (not 8–14 digits).
    """
    if not _BARCODE_RE.match(barcode):
        raise HTTPException(status_code=400, detail="Barcode must be 8–14 digits")

    rows = fetch_product(conn, barcode)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Barcode {barcode} not found")

    by_item = group_by_product(rows)
    prod    = by_item.get(barcode)
    if not prod:
        raise HTTPException(status_code=404, detail=f"Barcode {barcode} not found")

    return _to_model(prod)
