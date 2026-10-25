"""JWT authentication using Supabase ES256 + JWKS public-key verification.

Supabase migrated from HS256 (shared secret) to ES256 (asymmetric ECC).
Tokens are verified against the public keys published at:
  {SUPABASE_URL}/auth/v1/.well-known/jwks.json

JWKS is cached in process memory and refreshed automatically on a kid miss
(handles key rotation). A threading.Lock prevents thundering-herd refreshes.

SU11A-49 (F-05): a kid miss refetches at most once per JWKS_MIN_REFRESH_S
after the last successful fetch. Before, every token carrying a made-up kid
cost one outbound call to Supabase under the global lock, so anyone could tie
up workers with forged headers. Inside the window an unknown kid is simply an
invalid token (401). A failed fetch is retried no sooner than
JWKS_FAIL_BACKOFF_S later, and requests in between still answer 503 ("cannot
verify"), as a failed fetch always did.
"""
import logging
import os
import threading
import time
import uuid
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError
from sqlalchemy import text

from api.dependencies import get_db
from api.terms import consent_from_claims

log = logging.getLogger(__name__)

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
_JWKS_URL     = f"{_SUPABASE_URL}/auth/v1/.well-known/jwks.json" if _SUPABASE_URL else ""
_AUDIENCE     = "authenticated"
_ALGORITHM    = "ES256"

_bearer = HTTPBearer(auto_error=False)

# kid → JWK dict.  Populated lazily on first verification request.
_jwks_cache: dict[str, dict] = {}
_jwks_lock  = threading.Lock()

JWKS_MIN_REFRESH_S = 60.0
JWKS_FAIL_BACKOFF_S = 5.0
# time.monotonic() of the last successful / failed fetch; None = never.
_jwks_ok_at: float | None = None
_jwks_fail_at: float | None = None


def _fetch_jwks() -> dict[str, dict]:
    """Fetch JWKS from Supabase and return as {kid: jwk_dict}."""
    if not _JWKS_URL:
        raise RuntimeError("SUPABASE_URL env var is not set")
    resp = httpx.get(_JWKS_URL, timeout=10)
    resp.raise_for_status()
    keys = resp.json().get("keys", [])
    return {k["kid"]: k for k in keys if "kid" in k}


def _get_jwk(kid: str) -> Optional[dict]:
    """
    Return the JWK for kid, fetching / refreshing the JWKS if needed.
    Raises RuntimeError / httpx.HTTPError on fetch failure (caller maps to 503).
    Uses a lock so concurrent cache-miss requests share one JWKS fetch.
    """
    global _jwks_cache, _jwks_ok_at, _jwks_fail_at

    if kid in _jwks_cache:          # fast path — no lock needed for reads
        return _jwks_cache[kid]

    with _jwks_lock:                # slow path — only one refresh at a time
        if kid in _jwks_cache:      # re-check: another thread may have refreshed
            return _jwks_cache[kid]
        now = time.monotonic()
        if _jwks_ok_at is not None and now - _jwks_ok_at < JWKS_MIN_REFRESH_S:
            # Fresh set and still no such kid: not one of ours. No fetch.
            log.debug("JWKS kid miss inside the refresh window — not refetching")
            return None
        if _jwks_fail_at is not None and now - _jwks_fail_at < JWKS_FAIL_BACKOFF_S:
            raise RuntimeError("JWKS fetch backing off after a failure")
        # The kid comes from an unverified header: never log it raw.
        log.info("JWKS cache miss — refreshing from %s", _JWKS_URL)
        try:
            fresh = _fetch_jwks()
        except Exception:
            _jwks_fail_at = now
            raise
        _jwks_cache = fresh
        _jwks_ok_at = now
        _jwks_fail_at = None
        return _jwks_cache.get(kid)


def _decode(token: str) -> Optional[dict]:
    """
    Verify a Supabase ES256 JWT against the cached JWKS.

    Returns the decoded payload on success, None on any auth failure.
    Raises HTTPException(503) only if the JWKS endpoint itself is unreachable
    (distinguishes "server can't verify" from "token is invalid").
    """
    # Step 1 — parse header without verification to extract kid and alg
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        return None

    if header.get("alg") != _ALGORITHM:
        log.warning("JWT alg=%s rejected — only ES256 accepted", header.get("alg"))
        return None

    kid = header.get("kid")
    if not kid:
        return None

    # Step 2 — look up the public key
    try:
        jwk = _get_jwk(kid)
    except Exception as exc:
        log.error("JWKS fetch failed: %s", exc)
        raise HTTPException(status_code=503, detail="Auth service temporarily unavailable")

    if jwk is None:
        # debug, not warning: forged kids would otherwise flood the journal.
        log.debug("No public key for the token's kid")
        return None

    # Step 3 — verify signature, audience, and expiry
    try:
        return jwt.decode(token, jwk, algorithms=[_ALGORITHM], audience=_AUDIENCE)
    except ExpiredSignatureError:
        return None
    except JWTClaimsError:
        return None
    except JWTError:
        return None


class ApiCodeError(Exception):
    """An error answered as {"code": <code>} with the given status (SU11A-28).
    The handler is registered in api/main.py."""

    def __init__(self, status_code: int, code: str):
        super().__init__(code)
        self.status_code = status_code
        self.code = code


