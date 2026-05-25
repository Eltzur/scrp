from fastapi import APIRouter, Depends
from sqlalchemy.engine import Connection

from api.dependencies import get_db
from api.models import CoverageResponse
from db.query import fetch_coverage

router = APIRouter(tags=["Coverage"])


@router.get("/coverage", response_model=CoverageResponse, summary="Per-store 72h coverage by chain")
def coverage(conn: Connection = Depends(get_db)):
    """72h load coverage per chain, using active_stores.yaml as the configured denominator."""
    return fetch_coverage(conn)
