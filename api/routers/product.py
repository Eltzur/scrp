import os
import re
from pathlib import Path as FsPath

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.models import ProductWithPrices, Product, PriceQuote, ProductDetails
from api.dependencies import get_db
from db.query import fetch_product, group_by_product, fetch_gs1_details
from api.routers.search import _to_model

router = APIRouter(tags=["Product"])

_BARCODE_RE = re.compile(r"^\d{8,14}$")

# Images are served through the API rather than nginx on purpose: they live in
# dude's home directory, which www-data cannot read, and relocating ~11.5K files
# to a web root is a bigger change than proxying them. Override with the
# `gs1_images_dir` env var (lowercase per the project convention).
_IMAGE_DIR = FsPath(os.environ.get("gs1_images_dir") or (FsPath.home() / "gs1_images"))


def _image_path(item_code: str) -> FsPath | None:
    """Resolved path to this item's JPEG, or None when there isn't one.

    The fetcher names files `{gtin}.jpg`, and the enrichment join is
    `gtin = item_code`, so item_code indexes the directory directly with no DB
    round-trip. Callers MUST have validated item_code against _BARCODE_RE first;
    that digits-only check is what makes path traversal impossible here.
    """
    path = _IMAGE_DIR / f"{item_code}.jpg"
    return path if path.is_file() else None


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


@router.get(
    "/product/{barcode}/details",
    response_model=ProductDetails,
    summary="GS1 enrichment detail for one barcode",
)
def product_details(
    barcode: str = Path(description="EAN/barcode — 8 to 14 digits"),
    conn: Connection = Depends(get_db),
):
    """
    Kashrut, nutrition, ingredients and allergens for one barcode, joined from
    the GS1 catalog (active products only), plus whether an image exists.

    **A missing GS1 match is not an error.** Only ~8% of items have one, so this
    returns 200 with `has_gs1_data: false` and null sections for the rest —
    the client renders name and prices and omits the enrichment. 404 is reserved
    for a barcode that is not in the catalog at all; 400 for a malformed one.
    """
    if not _BARCODE_RE.match(barcode):
        raise HTTPException(status_code=400, detail="Barcode must be 8–14 digits")

    known = conn.execute(
        text("SELECT 1 FROM items WHERE item_code = :code"), {"code": barcode}
    ).first()
    if not known:
        raise HTTPException(status_code=404, detail=f"Barcode {barcode} not found")

    return fetch_gs1_details(conn, barcode, has_image=_image_path(barcode) is not None)


@router.get(
    "/product/{barcode}/image",
    summary="Product image (JPEG) for one barcode",
    responses={
        200: {"content": {"image/jpeg": {}}, "description": "Resized JPEG (800px, quality 80)"},
        404: {"description": "No image on file for this barcode"},
    },
    response_class=FileResponse,
)
def product_image(
    barcode: str = Path(description="EAN/barcode — 8 to 14 digits"),
):
    """
    Stream this product's GS1 image. 404 when we hold none — true for most
    barcodes, so the client should treat it as a normal placeholder case.

    Deliberately does not touch the database: the filename is the GTIN and the
    GTIN is the item_code, so a stat() answers the question outright.
    """
    if not _BARCODE_RE.match(barcode):
        raise HTTPException(status_code=400, detail="Barcode must be 8–14 digits")

    path = _image_path(barcode)
    if path is None:
        raise HTTPException(status_code=404, detail=f"No image for barcode {barcode}")

    # Content-addressed by barcode and only replaced by a re-fetch, so it is
    # safe to cache hard. immutable stops revalidation requests entirely.
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )
