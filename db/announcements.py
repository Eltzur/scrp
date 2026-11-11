"""SU11A-77: server-delivered app notices (table app_announcements,
db/migrations/su11a77_announcements.sql).

Rules (checked here, on the server, for every save - the admin screen only
repeats them as help text):
  - lengths: title 1..60, body 1..600 characters (after trimming);
  - plain text only: no markup (< >) and no links (http(s)://, www., e-mail,
    bare domains) - no payment or subscription links in the apps (Apple 3.1.1,
    Play Billing);
  - for 'ios' and 'both': none of בהרצה, בטא, beta, ניסיון, trial, "test version"
    (case-insensitive; Hebrew also inside a word, e.g. "בבטא") - Apple 2.2 does
    not allow beta / trial wording in an App Store app.
`version` grows only when the title or body changes, so a device shows a new
text once; switching a notice on / off does not change it.

The public read is cached in-process for CACHE_TTL_S per platform (and dropped
on every admin write in this process), so GET /announcements/active touches the
database at most once per 5 minutes per worker.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass

from sqlalchemy import text

log = logging.getLogger(__name__)

PLATFORMS = ("ios", "android", "both")
PUBLIC_PLATFORMS = ("ios", "android")
TITLE_MAX = 60
BODY_MAX = 600
CACHE_TTL_S = 300.0

# Hebrew words match inside a word (prefixes ב / ה / ו / ש...); Latin ones as words.
_HE_FORBIDDEN = ("בהרצה", "בטא", "ניסיון")
_EN_FORBIDDEN = re.compile(r"\b(beta|trial|test\s+version)\b", re.IGNORECASE)
_MARKUP = re.compile(r"[<>]")
_LINK = re.compile(
    r"(https?://|ftp://|www\.|mailto:|tel:|\b[\w.+-]+@[\w-]+\.[\w.]+\b"
    r"|\b[a-z0-9-]+\.(?:co\.il|org\.il|com|net|org|il|io|app|me|ly|info|biz|shop|store)\b)",
    re.IGNORECASE,
)


class AnnouncementError(ValueError):
    """A rejected save; `code` is the API error code, `field` the offending field."""

    def __init__(self, code: str, field: str | None = None, word: str | None = None):
        super().__init__(code)
        self.code, self.field, self.word = code, field, word


def clean(value: str | None) -> str:
    """Trim, and fold runs of spaces / tabs (line breaks in the body stay)."""
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in (value or "").replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).strip()


def forbidden_word(textval: str) -> str | None:
    """The first Apple 2.2 word found, or None."""
    low = textval.lower()
    for w in _HE_FORBIDDEN:
        if w in low:
            return w
    m = _EN_FORBIDDEN.search(textval)
    return m.group(1).lower() if m else None


def validate(platform: str, title: str | None, body: str | None) -> tuple[str, str]:
    """(title, body) cleaned, or AnnouncementError."""
    if platform not in PLATFORMS:
        raise AnnouncementError("unknown_platform", "platform")
    t, b = clean(title), clean(body)
    for field, val, mx in (("title", t, TITLE_MAX), ("body", b, BODY_MAX)):
        if not val:
            raise AnnouncementError("empty", field)
        if len(val) > mx:
            raise AnnouncementError("too_long", field)
        if _MARKUP.search(val):
            raise AnnouncementError("markup_not_allowed", field)
        if _LINK.search(val):
            raise AnnouncementError("links_not_allowed", field)
        if platform in ("ios", "both"):
            w = forbidden_word(val)
            if w:
                raise AnnouncementError("beta_wording_not_allowed_ios", field, w)
    return t, b


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
_COLS = "id, platform, title, body, active, version, updated_at, updated_by_hash"


def all_rows(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(text(f"SELECT {_COLS} FROM app_announcements ORDER BY id")).mappings()]


def row(conn, platform: str, lock: bool = False) -> dict | None:
    r = conn.execute(text(f"SELECT {_COLS} FROM app_announcements WHERE platform = :p"
                          f"{' FOR UPDATE' if lock and conn.dialect.name == 'postgresql' else ''}"),
                     {"p": platform}).mappings().first()
    return dict(r) if r else None


def update_text(conn, platform: str, title: str, body: str, actor_hash: str) -> tuple[dict, dict]:
    """(before, after). Validates; bumps version only when the text changes;
    an active notice is re-checked by validate() like any save. Does NOT commit."""
    t, b = validate(platform, title, body)
    before = row(conn, platform, lock=True)
    if before is None:
        raise AnnouncementError("not_found", "platform")
    changed = (t, b) != (before["title"], before["body"])
    conn.execute(text("""
        UPDATE app_announcements
        SET title = :t, body = :b, version = version + :bump, updated_at = now(), updated_by_hash = :a
        WHERE platform = :p"""), {"t": t, "b": b, "bump": 1 if changed else 0, "a": actor_hash, "p": platform})
    invalidate()
    return before, row(conn, platform)


def set_active(conn, platform: str, active: bool, actor_hash: str) -> tuple[dict, dict]:
    """(before, after). Switching on re-validates the stored text (an empty or
    no-longer-allowed text cannot go live). Does NOT commit."""
    before = row(conn, platform, lock=True)
    if before is None:
        raise AnnouncementError("not_found", "platform")
    if active:
        validate(platform, before["title"], before["body"])
    conn.execute(text("""
        UPDATE app_announcements SET active = :on, updated_at = now(), updated_by_hash = :a
        WHERE platform = :p"""), {"on": active, "a": actor_hash, "p": platform})
    invalidate()
    return before, row(conn, platform)


@dataclass(frozen=True)
class Notice:
    id: int
    version: int
    title: str
    body: str


def _load_active(conn, platform: str) -> Notice | None:
    """The platform's own active row first, else the active 'both' row."""
    rows = conn.execute(text("""
        SELECT id, platform, title, body, version FROM app_announcements
        WHERE active AND platform IN (:p, 'both')"""), {"p": platform}).mappings().all()
    pick = next((r for r in rows if r["platform"] == platform), None) or next(iter(rows), None)
    return Notice(pick["id"], pick["version"], pick["title"], pick["body"]) if pick else None


_cache: dict[str, tuple[float, Notice | None]] = {}
_lock = threading.Lock()


def active_for(conn_factory, platform: str, now: float | None = None) -> Notice | None:
    """The cached active notice for 'ios' / 'android'. `conn_factory()` is called
    only on a cache miss (at most once per CACHE_TTL_S per platform per process)."""
    if platform not in PUBLIC_PLATFORMS:
        raise AnnouncementError("unknown_platform", "platform")
    t = time.monotonic() if now is None else now
    with _lock:
        hit = _cache.get(platform)
        if hit is not None and t - hit[0] < CACHE_TTL_S:
            return hit[1]
    try:
        value = _load_active(conn_factory(), platform)
    except Exception as exc:  # noqa: BLE001 - no table yet / DB trouble: no notice, cached like one
        log.warning("announcements unavailable: %s", type(exc).__name__)
        value = None
    with _lock:
        _cache[platform] = (t, value)
    return value


def invalidate() -> None:
    with _lock:
        _cache.clear()
