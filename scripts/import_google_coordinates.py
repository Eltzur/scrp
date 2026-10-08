"""Load store coordinates from the Google result files (SU11A-23).

Decision (Dude, 2026-10-08): the Google results are the single source of truth for store
coordinates (coordinates first, address text second); OSM / Nominatim / Overture are retired as
coordinate sources.

    python3 -m scripts.import_google_coordinates \\
        --exact ~/google_compare/store_full_920_list.csv \\
        --reviewed ~/google_compare/156_store_update.xlsx                 # DRY RUN (default)
    ... --apply --expect N --session SU11A-23                              # write
    python3 -m scripts.import_google_coordinates --rollback SU11A-23       # restore from the backup table

Inputs (they live only in ~/google_compare/, never in the repo):
  --exact     CSV, rows with Exact == TRUE: Lat, Lon, Precision, formatted_address -> google_exact
  --reviewed  XLSX, sheet "Review 156" (or "Review"): the lat,lon pair in "Notes" (else "My decision")
              -> google_reviewed; label = "My decision" text when it is an address, else the Google
              formatted address. Rows with no parseable pair are listed, never guessed.

Apply (needs db/migrations/su11a23_stores_coord_source.sql applied first): pg_dump of `stores`
to ~/backups/pre-<session>-stores-<ts>.dump, then ONE transaction: backup table
stores_bak_<session> and the UPDATEs, rolled back unless the count equals --expect. Sets lat, lon,
geo_precision='address', geo_source='google', coord_source, geo_label, verified_at=now(),
verified_by=<session>. Manual rows (geo_source='manual') are skipped unless --override-manual.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from scripts.import_manual_pins import check_expect, haversine_km

# Explicit allow-list. Adding a source is a deliberate change: this tuple, the CHECK constraint in
# db/migrations/su11a23_stores_coord_source.sql and scripts/geo_guard.py, in one reviewed commit.
ALLOWED_SOURCES = ("google_exact", "google_reviewed", "manual_pin", "osm_house")
LOADABLE_SOURCES = ("google_exact", "google_reviewed")      # what this importer writes
BOUNDS = (29.4, 34.2, 33.4, 35.9)                           # lat_min, lon_min, lat_max, lon_max
FAR_MOVE_KM = 5.0
FAR_CENTROID_KM = 15.0
DUP_KM = 0.010
SESSION_RE = re.compile(r"^SU\d+[A-Z]-\d+[a-z]?$")
_PAIR = re.compile(r"(-?\d{1,2}\.\d+)\s*[,;/ ]\s*(-?\d{1,2}\.\d+)")


# ---------------------------------------------------------------------------
# Parsing (pure)
# ---------------------------------------------------------------------------
def parse_pair(text_value) -> tuple[float, float] | None:
    """The first lat,lon pair inside Israel's range in a free-text cell, else None."""
    if text_value is None:
        return None
    for m in _PAIR.finditer(str(text_value)):
        a, b = float(m.group(1)), float(m.group(2))
        for lat, lon in ((a, b), (b, a)):
            if BOUNDS[0] <= lat <= BOUNDS[2] and BOUNDS[1] <= lon <= BOUNDS[3]:
                return lat, lon
    return None


def rows_from_exact(rows: list[dict]) -> list[dict]:
    """Set A: Exact == TRUE rows of the 920-store CSV."""
    out = []
    for r in rows:
        if str(r.get("Exact", "")).strip().lower() != "true":
            continue
        out.append({"store_fk": r.get("store_fk"), "lat": r.get("Lat"), "lon": r.get("Lon"),
                    "source": "google_exact", "precision": (r.get("Precision") or "").strip(),
                    "label": (r.get("formatted_address") or "").strip(), "origin": "A"})
    return out


def rows_from_reviewed(rows: list[dict]) -> tuple[list[dict], list[tuple[dict, str]]]:
    """Set B: the hand-reviewed sheet. Returns (rows, unparseable [(row, why)])."""
    out, bad = [], []
    for r in rows:
        fk = r.get("store_fk")
        if fk in (None, ""):
            continue
        decision, notes = r.get("My decision"), r.get("Notes")
        pair = parse_pair(notes) or parse_pair(decision)
        if pair is None:
            bad.append((r, "no lat,lon pair in Notes or My decision"))
            continue
        dec_txt = "" if decision is None else str(decision).strip()
        label = dec_txt if dec_txt and parse_pair(dec_txt) is None else (r.get("Google formatted address") or "")
        out.append({"store_fk": fk, "lat": pair[0], "lon": pair[1], "source": "google_reviewed",
                    "precision": "reviewed", "label": str(label).strip(), "origin": "B",
                    "decision": dec_txt})
    return out, bad


