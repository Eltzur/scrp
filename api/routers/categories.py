"""Item categories for users, and user category suggestions (SU11A-57).

GET  /categories/tree                     public, cached: the active taxonomy for the picker
GET  /categories/browse-tree              SU11A-67: departments -> categories -> sub-categories with
                                          visible live item counts (db/category_browse.py), cached per build
GET  /categories/{id}/items               SU11A-67: a browse page (city / chain / sort / on_promo, paged)
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

import re
import time
from typing import Literal

from fastapi import Query

from api import categories as cats
from api.models import CategoryItem, CategoryItemsResult
from api.routers.search import _to_model
from db import category_browse as B
from db.query import today_key_values
from db.search_v2 import V2Unavailable
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


@router.get("/categories/browse-tree", summary="The browse tree with visible item counts (public, cached per build)")
def categories_browse_tree(response: Response, conn: Connection = Depends(get_db)):
    """{min_linked, total, built_at, departments: [{id, level, name_he, name_en, count,
    children: [... linked categories (count >= min_linked), each with its linked
    sub-categories]}]}. Visibility: db/category_browse.py VISIBLE_SQL. Tobacco is
    never listed."""
    tree = B.browse_tree(conn)
    conn.rollback()
    response.headers["Cache-Control"] = "public, max-age=600"
    return {k: v for k, v in tree.items() if not k.startswith("_")}


_NODE_ID = re.compile(r"^D\d{2}(\.C\d{2}(\.S\d{2})?)?$")


@router.get("/categories/{category_id}/items", response_model=CategoryItemsResult,
            summary="A category browse page (SU11A-67)")
def category_items(
    category_id: str,
    response: Response,
    city: str | None = Query(None, max_length=64, description="A city_canonical value (422 unknown_city)"),
    chain: str | None = Query(None, max_length=32, description="A chain_id (422 unknown_chain)"),
    sort: Literal["popular", "cheapest", "name"] = Query("popular"),
    on_promo: bool = Query(False, description="Only items with a promo in force (see db/category_browse.py)"),
    limit: int = Query(30, ge=1, le=B.LIMIT_MAX),
    offset: int = Query(0, ge=0, le=B.OFFSET_MAX),
    conn: Connection = Depends(get_db),
):
    """The category's visible live items with the search card's prices.
    404 category_not_found for an unknown, inactive or tobacco id. Without a
    city the page comes from the search build; with one, from the city's live
    stores (the filtered-search walk)."""
    t0 = time.perf_counter()
    if not _NODE_ID.match(category_id):
        raise ApiCodeError(404, "category_not_found")
    known = today_key_values(conn)
    if known is not None:
        if city is not None and city not in known[0]:
            raise ApiCodeError(422, "unknown_city")
        if chain is not None and chain not in known[1]:
            raise ApiCodeError(422, "unknown_chain")
    try:
        page = B.items_page(conn, category_id, city=city or None, chain=chain or None, sort=sort,
                            on_promo=on_promo, limit=limit, offset=offset)
    except B.NotFound:
        conn.rollback()
        raise ApiCodeError(404, "category_not_found") from None
    except V2Unavailable:
        conn.rollback()
        raise ApiCodeError(503, "build_unavailable") from None
    info = B.tree_node(conn, category_id) or {"count": 0, "children": []}
    conn.rollback()
    n = page.node
    path = [{"id": p["id"], "level": p["level"], "name_he": p["name_he"], "name_en": p["name_en"]}
            for p in cats.path(conn, category_id)]
    tm = page.timings_ms
    response.headers["Server-Timing"] = (f"candidates;dur={tm.get('candidates', 0)}, filter;dur={tm.get('filter', 0)}, "
                                         f"total;dur={round((time.perf_counter() - t0) * 1000, 1)};desc={page.mode}")
    if not city:
        response.headers["Cache-Control"] = "public, max-age=300"
    return CategoryItemsResult(
        category={"id": n["id"], "level": n["level"], "name_he": n["name_he"], "name_en": n["name_en"]},
        path=path,
        children=[{"id": c["id"], "level": c["level"], "name_he": c["name_he"], "name_en": c["name_en"],
                   "count": c["count"]} for c in info["children"]],
        count=info["count"], total=page.total, total_exact=page.total_exact, has_more=page.has_more,
        sort=sort,
        items=[CategoryItem(**_to_model(p).model_dump(), category_id=p.get("category_id")) for p in page.products],
    )


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
