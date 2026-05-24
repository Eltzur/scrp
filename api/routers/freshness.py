from fastapi import APIRouter, Depends
from sqlalchemy.engine import Connection

from api.dependencies import get_db
from api.models import FreshnessResponse
from db.query import fetch_freshness

router = APIRouter(tags=["Freshness"])


@router.get("/freshness", response_model=FreshnessResponse, summary="Data freshness per chain")
def freshness(conn: Connection = Depends(get_db)):
    """Most recent successful load timestamp per chain (files_loaded > 0)."""
    return fetch_freshness(conn)
