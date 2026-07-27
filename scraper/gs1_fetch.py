"""Fetch the GS1 Israel product catalog into gs1.products (phase 1: basic fields).

Sweeps `modification_timestamp` across every supplier connected to our GS1
account via the select_query.json endpoint, paginating with `get_chunks`
{start, rows} until a page comes back empty. Each row is upserted into
gs1.products by GS1's own `id`; a watermark row is written to gs1.sync_runs so
the next run only asks for what changed.

Phase 1 stores the basic fields only. `full_content` / `full_content_fetched_at`
are never written here — phase 2 owns them, and the upsert leaves them alone so
a re-sweep cannot wipe detail already fetched.

Credentials come from the environment as GS1_USERNAME / GS1_PASSWORD (uppercase
— that is what is already set in ~/scrp/.env on Kamatera; do not rename). The
repo-root .env is loaded automatically via python-dotenv, so the script does not
depend on the caller having sourced it first.

Run locally (dry run, nothing written):
    python -m scraper.gs1_fetch --dry-run --max-pages 1

Run against production:
    cd ~/scrp && source venv/bin/activate && python3 -m scraper.gs1_fetch

Force a full re-sweep instead of an incremental one:
    python -m scraper.gs1_fetch --full
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from sqlalchemy import text

from db.db import connect

log = logging.getLogger(__name__)

# Load the repo-root .env ourselves rather than trusting the caller to have done
# it. A plain `source .env` sets shell variables but does NOT export them to a
# python3 child (proven in SU10A-1: DATABASE_URL was set in the shell and unset
# in the subprocess), so depending on it silently yields "missing credentials".
#
# override=False so anything already exported wins — a manual
# `export GS1_USERNAME=...` or `set -a; source .env` still takes precedence.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH, override=False)

_ENDPOINT = "https://hq.gs1ildigital.org/external/app_query/select_query.json"

# Rows per get_chunks page. Conservative default — the endpoint's practical
# ceiling is unknown until we have run a full sweep.
_PAGE_SIZE = 500

# Safety valve: stop after this many pages even if the API keeps returning rows,
# so a misbehaving filter can't loop forever against a live endpoint.
_MAX_PAGES = 2000

# Timestamp format used when embedding the watermark back into the query string.
# The endpoint's filter dialect is MySQL-flavoured (NOW(), DATE_SUB(...)), so a
# plain quoted 'YYYY-MM-DD HH:MM:SS' literal is the safest bet. Confirm against
# a live response before trusting incremental mode in production.
_GS1_TS_FORMAT = "%Y-%m-%d %H:%M:%S"

# Full-sweep filter. Reuses the 10-year window already proven to work by hand
# rather than inventing a new "match everything" expression.
_FULL_SWEEP_FILTER = "modification_timestamp > DATE_SUB(NOW(), INTERVAL 3650 DAY)"

_HTTP_TIMEOUT = 60

# Our column -> candidate GS1 keys, matched AFTER every incoming key has been
# lowercased (see _lower_keys). Keep every candidate here lowercase: the live
# endpoint mixes conventions within one row (`Product_Status` capitalised,
# everything else not), so normalising once beats chasing each surprise.
_FIELD_MAP = {
    "id":                     ("id",),
    "product_code":           ("product_code", "productcode"),
    "gtin":                   ("gtin",),
    # The endpoint returns a SINGLE `gln` — there is no supplier/retailer split
    # (confirmed by the SU10A-1 dry run; su10a1b collapsed the two columns).
    # supplier_gln is still accepted as a fallback in case the API ever splits.
    "gln":                    ("gln", "supplier_gln", "suppliergln"),
    "group_id":               ("group_id", "groupid"),
    "group_name":             ("group_name", "groupname"),
    "brandname":              ("brandname", "brand_name"),
    "trade_item_description": ("trade_item_description", "tradeitemdescription"),
    "product_status":         ("product_status", "productstatus"),
    "effective_date_time":    ("effective_date_time", "effectivedatetime"),
    "discontinued_date_time": ("discontinued_date_time", "discontinueddatetime"),
    "modification_timestamp": ("modification_timestamp", "modificationtimestamp"),
}

# Timestamp formats tried in order, after ISO. The live endpoint mixes formats
# within a single row: modification_timestamp is 'YYYY-MM-DD HH:MM:SS' while
# effective_date_time is DD/MM/YYYY. Day-first is the Israeli convention, so
# '01/02/2018' is read as 1 February — not 2 January.
_TS_FORMATS = ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d")

_TIMESTAMP_COLUMNS = (
    "effective_date_time",
    "discontinued_date_time",
    "modification_timestamp",
)


def _credentials() -> tuple[str, str]:
    """Read GS1_USERNAME / GS1_PASSWORD, failing loudly rather than 401-ing later."""
    user = os.environ.get("GS1_USERNAME", "")
    password = os.environ.get("GS1_PASSWORD", "")
    missing = [n for n, v in (("GS1_USERNAME", user), ("GS1_PASSWORD", password)) if not v]
    if missing:
        raise RuntimeError(
            f"Missing environment variable(s): {', '.join(missing)}. "
            "Note the names are UPPERCASE — a casing mismatch here produced a "
            "session's worth of misleading 401s in SU10A-1."
        )
    return user, password


def _lower_keys(row: dict) -> dict:
    """Lowercase every incoming key once, so a casing surprise can't cause a miss."""
    return {str(k).lower(): v for k, v in row.items()}


