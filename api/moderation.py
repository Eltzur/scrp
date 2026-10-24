"""Moderation actions on ratings (SU11A-44), shared by the admin endpoints in
api/routers/ratings.py and the server CLI scripts/moderation.py.

Queue rule. A rating needs a moderator when
  - it is not active and no moderator has looked at it yet (blacklist auto-hide,
    pending_review), or
  - any report on it is newer than the last moderator decision (ratings.reviewed_at).
Every decision (hide / keep / restore / ban) stamps reviewed_at, so "keep" takes a
reported-but-fine rating out of the queue and a later report puts it back.

Log lines carry the action, the rating id and the item code only — never an
email (SU11A-32) and never the author's user id.

SU11A-54 (admin console): the queue no longer returns the author's user_id or
the reporters' ids (nothing used them; the console shows no user identifiers),
and gains item_name. moderate() / ban_author() take an optional `audit`
callback, run on the same connection after the change and before the commit,
so an admin write and its admin_audit row commit together. The CLI passes none.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import bindparam, text

log = logging.getLogger(__name__)

ACTIONS = ("hide", "keep", "restore")

_TS = "'YYYY-MM-DD\"T\"HH24:MI:SSOF'"

QUEUE_SQL = text(f"""
    SELECT r.id, r.item_code, i.item_name, r.rating, r.comment, r.status,
           to_char(r.created_at, {_TS}) AS created_at,
           to_char(r.updated_at, {_TS}) AS updated_at,
           to_char(r.reviewed_at, {_TS}) AS reviewed_at
    FROM ratings r
    LEFT JOIN items i ON i.item_code = r.item_code
    WHERE (r.status <> 'active' AND r.reviewed_at IS NULL)
       OR EXISTS (
            SELECT 1 FROM rating_reports rep
            WHERE rep.rating_id = r.id
              AND (r.reviewed_at IS NULL OR rep.created_at > r.reviewed_at)
       )
    ORDER BY r.created_at DESC
""")

REPORTS_SQL = text(f"""
    SELECT rep.id, rep.rating_id, rep.source, rep.reason,
           to_char(rep.created_at, {_TS}) AS created_at
    FROM rating_reports rep
    WHERE rep.rating_id IN :ids
    ORDER BY rep.created_at DESC, rep.id DESC
