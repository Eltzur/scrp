"""Insert items rows for GS1-matched orphan promoted item_codes (SU10A-6).

An "orphan" is an item_code present in promos but with no items row — so it has
no name anywhere (not prices, not item_chain_names, not a shelf feed). SU10A-6
measured 64,922 across all chains, 60,275 of them King Store: a source-side
asymmetry where the HQ promo catalog references far more products than any branch
price-publishes. Store coverage was ruled out (only 3 King Store branches
un-scraped, 0 orphan overlap), so these cannot be reached by scraping.

~1,696 King Store orphans carry a GTIN matching an ACTIVE GS1 product (5,372 match
a GTIN under any status, but 3,683 of those are cancelled and must not name a
customer-facing item — see gs1_enrich_items.py's active-only rule), so a real
manufacturer name (and, for 13-digit GTINs, an image already on disk served by
the API) is available. This creates minimal items rows for exactly those:
item_name + name_source='gs1', everything else NULL (no price/pack data exists
for a promo-only item). Once an orphan has a named items row, the promo-only
search path (SU10A-5) can surface it via its existing promo instead of it being
an invisible bare barcode.

Idempotent: ON CONFLICT (item_code) DO NOTHING — a re-run inserts only newly
matchable orphans and never clobbers a real scraped row.

Dry run (default):  python3 -m scraper.gs1_enrich_orphans
Apply:              python3 -m scraper.gs1_enrich_orphans --apply
All chains:         add --all   (default: King Store only, 7290058108879)
"""
import logging
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

from db.db import connect
from scraper.gs1_enrich_items import _ACTIVE_STATUS, _RANKED_CTE

log = logging.getLogger(__name__)
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

_KING_STORE = "7290058108879"


def _matchable(conn, all_chains: bool) -> int:
    chain_filter = "" if all_chains else "AND s.chain_id = :chain"
    params = {"active": _ACTIVE_STATUS}
    if not all_chains:
        params["chain"] = _KING_STORE
    return conn.execute(text(_RANKED_CTE + f"""
        , orphans AS (
            SELECT DISTINCT p.item_code
            FROM promos p
            JOIN stores s ON s.id = p.store_fk
            LEFT JOIN items i ON i.item_code = p.item_code
            WHERE i.item_code IS NULL {chain_filter}
        )
        SELECT count(*) FROM orphans o
        JOIN ranked r ON r.gtin = o.item_code AND r.rn = 1
    """), params).scalar()


def run(apply: bool = False, all_chains: bool = False, sample_size: int = 20) -> dict:
    conn = connect()
    try:
        ks = _matchable(conn, all_chains=False)
        allc = _matchable(conn, all_chains=True)
        log.info("GS1-matchable orphans — King Store: %s | all chains: %s",
                 f"{ks:,}", f"{allc:,}")

        chain_filter = "" if all_chains else "AND s.chain_id = :chain"
        params = {"active": _ACTIVE_STATUS}
        if not all_chains:
            params["chain"] = _KING_STORE

        select_set = _RANKED_CTE + f"""
            , orphans AS (
                SELECT DISTINCT p.item_code
                FROM promos p
                JOIN stores s ON s.id = p.store_fk
                LEFT JOIN items i ON i.item_code = p.item_code
                WHERE i.item_code IS NULL {chain_filter}
            )
            SELECT o.item_code, r.trade_item_description AS new_name, 'gs1' AS name_source
            FROM orphans o
            JOIN ranked r ON r.gtin = o.item_code AND r.rn = 1
        """

        if sample_size:
            rows = conn.execute(text(select_set + " ORDER BY RANDOM() LIMIT :lim"),
                                {**params, "lim": sample_size}).mappings().all()
            log.info("--- sample (%d) ---", len(rows))
            for r in rows:
                log.info("  %s -> %s", r["item_code"], r["new_name"])

        target = "all chains" if all_chains else "King Store only"
        if not apply:
            log.info("DRY RUN (%s) — nothing written. Re-run with --apply.", target)
            return {"king_store": ks, "all_chains": allc, "inserted": 0}

        result = conn.execute(text(f"""
            INSERT INTO items (item_code, item_name, name_source)
            {select_set}
            ON CONFLICT (item_code) DO NOTHING
        """), params)
        conn.commit()
        log.info("APPLIED (%s) — %s items inserted.", target, f"{result.rowcount:,}")
        return {"king_store": ks, "all_chains": allc, "inserted": result.rowcount}
    finally:
        conn.close()


def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Insert items rows for GS1-matched orphan promoted item_codes")
    p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    p.add_argument("--all", action="store_true", help="all chains (default: King Store only)")
    args = p.parse_args()
    run(apply=args.apply, all_chains=args.all)


if __name__ == "__main__":
    main()