def _pick(row: dict, column: str):
    """Pull `column` out of a key-lowercased GS1 row."""
    for key in _FIELD_MAP[column]:
        if key in row:
            return row[key]
    return None


def _parse_ts(value):
    """Best-effort timestamp parse. Returns None rather than aborting the sweep."""
    if value in (None, "", "null"):
        return None
    if isinstance(value, datetime):
        return value
    text_value = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text_value)
    except ValueError:
        pass
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(text_value, fmt)
        except ValueError:
            continue
    log.warning("Unparseable timestamp %r — storing NULL", value)
    return None


def _normalise(row) -> dict | None:
    """Map one GS1 row onto our column set. Returns None if it can't be keyed."""
    if not isinstance(row, dict):
        log.warning("Skipping non-dict row (%s)", type(row).__name__)
        return None
    low = _lower_keys(row)
    out = {col: _pick(low, col) for col in _FIELD_MAP}
    if out["id"] is None or out["product_code"] is None:
        log.warning("Skipping row with no id/product_code (keys: %s)", sorted(low)[:12])
        return None
    out["id"] = str(out["id"])
    out["product_code"] = str(out["product_code"])
    for col in _TIMESTAMP_COLUMNS:
        out[col] = _parse_ts(out[col])
    return out


def _extract_rows(payload) -> list:
    """Pull the row list out of the response envelope.

    The live endpoint returns a DOUBLY nested bare list — [[{...}, {...}]] — so
    payload[0] is the row list, not payload itself. Assuming otherwise is what
    made the first SU10A-1 dry run crash. The dict branch is kept in case the
    envelope ever changes.
    """
    candidate = payload

    if isinstance(candidate, dict):
        for key in ("results", "result", "rows", "data", "records", "items"):
            value = candidate.get(key)
            if isinstance(value, list):
                candidate = value
                break
        else:
            log.error("Could not find a row list in response. Top-level keys: %s",
                      sorted(map(str, candidate)))
            return []

    if not isinstance(candidate, list):
        log.error("Unexpected response type %s", type(candidate).__name__)
        return []

    # Unwrap list-of-list nesting (one level in practice). Bounded so a
    # pathological shape can't spin here.
    depth = 0
    while candidate and isinstance(candidate[0], list) and depth < 3:
        candidate = candidate[0]
        depth += 1

    return candidate


