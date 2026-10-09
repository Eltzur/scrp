"""DELETE /account — in-app account deletion (SU11A-28, designed in SU11A-27).

Order of operations:
  1. Verify the token (no deleted-accounts check, so a retry after a 202 gets here).
  2. Require a fresh sign-in: iat within FRESH_SIGNIN_S, else 401 reauth_required.
  3. Refuse protected users (DELETE_PROTECTED_USER_IDS): 403 account_protected.
  4. One transaction: record the request in deleted_accounts, delete the user's
     flights rows (no FK to users), delete the users row. saved_baskets,
     favorites and ratings follow by ON DELETE CASCADE, rating_reports via
     rating_id by CASCADE, and reports the user filed keep their row with
     reporter_user_id SET NULL (schema re-verified in SU11A-28).
  5. Delete the Supabase auth user. Success -> auth_deleted_at set, 204.
     Failure -> attempts + 1, last_error = short code, 202 deletion_pending.
     A Supabase failure never becomes a 500; scripts/sweep_account_deletes.py
     retries pending rows.
Repeating the call is safe: step 4 finds nothing to delete and step 5 treats a
404 from Supabase as success.
"""
import logging
import os
import time
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text

from api import supabase_admin
from api.auth import get_user_for_account_delete
from api.dependencies import get_db

log = logging.getLogger(__name__)

router = APIRouter(tags=["account"])

FRESH_SIGNIN_S = 300

INSERT_REQUEST_SQL = text(
    "INSERT INTO deleted_accounts (user_id) VALUES (CAST(:uid AS uuid)) "
    "ON CONFLICT (user_id) DO NOTHING"
)
DELETE_APP_ROWS_SQL = [
    text("DELETE FROM flights.alerts WHERE user_id = CAST(:uid AS uuid)"),
    text("DELETE FROM flights.saved_searches WHERE user_id = CAST(:uid AS uuid)"),
    text("DELETE FROM users WHERE id = :uid"),
]
MARK_DONE_SQL = text(
    "UPDATE deleted_accounts SET auth_deleted_at = CURRENT_TIMESTAMP, last_error = NULL "
    "WHERE user_id = CAST(:uid AS uuid)"
)
MARK_FAILED_SQL = text(
    "UPDATE deleted_accounts SET attempts = attempts + 1, last_error = :err "
    "WHERE user_id = CAST(:uid AS uuid)"
)


def _code(status: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code})


def protected_user_ids() -> set[str]:
    raw = os.environ.get("DELETE_PROTECTED_USER_IDS", "")
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def is_fresh(iat, now: float | None = None) -> bool:
    if iat is None:
        return False
    now = time.time() if now is None else now
    return now - iat <= FRESH_SIGNIN_S


def finish_auth_delete(conn, user_id: str) -> tuple[bool, str | None]:
    """Call the Supabase admin API once and record the outcome. Shared with the sweep."""
    try:
        ok, err = supabase_admin.delete_auth_user(user_id)
    except supabase_admin.AdminConfigError:
        ok, err = False, "config"
    conn.execute(MARK_DONE_SQL if ok else MARK_FAILED_SQL, {"uid": user_id, "err": err})
    conn.commit()
    return ok, err


@router.delete("/account", status_code=204, summary="Delete the signed-in account (fresh sign-in required)")
def delete_account(user=Depends(get_user_for_account_delete), conn=Depends(get_db)):
    user_id = user["id"]
    try:
        uuid.UUID(user_id)
    except ValueError:
        return _code(401, "invalid_token")

    if not is_fresh(user["iat"]):
        return _code(401, "reauth_required")
    if user_id.lower() in protected_user_ids():
        return _code(403, "account_protected")

    params = {"uid": user_id}
    try:
        conn.execute(INSERT_REQUEST_SQL, params)
        for stmt in DELETE_APP_ROWS_SQL:
            conn.execute(stmt, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    ok, err = finish_auth_delete(conn, user_id)
    if ok:
        log.info("account deleted user_id=%s", user_id)
        return Response(status_code=204)
    log.warning("account delete pending user_id=%s error=%s", user_id, err)
    return _code(202, "deletion_pending")
