"""Import manual store pins exported by tools/pin_tool (SU11A-19).

    python3 -m scripts.import_manual_pins picks_YYYYMMDD_HHMM.csv                     # dry run
    python3 -m scripts.import_manual_pins picks.csv --apply --expect N --session su11a20

Input columns: store_fk, lat, lon, method, candidate_id, timestamp
(method: candidate_osm / candidate_overture / clicked / confirmed_existing).

Every row is validated (validate_picks, unit-tested in tests/test_import_manual_pins.py):
  * store_fk exists and is a LIVE PHYSICAL store (db/query.py live_store_clause);
  * method is one of the four above; lat/lon are numbers inside Israel's bounding box;
  * within 15 km of the CBS centroid of the store's city_canonical (else rejected, listed);
  * no two stores in the file within 10 m of each other unless their addresses are the same;
  * stores already at geo_source='manual' are skipped unless --overwrite-manual;
  * a store_fk listed twice: the row with the latest timestamp wins (reported).

--apply (needs --expect N = the dry run's "to write" count, and --session for the backup
name): pg_dump of the stores table to ~/backups/pre-<session>-stores-<ts>.dump, then in ONE
transaction a stores_bak_<session> copy and the UPDATEs; rolls back unless the updated count
equals --expect. Sets lat, lon, geo_precision='address', geo_source='manual',
geo_input='manual <method> <candidate_id> <date>', geocoded_at=now().

geo_source='manual' rows are never re-geocoded (scripts/geo_nominatim.needs_geocode, SU10S-25)
and /stores/coordinates serves lat/lon/geo_precision straight from the table.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import re
import statistics
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ISRAEL_BBOX = (29.45, 34.2, 33.35, 35.95)     # lat_min, lon_min, lat_max, lon_max
MAX_CENTROID_KM = 15.0
DUP_KM = 0.010
METHODS = {"candidate_osm", "candidate_overture", "clicked", "confirmed_existing"}


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _norm_addr(a: str | None) -> str:
    return re.sub(r"\s+", " ", (a or "").strip())


def geo_input_for(row: dict) -> str:
    date = (row.get("timestamp") or "")[:10] or datetime.now().strftime("%Y-%m-%d")
    cid = (row.get("candidate_id") or "-").strip() or "-"
    return f"manual {row['method']} {cid} {date}"


def validate_picks(rows: list[dict], stores: dict[int, dict], centroids: dict[str, tuple[float, float]],
                   overwrite_manual: bool = False) -> tuple[list[dict], list[tuple[dict, str]], list[dict], dict]:
    """Pure validation. `stores` maps store_fk -> {live, is_physical, city_canonical, address,
    geo_source, chain, lat, lon} for every store row; `centroids` maps city -> (lat, lon).

    Returns (accepted, rejected [(row, reason)], skipped_manual, info)."""
    info = Counter()
    # 1. last row per store_fk wins (by timestamp, then file order)
    latest: dict[int, dict] = {}
    rejected: list[tuple[dict, str]] = []
    for i, r in enumerate(rows):
        try:
            fk = int(str(r.get("store_fk", "")).strip())
        except ValueError:
            rejected.append((r, "store_fk is not a number")); continue
        r = {**r, "store_fk": fk, "_order": i}
        prev = latest.get(fk)
        if prev is not None:
            info["duplicate store_fk rows superseded"] += 1
            if (r.get("timestamp") or "", i) < (prev.get("timestamp") or "", prev["_order"]):
                continue
        latest[fk] = r

    cand: list[dict] = []
    skipped: list[dict] = []
    for fk, r in latest.items():
        s = stores.get(fk)
        if s is None:
            rejected.append((r, "unknown store_fk")); continue
        if not (s.get("is_physical") and s.get("live")):
            rejected.append((r, "not a live physical store")); continue
        if r.get("method") not in METHODS:
            rejected.append((r, f"bad method {r.get('method')!r}")); continue
        try:
            lat, lon = float(r["lat"]), float(r["lon"])
        except (TypeError, ValueError, KeyError):
            rejected.append((r, "lat/lon not numbers")); continue
        if not (math.isfinite(lat) and math.isfinite(lon)):
            rejected.append((r, "lat/lon not finite")); continue
        lat0, lon0, lat1, lon1 = ISRAEL_BBOX
        if not (lat0 <= lat <= lat1 and lon0 <= lon <= lon1):
            rejected.append((r, "outside Israel bounding box")); continue
        city = s.get("city_canonical")
        cen = centroids.get(city) if city else None
        if cen is None:
            rejected.append((r, "no CBS centroid for the store's city_canonical - cannot check distance")); continue
        d = haversine_km(lat, lon, *cen)
        if d > MAX_CENTROID_KM:
            rejected.append((r, f"{d:.1f} km from the {city} centroid (max {MAX_CENTROID_KM:.0f})")); continue
        if s.get("geo_source") == "manual" and not overwrite_manual:
            skipped.append(r); continue
        cand.append({**r, "lat": lat, "lon": lon, "_store": s})

    # 2. no two stores in this file within 10 m unless the addresses are the same
    bad: dict[int, str] = {}
    for i, a in enumerate(cand):
        for b in cand[i + 1:]:
            if haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) <= DUP_KM and \
                    _norm_addr(a["_store"].get("address")) != _norm_addr(b["_store"].get("address")):
                bad[a["store_fk"]] = f"within 10 m of store_fk {b['store_fk']} (different address)"
                bad[b["store_fk"]] = f"within 10 m of store_fk {a['store_fk']} (different address)"
    accepted = []
    for r in cand:
        if r["store_fk"] in bad:
            rejected.append((r, bad[r["store_fk"]]))
        else:
            r["geo_input"] = geo_input_for(r)
            accepted.append(r)
    return accepted, rejected, skipped, dict(info)


def check_expect(planned: int, expect: int | None) -> None:
    if expect is None:
        raise SystemExit("--apply needs --expect N (the dry run's 'to write' count)")
    if expect != planned:
        raise SystemExit(f"ABORT: --expect {expect} but {planned} rows would be written; nothing written")


def move_report(accepted: list[dict]) -> list[str]:
    out = []
    by_chain = Counter(r["_store"].get("chain") for r in accepted)
    out.append("per chain: " + ", ".join(f"{c} {n}" for c, n in by_chain.most_common()))
    moves = [(haversine_km(r["_store"]["lat"], r["_store"]["lon"], r["lat"], r["lon"]), r)
             for r in accepted if r["_store"].get("lat") is not None]
    if moves:
        ds = sorted(m for m, _ in moves)
        p90 = statistics.quantiles(ds, n=10, method="inclusive")[8] if len(ds) > 1 else ds[0]
        out.append(f"moved from previous position ({len(ds)} with one): median {statistics.median(ds)*1000:.0f} m"
                   f" | p90 {p90*1000:.0f} m | max {ds[-1]*1000:.0f} m")
        big = [(m, r) for m, r in moves if m > 1.0]
        out.append(f"moves over 1 km: {len(big)}")
        for m, r in sorted(big, key=lambda x: -x[0]):
            s = r["_store"]
            out.append(f"   {m:6.2f} km  store_fk {r['store_fk']} {s.get('chain')} {s.get('store_id')} "
                       f"{s.get('address')!r}, {s.get('city_canonical')} [{s.get('geo_precision')} -> manual]")
    return out


def main() -> None:
    from sqlalchemy import text            # noqa: PLC0415 - keep the pure part importable in tests

    from db.db import connect              # noqa: PLC0415
    from db.query import live_store_clause  # noqa: PLC0415
    from scripts.geo_centroids import load_cbs_centroids  # noqa: PLC0415

    ap = argparse.ArgumentParser(description="Import manual pins from the pin tool (dry run by default)")
    ap.add_argument("picks")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--expect", type=int)
    ap.add_argument("--session", help="session id for the backup names, e.g. su11a20 (required with --apply)")
    ap.add_argument("--overwrite-manual", action="store_true")
    args = ap.parse_args()
    if args.apply and not (args.session and re.fullmatch(r"[a-z0-9_]+", args.session)):
        raise SystemExit("--apply needs --session (lowercase letters, digits, underscore)")

    with open(args.picks, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    conn = connect()
    try:
        live_sql, live_params = live_store_clause(conn)
        live_ids = {r[0] for r in conn.execute(text(
            f"SELECT s.id FROM stores s WHERE true {live_sql}"), live_params)}
        stores = {r["id"]: {**dict(r), "live": r["id"] in live_ids} for r in conn.execute(text("""
            SELECT s.id, s.store_id, c.name AS chain, s.is_physical, s.city_canonical,
                   COALESCE(NULLIF(btrim(s.address_override), ''), s.address) AS address,
                   s.lat, s.lon, s.geo_precision, s.geo_source
            FROM stores s LEFT JOIN chains c ON c.chain_id = s.chain_id""")).mappings()}

        accepted, rejected, skipped, info = validate_picks(rows, stores, load_cbs_centroids(),
                                                           args.overwrite_manual)
        print(f"rows in file {len(rows)} | to write {len(accepted)} | rejected {len(rejected)} | "
              f"skipped (already manual) {len(skipped)} | {info}")
        print("methods:", dict(Counter(r["method"] for r in accepted)))
        for r, why in rejected:
            print(f"   REJECT store_fk {r.get('store_fk')}: {why}")
        for line in move_report(accepted):
            print(line)

        if not args.apply:
            conn.rollback()
            print(f"\nDRY RUN - nothing written. To write: --apply --expect {len(accepted)} --session <id>")
            return
        check_expect(len(accepted), args.expect)

        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        dump = Path.home() / "backups" / f"pre-{args.session}-stores-{ts}.dump"
        dump.parent.mkdir(parents=True, exist_ok=True)
        rc = subprocess.run(["pg_dump", os.environ["DATABASE_URL"], "-t", "stores", "-Fc", "-f", str(dump)],
                            stderr=subprocess.DEVNULL).returncode     # never print the connection string
        if rc != 0 or not dump.exists() or dump.stat().st_size == 0:
            conn.rollback()
            raise SystemExit(f"ABORT: pg_dump failed (exit {rc}); nothing written")
        print(f"pg_dump -> {dump} ({dump.stat().st_size} bytes)")

        bak = f"stores_bak_{args.session}"
        if conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{bak}"}).scalar():
            conn.rollback()
            raise SystemExit(f"ABORT: {bak} already exists; nothing written")
        conn.execute(text(f"CREATE TABLE {bak} AS SELECT * FROM stores"))
        n = 0
        for r in accepted:
            n += conn.execute(text("""
                UPDATE stores SET lat = :lat, lon = :lon, geo_precision = 'address',
                       geo_source = 'manual', geo_input = :gi, geocoded_at = now()
                WHERE id = :fk AND is_physical
                  AND (geo_source IS DISTINCT FROM 'manual' OR :ow)
            """), {"lat": r["lat"], "lon": r["lon"], "gi": r["geo_input"], "fk": r["store_fk"],
                   "ow": args.overwrite_manual}).rowcount
        if n != args.expect:
            conn.rollback()
            raise SystemExit(f"ABORT + ROLLBACK: updated {n}, expected {args.expect}")
        conn.commit()
        print(f"COMMITTED: {n} manual pins; backup table {bak}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
