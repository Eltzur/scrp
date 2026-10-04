"""One-time backfill of stores.address from the chains' Stores/StoresFull files (SU11A-15).

    python3 -m scripts.backfill_store_addresses                    # dry run (default)
    python3 -m scripts.backfill_store_addresses --apply --expect N # N = the dry run's count

WHY. Four loaders never store the address every chain publishes:
shufersal.py, victory.py and hazihinam.py insert no address column, and
binaprojects.py (King Store, Shefa, Shuk HaIr) wrote "" every night until
SU11A-15. So ~460 live stores could only sit on their city centroid. Their
live store lists carry no address either (Victory getbranches: name/number;
Bina Select_Store: Kod/Nm), so the source is the Stores/StoresFull XML in
Store_XML/ (gitignored; newest file per chain is used, its date is printed).

WHAT IT WRITES. stores.address only, and only where ALL of these hold:
  * the row is physical and live (db/query.py live_store_clause);
  * address AND address_override are both empty (a hand fix is never touched);
  * geo_source is not 'manual' (a hand-placed pin is never touched);
  * exactly one feed store and exactly one stores row share (chain, store_id);
  * the feed address is not junk ("unknown", "-", …) and not a URL.
The value is the feed address exactly as published (outer whitespace trimmed).
Query cleaning happens later, in scripts/geo_clean.py, never in storage.

SAFETY (--apply): pg_dump of the stores table to
~/backups/pre-su11a15-stores-<timestamp>.dump, then in ONE transaction a
stores_bak_su11a15 copy and the guarded UPDATEs; it rolls back unless the
updated count equals both the planned count and --expect.
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from db.db import connect
from db.query import live_store_clause
from scripts.geo_nominatim import _JUNK

ROOT = Path(__file__).resolve().parent.parent
_FNAME = re.compile(r"^Stores(?:Full)?(\d{13})-", re.I)

# Only the chains whose loaders drop the address. Every other loader stores
# the feed address itself, and a cached file can predate a renumbering
# (Carrefour, July 2026 - SU11A-14), so other chains are deliberately left out.
CHAINS = {
    "7290027600007": "Shufersal",
    "7290696200003": "Victory",
    "7290700100008": "Hazi Hinam",
    "7290058108879": "King Store",
    "7290058134977": "Shefa Birkat Hashem",
    "7290058148776": "Shuk HaIr",
    "7290785400000": "Keshet",
}

_TARGET_SQL = """
    SELECT s.id, s.chain_id, s.store_id
    FROM stores s
    WHERE s.is_physical
      AND s.chain_id = ANY(:chains)
      AND coalesce(btrim(s.address), '') = ''
      AND coalesce(btrim(s.address_override), '') = ''
      AND s.geo_source IS DISTINCT FROM 'manual'
      {live}
