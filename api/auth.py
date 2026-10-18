"""JWT authentication using Supabase ES256 + JWKS public-key verification.

Supabase migrated from HS256 (shared secret) to ES256 (asymmetric ECC).
Tokens are verified against the public keys published at:
  {SUPABASE_URL}/auth/v1/.well-known/jwks.json

JWKS is cached in process memory and refreshed automatically on a kid miss
(handles key rotation). A threading.Lock prevents thundering-herd refreshes.
"""
import logging
import os
import threading
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
    global _jwks_cache

    if kid in _jwks_cache:          # fast path — no lock needed for reads
        return _jwks_cache[kid]

    with _jwks_lock:                # slow path — only one refresh at a time
        if kid in _jwks_cache:      # re-check: another thread may have refreshed
            return _jwks_cache[kid]
        log.info("JWKS cache miss for kid=%s — refreshing from %s", kid, _JWKS_URL)
        _jwks_cache = _fetch_jwks()
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
        log.warning("No public key for kid=%s after JWKS refresh", kid)
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