def read_exact_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def read_reviewed_xlsx(path: str) -> list[dict]:
    from openpyxl import load_workbook  # noqa: PLC0415

    wb = load_workbook(path, read_only=True, data_only=True)
    name = next((n for n in ("Review", "Review 156") if n in wb.sheetnames), None)
    if name is None:
        raise SystemExit(f"no 'Review' sheet in {path} (sheets: {wb.sheetnames})")
    it = wb[name].iter_rows(values_only=True)
    head = [str(h).strip() if h is not None else "" for h in next(it)]
    return [dict(zip(head, r)) for r in it if any(v is not None for v in r)]


# ---------------------------------------------------------------------------
# Validation (pure)
# ---------------------------------------------------------------------------
def validate(cands: list[dict], stores: dict[int, dict], centroids: dict[str, tuple[float, float]],
             override_manual: bool = False) -> dict:
    """`stores` maps store_fk -> {live, is_physical, chain, city_canonical, lat, lon, geo_source, ...}
    for every row of `stores`. Returns a report dict; nothing is written."""
    rep: dict = {"accepted": [], "rejected": [], "skipped_manual": [], "precision_review": [],
                 "far_moves": [], "far_centroid": [], "manual_pins": [], "move_hist": Counter()}
    by_fk: dict[int, list[dict]] = {}
    for c in cands:
        try:
            fk = int(str(c.get("store_fk")).strip().split(".")[0])
        except (TypeError, ValueError):
            rep["rejected"].append((c, "store_fk is not a number")); continue
        by_fk.setdefault(fk, []).append({**c, "store_fk": fk})

    live_phys = {fk for fk, s in stores.items() if s.get("live") and s.get("is_physical")}
    in_a = {fk for fk, cs in by_fk.items() if any(c["origin"] == "A" for c in cs)}
    in_b = {fk for fk, cs in by_fk.items() if any(c["origin"] == "B" for c in cs)}
    rep["overlap_a_b"] = sorted(in_a & in_b)
    rep["missing"] = sorted(live_phys - set(by_fk))
    rep["extra"] = sorted(set(by_fk) - live_phys)

    ok = []
    for fk, cs in by_fk.items():
        if len(cs) != 1:
            rep["rejected"].extend((c, f"{len(cs)} coordinates for this store_fk") for c in cs)
            continue
        c = cs[0]
        if c.get("source") not in ALLOWED_SOURCES:
            rep["rejected"].append((c, f"source {c.get('source')!r} not in the allow-list")); continue
        if c["source"] not in LOADABLE_SOURCES:
            rep["rejected"].append((c, f"source {c['source']!r} is not loaded by this importer")); continue
        s = stores.get(fk)
        if s is None:
            rep["rejected"].append((c, "unknown store_fk")); continue
        if not (s.get("live") and s.get("is_physical")):
            rep["rejected"].append((c, "not a live physical store")); continue
        try:
            lat, lon = float(c["lat"]), float(c["lon"])
        except (TypeError, ValueError, KeyError):
            rep["rejected"].append((c, "unparseable coordinate")); continue
        if not (BOUNDS[0] <= lat <= BOUNDS[2] and BOUNDS[1] <= lon <= BOUNDS[3]):
            rep["rejected"].append((c, "outside Israel bounds")); continue
        c = {**c, "lat": lat, "lon": lon, "_store": s}
        if s.get("lat") is not None:
            d = haversine_km(lat, lon, s["lat"], s["lon"])
            c["moved_km"] = d
            rep["move_hist"]["<50 m" if d < 0.05 else "<500 m" if d < 0.5 else "<5 km" if d < 5 else ">=5 km"] += 1
            if d >= FAR_MOVE_KM:
                rep["far_moves"].append(c)
        else:
            rep["move_hist"]["no current point"] += 1
        cen = centroids.get(s.get("city_canonical") or "")
        if cen and haversine_km(lat, lon, *cen) > FAR_CENTROID_KM:
            rep["far_centroid"].append({**c, "centroid_km": haversine_km(lat, lon, *cen)})
        if c["source"] == "google_exact" and c.get("precision") != "rooftop":
            rep["precision_review"].append(c)
        if s.get("geo_source") == "manual" or s.get("coord_source") == "manual_pin":
            rep["manual_pins"].append(c)
            if not override_manual:
                rep["skipped_manual"].append(c); continue
        ok.append(c)

    # Two stores within 10 m: reported (not rejected) - same chain vs different chains.
    dups_same, dups_diff = [], []
    for i, a in enumerate(ok):
        for b in ok[i + 1:]:
            if haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) <= DUP_KM:
                (dups_same if a["_store"].get("chain") == b["_store"].get("chain") else dups_diff).append((a, b))
    rep["dups_same_chain"], rep["dups_diff_chain"] = dups_same, dups_diff
    rep["accepted"] = ok
    return rep


