"""Admin console API, phase 1 (SU11A-54). Served on api-super.xxl.co.il and
called by the console on admin.xxl.co.il.

Every endpoint here, and the moderation endpoints in api/routers/ratings.py,
depends on api/auth.py require_admin_mfa: valid token + ADMIN_USER_EMAILS +
aal2 (TOTP). Writes live in ratings.py (moderate, ban-author) and record an
admin_audit row; this file only reads.

Data minimisation: no user email and no user id leaves these endpoints. A
rating's author is described by "banned?" and "how many active ratings", never
by identity; reports carry source, reason and date, never the reporter.

GET /admin/me                       {is_admin, mfa} for the console
GET /admin/ratings/history          recent moderator decisions
GET /admin/ratings/{id}             one rating with all its reports
GET /admin/status                   platform status (cached 30 s); SU11A-57: + open category suggestions
GET /admin/audit                    the audit log

The api-super host's nginx rate limit and X-Robots-Tag cover /admin/* like
every other path; main.py adds Cache-Control: no-store, Server-Timing and the
JSON 500 for /admin/*.
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api import admin_audit, metrics, moderation
from api.auth import require_admin_mfa
from api.dependencies import get_db
from db.query import fetch_coverage, fetch_freshness

log = logging.getLogger(__name__)

router = APIRouter(tags=["Admin"], dependencies=[Depends(require_admin_mfa)])

_TS = "'YYYY-MM-DD\"T\"HH24:MI:SSOF'"


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


@router.get("/admin/me", summary="Admin session check (admin + 2FA)")
def me():
    """Reaching this body means all three checks passed; a failed check answers
    403 admin_required / mfa_required before it."""
    return {"is_admin": True, "mfa": True}


# ---------------------------------------------------------------------------
# Ratings: history and detail
# ---------------------------------------------------------------------------

@router.get("/admin/ratings/history", summary="Recent moderator decisions (admin + 2FA)")
def ratings_history(
    limit: int = Query(50, ge=1, le=200),
    before: datetime | None = Query(None, description="cursor: next.before of the previous page"),
    before_id: int | None = Query(None, description="cursor: next.before_id of the previous page"),
    conn: Connection = Depends(get_db),
):
    """Ratings by last decision (ratings.reviewed_at), newest first, each with
    the last audited action on it. last_action is null for decisions made with
    scripts/moderation.py or before SU11A-54 (those are not audited)."""
    where = "r.reviewed_at IS NOT NULL"
    params: dict = {"limit": limit}
    if before is not None:
        where += " AND (r.reviewed_at < :before OR (r.reviewed_at = :before AND r.id < :bid))"
        params.update(before=before, bid=before_id if before_id is not None else 2**62)
    rows = conn.execute(text(f"""
        SELECT r.id, r.item_code, i.item_name, r.rating, r.comment, r.status,
               r.reviewed_at AS cursor_at,
               to_char(r.reviewed_at, {_TS}) AS reviewed_at,
               (SELECT a.action FROM admin_audit a
                WHERE a.target_type = 'rating' AND a.target_id = CAST(r.id AS TEXT)
                ORDER BY a.at DESC, a.id DESC LIMIT 1) AS last_action
        FROM ratings r
        LEFT JOIN items i ON i.item_code = r.item_code
        WHERE {where}
        ORDER BY r.reviewed_at DESC, r.id DESC
        LIMIT :limit
    """), params).mappings().all()
    conn.rollback()
    items = [{k: v for k, v in r.items() if k != "cursor_at"} for r in rows]
    nxt = None
    if len(rows) == limit:
        nxt = {"before": _iso(rows[-1]["cursor_at"]), "before_id": rows[-1]["id"]}
    return {"count": len(items), "items": items, "next": nxt}


@router.get("/admin/ratings/{rating_id:int}", summary="One rating with its reports (admin + 2FA)")
def rating_detail(rating_id: int, conn: Connection = Depends(get_db)):
    row = conn.execute(text(f"""
        SELECT r.id, r.item_code, i.item_name, r.rating, r.comment, r.status,
               to_char(r.created_at, {_TS}) AS created_at,
               to_char(r.updated_at, {_TS}) AS updated_at,
               to_char(r.reviewed_at, {_TS}) AS reviewed_at
        FROM ratings r
        LEFT JOIN items i ON i.item_code = r.item_code
        WHERE r.id = :id
    """), {"id": rating_id}).mappings().first()
    if row is None:
        conn.rollback()
        raise HTTPException(status_code=404, detail="Rating not found")
    out = dict(row)
    out["reports"] = moderation.reports_for(conn, rating_id)
    conn.rollback()
    preview = moderation.author_preview(conn, rating_id) or {}
    out["author"] = {"banned": preview.get("banned"), "active_ratings": preview.get("active_ratings")}
    trail = conn.execute(text(f"""
        SELECT id, to_char(at, {_TS}) AS at, action
        FROM admin_audit
        WHERE target_type = 'rating' AND target_id = :tid
        ORDER BY id DESC LIMIT 20
    """), {"tid": str(rating_id)}).mappings().all()
    conn.rollback()
    out["audit"] = [dict(t) for t in trail]
    return out


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

STATUS_TTL_S = 30.0
_status_lock = threading.Lock()
_status_cache: tuple[float, dict] | None = None


def _safe(conn, fn):
    """One status section; any failure (missing table, no permission, a
    platform without /proc) answers null for that section only."""
    try:
        return fn()
    except Exception as exc:
        log.info("admin status: section unavailable (%s)", type(exc).__name__)
        try:
            conn.rollback()
        except Exception:
            pass
        return None


def _chains(conn) -> list[dict]:
    """Same sources as the web's "סטטוס עדכון מחירים" (/freshness) and /coverage."""
    fresh = fetch_freshness(conn)["chains"]
    cover = {c["chain_name"]: c for c in fetch_coverage(conn)["chains"] if c.get("chain_name")}
    out = []
    for c in fresh:
        cv = cover.get(c["chain_name"]) or {}
        out.append({
            "chain_name": c["chain_name"],
            "last_loaded_at": _iso(c["last_loaded_at"]),
            "stores_loaded_72h": cv.get("stores_loaded_72h"),
            "stores_configured": cv.get("stores_configured"),
        })
    return out


