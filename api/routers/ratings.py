"""Item ratings, reports, and a minimal moderation queue (SU10R-1).

Scale is 1-3 (1 = poor, 2 = neutral, 3 = very good). The PERCENTAGE IS NEVER
STORED: GET computes avg(rating)/3*100 at read time, the same "store raw, stay
re-fixable" rule the promo discount logic follows in db/query.py. Storing a
derived percentage would bake today's formula into historical rows.

Moderation model, deliberately asymmetric:
  - a BLACKLIST match hides the content immediately AND files a system report,
    because it is high-confidence and the text must never go live;
  - a USER report only flags — it does not hide. One person pressing "report"
    is not enough to remove another person's review, or reporting becomes a
    censorship button.

Editing never launders a flagged review: an existing row keeps whatever status
it already had. Only an explicit moderator action can move it back to active,
and no endpoint for that exists yet by design (see the admin section).
"""
from __future__ import annotations

import logging
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.auth import get_current_user
from api.dependencies import get_db

log = logging.getLogger(__name__)

router = APIRouter(tags=["Ratings"])

MIN_RATING, MAX_RATING = 1, 3

# Comma-separated emails allowed to read the moderation queue. Deliberately NOT
# a role system: users is a Supabase UUID + email with no role column, and
# inventing RBAC for one read-only endpoint is not worth it. Revisit if the
# moderation surface grows past viewing.
_ADMIN_EMAILS_ENV = "ADMIN_USER_EMAILS"


# ---------------------------------------------------------------------------
# Request / response shapes
# ---------------------------------------------------------------------------

class RatingIn(BaseModel):
    rating: int = Field(..., ge=MIN_RATING, le=MAX_RATING,
                        description="1 = poor, 2 = neutral, 3 = very good")
    comment: str | None = Field(None, max_length=2000)


class ReportIn(BaseModel):
    reason: str | None = Field(None, max_length=1000)


class RatingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rating: int
    comment: str | None
    created_at: str
    updated_at: str


class RatingsResponse(BaseModel):
    item_code: str
    count: int = Field(description="Number of ACTIVE ratings counted in the average")
    average_pct: float | None = Field(
        None, description="avg(rating)/3*100, computed at read time. null when count = 0")
    average_raw: float | None = Field(None, description="Raw 1-3 mean, for callers that want it")
    ratings: list[RatingOut]


class SubmitResponse(BaseModel):
    id: int
    status: str
    blocked: bool = Field(description="True when a blacklist term hid the comment")


# ---------------------------------------------------------------------------
# Blacklist
# ---------------------------------------------------------------------------

def _blacklist_hit(conn: Connection, comment: str | None) -> str | None:
    """Return the first blacklisted term found in `comment`, else None.

    WHOLE-WORD matching, not substring. Substring matching was the original
    implementation and was wrong: "זבל" would have fired inside "מזבלה" (a
    rubbish dump) and inside its own plural, hiding innocent text.

    \\b works correctly on Hebrew — verified empirically, not assumed. Python's
    re is Unicode-aware, Hebrew letters are \\w, so a boundary falls at spaces
    and punctuation exactly as it does for Latin. Confirmed matching for a bare
    term, a term mid-sentence, and a term against punctuation or parentheses;
    confirmed NOT matching "זבלים" or "מזבלה".

    KNOWN GAP — Hebrew inseparable prefixes. ה/ו/ב/כ/ל/מ/ש attach with no
    space, so "הזבל" is the same word with a definite article and does NOT
    match here. Allowing an optional prefix was tested and REJECTED: the
    pattern \\b[ובכלמהש]{0,2}TERM\\b flags "הזין את הנתונים" — "entered the
    data", one of the most ordinary phrases in Hebrew software text — because
    it contains the slang term זין. Hiding legitimate reviews is worse than
    missing a prefixed insult, especially since this filter sits in front of a
    human moderation queue and anything it misses can still be user-reported.

    The list is read per request rather than cached: it is tiny, it must take
    effect the moment a term is added, and a stale cache means abusive text
    goes live.
    """
    if not comment or not comment.strip():
        return None
    terms = [r[0] for r in conn.execute(text("SELECT term FROM rating_blacklist")).all()]
    if not terms:
        return None
    for term in terms:
        t = (term or "").strip()
        # Guard against an empty/whitespace row matching everything.
        if not t:
            continue
        # IGNORECASE is a no-op for Hebrew, which is caseless, but the list is
        # not required to stay Hebrew-only.
        if re.search(rf"\b{re.escape(t)}\b", comment, flags=re.IGNORECASE):
            return term
    return None