def _fetch_page(session: requests.Session, query: str, start: int, rows: int) -> list[dict]:
    """One get_chunks page. Raises on HTTP error so the run is marked failed."""
    body = {"query": query, "get_chunks": {"start": start, "rows": rows}}
    resp = session.post(_ENDPOINT, json=body, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    return _extract_rows(resp.json())


_UPSERT_SQL = text("""
    INSERT INTO gs1.products (
        id, product_code, gtin, gln,
        group_id, group_name, brandname, trade_item_description,
        product_status, effective_date_time, discontinued_date_time,
        modification_timestamp, fetched_at
    ) VALUES (
        :id, :product_code, :gtin, :gln,
        :group_id, :group_name, :brandname, :trade_item_description,
        :product_status, :effective_date_time, :discontinued_date_time,
        :modification_timestamp, now()
    )
    ON CONFLICT (id) DO UPDATE SET
        product_code           = excluded.product_code,
        gtin                   = excluded.gtin,
        gln                    = excluded.gln,
        group_id               = excluded.group_id,
        group_name             = excluded.group_name,
        brandname              = excluded.brandname,
        trade_item_description = excluded.trade_item_description,
        product_status         = excluded.product_status,
        effective_date_time    = excluded.effective_date_time,
        discontinued_date_time = excluded.discontinued_date_time,
        modification_timestamp = excluded.modification_timestamp,
        fetched_at             = now()
    -- full_content / full_content_fetched_at intentionally untouched (phase 2).
""")


def _read_watermark(conn) -> datetime | None:
    row = conn.execute(text("""
        SELECT last_modification_timestamp
        FROM gs1.sync_runs
        WHERE status = 'ok' AND last_modification_timestamp IS NOT NULL
        ORDER BY started_at DESC
        LIMIT 1
    """)).fetchone()
    return row[0] if row else None


def _build_query(watermark: datetime | None) -> str:
    if watermark is None:
        return _FULL_SWEEP_FILTER
    return f"modification_timestamp > '{watermark.strftime(_GS1_TS_FORMAT)}'"


def run(full: bool = False, dry_run: bool = False, page_size: int = _PAGE_SIZE,
        max_pages: int = _MAX_PAGES) -> int:
    """Sweep the catalog. Returns the number of rows fetched."""
    user, password = _credentials()

    conn = connect()
    watermark = None if full else _read_watermark(conn)
    query = _build_query(watermark)
    log.info("Watermark: %s", watermark.isoformat() if watermark else "(none — full sweep)")
    log.info("Query: %s", query)

    run_id = None
    if not dry_run:
        run_id = conn.execute(text("""
            INSERT INTO gs1.sync_runs (started_at, status)
            VALUES (now(), 'running') RETURNING id
        """)).scalar()
        conn.commit()
        log.info("sync_runs id=%s opened", run_id)

    session = requests.Session()
    session.auth = (user, password)
    session.headers.update({"Content-Type": "application/json"})

    total = 0
    max_seen: datetime | None = watermark
    start = 0
    pages = 0

    try:
        while pages < max_pages:
            batch = _fetch_page(session, query, start, page_size)
            pages += 1
            if not batch:
                log.info("Empty page at start=%d — sweep complete", start)
                break

            if pages == 1:
                # Diagnostic only — must never be able to kill the sweep. The
                # first SU10A-1 dry run died here when the row turned out to be
                # a nested list rather than a dict.
                first = batch[0]
                if isinstance(first, dict):
                    log.info("First row keys: %s", sorted(map(str, first)))
                else:
                    log.warning("Unexpected first-row shape: %s -> %.200s",
                                type(first).__name__, first)

            rows = [r for r in (_normalise(row) for row in batch) if r is not None]
            for r in rows:
                ts = r["modification_timestamp"]
                if ts is not None and (max_seen is None or ts > max_seen):
                    max_seen = ts

            if rows and not dry_run:
                conn.execute(_UPSERT_SQL, rows)
                conn.commit()

            total += len(rows)
            start += page_size
            log.info("page %d: %d rows (running total %d)", pages, len(rows), total)

        else:
            log.warning("Hit the %d-page safety valve — stopping early", max_pages)

        if not dry_run:
            conn.execute(text("""
                UPDATE gs1.sync_runs
                SET completed_at = now(), rows_fetched = :n,
                    last_modification_timestamp = :ts, status = 'ok'
                WHERE id = :id
            """), {"n": total, "ts": max_seen, "id": run_id})
            conn.commit()
        log.info("Done: %d rows, watermark now %s",
                 total, max_seen.isoformat() if max_seen else "(unset)")
        return total

    except Exception:
        # Leave the watermark alone on failure so the next run re-covers the gap.
        if not dry_run and run_id is not None:
            conn.execute(text("""
                UPDATE gs1.sync_runs
                SET completed_at = now(), rows_fetched = :n, status = 'error'
                WHERE id = :id
            """), {"n": total, "id": run_id})
            conn.commit()
        log.exception("GS1 sweep failed after %d rows", total)
        raise
    finally:
        conn.close()


def main():
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Fetch the GS1 Israel catalog into gs1.products")
    parser.add_argument("--full", action="store_true",
                        help="ignore the watermark and re-sweep everything")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch and parse but write nothing to the database")
    parser.add_argument("--page-size", type=int, default=_PAGE_SIZE,
                        help=f"rows per get_chunks page (default {_PAGE_SIZE})")
    parser.add_argument("--max-pages", type=int, default=_MAX_PAGES,
                        help=f"safety valve (default {_MAX_PAGES})")
    args = parser.parse_args()

    try:
        run(full=args.full, dry_run=args.dry_run,
            page_size=args.page_size, max_pages=args.max_pages)
    except Exception as e:
        log.error("Aborted: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
