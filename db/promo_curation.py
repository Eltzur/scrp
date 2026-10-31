"""Promo curation on the public read path (SU11A-58, table promo_curation in
db/migrations/su11a58_promo_curation.sql).

Admins pin a promotion (shown first, in rank order) or hide it (left out) on the
promo LISTS only: /promos/grouped (web PromosPage) and /promos/today. A
promotion is (chain_id, promo_id), the chain's PromotionId, which survives the
daily reload; promos.id does not.

NEVER PRICING. Nothing in search, compare, basket, /product, /promos/bulk or
the search build reads this: a hidden promo still prices its items exactly as
before. tests/test_promo_curation_su11a58_pg.py proves those answers are
byte-identical with and without curation rows.

Expiry is read-time: only rows that are active, started and not past ends_at
are loaded; a pin whose promotion left the feed simply matches no promo row.

Cache: per gunicorn worker, TTL_S. An admin write clears the cache of the
worker that handled it; the other workers pick it up within TTL_S.

FAIL OPEN: a missing table (migration not applied) or any read error means no
curation, logged at INFO, retried after TTL_S. The load runs first on the
request's connection and rolls back on failure, so it cannot abort the read.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection

log = logging.getLogger(__name__)

TTL_S = 30.0
NO_PIN = 1_000_000   # sort key of an unpinned row: after every pin


@dataclass(frozen=True)
class Pin:
    chain_id: str
    promo_id: str
    sponsored: bool


@dataclass(frozen=True)
class Curation:
    pins: tuple[Pin, ...]                    # display order: position 1 = pins[0]
    hides: frozenset[tuple[str, str]]        # (chain_id, promo_id)

    def __bool__(self) -> bool:
        return bool(self.pins or self.hides)

    def pin_at(self, position) -> Pin | None:
        """The pin at a 1-based position as returned by pin_rank_sql (None: not pinned)."""
        if position is None:
            return None
        p = int(position)
        return self.pins[p - 1] if 1 <= p <= len(self.pins) else None


EMPTY = Curation((), frozenset())

_EFFECTIVE_SQL = """
    SELECT kind, chain_id, promo_id, rank, sponsored
    FROM promo_curation
    WHERE active AND starts_at <= now() AND (ends_at IS NULL OR ends_at > now())
    ORDER BY kind, rank, id
"""

_lock = threading.Lock()
_cache: tuple[float, Curation] | None = None


def _load(conn: Connection) -> Curation:
    pins, hides = [], set()
    for r in conn.execute(text(_EFFECTIVE_SQL)).mappings():
        if r["kind"] == "pin":
            pins.append(Pin(r["chain_id"], r["promo_id"], bool(r["sponsored"])))
        else:
            hides.add((r["chain_id"], r["promo_id"]))
    # A promotion both pinned and hidden is hidden: the hide is the safer reading.
    pins = [p for p in pins if (p.chain_id, p.promo_id) not in hides]
    return Curation(tuple(pins), frozenset(hides))


def get_curation(conn: Connection) -> Curation:
    """The effective curation (cached TTL_S). Call before any other query on conn."""
    global _cache
    now = time.monotonic()
    with _lock:
        cached = _cache
    if cached is not None and now < cached[0]:
        return cached[1]
    try:
        cur = _load(conn)
        conn.rollback()
    except Exception as exc:  # noqa: BLE001 - missing table or any error: no curation
        log.info("promo curation unavailable, applying none (%s)", type(exc).__name__)
        try:
            conn.rollback()
        except Exception:
            pass
        cur = EMPTY
    with _lock:
        _cache = (now + TTL_S, cur)
    return cur


def invalidate() -> None:
    """After an admin write (this worker), and in tests."""
    global _cache
    with _lock:
        _cache = None


def hide_sql(cur: Curation, chain_col: str, promo_col: str) -> tuple[str, dict]:
    """' AND <not hidden>' for a WHERE clause, or '' when nothing is hidden.

    A row with promo_id NULL is never hidden (curation needs a PromotionId);
    the IS NULL arm keeps the row-value NOT IN from turning it into NULL."""
    if not cur.hides:
        return "", {}
    params, rows = {}, []
    for k, (chain_id, promo_id) in enumerate(sorted(cur.hides)):
        rows.append(f"(:cur_hc{k}, :cur_hp{k})")
        params[f"cur_hc{k}"], params[f"cur_hp{k}"] = chain_id, promo_id
    return (f" AND ({promo_col} IS NULL OR ({chain_col}, {promo_col}) NOT IN ({', '.join(rows)}))",
            params)


def pin_rank_sql(cur: Curation, chain_col: str, promo_col: str) -> tuple[str, dict]:
    """A CASE giving a pinned row its 1-based position (NULL otherwise), or
    ('', {}) when nothing is pinned."""
    if not cur.pins:
        return "", {}
    params, arms = {}, []
    for k, p in enumerate(cur.pins):
        arms.append(f"WHEN {chain_col} = :cur_pc{k} AND {promo_col} = :cur_pp{k} THEN {k + 1}")
        params[f"cur_pc{k}"], params[f"cur_pp{k}"] = p.chain_id, p.promo_id
    return f"CASE {' '.join(arms)} END", params


def mark(rows: list[dict], cur: Curation) -> list[dict]:
    """Replace each row's pin_rank (if any) with pinned / sponsored flags."""
    for r in rows:
        pin = cur.pin_at(r.pop("pin_rank", None))
        r["pinned"] = pin is not None
        r["sponsored"] = bool(pin and pin.sponsored)
    return rows
