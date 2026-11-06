"""GET /admin/stats (SU11A-69): the admin console's סטטיסטיקות screen.

Read-only, admin allowlist + aal2 like every /admin route (require_admin_mfa);
reads are not audited. Everything comes from stats_daily / stats_runs, which
scripts/stats_collect.py fills once a day with AGGREGATES only (counts per day
per host / platform / path without query string / referrer domain). No user
email, user id, IP address or user agent exists in these tables.

Without the su11a69 migration every source answers "never_run" and the series
are empty (no 500), so the screen can ship before the migration.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.engine import Connection

from api.auth import require_admin_mfa
from api.dependencies import get_db
from db import stats as S

log = logging.getLogger(__name__)

router = APIRouter(tags=["Admin"], dependencies=[Depends(require_admin_mfa)])

DEFAULT_DAYS = 30
MAX_DAYS = 400


def _today_il() -> date:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Jerusalem")).date()


@router.get("/admin/stats", summary="Traffic, app activity and store statistics (admin + 2FA)")
def stats(
    days: int = Query(DEFAULT_DAYS, ge=1, le=MAX_DAYS, description="days up to yesterday (Israel time)"),
    conn: Connection = Depends(get_db),
):
    day_to = _today_il() - timedelta(days=1)
    day_from = day_to - timedelta(days=days - 1)
    body = {"from": day_from.isoformat(), "to": day_to.isoformat(), "days": days,
            "sources": {s: {"status": "never_run", "last_run_at": None, "last_success_at": None,
                            "last_error_at": None, "error": None, "as_of": None, "note": None}
                        for s in S.SOURCES},
            "series": [], "top_paths": [], "top_referrers": []}
    try:
        body["sources"] = S.runs(conn)
        body["series"] = S.series(conn, day_from, day_to)
        body["top_paths"] = S.top(conn, "top_path", day_from, day_to, 20)
        body["top_referrers"] = S.top(conn, "referrer", day_from, day_to, 10)
    except Exception as exc:  # tables missing before the migration
        log.info("admin stats unavailable (%s)", type(exc).__name__)
        body["unavailable"] = True
    finally:
        conn.rollback()
    return body
