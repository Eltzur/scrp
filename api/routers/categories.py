"""Item categories for users, and user category suggestions (SU11A-57).

GET  /categories/tree                     public, cached: the active taxonomy for the picker
GET  /items/{code}/category               the item's category path (department › category ›
                                          sub-category); a LOW-confidence label shows the
                                          department only (api/categories.public_path)
POST /items/{code}/category-suggestions   signed in: "this item belongs in X"

Suggestion gates, the same as posting a rating (api/routers/ratings.py), in order:
  1. signed in, else 401 {"code":"login_required"};
  2. not banned, else 403 account_banned;
  3. the current terms accepted, else 403 terms_required. Always on here, unlike
     RATINGS_REQUIRE_TERMS: only builds that have the consent flow have this button;
  4. at most DAILY_LIMIT suggestions per user in 24 hours, else 429 daily_limit;
  5. one open suggestion per user and item, else 409 already_suggested;
  6. the item exists (404 item_not_found), the suggested id is an active category
     (422 invalid_category) and differs from the item's current one (422 same_category);
  7. the comment (at most 200 characters) goes through the ratings blacklist: on a hit
     the suggestion is stored WITHOUT the comment (comment_blocked = true) and the answer
     is the same 201 as any other, so the filter's words are not revealed.
The admin console reviews them (api/routers/admin_categories.py) and never sees who
suggested. DELETE /account removes them (FK ON DELETE CASCADE on users).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from api import categories as cats
from api.auth import ApiCodeError, get_current_user_login_code
from api.dependencies import get_db
from api.routers.ratings import _blacklist_hit, _posting_state
from api.terms import TERMS_VERSION

log = logging.getLogger(__name__)

router = APIRouter(tags=["Categories"])

DAILY_LIMIT = 20
COMMENT_MAX = 200


@router.get("/categories/tree", summary="The active category taxonomy (public, cached)")
def categories_tree(response: Response, conn: Connection = Depends(get_db)):
    """Flat, parents before children: {version, nodes: [{id, parent_id, level,
    name_he, name_en}]}. The same for everyone: a shared cache may keep it."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return cats.public_tree(conn)


@router.get("/items/{item_code}/category", summary="An item's category path (low confidence: department only)")
def item_category(item_code: str, response: Response, conn: Connection = Depends(get_db)):
    """{item_code, category_id, path: [{id, name_he, name_en, level}], partial}.
    partial = true when the label is low-confidence and only the department is
    shown. No label: path [] and category_id null. Source and confidence are not
    returned."""
    lab = cats.label(conn, item_code)
    conn.rollback()
    response.headers["Cache-Control"] = "public, max-age=300"
    return {"item_code": item_code, **cats.public_path(conn, lab)}


class SuggestionIn(BaseModel):
    category_id: str = Field(..., min_length=1, max_length=32)
    comment: str | None = Field(None, max_length=COMMENT_MAX)


@router.post("/items/{item_code}/category-suggestions", status_code=201,
             summary="Suggest a better category for an item (signed in)")
def suggest_category(item_code: str, body: SuggestionIn,
                     user=Depends(get_current_user_login_code), conn: Connection = Depends(get_db)):
    uid = user["id"]
    state = _posting_state(conn, uid)
    if state is not None and state["banned_at"] is not None:
        raise ApiCodeError(403, "account_banned")
    if state is None or state["terms_version"] != TERMS_VERSION:
        raise ApiCodeError(403, "terms_required")

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    today = conn.execute(text(
        "SELECT count(*) FROM category_suggestions WHERE user_id = :u AND created_at >= :since"
    ), {"u": uid, "since": since}).scalar()
    if (today or 0) >= DAILY_LIMIT:
        raise ApiCodeError(429, "daily_limit")
    if conn.execute(text(
        "SELECT 1 FROM category_suggestions WHERE user_id = :u AND item_code = :c AND status = 'open'"
    ), {"u": uid, "c": item_code}).first():
        raise ApiCodeError(409, "already_suggested")

    if not conn.execute(text("SELECT 1 FROM items WHERE item_code = :c"), {"c": item_code}).first():
        raise ApiCodeError(404, "item_not_found")
    current = cats.label(conn, item_code)
    current_id = current["category_id"] if current else None
    suggested = body.category_id.strip()
    if cats.active_node(conn, suggested) is None:
        raise ApiCodeError(422, "invalid_category")
    if suggested == current_id:
        raise ApiCodeError(422, "same_category")

    comment = (body.comment or "").strip() or None
    blocked = comment is not None and _blacklist_hit(conn, comment) is not None
    try:
        sid = conn.execute(text("""
            INSERT INTO category_suggestions
                (item_code, user_id, current_category_id, suggested_category_id, comment, comment_blocked)
            VALUES (:c, :u, :cur, :sug, :comment, :blocked)
            RETURNING id
        """), {"c": item_code, "u": uid, "cur": current_id, "sug": suggested,
               "comment": None if blocked else comment, "blocked": blocked}).scalar()
        conn.commit()
    except IntegrityError:
        # Two taps at once: the partial unique index decided.
        conn.rollback()
        raise ApiCodeError(409, "already_suggested") from None
    if blocked:
        log.warning("category suggestion %s: comment withheld by the blacklist (item %s)", sid, item_code)
    return {"id": sid, "status": "open"}
