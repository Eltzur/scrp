"""SU11A-77: GET /announcements/active?platform=ios|android - the app notice.

Public, no auth, no identifiers: the answer depends on the platform only, so it
is the same for everyone and cacheable. 200 {id, version, title, body} or 204
when no notice is active for that platform. The value is cached in-process for
5 minutes (db/announcements.py), and a database connection is opened only on a
cache miss - never per request. A missing table or a database error reads as
"no notice" (204), cached the same way.

nginx: the general xxl_api zone (`location /`); not xxl_heavy - it reads one
tiny table at most every 5 minutes per worker.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse

from api.auth import ApiCodeError
from db import announcements as A
from db.db import get_engine

router = APIRouter(tags=["Announcements"])

CACHE_CONTROL = "public, max-age=300"


def _open():
    """A connection, only on a cache miss (patched in tests)."""
    return get_engine().connect()


@router.get("/announcements/active", summary="The active app notice for a platform (204 when none)",
            responses={204: {"description": "No active notice for this platform"},
                       400: {"description": "unknown_platform"}})
def active(platform: str = Query(..., max_length=16, description="ios | android")):
    if platform not in A.PUBLIC_PLATFORMS:
        raise ApiCodeError(400, "unknown_platform")
    opened = []

    def factory():
        c = _open()
        opened.append(c)
        return c

    try:
        n = A.active_for(factory, platform)
    finally:
        for c in opened:
            c.close()
    if n is None:
        return Response(status_code=204, headers={"Cache-Control": CACHE_CONTROL})
    return JSONResponse({"id": n.id, "version": n.version, "title": n.title, "body": n.body},
                        headers={"Cache-Control": CACHE_CONTROL})
