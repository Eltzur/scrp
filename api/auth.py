"""JWT authentication dependency for FastAPI using Supabase-issued tokens."""
import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import text

from api.dependencies import get_db

_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
_ALGORITHM  = "HS256"
_AUDIENCE   = "authenticated"

_bearer = HTTPBearer(auto_error=False)


def _decode(token: str) -> dict | None:
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_ALGORITHM], audience=_AUDIENCE)
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
    payload = _decode(credentials.credentials)
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
    payload = _decode(credentials.credentials)
    if not payload:
        return None
    user_id = payload.get("sub")
    email   = payload.get("email", "")
    if not user_id:
        return None
    _upsert_user(conn, user_id, email)
    return {"id": user_id, "email": email}
