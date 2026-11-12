"""SU11A-82 (SU11A-79 H2): shared helpers for the server alerts.

Used by scripts/ops_alert.py (a unit failed) and scripts/ops_health_check.py
(the daily check). Mail goes through api/mailer.py, i.e. the SMTP settings the
API already uses (smtp_host, smtp_port, smtp_user, smtp_password,
moderation_email_to from ~/scrp/.env via the unit's EnvironmentFile). This
module never reads, prints or logs those values.

Every text that goes into a mail passes through redact(): journal lines are
written by our own programs and should hold no secret, but a stray connection
string, token or key must never leave the server by e-mail.
"""
from __future__ import annotations

import os
import re

DEFAULT_HOST_LABEL = "scrp-prod-il"
DEFAULT_TO = "info@xxl.co.il"

_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    # scheme://user:password@host  ->  scheme://user:***@host
    (re.compile(r"(\b[a-z][a-z0-9+.-]*://[^\s:/@]+):[^\s@/]+@", re.I), r"\1:***@"),
    # JWTs (Supabase tokens, anon / service keys)
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "***JWT***"),
    # Authorization headers
    (re.compile(r"(\bauthorization\b\s*[:=]\s*(?:bearer\s+|basic\s+)?|\bbearer\s+)[^\s,;]+", re.I), r"\1***"),
    # key=value / key: value pairs whose key names a secret
    (re.compile(r"(\b[\w.-]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)[\w.-]*\b\s*[=:]\s*)"
                r"(\"[^\"]*\"|'[^']*'|[^\s,;]+)", re.I), r"\1***"),
    # Supabase secret keys, AWS-style and Google API keys
    (re.compile(r"\bsb_secret_[A-Za-z0-9_-]+"), "***"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "***"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "***"),
]


def redact(text: str) -> str:
    """Mask anything that looks like a credential. Idempotent."""
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


def host_label() -> str:
    """The server name used in subjects (env ops_host_label, default scrp-prod-il)."""
    return (os.environ.get("ops_host_label") or DEFAULT_HOST_LABEL).strip() or DEFAULT_HOST_LABEL


def alert_recipient() -> str:
    """env ops_alert_to, else info@xxl.co.il (an address, not a secret)."""
    return (os.environ.get("ops_alert_to") or DEFAULT_TO).strip() or DEFAULT_TO


def env_number(name: str, default: float) -> float:
    """A numeric setting from the environment; an empty or bad value means the default."""
    raw = (os.environ.get(name) or "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def send_alert(subject: str, body: str) -> bool:
    """Send one alert mail via api/mailer.py. Returns True when sent. Never raises."""
    from api import mailer  # imported late: tests patch it, and nothing loads SMTP at import time
    return mailer.send_email(redact(subject), redact(body), to=alert_recipient())
