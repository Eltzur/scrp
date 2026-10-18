"""Terms of use version and the sign-up consent record (SU11A-44, designed in SU11A-42).

TERMS_VERSION is the ONE place the API names the current terms. The web
(web/src/legal/terms.ts) and the app (src/legal/terms.ts) carry the same string;
change all three together, and the clients will ask existing users to accept
again (GET /me/terms -> required).

Sign-up consent travels without a new endpoint: the clients pass
options.data = {terms_version, terms_accepted_at} to supabase.auth.signUp, Supabase
keeps it as user_metadata, and it arrives in every access token. _upsert_user
(api/auth.py) copies it into users.terms_version / users.terms_accepted_at the first
time it sees a user with no consent recorded, and never overwrites afterwards.
user_metadata is editable by the user (updateUser), which is why it is copied once
and then ignored.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

TERMS_VERSION = "2026-10-1"

_MAX_VERSION_LEN = 32

# RATINGS_REQUIRE_TERMS (scrp-api EnvironmentFile, read per request, same casing
# convention as SEARCH_V2 / ADMIN_USER_EMAILS): when on, POST /items/{code}/rating
# answers 403 terms_required until the caller accepted TERMS_VERSION. Default OFF.
# Keep it off until build 8 has replaced 1.2.1 on Play: older builds have no
# consent flow, so rating from them would break.
_REQUIRE_TERMS_ENV = "RATINGS_REQUIRE_TERMS"


def require_terms_for_ratings() -> bool:
    return (os.environ.get(_REQUIRE_TERMS_ENV) or "").strip().lower() in ("1", "true", "on")


def consent_from_claims(payload: dict | None, now: datetime | None = None
                        ) -> tuple[str | None, datetime | None]:
    """(terms_version, terms_accepted_at) from a token's user_metadata, or (None, None).

    The version must be a non-empty string of at most 32 characters. The timestamp
    is the metadata value when it parses and is not in the future, else `now`.
    """
    now = now or datetime.now(timezone.utc)
    meta = (payload or {}).get("user_metadata")
    if not isinstance(meta, dict):
        return None, None
    version = meta.get("terms_version")
    if not isinstance(version, str):
        return None, None
    version = version.strip()
    if not version or len(version) > _MAX_VERSION_LEN:
        return None, None
    return version, _parse_accepted_at(meta.get("terms_accepted_at"), now)


def _parse_accepted_at(raw, now: datetime) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        return now
    try:
        ts = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return now
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts if ts <= now else now
