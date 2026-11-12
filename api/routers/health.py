"""GET /health (liveness) and GET /stats (public database counts).

SU11A-80 (SU11A-79 C1): /stats was called on every web home-page view and ran
COUNT(*) over all of `prices` (7.9 M rows, ~1.1 s) per request. It is now
served from an in-process cache for STATS_TTL_S per worker, single-flight: when
the cache is cold, concurrent requests wait for ONE load instead of each
running the queries. A database connection is opened only on a miss (never per
request). A failed load is not cached; the request answers the JSON 500.
"""
from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Response

from api.models import StatsResponse
from db.db import get_engine
from db.query import fetch_stats

router = APIRouter(tags=["Health"])

STATS_TTL_S = 600.0
CACHE_CONTROL = "public, max-age=300"

_cache: tuple[float, dict] | None = None
_load_lock = threading.Lock()   # single-flight: one load per worker at a time


def _open():
    """A connection, only on a cache miss (patched in tests)."""
    return get_engine().connect()


def _fresh(hit: tuple[float, dict] | None, now: float) -> bool:
    return hit is not None and now - hit[0] < STATS_TTL_S


def cached_stats(now: float | None = None) -> dict:
    """The /stats body, from the cache while it is younger than STATS_TTL_S."""
    global _cache
    t = time.monotonic() if now is None else now
    hit = _cache
    if _fresh(hit, t):
        return hit[1]
    with _load_lock:
        hit = _cache            # another thread may have loaded it while we waited
        if _fresh(hit, t):
            return hit[1]
        conn = _open()
        try:
            value = fetch_stats(conn)
        finally:
            conn.close()
        _cache = (t, value)
        return value


def invalidate() -> None:
    global _cache
    with _load_lock:
        _cache = None


@router.get("/health", summary="Liveness check")
def health():
    """Returns ok when the server is running."""
    return {"status": "ok"}


@router.get("/stats", response_model=StatsResponse, summary="Database statistics (cached 10 min per worker)")
def stats(response: Response):
    """Counts of chains, stores, items, and prices; last successful fetch per chain."""
    response.headers["Cache-Control"] = CACHE_CONTROL
    return cached_stats()
