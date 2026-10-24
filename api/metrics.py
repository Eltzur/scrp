"""In-process request counters for GET /admin/status (SU11A-54).

Per worker process, kept in memory only: a restart starts from zero, and each
gunicorn worker counts its own requests (the status answer says which pid and
since when). Hour buckets; "last 24 h" is the current hour plus the 23 before.

What the app can see: every request that reaches FastAPI, its 5xx answers,
statement-timeout cancels (503 query_timeout) and 429s the app itself sends.
nginx's rate-limit 429s never reach the app, so they are not counted here
(nginx error.log has them).
"""
from __future__ import annotations

import os
import threading
import time
from collections import Counter
from datetime import datetime, timezone

WINDOW_HOURS = 24
KEYS = ("requests", "http_5xx", "query_timeout", "http_429")

_lock = threading.Lock()
_buckets: dict[int, Counter] = {}
STARTED_AT = datetime.now(timezone.utc)


def _hour(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // 3600)


def inc(key: str, n: int = 1, now: float | None = None) -> None:
    h = _hour(now)
    with _lock:
        _buckets.setdefault(h, Counter())[key] += n
        for old in [k for k in _buckets if k <= h - WINDOW_HOURS]:
            del _buckets[old]


def record_status(status: int, now: float | None = None) -> None:
    inc("requests", now=now)
    if status >= 500:
        inc("http_5xx", now=now)
    elif status == 429:
        inc("http_429", now=now)


def snapshot(now: float | None = None) -> dict:
    h = _hour(now)
    total: Counter = Counter()
    with _lock:
        for k, c in _buckets.items():
            if k > h - WINDOW_HOURS:
                total.update(c)
    return {
        "scope": "worker",
        "pid": os.getpid(),
        "since": STARTED_AT.isoformat(timespec="seconds"),
        "window_hours": WINDOW_HOURS,
        **{k: int(total.get(k, 0)) for k in KEYS},
    }


def reset() -> None:
    """Tests only."""
    with _lock:
        _buckets.clear()
