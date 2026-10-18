"""Terms-of-use consent for the signed-in user (SU11A-44). See api/terms.py.

Sign-up consent arrives through the token's user_metadata and is copied by
_upsert_user; these endpoints serve existing users, whom the clients ask the
first time they post a rating.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.auth import ApiCodeError, get_current_user
from api.dependencies import get_db
from api.terms import TERMS_VERSION

router = APIRouter(tags=["Terms"])


class TermsStatus(BaseModel):
    current_version: str
    accepted_version: str | None
    accepted_at: str | None
    required: bool = Field(description="True when the accepted version is not the current one")


class AcceptIn(BaseModel):
    version: str = Field(..., max_length=32)


@router.get("/me/terms", response_model=TermsStatus, summary="The caller's terms consent")
def my_terms(user=Depends(get_current_user), conn: Connection = Depends(get_db)):
    row = conn.execute(text("""
        SELECT terms_version,
               to_char(terms_accepted_at, 'YYYY-MM-DD"T"HH24:MI:SSOF') AS accepted_at
        FROM users WHERE id = :uid
    """), {"uid": user["id"]}).mappings().first()
    accepted = row["terms_version"] if row else None
    return TermsStatus(
        current_version=TERMS_VERSION,
        accepted_version=accepted,
        accepted_at=row["accepted_at"] if row else None,
        required=accepted != TERMS_VERSION,
    )


@router.post("/me/terms", status_code=204, summary="Accept the current terms")
def accept_terms(body: AcceptIn, user=Depends(get_current_user), conn: Connection = Depends(get_db)):
    """Only the current version can be accepted: a client showing older terms
    gets 400 terms_version_mismatch and must reload them."""
    if body.version != TERMS_VERSION:
        raise ApiCodeError(400, "terms_version_mismatch")
    conn.execute(text("""
        UPDATE users SET terms_version = :v, terms_accepted_at = :now WHERE id = :uid
    """), {"v": TERMS_VERSION, "now": datetime.now(timezone.utc), "uid": user["id"]})
    conn.commit()
    return Response(status_code=204)