def _upsert_user(conn, user_id: str, email: str, payload: dict | None = None) -> None:
    """Create or refresh the users row. SU11A-44: also copies the sign-up terms
    consent from the token's user_metadata, in the same statement, only while
    users.terms_version is still NULL (never overwrites; see api/terms.py)."""
    version, accepted_at = consent_from_claims(payload)
    conn.execute(text("""
        INSERT INTO users (id, email, terms_version, terms_accepted_at)
        VALUES (:id, :email, :tv, :ta)
        ON CONFLICT(id) DO UPDATE SET
            email             = excluded.email,
            terms_accepted_at = CASE WHEN users.terms_version IS NULL
                                     THEN excluded.terms_accepted_at
                                     ELSE users.terms_accepted_at END,
            terms_version     = COALESCE(users.terms_version, excluded.terms_version)
    """), {"id": user_id, "email": email, "tv": version, "ta": accepted_at})
    conn.commit()


def _is_deleted(conn, user_id: str) -> bool:
    """One primary-key lookup in deleted_accounts (SU11A-28). A sub that is not a
    UUID can never be in the table, so it skips the query."""
    try:
        uuid.UUID(user_id)
    except ValueError:
        return False
    row = conn.execute(
        text("SELECT 1 FROM deleted_accounts WHERE user_id = CAST(:uid AS uuid)"),
        {"uid": user_id},
    ).first()
    return row is not None


def _verified_claims(credentials: HTTPAuthorizationCredentials | None) -> dict | None:
    """Decoded payload with a `sub`, or None. May raise HTTPException(503)."""
    if not credentials:
        return None
    payload = _decode(credentials.credentials)
    if not payload or not payload.get("sub"):
        return None
    return payload


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    conn=Depends(get_db),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _decode(credentials.credentials)   # may raise 503
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_id = payload.get("sub")
    email   = payload.get("email", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    # SU11A-28: a deleted account's still-valid token must not recreate its row.
    if _is_deleted(conn, user_id):
        raise ApiCodeError(401, "account_deleted")
    _upsert_user(conn, user_id, email, payload)
    return {"id": user_id, "email": email}


def get_current_user_login_code(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    conn=Depends(get_db),
) -> dict:
    """get_current_user, but a missing or invalid token answers 401
    {"code":"login_required"} (SU11A-57: the clients show "registered users
    only" on that code). account_deleted and a JWKS outage (503) are unchanged."""
    if not credentials:
        raise ApiCodeError(401, "login_required")
    try:
        return get_current_user(credentials, conn)
    except HTTPException as exc:
        if exc.status_code == 401:
            raise ApiCodeError(401, "login_required") from None
        raise


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    conn=Depends(get_db),
) -> dict | None:
    payload = _verified_claims(credentials)       # may raise 503
    if not payload:
        return None
    user_id = payload["sub"]
    email   = payload.get("email", "")
    # SU11A-28: public endpoints answer a deleted account as anonymous, and its
    # row is not recreated.
    if _is_deleted(conn, user_id):
        return None
    _upsert_user(conn, user_id, email, payload)
    return {"id": user_id, "email": email}


def get_user_id_soft(request: Request) -> str | None:
    """The caller's user id, or None: for GET /items/{code}/ratings only (SU11A-44).

    ANY token problem answers as signed out — no header, not Bearer, garbage,
    expired, bad signature, a JWKS fetch failure (which _decode turns into 503)
    or anything else. It never raises, never answers 401/503 and never writes
    the users row: a Supabase hiccup must not take public reviews down for
    signed-in users. Logged at debug level only, without the token.
    """
    try:
        header = request.headers.get("authorization") or ""
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return None
        payload = _decode(token.strip())
        sub = (payload or {}).get("sub")
        return sub if isinstance(sub, str) and sub else None
    except Exception as exc:
        log.debug("soft auth: answering as anonymous (%s)", type(exc).__name__)
        return None


def get_user_for_account_delete(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """DELETE /account only (SU11A-28): verifies the token but skips the
    deleted-accounts check (a retry after a 202 must get through) and does not
    upsert the users row. Returns id and iat (None when the claim is absent)."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _verified_claims(credentials)       # may raise 503
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    iat = payload.get("iat")
    return {"id": payload["sub"], "iat": iat if isinstance(iat, (int, float)) else None}


# ---------------------------------------------------------------------------
# Admin gate (SU11A-54)
# ---------------------------------------------------------------------------
# Comma-separated emails allowed into the admin endpoints. Deliberately NOT a
# role system: users is a Supabase UUID + email with no role column.
ADMIN_EMAILS_ENV = "ADMIN_USER_EMAILS"


def admin_emails() -> set[str]:
    raw = os.environ.get(ADMIN_EMAILS_ENV, "")
    return {e.strip().casefold() for e in raw.split(",") if e.strip()}


def require_admin_mfa(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    conn=Depends(get_db),
) -> dict:
    """Every /admin/* endpoint (SU11A-54). ALL of:
      1. a valid Supabase token (same verification as every other endpoint);
      2. its email in ADMIN_USER_EMAILS — fails CLOSED: unset or empty admits
         nobody — and the account not deleted;
      3. the claim aal == "aal2": the session passed a TOTP check.
    1 or 2 missing -> 403 {"code":"admin_required"}; 3 missing -> 403
    {"code":"mfa_required"}. The allowlist is checked first, so a non-admin
    never learns that a second factor exists. A JWKS fetch failure stays 503.

    Never writes the users row (an admin needs none) and returns the user id
    only: callers must not get the email in hand to log it.
    """
    payload = _verified_claims(credentials)       # may raise 503
    if not payload:
        raise ApiCodeError(403, "admin_required")
    allowed = admin_emails()
    email = (payload.get("email") or "").casefold()
    if not allowed or not email or email not in allowed:
        raise ApiCodeError(403, "admin_required")
    if _is_deleted(conn, payload["sub"]):
        raise ApiCodeError(403, "admin_required")
    if payload.get("aal") != "aal2":
        raise ApiCodeError(403, "mfa_required")
    return {"id": payload["sub"]}