# ---------------------------------------------------------------------------
# Submit / edit
# ---------------------------------------------------------------------------

@router.post("/items/{item_code}/rating", response_model=SubmitResponse,
             summary="Create or edit the caller's rating for one item")
def submit_rating(
    item_code: str,
    body: RatingIn,
    user=Depends(get_current_user),
    conn: Connection = Depends(get_db),
):
    term = _blacklist_hit(conn, body.comment)
    blocked = term is not None

    row = conn.execute(text("""
        INSERT INTO ratings (user_id, item_code, rating, comment, status)
        VALUES (:uid, :code, :rating, :comment, :status)
        ON CONFLICT (user_id, item_code) DO UPDATE
        SET rating     = excluded.rating,
            comment    = excluded.comment,
            -- Status is PRESERVED on edit unless the new text trips the
            -- blacklist. Editing must not reset a flagged row to active —
            -- that would let anyone launder a reported review by retyping it.
            status     = CASE WHEN :blocked THEN 'hidden' ELSE ratings.status END,
            updated_at = now()
        RETURNING id, status
    """), {
        "uid": user["id"],
        "code": item_code,
        "rating": body.rating,
        "comment": body.comment,
        "status": "hidden" if blocked else "active",
        "blocked": blocked,
    }).mappings().one()

    if blocked:
        # A record of WHAT was blocked and WHY, so the queue shows the reason
        # rather than an unexplained hidden row. reporter_user_id stays NULL:
        # no human filed this.
        conn.execute(text("""
            INSERT INTO rating_reports (rating_id, reporter_user_id, reason, source)
            VALUES (:rid, NULL, :reason, 'blacklist')
        """), {"rid": row["id"], "reason": f"blacklist term matched: {term}"})
        log.warning("rating %s auto-hidden (item %s, user %s): term=%r",
                    row["id"], item_code, user["id"], term)

    conn.commit()

    if blocked:
        _notify_moderation(rating_id=row["id"], item_code=item_code,
                           user_email=user.get("email", ""), term=term)

    return SubmitResponse(id=row["id"], status=row["status"], blocked=blocked)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@router.post("/ratings/{rating_id}/report", status_code=201,
             summary="Flag a rating for moderator review")
def report_rating(
    rating_id: int,
    body: ReportIn,
    user=Depends(get_current_user),
    conn: Connection = Depends(get_db),
):
    exists = conn.execute(
        text("SELECT 1 FROM ratings WHERE id = :id"), {"id": rating_id}
    ).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Rating not found")

    # No uniqueness check on purpose: repeat reports from DIFFERENT users are
    # the signal. Status is deliberately untouched — a user report flags, it
    # does not hide, or reporting becomes a censorship button.
    conn.execute(text("""
        INSERT INTO rating_reports (rating_id, reporter_user_id, reason, source)
        VALUES (:rid, :uid, :reason, 'user')
    """), {"rid": rating_id, "uid": user["id"], "reason": body.reason})
    conn.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Public read
# ---------------------------------------------------------------------------

@router.get("/items/{item_code}/ratings", response_model=RatingsResponse,
            summary="Public ratings + aggregate for one item")