def backup_table(session: str) -> str:
    return "stores_bak_" + re.sub(r"[^a-z0-9]+", "_", session.lower())


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def fetch_stores(conn) -> dict[int, dict]:
    from sqlalchemy import text  # noqa: PLC0415

    from db.query import live_store_clause  # noqa: PLC0415
    from scripts.geo_guard import coord_source_col, has_coord_source  # noqa: PLC0415

    live_sql, live_params = live_store_clause(conn)
    live_ids = {r[0] for r in conn.execute(text(f"SELECT s.id FROM stores s WHERE true {live_sql}"), live_params)}
    rows = conn.execute(text(f"""
        SELECT s.id, s.store_id, c.name AS chain, s.store_name, s.is_physical, s.city_canonical,
               s.lat, s.lon, s.geo_precision, s.geo_source, {coord_source_col("s", has_coord_source(conn))}
        FROM stores s LEFT JOIN chains c ON c.chain_id = s.chain_id""")).mappings()
    return {r["id"]: {**dict(r), "live": r["id"] in live_ids} for r in rows}


def print_report(rep: dict, unparseable: list) -> None:
    acc, rej = rep["accepted"], rep["rejected"]
    print(f"to be applied {len(acc)} | skipped manual {len(rep['skipped_manual'])} | rejected {len(rej)}")
    print("by source:", dict(Counter(c["source"] for c in acc)))
    print(f"coverage: A and B overlap {len(rep['overlap_a_b'])} {rep['overlap_a_b'][:20]} | "
          f"live physical stores with no row {len(rep['missing'])} {rep['missing'][:40]} | "
          f"rows that are not live physical {len(rep['extra'])} {rep['extra'][:40]}")
    for c, why in rej:
        print(f"   REJECT store_fk {c.get('store_fk')} ({c.get('origin')}): {why}")
    print("unparseable rows in the reviewed file:", len(unparseable))
    for r, why in unparseable:
        print(f"   store_fk {r.get('store_fk')} {r.get('chain')} {r.get('store')!r}: {why} | My decision: {r.get('My decision')!r}")
    print("distance new vs current point:", dict(rep["move_hist"]))
    print(f"moves >= {FAR_MOVE_KM:.0f} km: {len(rep['far_moves'])}")
    for c in sorted(rep["far_moves"], key=lambda c: -c["moved_km"]):
        s = c["_store"]
        print(f"   {c['moved_km']:6.1f} km  {c['store_fk']} {s.get('chain')} {s.get('store_id')} {s.get('store_name')!r} "
              f"{s.get('city_canonical')} [{s.get('geo_precision')}/{s.get('geo_source')}] ({c['source']})")
    print(f"farther than {FAR_CENTROID_KM:.0f} km from the city centroid: {len(rep['far_centroid'])}")
    for c in sorted(rep["far_centroid"], key=lambda c: -c["centroid_km"]):
        s = c["_store"]
        print(f"   {c['centroid_km']:6.1f} km  {c['store_fk']} {s.get('chain')} {s.get('store_name')!r} {s.get('city_canonical')} ({c['source']})")
    pr = Counter(c["precision"] for c in rep["precision_review"])
    print(f"Exact=TRUE rows whose Precision is not rooftop (for approval): {len(rep['precision_review'])} {dict(pr)}")
    for c in rep["precision_review"]:
        s = c["_store"]
        print(f"   {c['store_fk']} {s.get('chain')} {s.get('store_name')!r} {s.get('city_canonical')}: {c['precision']}")
    for name, key in (("same chain", "dups_same_chain"), ("different chains", "dups_diff_chain")):
        print(f"two stores within 10 m, {name}: {len(rep[key])}")
        for a, b in rep[key]:
            print(f"   {a['store_fk']} {a['_store'].get('chain')} {a['_store'].get('store_name')!r} <-> "
                  f"{b['store_fk']} {b['_store'].get('chain')} {b['_store'].get('store_name')!r}")
    print(f"manual pins ({len(rep['manual_pins'])}), unchanged in a dry run:")
    for c in rep["manual_pins"]:
        s = c["_store"]
        d = f"{c['moved_km'] * 1000:.0f} m" if "moved_km" in c else "-"
        print(f"   {c['store_fk']} {s.get('chain')} {s.get('store_name')!r}: current {s.get('lat'):.6f},{s.get('lon'):.6f} "
              f"| file point {c['lat']:.6f},{c['lon']:.6f} | {d}")


