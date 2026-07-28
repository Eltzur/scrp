"""Daily scraper cron entry point.

Reads scheduled_stores.yaml, runs each chain's scraper in snapshot (replace) mode.
Exit 0 = all chains succeeded. Exit 1 = one or more chains errored.
"""
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml
from sqlalchemy import text

from db.db import connect, init_db
from scraper.registry import get_scraper, uses_delta
from scraper.canonical import update_canonical_names

log = logging.getLogger(__name__)
CONFIG          = Path(__file__).parent / "active_stores.yaml"   # verified stores only
CONFIG_INTENDED = Path(__file__).parent / "scheduled_stores.yaml" # full intent list


def pick_stores(conn, chain_id: str, n: int) -> list[str]:
    """Select n stores for a chain, preferring city diversity."""
    rows = conn.execute(text("""
        SELECT store_id FROM (
            SELECT store_id, city_norm,
                   ROW_NUMBER() OVER (PARTITION BY COALESCE(city_norm, store_id) ORDER BY store_id) AS rn
            FROM stores
            WHERE chain_id = :chain_id
        ) ranked
        WHERE rn = 1
        ORDER BY city_norm NULLS LAST, store_id
        LIMIT :n
    """), {"chain_id": chain_id, "n": n}).fetchall()

    if len(rows) < n:
        # Top up with any remaining stores not already selected
        selected = {r[0] for r in rows}
        extras = conn.execute(text("""
            SELECT store_id FROM stores
            WHERE chain_id = :chain_id AND store_id NOT IN :selected
            ORDER BY store_id LIMIT :n
        """).bindparams(
            **{"n": n - len(rows)}
        ), {"chain_id": chain_id, "selected": tuple(selected) or ("",)}).fetchall()
        rows = list(rows) + list(extras)

    return [r[0] for r in rows]


def run_chain(chain_id: str, n_stores: int, store_ids: list | None = None,
              delta: bool = False) -> dict:
    conn = connect()
    try:
        scraper = get_scraper(chain_id)
        if not scraper:
            raise ValueError(f"No scraper registered for chain_id={chain_id}")

        log.info(f"[{chain_id}] Loading store list...")
        scraper.load_stores(conn)

        if not store_ids:
            store_ids = pick_stores(conn, chain_id, n_stores)
        if not store_ids:
            raise RuntimeError(f"No stores found in DB for chain {chain_id} after load_stores")

        mode = "delta" if delta else "full"
        log.info(f"[{chain_id}] Scraping {len(store_ids)} stores ({mode}): {store_ids}")
        return scraper.load_prices_for_stores(store_ids, conn, replace=True, delta=delta)
    finally:
        conn.close()


def report_coverage(conn, fetch_run_ids: list[int]) -> None:
    if not fetch_run_ids:
        log.warning("Coverage report skipped — no fetch_run_ids collected.")
        return

    ids_sql = ",".join(str(i) for i in fetch_run_ids)
    rows = conn.execute(text(f"""
        SELECT fsr.chain_id, c.name,
               COUNT(*)                                          AS total,
               COUNT(*) FILTER (WHERE fsr.status = 'loaded')    AS loaded,
               COUNT(*) FILTER (WHERE fsr.status = 'no_file')   AS no_file,
               COUNT(*) FILTER (WHERE fsr.status = 'error')     AS error
        FROM fetch_store_runs fsr
        LEFT JOIN chains c ON c.chain_id = fsr.chain_id
        WHERE fsr.fetch_run_id IN ({ids_sql})
        GROUP BY fsr.chain_id, c.name
        ORDER BY fsr.chain_id
    """)).fetchall()

    if not rows:
        log.warning("Coverage report: no fetch_store_runs rows found for this run.")
        return

    grand_total = grand_loaded = grand_no_file = grand_error = 0
    low_coverage = []

    for chain_id, name, total, loaded, no_file, error in rows:
        pct = loaded / total * 100 if total else 0
        label = name or chain_id
        log.info(
            f"  {chain_id} ({label}): {loaded}/{total} loaded ({pct:.1f}%), "
            f"{no_file} no_file, {error} errors"
        )
        grand_total   += total
        grand_loaded  += loaded
        grand_no_file += no_file
        grand_error   += error
        if total > 5 and pct < 85.0:
            low_coverage.append((chain_id, label, pct))

    grand_pct = grand_loaded / grand_total * 100 if grand_total else 0
    log.info(
        f"  TOTAL: {grand_loaded}/{grand_total} stores loaded ({grand_pct:.1f}%), "
        f"{grand_no_file} no_file, {grand_error} errors"
    )
    for chain_id, label, pct in low_coverage:
        log.warning(
            f"  LOW COVERAGE: {chain_id} ({label}) only {pct:.1f}% — investigate no_file stores"
        )


