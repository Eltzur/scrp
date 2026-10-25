"""Israeli Price Comparison API."""
import json
import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from api import metrics
from api.auth import ApiCodeError
from api.routers import account, admin, admin_categories, blocks, categories, health, catalog, search, product, basket, saved_baskets, favorites, freshness, coverage, promos, ratings, stores, terms
from db import db as _db

log = logging.getLogger(__name__)

# SU11A-49 (F-01): every API connection gets a statement_timeout, so one
# expensive anonymous request cannot hold Postgres and a worker for minutes.
# Set here and not on the scrp_app role: the loader, build_search_items and the
# ops scripts use the same role and must keep running long statements.
# Env api_statement_timeout_ms (lowercase per CLAUDE.md); 0 turns it off.
API_STATEMENT_TIMEOUT_MS = int(os.environ.get("api_statement_timeout_ms") or 15000)
_db.set_statement_timeout(API_STATEMENT_TIMEOUT_MS)

# SQLSTATE 57014 query_canceled: what statement_timeout raises.
_QUERY_CANCELED = "57014"

app = FastAPI(
    title="Israeli Price Comparison API",
    version="0.1.0",
    description=(
        "Search and compare grocery prices across Israeli supermarket chains "
        "(Shufersal, Rami Levy, Osher Ad). Data sourced from mandatory Price "
        "Transparency XML files published under the 2014 regulation."
    ),
)

_DEFAULT_ORIGINS = "http://localhost:5173,http://localhost:3000"
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",")
    if o.strip()
]
# SU11A-54: the admin console's origin is always allowed, whatever the env
# list says, so enabling the console needs no .env edit. CORS only lets that
# page read answers; every /admin/* call still needs admin + 2FA.
ADMIN_ORIGIN = "https://admin.xxl.co.il"
if ADMIN_ORIGIN not in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS.append(ADMIN_ORIGIN)


class RequestMetricsMiddleware:
    """Plain ASGI (no BaseHTTPMiddleware). SU11A-54:
      - every HTTP answer feeds api/metrics.py (requests, 5xx, 429);
      - /admin/* answers get Cache-Control: no-store and a Server-Timing total,
        and an unhandled error there answers 500 {"code":"server_error"}
        (JSON, no stack) instead of the plain-text 500. Other paths keep the
        plain 500.
    Added before CORSMiddleware, so CORS wraps it and the JSON 500 carries the
    CORS headers the console needs to read it."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_admin = scope.get("path", "").startswith("/admin/")
        t0 = time.perf_counter()
        started = False

        async def _send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                metrics.record_status(message["status"])
                if is_admin:
                    dur = round((time.perf_counter() - t0) * 1000, 1)
                    headers = [(k, v) for k, v in message.get("headers", [])
                               if k.lower() not in (b"cache-control", b"server-timing")]
                    headers += [(b"cache-control", b"no-store"),
                                (b"server-timing", f"total;dur={dur}".encode())]
                    message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception as exc:
            if not is_admin or started:
                if not started:
                    metrics.record_status(500)
                raise
            log.error("admin request failed: %s %s (%s)", scope.get("method"),
                      scope.get("path"), type(exc).__name__)
            body = json.dumps({"code": "server_error"}).encode()
            await _send({"type": "http.response.start", "status": 500, "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})


app.add_middleware(RequestMetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(catalog.router)
app.include_router(search.router)
app.include_router(product.router)
app.include_router(basket.router)
app.include_router(saved_baskets.router)
app.include_router(favorites.router)
app.include_router(freshness.router)
app.include_router(coverage.router)
app.include_router(promos.router)
app.include_router(ratings.router)
app.include_router(stores.router)
app.include_router(account.router)
app.include_router(blocks.router)   # SU11A-44
app.include_router(terms.router)    # SU11A-44
app.include_router(admin.router)    # SU11A-54 (after ratings: /admin/ratings/pending is there)
app.include_router(categories.router)        # SU11A-57
app.include_router(admin_categories.router)  # SU11A-57


@app.exception_handler(ApiCodeError)
def _api_code_error(_request: Request, exc: ApiCodeError) -> JSONResponse:
    """Answers {"code": ...} (SU11A-28, e.g. 401 account_deleted)."""
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code})


@app.exception_handler(DBAPIError)
def _db_error(request: Request, exc: DBAPIError) -> JSONResponse:
    """A statement_timeout cancel answers 503 {"code": "query_timeout"} (SU11A-49).

    The body carries no SQL, parameters or stack. The log line names the method
    and path only - never the query string, which holds the search text.
    Any other database error is re-raised and becomes the usual plain 500."""
    if getattr(exc.orig, "pgcode", None) != _QUERY_CANCELED:
        raise exc
    metrics.inc("query_timeout")
    log.warning("query timeout (%s ms): %s %s", API_STATEMENT_TIMEOUT_MS,
                request.method, request.url.path)
    return JSONResponse(status_code=503, content={"code": "query_timeout"},
                        headers={"Retry-After": "5"})