def get_ratings(item_code: str, conn: Connection = Depends(get_db)):
    """Active ratings only. Hidden and pending rows never appear here for
    anyone, including their own author — this endpoint has no auth and must not
    leak moderated content through a side channel."""
    agg = conn.execute(text("""
        SELECT count(*) AS n, avg(rating)::float AS mean
        FROM ratings WHERE item_code = :code AND status = 'active'
    """), {"code": item_code}).mappings().one()

    rows = conn.execute(text("""
        SELECT id, rating, comment,
               to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SSOF') AS created_at,
               to_char(updated_at, 'YYYY-MM-DD"T"HH24:MI:SSOF') AS updated_at
        FROM ratings
        WHERE item_code = :code AND status = 'active'
        ORDER BY updated_at DESC
    """), {"code": item_code}).mappings().all()

    mean = agg["mean"]
    return RatingsResponse(
        item_code=item_code,
        count=agg["n"],
        # Computed here, never stored. 1-3 maps to 33.3 / 66.7 / 100.
        average_pct=round(mean / MAX_RATING * 100, 1) if mean is not None else None,
        average_raw=round(mean, 3) if mean is not None else None,
        ratings=[RatingOut(**r) for r in rows],
    )


# ---------------------------------------------------------------------------
# Moderation queue (read-only)
# ---------------------------------------------------------------------------

def _admin_emails() -> set[str]:
    raw = os.environ.get(_ADMIN_EMAILS_ENV, "")
    return {e.strip().casefold() for e in raw.split(",") if e.strip()}


def require_admin(user=Depends(get_current_user)) -> dict:
    """Allowlist gate, not a role system.

    Fails CLOSED: an unset or empty ADMIN_USER_EMAILS admits nobody. The
    opposite default would silently open the queue to every signed-in user the
    moment the env var went missing.
    """
    allowed = _admin_emails()
    email = (user.get("email") or "").casefold()
    if not allowed or email not in allowed:
        # 404, not 403 — do not confirm the endpoint exists to non-admins.
        raise HTTPException(status_code=404)
    return user


@router.get("/admin/ratings/pending", summary="Moderation queue (allowlisted emails only)")
def pending_ratings(_admin=Depends(require_admin), conn: Connection = Depends(get_db)):
    """Everything not active, newest first, with its reports attached.

    VIEW ONLY. There is deliberately no endpoint to change status in this pass:
    seeing real moderation volume first should inform what the workflow needs,
    rather than committing to one now. That is the obvious next step.
    """
    rows = conn.execute(text("""
        SELECT r.id, r.user_id, r.item_code, r.rating, r.comment, r.status,
               to_char(r.created_at, 'YYYY-MM-DD"T"HH24:MI:SSOF') AS created_at,
               to_char(r.updated_at, 'YYYY-MM-DD"T"HH24:MI:SSOF') AS updated_at,
               COALESCE(
                   json_agg(
                       json_build_object(
                           'id', rep.id,
                           'source', rep.source,
                           'reason', rep.reason,
                           'reporter_user_id', rep.reporter_user_id,
                           'created_at', to_char(rep.created_at, 'YYYY-MM-DD"T"HH24:MI:SSOF')
                       ) ORDER BY rep.created_at DESC
                   ) FILTER (WHERE rep.id IS NOT NULL),
                   '[]'::json
               ) AS reports
        FROM ratings r
        LEFT JOIN rating_reports rep ON rep.rating_id = r.id
        WHERE r.status <> 'active'
        GROUP BY r.id
        ORDER BY r.created_at DESC
    """)).mappings().all()
    return {"count": len(rows), "items": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# Moderation notification — NOT IMPLEMENTED
# ---------------------------------------------------------------------------

def _notify_moderation(*, rating_id: int, item_code: str, user_email: str, term: str) -> None:
    """Would email info@xxl.co.il on a blacklist auto-hide.

    NOT WIRED UP: this repo has no email-sending infrastructure of any kind —
    no SMTP settings, no transactional-email client, and nothing in
    requirements.txt that can send mail (verified SU10R-1). Session 9i, which
    scoped "contact form ... + email notifications", is still listed as pending
    in docs/super/handoff_super.md, so that remains unbuilt too.

    Rather than guess at credentials or pick a provider unilaterally, this logs
    at WARNING so auto-hides are still discoverable via
    `journalctl -u scrp-api`, and the queue endpoint above is the real
    interim surface. Wire this once the email approach is decided.
    """
    log.warning(
        "[MODERATION] blacklist auto-hide — would email info@xxl.co.il: "
        "rating_id=%s item_code=%s author=%s term=%r",
        rating_id, item_code, user_email, term,
    )