def _table_build(conn, table: str) -> dict:
    built = conn.execute(text(f"SELECT built_at FROM {table} LIMIT 1")).scalar()
    rows = _safe(conn, lambda: conn.execute(text(
        "SELECT n_live_tup FROM pg_stat_user_tables WHERE relname = :t"), {"t": table}).scalar())
    return {"built_at": _iso(built), "rows_approx": None if rows is None else int(rows)}


def _moderation_counts(conn) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    pending = len(moderation.queue(conn))
    hidden = conn.execute(text("""
        SELECT count(*) FROM ratings
        WHERE status = 'hidden' AND COALESCE(reviewed_at, updated_at) >= :since
    """), {"since": since}).scalar()
    banned = conn.execute(text("SELECT count(*) FROM users WHERE banned_at IS NOT NULL")).scalar()
    return {"pending": pending, "hidden_7d": int(hidden or 0), "banned_users": int(banned or 0)}


def _suggestion_counts(conn) -> dict:
    """SU11A-57: open user category suggestions (null until su11a57 is applied)."""
    row = conn.execute(text("""
        SELECT count(*) AS n, count(DISTINCT item_code) AS items
        FROM category_suggestions WHERE status = 'open'
    """)).mappings().one()
    return {"pending": int(row["n"] or 0), "pending_items": int(row["items"] or 0)}


def _proc_kb(path: str, keys: tuple[str, ...]) -> dict:
    out: dict = {}
    with open(path, encoding="ascii") as f:
        for line in f:
            name, _, rest = line.partition(":")
            if name in keys:
                out[name] = int(rest.split()[0]) * 1024
    return out


def _memory() -> dict:
    proc = _safe_local(lambda: _proc_kb("/proc/self/status", ("VmRSS",)).get("VmRSS"))
    sysm = _safe_local(lambda: _proc_kb("/proc/meminfo", ("MemTotal", "MemAvailable"))) or {}
    return {"process_rss_bytes": proc, "system_total_bytes": sysm.get("MemTotal"),
            "system_available_bytes": sysm.get("MemAvailable")}


def _safe_local(fn):
    try:
        return fn()
    except Exception:
        return None


def _disk() -> dict | None:
    def read():
        u = shutil.disk_usage("/")
        return {"path": "/", "total_bytes": u.total, "free_bytes": u.free}
    return _safe_local(read)


def build_status(conn) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chains": _safe(conn, lambda: _chains(conn)),
        "search_items": _safe(conn, lambda: _table_build(conn, "search_items")),
        "search_item_prices": _safe(conn, lambda: _table_build(conn, "search_item_prices")),
        "moderation": _safe(conn, lambda: _moderation_counts(conn)),
        "category_suggestions": _safe(conn, lambda: _suggestion_counts(conn)),
        "db_size_bytes": _safe(conn, lambda: conn.execute(
            text("SELECT pg_database_size(current_database())")).scalar()),
        "disk": _disk(),
        "memory": _memory(),
        "process": {"pid": os.getpid()},
    }


@router.get("/admin/status", summary="Platform status (admin + 2FA, cached 30 s)")
def status(conn: Connection = Depends(get_db)):
    """Only what the API can read without sudo; anything it cannot read is null.
    The DB / disk / memory part is cached STATUS_TTL_S; the counters are this
    worker's own, read fresh on every call."""
    global _status_cache
    now = time.monotonic()
    with _status_lock:
        cached = _status_cache
    if cached is None or now - cached[0] >= STATUS_TTL_S:
        body = build_status(conn)
        conn.rollback()
        with _status_lock:
            _status_cache = (now, body)
        cached = (now, body)
    return {**cached[1], "cache_age_s": round(now - cached[0], 1), "counters": metrics.snapshot()}


def reset_status_cache() -> None:
    """Tests only."""
    global _status_cache
    with _status_lock:
        _status_cache = None


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@router.get("/admin/audit", summary="Admin audit log (admin + 2FA)")
def audit(
    limit: int = Query(50, ge=1, le=200),
    before: int | None = Query(None, ge=1, description="cursor: next_before of the previous page"),
    conn: Connection = Depends(get_db),
):
    items = admin_audit.entries(conn, limit=limit, before=before)
    return {"count": len(items), "items": items,
            "next_before": items[-1]["id"] if len(items) == limit else None}
