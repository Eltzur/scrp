"""Admin statistics storage (SU11A-69): daily aggregates in stats_daily and
the collector's per-source state in stats_runs (db/migrations/su11a69_stats.sql).

Written by scripts/stats_collect.py, read by GET /admin/stats.

Privacy rule: a row is (source, metric, dimension, day, value). dimension is a
host, a platform, a path without its query string, a referrer domain or ''.
check_dimension() refuses anything that looks like an IP address, a query
string or a full URL before it reaches the database, as a last line of
defence behind scripts/stats_logs.py.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.engine import Connection

SOURCES = ("web", "api", "ga4", "play", "appstore")
# Metrics summed over a range into a top list instead of a daily series.
TOP_METRICS = ("top_path", "referrer")
DIM_MAX = 200

_IPV4 = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}(?![\d.])")
_IPV6 = re.compile(r"(?i)(?<![\w:])[0-9a-f]{1,4}(?::[0-9a-f]{0,4}){2,7}(?![\w:])")


class UnsafeDimension(ValueError):
    """A dimension that could carry personal data: never stored."""


def check_dimension(dim: str) -> str:
    if len(dim) > DIM_MAX:
        raise UnsafeDimension("dimension too long")
    if "?" in dim or "://" in dim or "=" in dim or "@" in dim:
        raise UnsafeDimension("query string, URL or email in a dimension")
    if _IPV4.search(dim) or _IPV6.search(dim):
        raise UnsafeDimension("IP address in a dimension")
    return dim


Row = tuple[str, str, date, int]  # (metric, dimension, day, value)


def replace_days(conn: Connection, source: str, days: Iterable[date], rows: Iterable[Row]) -> int:
    """Replace every row of `source` on `days` with `rows`, in the caller's
    transaction. The log sources recompute a whole day, so a re-run gives the
    same rows (and a top-20 list that changed leaves no stale entry)."""
    assert source in SOURCES
    days = sorted(set(days))
    rows = [(m, check_dimension(d), day, int(v)) for m, d, day, v in rows]
    if not days:
        return 0
    if any(r[2] not in days for r in rows):
        raise ValueError("row outside the replaced days")
    conn.execute(text("DELETE FROM stats_daily WHERE source = :s AND day IN :days")
                 .bindparams(_expanding("days")), {"s": source, "days": days})
    return upsert(conn, source, rows)


def upsert(conn: Connection, source: str, rows: Iterable[Row]) -> int:
    """Insert or update (source, metric, dimension, day) -> value. Used as-is by
    the API sources (GA4, Play, App Store), whose numbers can still move for a
    few days and are re-read on every run."""
    assert source in SOURCES
    n = 0
    for metric, dim, day, value in rows:
        if value < 0:
            raise ValueError("negative count")
        conn.execute(text("""
            INSERT INTO stats_daily (source, metric, dimension, day, value, updated_at)
            VALUES (:s, :m, :d, :day, :v, CURRENT_TIMESTAMP)
            ON CONFLICT (source, metric, dimension, day)
            DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
        """), {"s": source, "m": metric, "d": check_dimension(dim), "day": day, "v": int(value)})
        n += 1
    return n


def record_run(conn: Connection, source: str, status: str, *, error: str | None = None,
               as_of: date | None = None, note: str | None = None) -> None:
    """One stats_runs row per source. A failure keeps the last success time and
    the previous as_of; error text must already be safe (no secrets)."""
    assert source in SOURCES and status in ("ok", "error", "not_configured")
    now = datetime.now(timezone.utc)
    conn.execute(text("""
        INSERT INTO stats_runs (source, status, last_run_at, last_success_at, last_error_at,
                                last_error, as_of, note)
        VALUES (:s, :st, :now,
                CASE WHEN :st = 'ok' THEN :now END,
                CASE WHEN :st = 'error' THEN :now END,
                :err, :as_of, :note)
        ON CONFLICT (source) DO UPDATE SET
            status = EXCLUDED.status,
            last_run_at = EXCLUDED.last_run_at,
            last_success_at = COALESCE(EXCLUDED.last_success_at, stats_runs.last_success_at),
            last_error_at = COALESCE(EXCLUDED.last_error_at, stats_runs.last_error_at),
            last_error = CASE WHEN EXCLUDED.status = 'error' THEN EXCLUDED.last_error
                              WHEN EXCLUDED.status = 'ok' THEN NULL ELSE stats_runs.last_error END,
            as_of = CASE WHEN EXCLUDED.as_of IS NULL THEN stats_runs.as_of
                         WHEN stats_runs.as_of IS NULL OR EXCLUDED.as_of > stats_runs.as_of
                         THEN EXCLUDED.as_of ELSE stats_runs.as_of END,
            note = EXCLUDED.note
    """), {"s": source, "st": status, "now": now, "err": (error or None) and error[:300],
           "as_of": as_of, "note": (note or None) and note[:300]})


def has_run(conn: Connection, source: str) -> bool:
    return conn.execute(text("SELECT 1 FROM stats_runs WHERE source = :s AND status = 'ok'"),
                        {"s": source}).first() is not None


# ---------------------------------------------------------------------------
# Read side (GET /admin/stats, the dashboard card)
# ---------------------------------------------------------------------------

def _iso(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def runs(conn: Connection) -> dict[str, dict]:
    rows = conn.execute(text("""
        SELECT source, status, last_run_at, last_success_at, last_error_at, last_error, as_of, note
        FROM stats_runs
    """)).mappings().all()
    out = {s: {"status": "never_run", "last_run_at": None, "last_success_at": None,
               "last_error_at": None, "error": None, "as_of": None, "note": None} for s in SOURCES}
    for r in rows:
        if r["source"] in out:
            out[r["source"]] = {"status": r["status"], "last_run_at": _iso(r["last_run_at"]),
                                "last_success_at": _iso(r["last_success_at"]),
                                "last_error_at": _iso(r["last_error_at"]), "error": r["last_error"],
                                "as_of": _iso(r["as_of"]), "note": r["note"]}
    return out


def series(conn: Connection, day_from: date, day_to: date) -> list[dict]:
    """Daily series per (source, metric, dimension), top-list metrics excluded."""
    rows = conn.execute(text("""
        SELECT source, metric, dimension, day, value FROM stats_daily
        WHERE day BETWEEN :a AND :b AND metric NOT IN ('top_path', 'referrer')
        ORDER BY source, metric, dimension, day
    """), {"a": day_from, "b": day_to}).all()
    out: dict[tuple, dict] = {}
    for src, metric, dim, day, value in rows:
        key = (src, metric, dim)
        s = out.setdefault(key, {"source": src, "metric": metric, "dimension": dim, "points": []})
        s["points"].append([_iso(day), int(value)])
    return list(out.values())


def top(conn: Connection, metric: str, day_from: date, day_to: date, limit: int = 20) -> list[dict]:
    assert metric in TOP_METRICS
    rows = conn.execute(text("""
        SELECT dimension, sum(value) AS v FROM stats_daily
        WHERE source = 'web' AND metric = :m AND day BETWEEN :a AND :b
        GROUP BY dimension ORDER BY v DESC, dimension LIMIT :n
    """), {"m": metric, "a": day_from, "b": day_to, "n": limit}).all()
    return [{"dimension": d, "value": int(v)} for d, v in rows]


def latest_summary(conn: Connection) -> dict:
    """The dashboard card: the latest web day and the latest API day. The API
    total leaves the admin console out (SU11A-70: platform "admin")."""
    out: dict = {}
    for src, metrics in (("web", ("page_views", "visitors")), ("api", ("calls",))):
        day = conn.execute(text("SELECT max(day) FROM stats_daily WHERE source = :s"), {"s": src}).scalar()
        if day is None:
            out[src] = None
            continue
        vals = dict(conn.execute(text("""
            SELECT metric, sum(value) FROM stats_daily
            WHERE source = :s AND day = :d AND metric IN :ms
              AND NOT (source = 'api' AND dimension = 'admin')
            GROUP BY metric
        """).bindparams(_expanding("ms")), {"s": src, "d": day, "ms": list(metrics)}).all())
        out[src] = {"day": _iso(day), **{m: int(vals.get(m) or 0) for m in metrics}}
    return out


def _expanding(name: str):
    from sqlalchemy import bindparam
    return bindparam(name, expanding=True)