def run(args, conn, stores, centroids, cands, unparseable) -> dict:
    """Validate, print, and (only with --apply) write. Dry run: SELECTs already done, no writes here."""
    rep = validate(cands, stores, centroids, args.override_manual)
    print_report(rep, unparseable)
    if not args.apply:
        conn.rollback()
        print(f"\nDRY RUN - nothing written. To write: --apply --expect {len(rep['accepted'])} --session SU11A-23")
        return rep
    apply(args, conn, rep["accepted"])
    return rep


def apply(args, conn, accepted: list[dict]) -> None:
    from sqlalchemy import text  # noqa: PLC0415

    from scripts.geo_guard import has_coord_source  # noqa: PLC0415

    check_expect(len(accepted), args.expect)
    if not has_coord_source(conn):
        conn.rollback()
        raise SystemExit("ABORT: apply db/migrations/su11a23_stores_coord_source.sql first; nothing written")
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    dump = Path.home() / "backups" / f"pre-{args.session}-stores-{ts}.dump"
    dump.parent.mkdir(parents=True, exist_ok=True)
    rc = subprocess.run(["pg_dump", os.environ["DATABASE_URL"], "-t", "stores", "-Fc", "-f", str(dump)],
                        stderr=subprocess.DEVNULL).returncode          # never print the connection string
    if rc != 0 or not dump.exists() or dump.stat().st_size == 0:
        conn.rollback()
        raise SystemExit(f"ABORT: pg_dump failed (exit {rc}); nothing written")
    print(f"pg_dump -> {dump} ({dump.stat().st_size} bytes)")
    bak = backup_table(args.session)
    if conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{bak}"}).scalar():
        conn.rollback()
        raise SystemExit(f"ABORT: {bak} already exists; nothing written")
    conn.execute(text(f"CREATE TABLE {bak} AS SELECT * FROM stores"))
    n = 0
    for c in accepted:
        n += conn.execute(text("""
            UPDATE stores SET lat = :lat, lon = :lon, geo_precision = 'address', geo_source = 'google',
                   coord_source = :src, geo_label = :label, verified_at = now(), verified_by = :session
            WHERE id = :fk AND is_physical
              AND (COALESCE(geo_source, '') <> 'manual' OR :ow)
        """), {"lat": c["lat"], "lon": c["lon"], "src": c["source"], "label": c.get("label") or None,
               "session": args.session, "fk": c["store_fk"], "ow": args.override_manual}).rowcount
    if n != args.expect:
        conn.rollback()
        raise SystemExit(f"ABORT + ROLLBACK: updated {n}, expected {args.expect}")
    conn.commit()
    print(f"COMMITTED: {n} stores; backup table {bak}")


def rollback(session: str, conn) -> None:
    from sqlalchemy import text  # noqa: PLC0415

    bak = backup_table(session)
    if not conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{bak}"}).scalar():
        raise SystemExit(f"no backup table {bak}; nothing restored")
    n = conn.execute(text(f"""
        UPDATE stores s SET lat = b.lat, lon = b.lon, geo_precision = b.geo_precision,
               geo_source = b.geo_source, coord_source = b.coord_source, geo_label = b.geo_label,
               verified_at = b.verified_at, verified_by = b.verified_by
        FROM {bak} b
        WHERE s.id = b.id AND s.verified_by = :session"""), {"session": session}).rowcount
    conn.commit()
    print(f"RESTORED {n} stores from {bak}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Load Google store coordinates (dry run by default)")
    ap.add_argument("--exact", help="CSV with Exact / Lat / Lon / Precision / formatted_address")
    ap.add_argument("--reviewed", help="XLSX with the 'Review' sheet (Notes holds lat,lon)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--expect", type=int)
    ap.add_argument("--session", default="SU11A-23")
    ap.add_argument("--override-manual", action="store_true", help="also overwrite geo_source='manual' rows")
    ap.add_argument("--rollback", metavar="SESSION", help="restore the stores changed by SESSION from its backup table")
    args = ap.parse_args()
    if not SESSION_RE.match(args.rollback or args.session):
        raise SystemExit("session must look like SU11A-23")

    from db.db import connect  # noqa: PLC0415
    from scripts.geo_centroids import load_cbs_centroids  # noqa: PLC0415

    conn = connect()
    try:
        if args.rollback:
            rollback(args.rollback, conn)
            return
        if not (args.exact and args.reviewed):
            raise SystemExit("pass --exact and --reviewed")
        cands = rows_from_exact(read_exact_csv(args.exact))
        b_rows, unparseable = rows_from_reviewed(read_reviewed_xlsx(args.reviewed))
        cands += b_rows
        print(f"set A (Exact TRUE): {sum(c['origin'] == 'A' for c in cands)} | set B parsed: {len(b_rows)} "
              f"| set B unparseable: {len(unparseable)}")
        run(args, conn, fetch_stores(conn), load_cbs_centroids(), cands, unparseable)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
