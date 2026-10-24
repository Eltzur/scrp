"""The admin audit log (SU11A-54, table admin_audit in su11a54_admin.sql).

One row per admin write, inserted on the SAME connection as the change and
before its commit, so a write and its audit row land together or not at all.

No email and no raw user id is ever stored: the actor is
sha256(AUDIT_SALT + Supabase user id), the client IP the same with its own
prefix. The salt is a fixed constant, not a secret: it only keeps the hashes
from matching a plain sha256 of an id found elsewhere. The same admin always
gets the same actor hash, so the log still shows "who" as a stable pseudonym.
"""
from __future__ import annotations

import hashlib
import json

from fastapi import Request
from sqlalchemy import text

AUDIT_SALT = "xxl-admin-audit-v1:"

_TS = "'YYYY-MM-DD\"T\"HH24:MI:SSOF'"


def _hash(kind: str, value: str) -> str:
    return hashlib.sha256(f"{AUDIT_SALT}{kind}:{value}".encode("utf-8")).hexdigest()


def actor_hash(user_id: str) -> str:
    return _hash("actor", user_id)


def client_ip(request: Request | None) -> str | None:
    """nginx sets X-Real-IP (deploy/nginx/xxl-api-proxy.conf); direct calls
    on 127.0.0.1 fall back to the socket peer."""
    if request is None:
        return None
    ip = (request.headers.get("x-real-ip") or "").strip()
    if not ip and request.client:
        ip = request.client.host
    return ip or None


def record(conn, *, actor_id: str, action: str, target_type: str | None = None,
           target_id: str | int | None = None, detail: dict | None = None,
           ip: str | None = None) -> None:
    """Insert one audit row. Does NOT commit: the caller's commit covers it."""
    conn.execute(text("""
        INSERT INTO admin_audit (actor_hash, action, target_type, target_id, detail, ip_hash)
        VALUES (:actor, :action, :ttype, :tid, CAST(:detail AS jsonb), :ip)
    """), {
        "actor": actor_hash(actor_id),
        "action": action,
        "ttype": target_type,
        "tid": None if target_id is None else str(target_id),
        "detail": None if detail is None else json.dumps(detail, ensure_ascii=False),
        "ip": None if not ip else _hash("ip", ip),
    })


def _detail(v):
    """jsonb comes back as a dict from psycopg, as text from SQLite (tests)."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return None
    return v


def entries(conn, *, limit: int, before: int | None = None) -> list[dict]:
    """Newest first. `before` is an id cursor (the last id of the previous page).
    The actor is shown as the first 10 hex digits of its hash; ip_hash is not
    returned at all."""
    where = "WHERE id < :before" if before is not None else ""
    rows = conn.execute(text(f"""
        SELECT id, to_char(at, {_TS}) AS at, actor_hash, action, target_type, target_id, detail
        FROM admin_audit {where}
        ORDER BY id DESC
        LIMIT :limit
    """), {"limit": limit, "before": before}).mappings().all()
    conn.rollback()
    return [{
        "id": r["id"], "at": r["at"], "actor": (r["actor_hash"] or "")[:10],
        "action": r["action"], "target_type": r["target_type"], "target_id": r["target_id"],
        "detail": _detail(r["detail"]),
    } for r in rows]
