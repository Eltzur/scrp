"""Supabase Auth admin calls (SU11A-28). Server-side only.

The admin key (SUPABASE_SERVICE_ROLE_KEY) has full power over the Supabase
project shared by super, web and flights. It is read from the environment at
call time, sent only in request headers, and never logged, raised or returned:
log lines carry the user id and an HTTP status code, nothing else.

Header rule (Supabase "API keys" docs, checked 2026-10-09): the key always goes
in `apikey`. New `sb_secret_...` keys are not JWTs, so `Authorization: Bearer`
is added only for a legacy JWT-style service-role key (starts with "eyJ").
"""
import logging
import os

import httpx

log = logging.getLogger(__name__)

_TIMEOUT_S = 10.0


class AdminConfigError(RuntimeError):
    """A required admin setting is missing. The message never contains a value."""


def admin_headers(key: str) -> dict[str, str]:
    headers = {"apikey": key}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def delete_auth_user(user_id: str) -> tuple[bool, str | None]:
    """Hard-delete one Supabase auth user. No retry inside the call.

    Returns (True, None) on 200/204, and on 404 (already gone).
    Returns (False, <short code>) on any other status, a network error or a
    timeout. Raises AdminConfigError when SUPABASE_URL or the key is unset.
    """
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url:
        raise AdminConfigError("SUPABASE_URL is not set")
    if not key:
        raise AdminConfigError("SUPABASE_SERVICE_ROLE_KEY is not set")

    try:
        resp = httpx.request(
            "DELETE",
            f"{url}/auth/v1/admin/users/{user_id}",
            headers=admin_headers(key),
            json={"should_soft_delete": False},
            timeout=_TIMEOUT_S,
        )
    except httpx.TimeoutException:
        log.warning("auth admin delete user_id=%s failed: timeout", user_id)
        return False, "timeout"
    except httpx.HTTPError as exc:
        # The exception text can embed the request; log only its class name.
        log.warning("auth admin delete user_id=%s failed: %s", user_id, type(exc).__name__)
        return False, "network"

    status = resp.status_code
    if status in (200, 204, 404):
        log.info("auth admin delete user_id=%s status=%s", user_id, status)
        return True, None
    log.warning("auth admin delete user_id=%s status=%s", user_id, status)
    return False, f"http_{status}"
