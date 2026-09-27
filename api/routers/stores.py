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
from db.query import live_store_clause

router = APIRouter(tags=["Stores"])

# One day. Coordinates change only when a store is re-geocoded (weekly), and
# liveness only when the daily cron loads, so a day-old copy is at most one
# load behind.
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


# Liveness (SU10S-17) is appended at request time: a branch its chain stopped
# publishing keeps its coordinates forever, and without this it would still be
# offered as a nearby store (SU10S-16 found two, ids 184 and 195).
_SQL = """
    SELECT s.id, round(s.lat::numeric, 5) AS lat, round(s.lon::numeric, 5) AS lon,
           s.geo_precision
    FROM stores s
    WHERE s.is_physical AND s.lat IS NOT NULL AND s.lon IS NOT NULL{live}
    ORDER BY s.id
"""


@router.get("/stores/coordinates", response_model=list[StoreCoordinate],
            summary="Coordinates for every physical store (no input, cacheable)")
def store_coordinates(response: Response, conn: Connection = Depends(get_db)):
    """Every LIVE physical store that has a coordinate.

    Excludes stores their chain has stopped publishing (db/query.py
    live_store_clause), and online/fulfilment rows (`is_physical = false`) —
    those carry a real city in the data and would otherwise look like ordinary
    branches the user could walk into.

    Rounded to 5 decimals: about 1 m, far finer than a city centroid and
    finer than the underlying data justifies, but it keeps the payload small
    without ever being the limiting factor.
    """
    response.headers["Cache-Control"] = f"public, max-age={_MAX_AGE}"
    live_sql, live_params = live_store_clause(conn)
    rows = conn.execute(text(_SQL.format(live=live_sql)), live_params).mappings().all()
    return [
        StoreCoordinate(store_fk=r["id"], lat=float(r["lat"]), lon=float(r["lon"]),
                        precision=r["geo_precision"])
        for r in rows
    ]
