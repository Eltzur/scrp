"""Canonical name computation via weighted token voting.

For each barcode present in 2+ chains, picks the best item_name by:
1. Counting how many names contain each token (whitespace-split).
2. Winning tokens: those appearing in >50% of names (tokens in ALL names are
   a strict subset and are automatically included).
3. Returning the original name containing the most winning tokens (preserving
   natural word order since we return a whole name, not a reconstructed string).
4. Fallback to longest name when fewer than 2 winning tokens exist.
"""
import logging
from collections import Counter, defaultdict

from sqlalchemy import text

log = logging.getLogger(__name__)


def compute_canonical_name(names: list[str]) -> str:
    """
    Given a list of item names from different chains for the same barcode,
    return the best canonical name via weighted token voting.
    """
    if not names:
        return ""
    if len(names) == 1:
        return names[0]

    n = len(names)

    # Count how many distinct names contain each token
    token_support: Counter = Counter()
    for name in names:
        for token in set(name.split()):
            token_support[token] += 1

    # Winning tokens: appear in strictly more than half the names.
    # Tokens present in ALL names are a subset and always win.
    winning_tokens = {t for t, count in token_support.items() if count > n / 2}

    # Fewer than 2 winning tokens = no real consensus; fall back to longest name
    if len(winning_tokens) < 2:
        return max(names, key=len)

    # Return the name containing the most winning tokens (natural word order preserved)
    return max(names, key=lambda name: len(set(name.split()) & winning_tokens))


def update_canonical_names(conn) -> dict:
    """
    Recompute canonical item names for all barcodes with 2+ chain entries.
    Updates items.item_name with the majority-voted result.

    Only writes rows whose name_source is 'chain' (or NULL, the pre-column
    default). Canonical voting derives its answer from chain names, so it is the
    lowest-priority source; without this guard the nightly cron would silently
    overwrite every higher-priority name on each run. This matters now that GS1
    is a second writer to the same column (name_source='gs1').

    Commits every 1000 rows.
    Returns {"total_processed": N, "total_updated": N}.
    """
    log.info("Fetching multi-chain item names...")
    rows = conn.execute(text("""
        SELECT icn.item_code, icn.item_name
        FROM item_chain_names icn
        WHERE icn.item_name IS NOT NULL
          AND icn.item_code IN (
              SELECT item_code FROM item_chain_names
              GROUP BY item_code
              HAVING COUNT(DISTINCT chain_id) >= 2
          )
        ORDER BY icn.item_code
    """)).fetchall()

    names_by_code: dict[str, list[str]] = defaultdict(list)
    for code, name in rows:
        names_by_code[code].append(name)

    total = len(names_by_code)
    log.info(f"Computing canonical names for {total} barcodes...")

    total_processed = 0
    total_updated = 0

    for code, names in names_by_code.items():
        canonical = compute_canonical_name(names)

        result = conn.execute(text("""
            UPDATE items SET item_name = :name
            WHERE item_code = :code
              AND (item_name IS NULL OR item_name != :name)
              -- Lowest-priority writer: never clobber a name owned by a
              -- higher-priority source (e.g. name_source='gs1').
              AND (name_source IS NULL OR name_source = 'chain')
        """), {"name": canonical, "code": code})

        total_processed += 1
        if result.rowcount > 0:
            total_updated += 1

        if total_processed % 1000 == 0:
            conn.commit()
            log.info(f"  {total_processed}/{total} processed, {total_updated} updated...")

    conn.commit()
    log.info(f"Done: {total_processed} processed, {total_updated} updated.")
    return {"total_processed": total_processed, "total_updated": total_updated}
