"""N-chain overlap report.

Usage:
  python -m db.chain_overlap [db_file]

Output:
  1. Per-chain stats (barcodes, price rows, stores loaded)
  2. Pairwise overlap matrix
  3. All-chains intersection count
  4. Top 20 price deltas (any 2+ chains)
  5. Exclusivity counts per chain
  6. Top 10 exclusive products per chain
"""
import io
import sys
from pathlib import Path
from collections import defaultdict
from itertools import combinations

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from db.db import connect, DEFAULT_DB


def run(db_path: Path = DEFAULT_DB) -> None:
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    conn = connect(db_path)
    chains = conn.execute(
        "SELECT chain_id, name FROM chains ORDER BY name"
    ).fetchall()

    if not chains:
        print("No chains in database.")
        return

    def label(ch) -> str:
        return ch["name"] if ch["name"] else ch["chain_id"]

    print("=" * 65)
    print("CROSS-CHAIN OVERLAP REPORT")
    print("=" * 65)

    # ------------------------------------------------------------------
    # 1. Per-chain stats
    # ------------------------------------------------------------------
    print("\n── Per-chain summary ──────────────────────────────────────────")
    chain_codes: dict[str, set] = {}
    for ch in chains:
        cid = ch["chain_id"]
        codes = {r["item_code"] for r in conn.execute(
            "SELECT DISTINCT p.item_code FROM prices p "
            "JOIN stores s ON s.id=p.store_fk WHERE s.chain_id=?", (cid,)
        ).fetchall()}
        chain_codes[cid] = codes

        n_prices = conn.execute(
            "SELECT COUNT(*) FROM prices p "
            "JOIN stores s ON s.id=p.store_fk WHERE s.chain_id=?", (cid,)
        ).fetchone()[0]

        n_stores = conn.execute(
            "SELECT COUNT(DISTINCT s.id) FROM prices p "
            "JOIN stores s ON s.id=p.store_fk WHERE s.chain_id=?", (cid,)
        ).fetchone()[0]

        print(
            f"  {label(ch):<16}  {len(codes):>7,} barcodes  "
            f"{n_prices:>8,} price rows  {n_stores} stores loaded"
        )

    chain_ids = [ch["chain_id"] for ch in chains]

    # ------------------------------------------------------------------
    # 2. Pairwise overlap matrix
    # ------------------------------------------------------------------
    print("\n── Pairwise barcode overlap ────────────────────────────────────")
    col_w = 14
    header = f"{'':16}" + "".join(f"{label(ch):>{col_w}}" for ch in chains)
    print(header)
    for ch_a in chains:
        row = f"{label(ch_a):<16}"
        for ch_b in chains:
            if ch_a["chain_id"] == ch_b["chain_id"]:
                cell = f"{len(chain_codes[ch_a['chain_id']]):,}"
            else:
                overlap = chain_codes[ch_a["chain_id"]] & chain_codes[ch_b["chain_id"]]
                cell = f"{len(overlap):,}"
            row += f"{cell:>{col_w}}"
        print(row)

    # ------------------------------------------------------------------
    # 3. All-chains intersection
    # ------------------------------------------------------------------
    if len(chain_ids) >= 2:
        all_overlap = set.intersection(*chain_codes.values())
        print(f"\n── All-chains intersection ─────────────────────────────────────")
        pct = 100 * len(all_overlap) / max(len(set.union(*chain_codes.values())), 1)
        print(
            f"  Barcodes in ALL {len(chains)} chains: "
            f"{len(all_overlap):,}  ({pct:.1f}% of full union)"
        )

    # ------------------------------------------------------------------
    # 4. Top 20 price deltas (any 2+ chains)
    # ------------------------------------------------------------------
    print("\n── Top 20 price deltas (cheapest vs most expensive chain) ─────")

    rows = conn.execute("""
        SELECT p.item_code, s.chain_id, MIN(p.item_price) AS best_price, i.item_name
        FROM prices p
        JOIN stores s ON s.id = p.store_fk
        JOIN items  i ON i.item_code = p.item_code
        GROUP BY p.item_code, s.chain_id
    """).fetchall()

    by_item: dict[str, dict] = defaultdict(dict)
    item_names: dict[str, str] = {}
    for r in rows:
        by_item[r["item_code"]][r["chain_id"]] = r["best_price"]
        item_names[r["item_code"]] = r["item_name"] or r["item_code"]

    chain_name_map = {ch["chain_id"]: label(ch) for ch in chains}

    deltas = []
    for code, prices in by_item.items():
        present = [cid for cid in chain_ids if cid in prices]
        if len(present) < 2:
            continue
        cheapest_cid  = min(present, key=lambda c: prices[c])
        expensive_cid = max(present, key=lambda c: prices[c])
        delta = prices[expensive_cid] - prices[cheapest_cid]
        deltas.append((delta, code, cheapest_cid, prices[cheapest_cid],
                       expensive_cid, prices[expensive_cid]))

    deltas.sort(reverse=True)
    print(f"  {'CODE':<14}  {'Δ':>7}  {'Cheapest':>10}  {'Expensive':>10}  NAME")
    print("  " + "-" * 85)
    for delta, code, cheap_cid, cheap_p, exp_cid, exp_p in deltas[:20]:
        print(
            f"  {code:<14}  {delta:>7.2f}  "
            f"{chain_name_map[cheap_cid]}/{cheap_p:>6.2f}  "
            f"{chain_name_map[exp_cid]}/{exp_p:>6.2f}  "
            f"{item_names[code]}"
        )

    # ------------------------------------------------------------------
    # 5. Exclusivity counts
    # ------------------------------------------------------------------
    print("\n── Exclusive barcodes (present in 1 chain only) ───────────────")
    exclusive_codes: dict[str, set] = {}
    for cid in chain_ids:
        others = set.union(*(chain_codes[o] for o in chain_ids if o != cid))
        exclusive_codes[cid] = chain_codes[cid] - others

    for ch in chains:
        cid = ch["chain_id"]
        pct = 100 * len(exclusive_codes[cid]) / max(len(chain_codes[cid]), 1)
        print(f"  {label(ch):<16}  {len(exclusive_codes[cid]):>6,} exclusive barcodes  ({pct:.1f}% of chain's catalogue)")

    # ------------------------------------------------------------------
    # 6. Top 10 exclusives per chain
    # ------------------------------------------------------------------
    print("\n── Top 10 exclusive products per chain (by price, ascending) ──")
    for ch in chains:
        cid = ch["chain_id"]
        excl = exclusive_codes[cid]
        if not excl:
            print(f"\n  {label(ch)}: no exclusive barcodes.")
            continue

        placeholders = ",".join("?" * len(excl))
        top = conn.execute(f"""
            SELECT p.item_code, MIN(p.item_price) AS price, i.item_name
            FROM prices p
            JOIN stores s ON s.id = p.store_fk
            JOIN items  i ON i.item_code = p.item_code
            WHERE s.chain_id = ? AND p.item_code IN ({placeholders})
            GROUP BY p.item_code
            ORDER BY price
            LIMIT 10
        """, (cid, *excl)).fetchall()

        print(f"\n  {label(ch)} exclusives:")
        for r in top:
            print(f"    {r['item_code']:<14}  {r['price']:>8.2f}  {r['item_name']}")

    conn.close()
    print()


if __name__ == "__main__":
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    run(db)
