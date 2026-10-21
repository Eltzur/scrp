"""In-process response cache for /search (v2, unfiltered) and /suggest (SU11A-47).

Per gunicorn worker, no Redis. Values are the serialized JSON bodies, so a hit
costs a dict lookup and no database work beyond the cached build-stamp check.

Key: (endpoint, normalized q, limit, offset, group_by). Both answers depend
only on the normalized query, except the "query" field (and "corrected_from"
after a typo correction), which echo the text as typed. A hit for another
spelling of the same key gets its "query" value swapped in place, and a
corrected answer is served only for the exact same text.

Invalidation:
  - search_items.built_at changes (the caller passes it in; search_v2 checks it
    at most once per 60 s): everything is dropped
  - an entry older than TTL_S is not served. Prices on an answer can change
    between builds only when a promo ends (search_v2 then switches that page to
    the live fetch), so a stored answer is kept for a few minutes, not a day.
Bounded by entry count and total bytes; least recently used goes first.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from pydantic_core import to_json

MAX_ENTRIES = 1000
MAX_BYTES = 16 * 1024 * 1024   # 1,000 pages of 30 items run to ~30 MB; keep each worker under 16 MB
TTL_S = 600.0


@dataclass
class _Entry:
    body: bytes
    q: str             # the text as typed when the body was built
    prefix: int        # len(b'{"query":' + to_json(q)): where the echoed query ends
    exact_only: bool   # the body echoes q elsewhere too (corrected_from)
    expires: float


class ResponseCache:
    def __init__(self, max_entries: int = MAX_ENTRIES, max_bytes: int = MAX_BYTES, ttl_s: float = TTL_S):
        self.max_entries, self.max_bytes, self.ttl_s = max_entries, max_bytes, ttl_s
        self._d: OrderedDict[tuple, _Entry] = OrderedDict()
        self._bytes = 0
        self._stamp: Any = None
        self._lock = threading.Lock()
        self.hits = self.misses = 0

    def _check_stamp(self, stamp: Any) -> None:
        if stamp != self._stamp:
            self._d.clear()
            self._bytes = 0
            self._stamp = stamp

    def get(self, key: tuple, stamp: Any, q: str) -> bytes | None:
        with self._lock:
            self._check_stamp(stamp)
            e = self._d.get(key)
            if e is None or e.expires < time.monotonic() or (e.exact_only and e.q != q):
                self.misses += 1
                return None
            self._d.move_to_end(key)
            self.hits += 1
            if e.q == q:
                return e.body
            return b'{"query":' + to_json(q) + e.body[e.prefix:]

    def put(self, key: tuple, stamp: Any, q: str, body: bytes, exact_only: bool = False) -> None:
        head = b'{"query":' + to_json(q)
        if not body.startswith(head) or len(body) > self.max_bytes // 4:
            return   # not the expected shape, or too big to be worth a slot
        with self._lock:
            self._check_stamp(stamp)
            old = self._d.pop(key, None)
            if old is not None:
                self._bytes -= len(old.body)
            self._d[key] = _Entry(body, q, len(head), exact_only, time.monotonic() + self.ttl_s)
            self._bytes += len(body)
            while self._d and (len(self._d) > self.max_entries or self._bytes > self.max_bytes):
                _, gone = self._d.popitem(last=False)
                self._bytes -= len(gone.body)

    def clear(self) -> None:
        with self._lock:
            self._d.clear()
            self._bytes = 0
            self._stamp = None

    def __len__(self) -> int:
        return len(self._d)
