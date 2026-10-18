"""Blocking the author of a rating (SU11A-44, designed in SU11A-42).

Ratings are anonymous, so a user blocks "the author of this rating": the server
resolves the author from the rating id and never tells the blocker who it is.
Blocked authors' comments disappear for the blocker in GET /items/{code}/ratings
(api/routers/ratings.py); their scores stay in the averages.

A NEW block also files a rating_reports row with source 'block' and emails
info@ (the report notifier in api/routers/ratings.py), so every block reaches a
moderator. Repeating a block is a no-op and files nothing.

A banned user may still block (blocking protects them; it publishes nothing).
Rows go away with either account: both user columns are ON DELETE CASCADE.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.auth import ApiCodeError, get_current_user
from api.dependencies import get_db
from api.routers.ratings import _notify_report

log = logging.getLogger(__name__)

router = APIRouter(tags=["Blocks"])

EXCERPT_CHARS = 80


class BlockOut(BaseModel):
    id: int
    created_at: str
    item_code: str | None
    item_name: str | None
    comment_excerpt: str | None


@router.post("/ratings/{rating_id}/block-author",
             summary="Block the author of a rating (the author stays anonymous)")
def block_author(
    rating_id: int,
    background: BackgroundTasks,
    user=Depends(get_current_user),
    conn: Connection = Depends(get_db),
):
    found = conn.execute(
        text("SELECT user_id, item_code FROM ratings WHERE id = :id"), {"id": rating_id}
    ).mappings().first()
    if not found:
        raise HTTPException(status_code=404, detail="Rating not found")
    if found["user_id"] == user["id"]:
        raise ApiCodeError(400, "cannot_block_self")

    created = conn.execute(text("""
        INSERT INTO user_blocks (blocker_id, blocked_id, source_rating_id)
        VALUES (:me, :author, :rid)
        ON CONFLICT (blocker_id, blocked_id) DO NOTHING
        RETURNING id
    """), {"me": user["id"], "author": found["user_id"], "rid": rating_id}).first()

    if created is not None:
        conn.execute(text("""
            INSERT INTO rating_reports (rating_id, reporter_user_id, reason, source)
            VALUES (:rid, :uid, NULL, 'block')
        """), {"rid": rating_id, "uid": user["id"]})
    conn.commit()

    if created is not None:
        background.add_task(
            _notify_report,
            rating_id=rating_id, item_code=found["item_code"],
            reporter_email=user.get("email", ""), reason=None, kind="block",
        )
    # Never the author's id: the blocker only ever knows the rating.
    return {"ok": True}


@router.get("/me/blocks", response_model=list[BlockOut],
            summary="The caller's blocks, labelled by the rating they were made from")
def my_blocks(user=Depends(get_current_user), conn: Connection = Depends(get_db)):
    """No user ids and no emails: each row is labelled with the item and the first
    80 characters of the comment the block was made from (public text anyway).
    Nulls when that rating is gone."""
    rows = conn.execute(text("""
        SELECT b.id,
               to_char(b.created_at, 'YYYY-MM-DD"T"HH24:MI:SSOF') AS created_at,
               r.item_code,
               i.item_name,
               r.comment
        FROM user_blocks b
        LEFT JOIN ratings r ON r.id = b.source_rating_id
        LEFT JOIN items i   ON i.item_code = r.item_code
        WHERE b.blocker_id = :uid
        ORDER BY b.created_at DESC, b.id DESC
    """), {"uid": user["id"]}).mappings().all()
    return [
        BlockOut(
            id=r["id"], created_at=r["created_at"], item_code=r["item_code"],
            item_name=r["item_name"],
            comment_excerpt=(r["comment"] or "").strip()[:EXCERPT_CHARS] or None,
        )
        for r in rows
    ]


@router.delete("/me/blocks/{block_id}", status_code=204, summary="Unblock")
def unblock(block_id: int, user=Depends(get_current_user), conn: Connection = Depends(get_db)):
    gone = conn.execute(
        text("DELETE FROM user_blocks WHERE id = :id AND blocker_id = :uid"),
        {"id": block_id, "uid": user["id"]},
    ).rowcount
    if not gone:
        conn.rollback()
        raise HTTPException(status_code=404, detail="Block not found")
    conn.commit()
    return Response(status_code=204)
