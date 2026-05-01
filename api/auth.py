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
from typing import Optional

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError
from sqlalchemy import text

from api.dependencies import get_db

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


def _upsert_user(conn, user_id: str, email: str) -> None:
    conn.execute(text("""
        INSERT INTO users (id, email) VALUES (:id, :email)
        ON CONFLICT(id) DO UPDATE SET email = excluded.email
    """), {"id": user_id, "email": email})
    conn.commit()


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
    _upsert_user(conn, user_id, email)
    return {"id": user_id, "email": email}


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    conn=Depends(get_db),
) -> dict | None:
    if not credentials:
        return None
    payload = _decode(credentials.credentials)   # may raise 503
    if not payload:
        return None
    user_id = payload.get("sub")
    email   = payload.get("email", "")
    if not user_id:
        return None
    _upsert_user(conn, user_id, email)
    return {"id": user_id, "email": email}