""").bindparams(bindparam("ids", expanding=True))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def queue(conn) -> list[dict]:
    """Ratings that need a moderator, newest first, each with its reports.

    Keeps the SU10R-1 fields (including `reports`) except the user ids (dropped
    in SU11A-54) and adds report_count, latest_report_at, report_sources,
    report_reasons, reviewed_at, item_name.
    """
    rows = [dict(r) for r in conn.execute(QUEUE_SQL).mappings().all()]
    if not rows:
        return []
    by_rating: dict[int, list[dict]] = {r["id"]: [] for r in rows}
    for rep in conn.execute(REPORTS_SQL, {"ids": list(by_rating)}).mappings().all():
        by_rating[rep["rating_id"]].append({
            "id": rep["id"],
            "source": rep["source"],
            "reason": rep["reason"],
            "created_at": rep["created_at"],
        })
    for r in rows:
        reps = by_rating[r["id"]]
        r["reports"] = reps
        r["report_count"] = len(reps)
        r["latest_report_at"] = reps[0]["created_at"] if reps else None
        r["report_sources"] = sorted({p["source"] for p in reps})
        r["report_reasons"] = [p["reason"] for p in reps if p["reason"]]
    return rows


Audit = Callable[[object, dict], None]


def reports_for(conn, rating_id: int) -> list[dict]:
    """All reports on one rating, newest first, without reporter ids."""
    return [{"id": r["id"], "source": r["source"], "reason": r["reason"],
             "created_at": r["created_at"]}
            for r in conn.execute(REPORTS_SQL, {"ids": [rating_id]}).mappings().all()]


def moderate(conn, rating_id: int, action: str, audit: Audit | None = None) -> dict | None:
    """hide -> status 'hidden'; keep -> status unchanged; restore -> 'active'.
    All three stamp reviewed_at. None when the rating does not exist.
    `audit(conn, info)` runs before the commit; if it raises, nothing changes."""
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    status_sql = {"hide": "'hidden'", "keep": "status", "restore": "'active'"}[action]
    before = conn.execute(text("SELECT status FROM ratings WHERE id = :id"),
                          {"id": rating_id}).scalar()
    row = conn.execute(text(f"""
        UPDATE ratings SET status = {status_sql}, reviewed_at = :now
        WHERE id = :id
        RETURNING id, item_code, status
    """), {"id": rating_id, "now": _now()}).mappings().first()
    if row is None:
        conn.rollback()
        return None
    if audit is not None:
        try:
            audit(conn, {"item_code": row["item_code"], "status_before": before,
                         "status_after": row["status"]})
        except Exception:
            conn.rollback()
            raise
    conn.commit()
    log.warning("[MODERATION] admin %s: rating_id=%s item_code=%s",
                action, row["id"], row["item_code"])
    return {"ok": True, "rating_id": row["id"], "status": row["status"]}


def author_preview(conn, rating_id: int) -> dict | None:
    """What a ban through this rating would touch, without the author's identity."""
    row = conn.execute(text("""
        SELECT r.item_code,
               u.banned_at IS NOT NULL AS banned,
               (SELECT count(*) FROM ratings x
                WHERE x.user_id = r.user_id AND x.status = 'active') AS active_ratings
        FROM ratings r JOIN users u ON u.id = r.user_id
        WHERE r.id = :id
    """), {"id": rating_id}).mappings().first()
    conn.rollback()
    if row is None:
        return None
    return {"item_code": row["item_code"], "banned": bool(row["banned"]),
            "active_ratings": int(row["active_ratings"] or 0)}


def ban_author(conn, rating_id: int, ban: bool, audit: Audit | None = None) -> dict | None:
    """Ban (or unban) the author of a rating, found server-side.

    Ban: users.banned_at = now (kept if already set) and every ACTIVE rating of the
    author goes to 'hidden' with reviewed_at = now. Unban: banned_at = NULL only;
    hidden ratings stay hidden and are restored one by one. The response never
    carries the author's id or email. None when the rating does not exist.
    `audit(conn, info)` runs before the commit; if it raises, nothing changes.
    """
    found = conn.execute(
        text("SELECT user_id, item_code FROM ratings WHERE id = :id"), {"id": rating_id}
    ).mappings().first()
    if found is None:
        conn.rollback()
        return None
    now = _now()
    hidden = 0
    if ban:
        conn.execute(text(
            "UPDATE users SET banned_at = COALESCE(banned_at, :now) WHERE id = :uid"
        ), {"uid": found["user_id"], "now": now})
        hidden = conn.execute(text("""
            UPDATE ratings SET status = 'hidden', reviewed_at = :now
            WHERE user_id = :uid AND status = 'active'
        """), {"uid": found["user_id"], "now": now}).rowcount or 0
        # The rating the ban was made from counts as reviewed even when it was
        # already hidden (e.g. a blacklist auto-hide), so it leaves the queue.
        conn.execute(text("UPDATE ratings SET reviewed_at = :now WHERE id = :id"),
                     {"id": rating_id, "now": now})
    else:
        conn.execute(text("UPDATE users SET banned_at = NULL WHERE id = :uid"),
                     {"uid": found["user_id"]})
    if audit is not None:
        try:
            audit(conn, {"item_code": found["item_code"], "ratings_hidden": hidden})
        except Exception:
            conn.rollback()
            raise
    conn.commit()
    log.warning("[MODERATION] admin %s: rating_id=%s item_code=%s ratings_hidden=%s",
                "ban-author" if ban else "unban-author", rating_id, found["item_code"], hidden)
    return {"ok": True, "rating_id": rating_id, "banned": ban, "ratings_hidden": hidden}