"""


def _parse(path: Path) -> list[dict]:
    raw = path.read_bytes()
    root = None
    for enc in ("utf-16", "utf-8-sig"):
        try:
            s = raw.decode(enc)
            if "<" in s[:300]:
                root = ET.fromstring(s.lstrip("﻿"))
                break
        except Exception:
            continue
    if root is None:
        return []
    out = []
    for e in root.iter():
        if e.tag.lower() != "store":
            continue
        d = {ch.tag.lower(): (ch.text or "").strip() for ch in e}
        try:
            sid = int(d.get("storeid") or "")
        except ValueError:
            continue
        out.append({"sid": sid, "address": d.get("address", "")})
    return out


def feed_addresses(xml_dir: Path) -> tuple[dict, dict]:
    """{chain_id: {store_id_int: address}} from the newest file per chain, and the files used."""
    newest: dict[str, Path] = {}
    for p in xml_dir.iterdir():
        m = _FNAME.match(p.name)
        if m and m.group(1) in CHAINS and (m.group(1) not in newest or p.name > newest[m.group(1)].name):
            newest[m.group(1)] = p
    feeds, dupes = {}, collections.Counter()
    for chain, p in newest.items():
        seen: dict[int, list[str]] = collections.defaultdict(list)
        for row in _parse(p):
            seen[row["sid"]].append(row["address"])
        feeds[chain] = {sid: a[0] for sid, a in seen.items() if len(a) == 1}
        dupes[chain] = sum(1 for a in seen.values() if len(a) > 1)
    return feeds, {c: (p.name, dupes[c]) for c, p in newest.items()}


def usable(addr: str) -> bool:
    a = (addr or "").strip()
    return bool(a) and a.lower() not in _JUNK and not a.lower().startswith(("http", "www."))


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill stores.address from Store_XML (SU11A-15)")
    ap.add_argument("--dir", default=str(ROOT / "Store_XML"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--expect", type=int, help="required with --apply: the dry run's planned count")
    args = ap.parse_args()
    if args.apply and args.expect is None:
        sys.exit("--apply needs --expect N (the planned count printed by the dry run)")

    feeds, files = feed_addresses(Path(args.dir))
    for chain, (name, dup) in sorted(files.items()):
        print(f"  feed {chain}: {name}" + (f"  ({dup} duplicate store ids skipped)" if dup else ""))

    conn = connect()
    try:
        live_sql, live_params = live_store_clause(conn)
        rows = conn.execute(text(_TARGET_SQL.format(live=live_sql)),
                            {**live_params, "chains": list(CHAINS)}).mappings().all()
        ids_per_key = collections.Counter(
            (r[0], int(r[1])) for r in conn.execute(text(
                "SELECT chain_id, store_id FROM stores WHERE store_id ~ '^[0-9]+$' AND chain_id = ANY(:c)"),
            {"c": list(CHAINS)}).all())

        plan, skipped = [], collections.Counter()
        for r in rows:
            if not r["store_id"].isdigit():
                skipped["non-numeric store_id"] += 1; continue
            key = (r["chain_id"], int(r["store_id"]))
            feed = feeds.get(r["chain_id"])
            if feed is None:
                skipped["no feed file for chain"] += 1; continue
            if ids_per_key[key] != 1:
                skipped["store_id not unique in stores"] += 1; continue
            addr = feed.get(key[1])
            if addr is None:
                skipped["not in feed"] += 1; continue
            if not usable(addr):
                skipped["junk/empty/URL address"] += 1; continue
            plan.append((r["id"], r["chain_id"], r["store_id"], addr.strip()))

        by_chain = collections.Counter(c for _, c, _, _ in plan)
        print(f"\ncandidates (physical, live, no address/override, not manual): {len(rows)}")
        print(f"planned updates: {len(plan)}  by chain: {dict(by_chain)}")
        print(f"skipped: {dict(skipped)}")
        for p in plan[:15]:
            print(f"   id {p[0]} chain {p[1]} store {p[2]} -> {p[3]!r}")

        if not args.apply:
            conn.rollback()
            print("\nDRY RUN - nothing written. Re-run with --apply --expect "
                  f"{len(plan)} to write.")
            return
        if args.expect != len(plan):
            conn.rollback()
            sys.exit(f"ABORT: --expect {args.expect} but {len(plan)} planned; nothing written")

        # Backup 1: pg_dump of the whole stores table. The connection string is never printed.
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        dump = Path.home() / "backups" / f"pre-su11a15-stores-{ts}.dump"
        dump.parent.mkdir(parents=True, exist_ok=True)
        rc = subprocess.run(["pg_dump", os.environ["DATABASE_URL"], "-t", "stores", "-Fc",
                             "-f", str(dump)], stderr=subprocess.DEVNULL).returncode
        if rc != 0 or not dump.exists() or dump.stat().st_size == 0:
            conn.rollback()
            sys.exit(f"ABORT: pg_dump failed (exit {rc}); nothing written")
        print(f"pg_dump -> {dump} ({dump.stat().st_size} bytes)")

        # Backup 2 + guarded UPDATEs, one transaction.
        if conn.execute(text("SELECT to_regclass('public.stores_bak_su11a15')")).scalar():
            conn.rollback()
            sys.exit("ABORT: stores_bak_su11a15 already exists; nothing written")
        conn.execute(text("CREATE TABLE stores_bak_su11a15 AS SELECT * FROM stores"))
        n = 0
        for sid_pk, _, _, addr in plan:
            n += conn.execute(text("""
                UPDATE stores SET address = :a
                WHERE id = :id AND is_physical
                  AND coalesce(btrim(address), '') = ''
                  AND coalesce(btrim(address_override), '') = ''
                  AND geo_source IS DISTINCT FROM 'manual'
            """), {"a": addr, "id": sid_pk}).rowcount
        if n != len(plan) or n != args.expect:
            conn.rollback()
            sys.exit(f"ABORT + ROLLBACK: updated {n}, planned {len(plan)}, expected {args.expect}")
        conn.commit()
        print(f"COMMITTED: {n} addresses written; backup table stores_bak_su11a15")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
