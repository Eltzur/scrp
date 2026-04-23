from fastapi import APIRouter, Depends
from sqlalchemy.engine import Connection
from api.models import StatsResponse
from api.dependencies import get_db
from db.query import fetch_stats

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Liveness check")
def health():
    """Returns ok when the server is running."""
    return {"status": "ok"}


@router.get("/stats", response_model=StatsResponse, summary="Database statistics")
def stats(conn: Connection = Depends(get_db)):
    """Counts of chains, stores, items, and prices; last successful fetch per chain."""
    return fetch_stats(conn)
