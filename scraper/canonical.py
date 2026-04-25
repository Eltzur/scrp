"""Canonical name computation via majority token voting.

For each barcode present in 2+ chains, picks the best item_name by:
1. Counting how many names contain each token (whitespace-split).
2. Keeping tokens that appear in strictly more than half the names.
3. Returning the original name that contains the most such majority tokens.
4. Falling back to the longest name when no majority tokens exist.
"""
import logging
from collections import Counter, defaultdict

from sqlalchemy import text

log = logging.getLogger(__name__)


def compute_canonical_name(names: list[str]) -> str:
    """
    Given a list of item names from different chains for the same barcode,
    return the best canonical name via majority token voting.
    """
    if not names:
        return ""
    if len(names) == 1:
        return names[0]

    # Count how many distinct names contain each token
    token_support: Counter = Counter()
    for name in names:
        for token in set(name.split()):
            token_support[token] += 1

    threshold = len(names) / 2  # strictly more than half
    majority_tokens = {t for t, count in token_support.items() if count > threshold}

    if not majority_tokens:
        return max(names, key=len)

    def majority_score(name: str) -> int:
        return len(set(name.split()) & majority_tokens)

    return max(names, key=majority_score)


def update_canonical_names(conn) -> dict:
    """
    Recompute canonical item names for all barcodes with 2+ chain entries.
    Updates items.item_name with the majority-voted result.
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
