"""Cross-chain overlap report.

Usage:
  python -m db.chain_overlap [db_file]

Prints:
  - Unique barcodes per chain
  - Barcode overlap between chains
  - Top 10 price delta products (items cheapest in chain A vs chain B)
"""
import io
import sys
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from db.db import connect, DEFAULT_DB


def run(db_path: Path = DEFAULT_DB) -> None:
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    conn = connect(db_path)

    # --- Chains present in DB ---
    chains = conn.execute(
        "SELECT chain_id, name FROM chains ORDER BY chain_id"
    ).fetchall()

    if not chains:
        print("No chains in database.")
        return

    print("=" * 60)
    print("CHAIN OVERLAP REPORT")
    print("=" * 60)

    # --- Unique barcodes per chain ---
    print("\nUnique barcodes per chain:")
    chain_codes: dict[str, set] = {}
    for ch in chains:
        cid = ch["chain_id"]
        rows = conn.execute(
            """SELECT DISTINCT p.item_code
               FROM prices p
               JOIN stores s ON s.id = p.store_fk
               WHERE s.chain_id = ?""",
            (cid,),
        ).fetchall()
        codes = {r["item_code"] for r in rows}
        chain_codes[cid] = codes
        label = ch["name"] if ch["name"] else cid
        print(f"  {label:<30}  {len(codes):>7,} barcodes")

    # --- Pairwise overlap ---
    chain_ids = list(chain_codes.keys())
    if len(chain_ids) >= 2:
        print("\nBarcode overlap between chains:")
        for i in range(len(chain_ids)):
            for j in range(i + 1, len(chain_ids)):
                a, b = chain_ids[i], chain_ids[j]
                overlap = chain_codes[a] & chain_codes[b]
                name_a = next(ch["name"] or ch["chain_id"] for ch in chains if ch["chain_id"] == a)
                name_b = next(ch["name"] or ch["chain_id"] for ch in chains if ch["chain_id"] == b)
                pct = 100 * len(overlap) / max(len(chain_codes[a] | chain_codes[b]), 1)
                print(
                    f"  {name_a} ∩ {name_b}: "
                    f"{len(overlap):,} shared barcodes "
                    f"({pct:.1f}% of union)"
                )

        # --- Top 10 price delta products ---
        print("\nTop 10 largest price differences (shared items, cheapest store per chain):")
        # Get best price per (item_code, chain_id)
        rows = conn.execute(
            """SELECT p.item_code, s.chain_id, MIN(p.item_price) AS best_price, i.item_name
               FROM prices p
               JOIN stores s ON s.id = p.store_fk
               JOIN items  i ON i.item_code = p.item_code
               GROUP BY p.item_code, s.chain_id"""
        ).fetchall()

        # Build item_code -> {chain_id: best_price, name}
        by_item: dict[str, dict] = defaultdict(dict)
        item_names: dict[str, str] = {}
        for r in rows:
            by_item[r["item_code"]][r["chain_id"]] = r["best_price"]
            item_names[r["item_code"]] = r["item_name"] or r["item_code"]

        # Find items shared by at least first two chains, compute delta
        a, b = chain_ids[0], chain_ids[1]
        deltas = []
        for code, prices in by_item.items():
            if a in prices and b in prices:
                delta = abs(prices[a] - prices[b])
                deltas.append((delta, code, prices[a], prices[b]))

        deltas.sort(reverse=True)
        name_a = next(ch["name"] or ch["chain_id"] for ch in chains if ch["chain_id"] == a)
        name_b = next(ch["name"] or ch["chain_id"] for ch in chains if ch["chain_id"] == b)
        print(f"  {'CODE':<14}  {'DELTA':>7}  {name_a:>10}  {name_b:>10}  NAME")
        print("  " + "-" * 80)
        for delta, code, pa, pb in deltas[:10]:
            print(
                f"  {code:<14}  {delta:>7.2f}  "
                f"{pa:>10.2f}  {pb:>10.2f}  "
                f"{item_names[code]}"
            )

    conn.close()
    print()


if __name__ == "__main__":
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    run(db)
