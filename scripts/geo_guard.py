"""Which stores the automated geocoders must never touch (SU11A-23).

A coordinate that a person placed (geo_source='manual', coord_source='manual_pin') or that was
loaded from the Google results (geo_source='google', coord_source google_exact / google_reviewed)
is final: scripts/geo_nominatim.py and scripts/geo_centroids.py skip it, in SQL and again in
Python. Same pattern as the original manual-pin skip (SU10S-25).

`coord_source` only exists after db/migrations/su11a23_stores_coord_source.sql; until then the
SQL guard falls back to geo_source alone, so the weekly run keeps working before and after.
"""
from __future__ import annotations

from sqlalchemy import text

PROTECTED_GEO_SOURCES = ("manual", "google")
PROTECTED_COORD_SOURCES = ("google_exact", "google_reviewed", "manual_pin")


def is_protected(row) -> bool:
    """True when the row's coordinate must never be overwritten by an automated run."""
    get = row.get if hasattr(row, "get") else (lambda k: row[k] if k in row else None)
    return get("geo_source") in PROTECTED_GEO_SOURCES or get("coord_source") in PROTECTED_COORD_SOURCES


def has_coord_source(conn) -> bool:
    return bool(conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'stores' AND column_name = 'coord_source'")).first())


def protected_sql(alias: str = "s", with_coord_source: bool = False) -> str:
    """SQL predicate: TRUE for rows the geocoders may write."""
    p = f"{alias}." if alias else ""
    geo = ", ".join(f"'{v}'" for v in PROTECTED_GEO_SOURCES)
    sql = f"COALESCE({p}geo_source, '') NOT IN ({geo})"
    if with_coord_source:
        coord = ", ".join(f"'{v}'" for v in PROTECTED_COORD_SOURCES)
        sql += f" AND ({p}coord_source IS NULL OR {p}coord_source NOT IN ({coord}))"
    return sql


def coord_source_col(alias: str = "s", with_coord_source: bool = False) -> str:
    """Select-list item so rows always carry a coord_source key."""
    return f"{alias}.coord_source" if with_coord_source else "NULL::text AS coord_source"
