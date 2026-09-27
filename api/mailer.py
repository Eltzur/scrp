"""Outbound mail for internal alerts (SU10S-7).

WHY PLAIN SMTP AND NOT A TRANSACTIONAL PROVIDER. This sends internal-only
alerts to one inbox we own. SendGrid — the provider floated in earlier
sessions — dropped its free plan in 2025, and every alternative wants DNS
records and a sender-verification dance for what is, in the end, one mailbox
emailing another inside the same domain. Sending through the domain's own
mailbox provider needs no DNS change at all: mail leaves from Hostinger's
servers, which `xxl.co.il`'s SPF record already authorises
(`v=spf1 include:_spf.mail.hostinger.com ~all`, verified SU10S-7), so
alignment is inherited rather than configured. Cost: zero. New dependencies:
none — `smtplib` and `email` are stdlib.

THIS IS FOR INTERNAL ALERTS ONLY. User-facing mail (flights price alerts, a
contact-form autoresponder) is a different problem: deliverability to
strangers' inboxes, bounce handling, unsubscribe headers, reputation. Do not
grow this module into that — evaluate a real provider at that point. The SMTP
specifics are deliberately confined to `_smtp_send` so swapping the transport
touches one function.

CONFIG comes from the environment, lowercase per CLAUDE.md:

    smtp_host  smtp_port  smtp_user  smtp_password  moderation_email_to

NOTE FOR DEPLOYMENT: the API receives its environment from systemd's
`EnvironmentFile=/home/dude/scrp/.env` (there is no `load_dotenv()` anywhere
in `api/`). systemd reads that file when the unit *starts*, so adding these
keys to `.env` does nothing until `scrp-api` is restarted.

Nothing here ever raises into a caller and nothing here ever logs a
credential.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
import time
from collections import deque
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10

# Rolling caps. These exist so a bug, or a burst of abuse, cannot turn the
# moderation queue into a mail flood that gets the sending mailbox
# rate-limited by the provider.
_MAX_PER_HOUR = 20
_MAX_PER_DAY = 60

# Send timestamps, newest last. In memory ON PURPOSE: a shared counter would
# need Redis or a table, which is a lot of infrastructure for a guard rail.
#
# CONSEQUENCE: gunicorn runs `--workers 2`, and each worker is a separate
# process with its own copy of this deque, so the EFFECTIVE ceiling is
# 2 x the numbers above (40/hour, 120/day) in the worst case where load
# happens to split evenly. That is well within what the mailbox tolerates and
# still bounds the failure, so it is accepted rather than engineered around.
# If the worker count ever grows a lot, revisit.
_sent_at: deque[float] = deque()


def _prune(now: float) -> None:
    while _sent_at and now - _sent_at[0] > 86_400:
        _sent_at.popleft()


def _throttled(now: float) -> str | None:
    """Reason string when the caps are hit, else None."""
    _prune(now)
    last_hour = sum(1 for t in _sent_at if now - t <= 3_600)
    if last_hour >= _MAX_PER_HOUR:
        return f"{last_hour} sent in the last hour (cap {_MAX_PER_HOUR})"
    if len(_sent_at) >= _MAX_PER_DAY:
        return f"{len(_sent_at)} sent in the last 24h (cap {_MAX_PER_DAY})"
    return None


def _config() -> dict[str, str] | None:
    """Env config, or None when anything required is missing."""
    cfg = {
        "host": os.environ.get("smtp_host", "").strip(),
        "port": os.environ.get("smtp_port", "").strip(),
        "user": os.environ.get("smtp_user", "").strip(),
        "password": os.environ.get("smtp_password", ""),
        "to": os.environ.get("moderation_email_to", "").strip(),
    }
    # Report WHICH keys are missing, by name — never a value, and never the
    # password's presence-or-absence in a way that leaks its content.
    missing = [k for k, v in cfg.items() if not v]
    if missing:
        log.warning("mail not configured — missing: %s", ", ".join(sorted(missing)))
        return None
    return cfg


def _smtp_send(cfg: dict[str, str], msg: EmailMessage) -> None:
    """The only transport-specific code. Raises on failure; caller handles it.

    Port 465 is implicit TLS (SMTP_SSL); anything else is treated as
    submission with STARTTLS. Both were confirmed reachable from the
    production VPS in SU10S-7 — worth knowing, because a blocked outbound
    port is the usual reason this silently stops working on a new host.
    """
    port = int(cfg["port"])
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(cfg["host"], port, timeout=_TIMEOUT_SECONDS,
                              context=context) as srv:
            srv.login(cfg["user"], cfg["password"])
            srv.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], port, timeout=_TIMEOUT_SECONDS) as srv:
            srv.starttls(context=context)
            srv.login(cfg["user"], cfg["password"])
            srv.send_message(msg)


def send_email(subject: str, body_text: str, to: str | None = None) -> bool:
    """Send one plain-text email. Returns True on success, False otherwise.

    NEVER RAISES. Callers are request handlers and background tasks where a
    mail problem must not become a user-visible error or a crashed task.

    Everything is UTF-8: subject and body are Hebrew in practice, and
    EmailMessage handles the header encoding so they arrive readable rather
    than as mojibake or `=?utf-8?B?...?=` in a client that cannot decode it.
    """
    cfg = _config()
    if cfg is None:
        return False

    now = time.time()
    reason = _throttled(now)
    if reason is not None:
        # Logged at WARNING with the event still visible, so a throttled alert
        # is not simply lost — journalctl remains the fallback surface.
        log.warning("[MODERATION] throttled — %s. Suppressed mail: %s", reason, subject)
        return False

    recipient = (to or cfg["to"]).strip()
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg["user"]
        msg["To"] = recipient
        msg["Date"] = formatdate(localtime=True)
        # Without an explicit Message-ID some providers generate a weak one, and
        # a few spam filters score that. Cheap to set correctly.
        msg["Message-ID"] = make_msgid(domain=cfg["user"].split("@")[-1] or None)
        msg.set_content(body_text, subtype="plain", charset="utf-8")

        _smtp_send(cfg, msg)
    except Exception as exc:
        # Type plus a SHORT message. Never the config, never the password:
        # smtplib puts the server's response in the exception, not the
        # credential, but the message is truncated anyway so a chatty server
        # cannot echo something unexpected into the journal.
        log.warning("mail send failed (%s): %s", type(exc).__name__, str(exc)[:200])
        return False

    _sent_at.append(now)
    log.info("mail sent to %s: %s", recipient, subject)
    return True
