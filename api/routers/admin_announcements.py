"""SU11A-77: the admin console's app notices (admin + 2FA on every route:
api/auth.py require_admin_mfa = token + ADMIN_USER_EMAILS + aal2).

  GET  /admin/announcements                    the three scopes (ios / android / both)
  PUT  /admin/announcements/{platform}         title + body (validated server-side)
  POST /admin/announcements/{platform}/active  {active: true|false}

Every write records an admin_audit row (target_type 'announcement', target_id
the platform, before / after) on the same connection before the commit, as in
SU11A-54 / 58. The text rules (db/announcements.py) are enforced here, not only
in the screen: plain text, no links (Apple 3.1.1 / Play Billing), and for ios /
both no "בהרצה" / beta / trial wording (Apple 2.2).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from api import admin_audit
from api.auth import require_admin_mfa
from api.dependencies import get_db
from db import announcements as A

router = APIRouter(tags=["Admin"], dependencies=[Depends(require_admin_mfa)])

AUDIT_TARGET = "announcement"


class TextIn(BaseModel):
    title: str = Field(..., max_length=200)      # the real limits (60 / 600) are checked after trimming
    body: str = Field(..., max_length=2000)


class ActiveIn(BaseModel):
    active: bool


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _out(r: dict) -> dict:
    return {"platform": r["platform"], "title": r["title"], "body": r["body"], "active": bool(r["active"]),
            "version": r["version"], "updated_at": _iso(r["updated_at"])}


def _snap(r: dict | None) -> dict | None:
    return None if r is None else {k: r[k] for k in ("title", "body", "version")} | {"active": bool(r["active"])}


def _error(conn, exc: A.AnnouncementError) -> JSONResponse:
    conn.rollback()
    status = 404 if exc.code == "not_found" else 422
    body = {"code": exc.code, "field": exc.field}
    if exc.word:
        body["word"] = exc.word
    return JSONResponse(body, status_code=status)


def _audit(conn, request: Request, admin: dict, action: str, platform: str, before, after) -> None:
    admin_audit.record(conn, actor_id=admin["id"], action=action, target_type=AUDIT_TARGET, target_id=platform,
                       detail={"before": _snap(before), "after": _snap(after)},
                       ip=admin_audit.client_ip(request))


@router.get("/admin/announcements", summary="The app notices per platform scope (admin + 2FA)")
def list_announcements(conn: Connection = Depends(get_db)):
    return {"items": [_out(r) for r in A.all_rows(conn)],
            "rules": {"title_max": A.TITLE_MAX, "body_max": A.BODY_MAX}}


@router.put("/admin/announcements/{platform}", summary="Save a notice's title and body (admin + 2FA)")
def update_announcement(platform: str, body: TextIn, request: Request,
                        admin=Depends(require_admin_mfa), conn: Connection = Depends(get_db)):
    """422 {code: empty | too_long | markup_not_allowed | links_not_allowed |
    beta_wording_not_allowed_ios | unknown_platform, field[, word]}; 404 not_found.
    The version grows only when the text changes."""
    try:
        before, after = A.update_text(conn, platform, body.title, body.body, admin_audit.actor_hash(admin["id"]))
    except A.AnnouncementError as exc:
        return _error(conn, exc)
    _audit(conn, request, admin, "announcement.update", platform, before, after)
    conn.commit()
    return _out(after)


@router.post("/admin/announcements/{platform}/active", summary="Switch a notice on or off (admin + 2FA)")
def activate_announcement(platform: str, body: ActiveIn, request: Request,
                          admin=Depends(require_admin_mfa), conn: Connection = Depends(get_db)):
    """Switching on re-validates the stored text (422 as above)."""
    if platform not in A.PLATFORMS:
        return _error(conn, A.AnnouncementError("unknown_platform", "platform"))
    try:
        before, after = A.set_active(conn, platform, body.active, admin_audit.actor_hash(admin["id"]))
    except A.AnnouncementError as exc:
        return _error(conn, exc)
    _audit(conn, request, admin, "announcement.activate" if body.active else "announcement.deactivate",
           platform, before, after)
    conn.commit()
    return _out(after)
