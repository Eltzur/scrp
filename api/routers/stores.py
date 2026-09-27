"""Store coordinates for on-device distance (SU10S-10).

ONE endpoint, and it takes NO input at all — that is the entire design, not an
oversight. The client downloads this table once, holds it, and computes
distance to the user locally. The user's location therefore never leaves the
device.

That matters concretely rather than theoretically: gunicorn and nginx both log
full request paths, so a `?lat=…&lon=…` parameter would write a user's
coordinates to disk on every single request, in two places, indefinitely. A
"find stores near me" endpoint is the obvious shape and the wrong one.

The payload is small enough to make that practical — under a thousand rows of
four short fields. See SU10S-10 in docs/super/handoff_super.md.

ATTRIBUTION: street- and house-level coordinates come from OpenStreetMap via
Nominatim and are ODbL-licensed. Any UI showing them owes a visible
"© OpenStreetMap contributors". City-level rows come from the CBS 2024
locality table and carry no such requirement, but the two are mixed here, so
the attribution is owed wherever this endpoint is consumed.
"""
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.dependencies import get_db

router = APIRouter(tags=["Stores"])

# One day. Coordinates change only when a store is re-geocoded, which the
# weekly timer does at most once a week.
_MAX_AGE = 86_400


class StoreCoordinate(BaseModel):
    store_fk: int = Field(description="stores.id — matches `store_fk` on every price quote row")
    lat: float
    lon: float
    precision: str = Field(
        description="'address' (house-level), 'street' (street centreline), or "
                    "'city' (municipal centroid — approximate, and the majority; "
                    "do not present these as a precise location)"
    )


_SQL = """
    SELECT id, round(lat::numeric, 5) AS lat, round(lon::numeric, 5) AS lon,
           geo_precision
    FROM stores
    WHERE is_physical AND lat IS NOT NULL AND lon IS NOT NULL
    ORDER BY id
"""


@router.get("/stores/coordinates", response_model=list[StoreCoordinate],
            summary="Coordinates for every physical store (no input, cacheable)")
def store_coordinates(response: Response, conn: Connection = Depends(get_db)):
    """Every physical store that has a coordinate.

    Excludes online/fulfilment rows (`is_physical = false`) — those carry a
    real city in the data and would otherwise look like ordinary branches the
    user could walk into.

    Rounded to 5 decimals: about 1 m, far finer than a city centroid and
    finer than the underlying data justifies, but it keeps the payload small
    without ever being the limiting factor.
    """
    response.headers["Cache-Control"] = f"public, max-age={_MAX_AGE}"
    rows = conn.execute(text(_SQL)).mappings().all()
    return [
        StoreCoordinate(store_fk=r["id"], lat=float(r["lat"]), lon=float(r["lon"]),
                        precision=r["geo_precision"])
        for r in rows
    ]