def ping_supabase() -> None:
    """Ping Supabase Data API (a real Postgres read) to reset its 7-day
    inactivity timer. The old /auth/v1/health endpoint returned 200 without
    touching Postgres, so it did NOT count as activity and the project paused
    anyway (confirmed May 2026). This reads one row from public.keepalive via
    /rest/v1/, which is a genuine DB read. Non-fatal — logs result, never
    raises. Skips gracefully when env vars absent."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        log.warning("Supabase keep-alive skipped — SUPABASE_URL or SUPABASE_ANON_KEY not set.")
        return
    try:
        import requests as _requests
        r = _requests.get(
            f"{url}/rest/v1/keepalive?select=id&limit=1",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=10,
        )
        if r.ok and r.json():
            log.info(f"Supabase keep-alive ping OK ({r.status_code}) — DB read confirmed.")
        elif r.ok:
            log.warning(f"Supabase keep-alive returned {r.status_code} but empty body — DB read NOT confirmed.")
        else:
            log.warning(f"Supabase keep-alive ping returned {r.status_code} — project may be paused.")
    except Exception as exc:
        log.warning(f"Supabase keep-alive ping failed: {exc}")


def run_gs1_catalog() -> None:
    """Incremental GS1 Israel catalog sync (SU10A-1).

    Runs in incremental mode: no --full, so it picks up the watermark from the
    last successful run in gs1.sync_runs and only pulls what changed. Page cap
    stays at the module default (2000 pages) purely as a runaway backstop — the
    entire catalogue was 46 pages, so it is not a practical limit.

    A different vertical from the supermarket scrapers, so a GS1 failure is
    logged but never fails the cron — same treatment as the canonical-name step.
    Imported lazily (like ping_supabase's requests import) so a problem inside
    the GS1 module can never stop the price scrape from running.
    """
    try:
        from scraper.gs1_fetch import run as gs1_run
        rows = gs1_run()
        log.info(f"GS1 catalog sync OK — {rows} rows upserted.")
    except Exception as exc:
        log.error(f"GS1 catalog sync FAILED: {exc}", exc_info=True)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    log.info(f"DATABASE_URL set: {'YES' if os.environ.get('DATABASE_URL') else 'NO - WILL FAIL'}")

    config          = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    intended_config = yaml.safe_load(CONFIG_INTENDED.read_text(encoding="utf-8"))
    chains          = config.get("chains", [])

    active_total   = sum(len(e.get("store_ids", [])) for e in chains)
    intended_total = sum(len(e.get("store_ids", [])) for e in intended_config.get("chains", []))
    excluded       = intended_total - active_total
    log.info(
        f"Loaded {active_total} verified stores from active_stores.yaml. "
        f"{excluded} stores in scheduled_stores.yaml excluded (no PriceFull) — "
        f"see db/verification_report_9d1.md."
    )

    # init_db is a no-op on Postgres; runs schema.sql on SQLite only
    init_conn = connect()
    init_db(init_conn)
    init_conn.close()

    errors: list[str] = []
    errors_lock = threading.Lock()
    fetch_run_ids: list[int] = []
    fetch_run_ids_lock = threading.Lock()
    t_start = time.monotonic()

    def _run_entry(entry):
        chain_id  = entry["chain_id"]
        store_ids = entry.get("store_ids")
        n_stores  = entry.get("n_stores", 5)
        delta     = uses_delta(chain_id)
        t0 = time.monotonic()
        try:
            summary = run_chain(chain_id, n_stores, store_ids=store_ids, delta=delta)
            elapsed = time.monotonic() - t0
            log.info(
                f"[{chain_id}] OK — "
                f"{summary['files_loaded']}/{summary['files_attempted']} files, "
                f"{summary['items_inserted']} items, {elapsed:.0f}s"
            )
            frid = summary.get("fetch_run_id")
            if frid is not None:
                with fetch_run_ids_lock:
                    fetch_run_ids.append(frid)
        except Exception as exc:
            log.error(f"[{chain_id}] FAILED: {exc}", exc_info=True)
            with errors_lock:
                errors.append(chain_id)

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(_run_entry, chains))

    log.info("--- Coverage report ---")
    report_conn = connect()
    try:
        report_coverage(report_conn, fetch_run_ids)
    except Exception as exc:
        log.warning(f"Coverage report failed: {exc}")
    finally:
        report_conn.close()

    log.info("Running canonical name update...")
    conn = connect()
    try:
        canonical_summary = update_canonical_names(conn)
        log.info(
            f"Canonical names: {canonical_summary['total_processed']} processed, "
            f"{canonical_summary['total_updated']} updated."
        )
    except Exception as exc:
        log.error(f"Canonical name update failed: {exc}", exc_info=True)
    conn.close()

    log.info("Running GS1 catalog sync...")
    run_gs1_catalog()

    total = time.monotonic() - t_start
    log.info(f"Cron finished in {total:.0f}s. Errors: {errors or 'none'}")

    ping_supabase()

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
