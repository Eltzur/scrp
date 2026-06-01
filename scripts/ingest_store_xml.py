"""
Ingest store metadata from Store_XML/ into the database.

Reads every Stores*.xml and StoresFull*.xml in Store_XML/, resolves city names
using the same priority chain the scrapers use, and updates the stores table.

Usage:
    python -m scripts.ingest_store_xml            # dry-run (safe, default)
    python -m scripts.ingest_store_xml --apply    # write changes to DB
    python -m scripts.ingest_store_xml --dir /path/to/xml_dir
    python -m scripts.ingest_store_xml --chain 7290058140886  # single chain
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup so we can run as  python -m scripts.ingest_store_xml
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from db.db import get_engine
from scraper.cerberus import CITY_CODES
from scraper.city_names import city_override, normalize_city
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find(el: ET.Element, *tags: str) -> ET.Element | None:
    """Find first matching child by tag name (tries each tag in order).
    Uses explicit `is not None` to avoid the ElementTree falsy-element trap.
    """
    for tag in tags:
        child = el.find(tag)
        if child is not None:
            return child
    return None


def _text(el: ET.Element, *tags: str) -> str:
    child = _find(el, *tags)
    return (child.text or "").strip() if child is not None else ""


def _pad(store_id: str) -> str:
    s = store_id.strip()
    return s.zfill(3) if s.isdigit() else s


def resolve_city(chain_id: str, store_id_padded: str, raw_city: str) -> tuple[str | None, str | None]:
    """
    Return (city, city_norm) using the standard priority chain:
      1. STORE_CITY_OVERRIDES  (city_override)
      2. CITY_CODES lookup     (numeric raw)
      3. normalize_city        (Hebrew string passthrough)

    city     = human-readable city name (after CITY_CODES decode, before normalization)
    city_norm = normalize_city(city)
    """
    override = city_override(chain_id, store_id_padded)
    if override:
        return override, normalize_city(override)

    if raw_city.isdigit():
        city = CITY_CODES.get(int(raw_city))
        if city:
            return city, normalize_city(city)
        return None, None  # unknown numeric code

    city = raw_city or None
    return city, normalize_city(city)


# ---------------------------------------------------------------------------
# Per-chain accumulator
# ---------------------------------------------------------------------------

@dataclass
class ChainStats:
    chain_id: str
    xml_stores: int = 0
    db_matched: int = 0
    updated: int = 0
    skipped: int = 0
    no_city: int = 0
    proposals: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

def parse_stores_xml(path: Path) -> tuple[str | None, list[dict]]:
    """
    Parse a Stores or StoresFull XML file.
    Returns (chain_id, list_of_store_dicts).
    Each dict has: chain_id, store_id, store_name, address, raw_city, city, city_norm.
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        print(f"  [WARN] cannot parse {path.name}: {exc}")
        return None, []

    root = tree.getroot()

    # chain_id: prefer XML element, fall back to filename
    chain_el = _find(root, "ChainId", "ChainID", "CHAINID")
    if chain_el is not None and chain_el.text:
        chain_id = chain_el.text.strip()
    else:
        m = re.search(r"(\d{13})", path.name)
        chain_id = m.group(1) if m else None

    if not chain_id:
        print(f"  [WARN] cannot determine chain_id for {path.name}")
        return None, []

    stores = root.findall(".//Store") or root.findall(".//STORE") or root.findall(".//store")

    results = []
    for s in stores:
        store_id_raw = _text(s, "StoreId", "StoreID", "STOREID", "store_id")
        if not store_id_raw:
            continue
        store_id = _pad(store_id_raw)
        store_name = _text(s, "StoreName", "STORENAME", "store_name")
        address = _text(s, "Address", "ADDRESS", "address")
        raw_city = _text(s, "City", "CITY", "city")

        city, city_norm = resolve_city(chain_id, store_id, raw_city)

        results.append({
            "chain_id":   chain_id,
            "store_id":   store_id,
            "store_name": store_name,
            "address":    address,
            "raw_city":   raw_city,
            "city":       city,
            "city_norm":  city_norm,
        })

    return chain_id, results


# ---------------------------------------------------------------------------
# DB interaction
# ---------------------------------------------------------------------------

def fetch_db_store(conn, chain_id: str, store_id: str) -> dict | None:
    row = conn.execute(
        text("SELECT city, city_norm FROM stores WHERE chain_id=:c AND store_id=:s"),
        {"c": chain_id, "s": store_id},
    ).mappings().first()
    return dict(row) if row else None


