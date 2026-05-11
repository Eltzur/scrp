"""Daily scraper cron entry point.

Reads scheduled_stores.yaml, runs each chain's scraper in snapshot (replace) mode.
Exit 0 = all chains succeeded. Exit 1 = one or more chains errored.
"""
import logging
import sys
import time
from pathlib import Path

import yaml
from sqlalchemy import text

from db.db import connect, init_db
from scraper.registry import get_scraper
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


def run_chain(chain_id: str, n_stores: int, conn, store_ids: list | None = None) -> dict:
    scraper = get_scraper(chain_id)
    if not scraper:
        raise ValueError(f"No scraper registered for chain_id={chain_id}")

    log.info(f"[{chain_id}] Loading store list...")
    scraper.load_stores(conn)

    if not store_ids:
        store_ids = pick_stores(conn, chain_id, n_stores)
    if not store_ids:
        raise RuntimeError(f"No stores found in DB for chain {chain_id} after load_stores")

    log.info(f"[{chain_id}] Scraping {len(store_ids)} stores: {store_ids}")
    return scraper.load_prices_for_stores(store_ids, conn, replace=True)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    import os
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

    conn = connect()
    init_db(conn)

    errors: list[str] = []
    t_start = time.monotonic()

    for entry in chains:
        chain_id  = entry["chain_id"]
        store_ids = entry.get("store_ids")   # explicit list takes priority
        n_stores  = entry.get("n_stores", 5) # fallback: pick N by city diversity
        t0 = time.monotonic()
        try:
            summary = run_chain(chain_id, n_stores, conn, store_ids=store_ids)
            elapsed = time.monotonic() - t0
            log.info(
                f"[{chain_id}] OK — "
                f"{summary['files_loaded']}/{summary['files_attempted']} files, "
                f"{summary['items_inserted']} items, {elapsed:.0f}s"
            )
        except Exception as exc:
            log.error(f"[{chain_id}] FAILED: {exc}", exc_info=True)
            errors.append(chain_id)

    log.info("Running canonical name update...")
    try:
        canonical_summary = update_canonical_names(conn)
        log.info(
            f"Canonical names: {canonical_summary['total_processed']} processed, "
            f"{canonical_summary['total_updated']} updated."
        )
    except Exception as exc:
        log.error(f"Canonical name update failed: {exc}", exc_info=True)

    conn.close()
    total = time.monotonic() - t_start
    log.info(f"Cron finished in {total:.0f}s. Errors: {errors or 'none'}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