def apply_update(conn, chain_id: str, store_id: str, city: str | None, city_norm: str | None) -> None:
    conn.execute(
        text("""
            UPDATE stores
               SET city      = :city,
                   city_norm = :city_norm
             WHERE chain_id  = :c
               AND store_id  = :s
        """),
        {"city": city, "city_norm": city_norm, "c": chain_id, "s": store_id},
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest store city data from Store_XML/")
    parser.add_argument("--apply", action="store_true",
                        help="Write changes to DB (default is dry-run)")
    parser.add_argument("--dir", default=str(_ROOT / "Store_XML"),
                        help="Directory containing Store*.xml files")
    parser.add_argument("--chain", metavar="CHAIN_ID",
                        help="Process only this chain_id")
    args = parser.parse_args()

    dry_run = not args.apply
    xml_dir = Path(args.dir)

    if not xml_dir.is_dir():
        sys.exit(f"Store XML directory not found: {xml_dir}")

    xml_files = sorted(
        p for p in xml_dir.iterdir()
        if p.suffix.upper() == ".XML" and
        (p.name.startswith("Stores") or p.name.startswith("StoresFull"))
    )

    if not xml_files:
        sys.exit(f"No Stores*.xml files found in {xml_dir}")

    mode_label = "DRY RUN" if dry_run else "APPLY"
    print(f"\n=== ingest_store_xml — {mode_label} ===")
    print(f"XML dir : {xml_dir}")
    print(f"Files   : {len(xml_files)}")
    if args.chain:
        print(f"Filter  : chain_id={args.chain}")
    print()

    # Collect all stores grouped by chain_id
    chain_stores: dict[str, list[dict]] = {}
    for xml_path in xml_files:
        chain_id, stores = parse_stores_xml(xml_path)
        if not chain_id or not stores:
            continue
        if args.chain and chain_id != args.chain:
            continue
        # Use the file with the most stores per chain (latest / fullest)
        if chain_id not in chain_stores or len(stores) > len(chain_stores[chain_id]):
            chain_stores[chain_id] = stores

    if not chain_stores:
        print("No matching XML data found.")
        return

    engine = get_engine()
    stats_by_chain: list[ChainStats] = []

    with engine.connect() as conn:
        for chain_id, stores in sorted(chain_stores.items()):
            cs = ChainStats(chain_id=chain_id, xml_stores=len(stores))

            for s in stores:
                sid      = s["store_id"]
                city     = s["city"]
                cnorm    = s["city_norm"]

                if not city and not cnorm:
                    cs.no_city += 1

                db_row = fetch_db_store(conn, chain_id, sid)
                if db_row is None:
                    # Store not in DB — skip (we don't INSERT here)
                    continue

                cs.db_matched += 1

                # Skip if XML city value is literally "unknown" (bad source data)
                if s["raw_city"].lower() == "unknown":
                    cs.skipped += 1
                    continue

                # Skip if already matches
                if db_row["city_norm"] == cnorm and db_row["city"] == city:
                    cs.skipped += 1
                    continue

                # Safety: never overwrite existing good city_norm with NULL
                if db_row["city_norm"] is not None and cnorm is None:
                    cs.skipped += 1
                    continue

                cs.updated += 1
                cs.proposals.append({
                    "store_id":       sid,
                    "store_name":     s["store_name"],
                    "raw_city":       s["raw_city"],
                    "city":           city,
                    "city_norm":      cnorm,
                    "db_city":        db_row["city"],
                    "db_city_norm":   db_row["city_norm"],
                })

                if not dry_run:
                    apply_update(conn, chain_id, sid, city, cnorm)

            if not dry_run and cs.updated:
                conn.commit()

            stats_by_chain.append(cs)

    # ---------------------------------------------------------------------------
    # Report
    # ---------------------------------------------------------------------------
    print(f"{'Chain ID':<16} {'XML':>5} {'DB match':>8} {'Updated':>7} {'Skipped':>7} {'No city':>7}")
    print("-" * 60)
    totals = [0, 0, 0, 0, 0]
    for cs in stats_by_chain:
        print(f"{cs.chain_id:<16} {cs.xml_stores:>5} {cs.db_matched:>8} "
              f"{cs.updated:>7} {cs.skipped:>7} {cs.no_city:>7}")
        totals[0] += cs.xml_stores
        totals[1] += cs.db_matched
        totals[2] += cs.updated
        totals[3] += cs.skipped
        totals[4] += cs.no_city

    print("-" * 60)
    print(f"{'TOTAL':<16} {totals[0]:>5} {totals[1]:>8} "
          f"{totals[2]:>7} {totals[3]:>7} {totals[4]:>7}")

    # Detailed proposals for changed stores
    if dry_run:
        print(f"\n--- Proposed updates ({sum(cs.updated for cs in stats_by_chain)} rows) ---")
        for cs in stats_by_chain:
            if not cs.proposals:
                continue
            print(f"\n  {cs.chain_id}:")
            for p in cs.proposals:
                db_disp = f"city={p['db_city']!r} norm={p['db_city_norm']!r}"
                new_disp = f"city={p['city']!r} norm={p['city_norm']!r}"
                print(f"    store {p['store_id']} {p['store_name'][:25]:<25}"
                      f"  raw={p['raw_city']!r:<12}  {db_disp} → {new_disp}")
        print(f"\nRe-run with --apply to write {sum(cs.updated for cs in stats_by_chain)} updates.")
    else:
        print(f"\nDone — {sum(cs.updated for cs in stats_by_chain)} rows updated.")


if __name__ == "__main__":
    main()
