"""Manual pin campaign: export the work queue and shop-point candidates (SU11A-19). READ-ONLY.

    python3 -m scripts.export_pin_queue [--out ~/pin_tool_data] [--fetch]
                                        [--osm-shops FILE.json] [--overture FILE.json]

Writes into --out (created with mode 700):
  queue.csv        one row per LIVE PHYSICAL store whose geo_source is not 'manual'
  candidates.json  same-chain shop points per store (OpenStreetMap + Overture), with a
                   suggested candidate where exactly one point matches street + number

--fetch makes ONE download of Geofabrik's israel-and-palestine .osm.pbf (deleted after
extraction) and ONE Overture places query (DuckDB over the public parquet). It needs the
`osmium` and `duckdb` packages, which are NOT project dependencies - install them into a
throwaway directory and put it on PYTHONPATH:

    pip install --target /tmp/pinlib osmium duckdb
    PYTHONPATH=/tmp/pinlib python3 -m scripts.export_pin_queue --fetch

The extracted points are also written to --out (osm_shops.json, overture.json), so a later
run can pass them with --osm-shops / --overture instead of fetching again.

LICENCES. OpenStreetMap data (c) OpenStreetMap contributors, ODbL. Overture places: CDLA
Permissive 2.0 (Foursquare Apache 2.0, AllThePlaces CC0). No Google data is read or written.

Tiers: unplaced (geo_precision city / no coordinate), street, house_unconfirmed (house level
without a same-chain shop point within 150 m), house_confirmed (house level with one).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import text

from db.db import connect
from db.query import live_store_clause
from scripts.geo_centroids import load_cbs_centroids
from scripts.geo_clean import clean_address
import scripts.geo_nominatim as G

PBF_URL = "https://download.geofabrik.de/asia/israel-and-palestine-latest.osm.pbf"
OVERTURE_RELEASE = "2026-09-23.1"
OVERTURE_SRC = f"s3://overturemaps-us-west-2/release/{OVERTURE_RELEASE}/theme=places/type=place/*"
BBOX = (29.45, 34.2, 33.35, 35.95)          # lat_min, lon_min, lat_max, lon_max
CITY_RADIUS_KM = 6.0
CONFIRM_KM = 0.15
SHARED_PIN_KM = 0.03

# Chain mapping (SU11A-18). Order matters: BE and the contested "מגה" are matched first so
# they never fall into a chain. BE is Shufersal's pharmacy/beauty brand - never a grocery
# store (CLAUDE.md). "מגה" is listed under Shufersal in one brief and under Carrefour in
# scraper/carrefour.py, so it stays unmapped until decided.
PATTERNS = [
    (None, r"(^|[^a-z])be([^a-z]|$)|^בי |שופרסל be"),
    (None, r"(^|[^א-ת])מגה([^א-ת]|$)|(^|[^a-z])mega([^a-z]|$)"),
    ("7290027600007", r"שופרסל|shufersal|יש ?חסד|yesh ?hesed|יוניברס|universe|גוד ?מרקט|good ?market"),
    ("7290058140886", r"רמי ?לוי|rami ?lev[iy]"),
    ("7290696200003", r"ויקטורי|victory"),
    ("7290803800003", r"יוחננוף|yo?c?hananof"),
    ("7290055700007", r"קרפור|carrefour|יינות ?ביתן|yeinot ?bitan|yenot ?bitan"),
    ("7290873255550", r"טיב ?טעם|tiv ?taam"),
    ("7290876100000", r"פרש ?מרקט|fresh ?market"),
    ("7290058108879", r"קינג ?סטור|king ?store"),
    ("7290058134977", r"שפע ?ברכת|shefa ?birkat"),
    ("7290058148776", r"שוק ?העיר|shuk ?ha.?ir"),
    ("7290103152017", r"אושר ?עד|osher ?ad"),
    ("7290785400000", r"קשת ?טעמים|keshet ?teamim"),
    ("7290700100008", r"חצי ?חינם|ha?tzi ?hinam|hazi ?hinam"),
    ("7290058177776", r"סופר ?יודה|super ?yuda"),
]
SHUFERSAL_EXACT = {"דיל", "שלי", "אקספרס", "יש", "יש חסד", "יוניברס", "deal", "sheli", "express", "yesh"}

QUEUE_COLUMNS = ["store_fk", "chain_id", "chain", "store_id", "store_name", "city_canonical",
                 "address", "lat", "lon", "geo_precision", "geo_source", "tier", "flags",
                 "centroid_lat", "centroid_lon", "n_candidates", "suggested"]


def chain_of(texts) -> str | None:
    hay = " | ".join(t for t in texts if t).lower()
    for chain_id, pattern in PATTERNS:
        if re.search(pattern, hay):
            return chain_id            # None for BE / contested
    if {t.strip().lower() for t in texts if t} & SHUFERSAL_EXACT:
        return "7290027600007"
    return None


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
def fetch_osm(out: Path) -> list[dict]:
    """ONE download, streaming two-pass extraction (no node-location index), file deleted."""
    import osmium  # noqa: PLC0415 - optional dependency, only for --fetch

    pbf = out / "israel.osm.pbf"
    r = subprocess.run(["curl", "-sSL", "--connect-timeout", "30", "--max-time", "900",
                        "-o", str(pbf), "-w", "%{url_effective} %{size_download}", PBF_URL],
                       capture_output=True, text=True)
    if r.returncode != 0 or not pbf.exists():
        sys.exit(f"Geofabrik download failed (curl exit {r.returncode})")
    print(f"osm: downloaded {r.stdout.strip()} bytes")
    keep = ("name", "name:he", "name:en", "brand", "brand:he", "brand:en", "operator", "shop")
    shops = {"supermarket", "convenience"}

    class Pass1(osmium.SimpleHandler):
        def __init__(self):
            super().__init__(); self.nodes, self.ways, self.need = [], [], set()

        def node(self, n):
            if n.tags.get("shop") in shops and n.location.valid():
                self.nodes.append({"id": f"node/{n.id}", "lat": n.location.lat, "lon": n.location.lon,
                                   "tags": {k: v for k, v in n.tags if k in keep or k.startswith("addr:")}})

        def way(self, w):
            if w.tags.get("shop") in shops:
                refs = [x.ref for x in w.nodes]
                self.ways.append({"id": f"way/{w.id}", "refs": refs,
                                  "tags": {k: v for k, v in w.tags if k in keep or k.startswith("addr:")}})
                self.need.update(refs)

    class Pass2(osmium.SimpleHandler):
        def __init__(self, need):
            super().__init__(); self.need, self.loc = need, {}

        def node(self, n):
            if n.id in self.need and n.location.valid():
                self.loc[n.id] = (n.location.lat, n.location.lon)

    try:
        stamp = osmium.io.Reader(str(pbf), osmium.osm.osm_entity_bits.NOTHING).header().get(
            "osmosis_replication_timestamp")
        p1 = Pass1(); p1.apply_file(str(pbf))
        p2 = Pass2(p1.need); p2.apply_file(str(pbf))
    finally:
        pbf.unlink(missing_ok=True)
    pts = list(p1.nodes)
    for w in p1.ways:
        locs = [p2.loc[x] for x in w["refs"] if x in p2.loc]
        if locs:
            pts.append({"id": w["id"], "lat": sum(a for a, _ in locs) / len(locs),
                        "lon": sum(b for _, b in locs) / len(locs), "tags": w["tags"]})
    print(f"osm: data timestamp {stamp}; {len(pts)} supermarket/convenience points; pbf deleted")
    return pts


def fetch_overture(out: Path) -> list[dict]:
    """ONE read-only DuckDB query, memory-capped for the 3.8 GiB server."""
    import duckdb  # noqa: PLC0415 - optional dependency, only for --fetch

    tmp = out / "duck"
    tmp.mkdir(exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET extension_directory='{tmp}'; SET temp_directory='{tmp}'")
    con.execute("SET memory_limit='300MB'; SET threads=1")
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2'")
    lat0, lon0, lat1, lon1 = BBOX
    rows = con.execute(f"""
        SELECT id, names.primary AS name, brand.names.primary AS brand, taxonomy.primary AS cat,
               addresses[1].freeform AS street, addresses[1].locality AS locality, operating_status,
               (bbox.xmin + bbox.xmax) / 2 AS lon, (bbox.ymin + bbox.ymax) / 2 AS lat
        FROM read_parquet('{OVERTURE_SRC}', hive_partitioning = 1)
        WHERE bbox.xmin BETWEEN {lon0} AND {lon1} AND bbox.ymin BETWEEN {lat0} AND {lat1}
          AND (regexp_matches(coalesce(taxonomy.primary, ''), 'supermarket|grocery|convenience')
               OR regexp_matches(coalesce(basic_category, ''), 'supermarket|grocery|convenience'))
    """).fetchall()
    cols = [d[0] for d in con.description]
    con.close()
    subprocess.run(["rm", "-rf", str(tmp)])
    pts = [dict(zip(cols, r)) for r in rows]
    print(f"overture: release {OVERTURE_RELEASE}; {len(pts)} places")
    return pts


def normalise_points(osm: list[dict], ov: list[dict]) -> list[dict]:
    out = []
    for o in osm:
        t = o["tags"]
        texts = [t.get(k) for k in ("name", "name:he", "name:en", "brand", "brand:he", "brand:en", "operator")]
        out.append({"source": "osm", "id": o["id"], "lat": round(o["lat"], 7), "lon": round(o["lon"], 7),
                    "name": t.get("name") or t.get("name:he") or t.get("name:en"),
                    "brand": t.get("brand"), "chain_id": chain_of(texts),
                    "street": t.get("addr:street"), "housenumber": t.get("addr:housenumber"),
                    "city": t.get("addr:city"),
                    "addr": {k: v for k, v in t.items() if k.startswith("addr:")}})
    for o in ov:
        if o.get("operating_status") == "permanently_closed":
            continue
        st, num, letter = (G.parse_address(clean_address(o["street"])) if o.get("street")
                           else (None, None, None))
        out.append({"source": "overture", "id": o["id"], "lat": round(o["lat"], 7), "lon": round(o["lon"], 7),
                    "name": o.get("name"), "brand": o.get("brand"),
                    "chain_id": chain_of([o.get("name"), o.get("brand")]),
                    "street": st, "housenumber": f"{num}{letter or ''}" if num is not None else None,
                    "city": o.get("locality"),
                    "addr": {"freeform": o.get("street"), "locality": o.get("locality")}})
    return out


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------
_STORES_SQL = """
    SELECT s.id, s.chain_id, c.name AS chain, s.store_id, s.store_name,
           COALESCE(NULLIF(btrim(s.address_override), ''), s.address) AS address,
           s.city_canonical, s.lat, s.lon, s.geo_precision, s.geo_source
    FROM stores s LEFT JOIN chains c ON c.chain_id = s.chain_id
    WHERE s.is_physical {live}
    ORDER BY s.city_canonical NULLS LAST, c.name, s.store_id
"""


def ambiguous_pin_ids(rows, centroids, cities) -> set[int]:
    """SU11A-18 step 7, replayed from the geocoder cache only (no network): an address-level
    pin whose query has two ADDRESS candidates in the same city more than 500 m apart."""
    try:
        cache = json.loads(Path(G.CACHE_PATH).read_text(encoding="utf-8"))
    except Exception:
        return set()
    out = set()
    for r in rows:
        if r["geo_precision"] != "address" or r["geo_source"] != "nominatim":
            continue
        city = r["city_canonical"]
        q = clean_address(r["address"], [city])
        raw = G.build_geo_input(r["address"], city)[0]
        hits = None
        for qq in (q, raw):
            for p in ({"street": qq, "city": city}, {"q": f"{qq}, {city}"}):
                if cache.get(G.cache_key(p)):
                    hits = cache[G.cache_key(p)]; break
            if hits:
                break
        st, num, letter = G.parse_address(q)
        pts = []
        for h in hits or []:
            a = h.get("address") or {}
            roads = [a.get(k) for k in ("road", "pedestrian", "footway", "square", "place") if a.get(k)]
            if st and any(G.streets_match(st, x) for x in roads) and G.house_matches(num, letter, a.get("house_number")):
                rc = [a[k] for k in G._CITY_KEYS if a.get(k)]
                if not rc or any(cities.same(c, city) for c in rc):
                    pts.append((float(h["lat"]), float(h["lon"])))
        if any(G.haversine_km(*a, *b) > 0.5 for i, a in enumerate(pts) for b in pts[i + 1:]):
            out.add(r["id"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Export the manual-pin queue and candidates (read-only)")
    ap.add_argument("--out", default=str(Path.home() / "pin_tool_data"))
    ap.add_argument("--fetch", action="store_true", help="ONE Geofabrik download + ONE Overture query")
    ap.add_argument("--osm-shops", help="reuse an osm_shops.json written by an earlier --fetch")
    ap.add_argument("--overture", help="reuse an overture.json written by an earlier --fetch")
    args = ap.parse_args()

    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)

    if args.fetch:
        osm_raw, ov_raw = fetch_osm(out), fetch_overture(out)
        for name, data in (("osm_shops.json", osm_raw), ("overture.json", ov_raw)):
            (out / name).write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
            os.chmod(out / name, 0o600)
    else:
        if not (args.osm_shops and args.overture):
            sys.exit("pass --fetch, or both --osm-shops and --overture")
        osm_raw = json.loads(Path(args.osm_shops).read_text(encoding="utf-8"))
        ov_raw = json.loads(Path(args.overture).read_text(encoding="utf-8"))

    centroids = load_cbs_centroids()
    cities = G.CityResolver(list(centroids))
    points = [p for p in normalise_points(osm_raw, ov_raw) if p["chain_id"]]
    for p in points:
        c = cities.canonical(p["city"]) if p["city"] else None
        p["city_canonical"] = c if c in centroids else None

    conn = connect()
    try:
        live_sql, live_params = live_store_clause(conn)
        rows = [dict(r) for r in conn.execute(text(_STORES_SQL.format(live=live_sql)), live_params).mappings()]
    finally:
        conn.rollback()
        conn.close()

    ambiguous = ambiguous_pin_ids(rows, centroids, cities)
    firm = [r for r in rows if r["lat"] is not None and r["geo_precision"] in ("address", "street")]
    shared = set()
    for i, a in enumerate(firm):
        for b in firm[i + 1:]:
            if a["chain_id"] == b["chain_id"] and G.haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) <= SHARED_PIN_KM:
                shared |= {a["id"], b["id"]}

    by_chain = defaultdict(list)
    for p in points:
        by_chain[p["chain_id"]].append(p)

    queue, cand_out, used = [], {}, {}
    for r in rows:
        if r["geo_source"] == "manual":
            continue
        city = r["city_canonical"]
        cen = centroids.get(city) if city else None
        cands = []
        for p in by_chain.get(r["chain_id"], []):
            if city and p["city_canonical"] and cities.same(p["city_canonical"], city):
                cands.append(p)
            elif cen and G.haversine_km(p["lat"], p["lon"], *cen) <= CITY_RADIUS_KM:
                cands.append(p)
        addr = (r["address"] or "").strip()
        st, num, letter = G.parse_address(clean_address(addr, [city or ""])) if addr else (None, None, None)
        strong = [p for p in cands if st and num is not None and p["street"] and p["housenumber"]
                  and G.streets_match(st, p["street"]) and G.house_matches(num, letter, p["housenumber"])]
        suggested = strong[0]["id"] if len(strong) == 1 else None

        if r["lat"] is None or r["geo_precision"] == "city":
            tier = "unplaced"
        elif r["geo_precision"] == "street":
            tier = "street"
        else:
            near = any(G.haversine_km(p["lat"], p["lon"], r["lat"], r["lon"]) <= CONFIRM_KM for p in cands)
            tier = "house_confirmed" if near and r["id"] not in ambiguous else "house_unconfirmed"
        flags = []
        if r["id"] in ambiguous:
            flags.append("ambiguous_pin")
        if r["id"] in shared:
            flags.append("shares_pin_30m")
        if not addr or addr.lower() in G._JUNK:
            flags.append("no_address")
        elif not re.search(r"\d", addr):
            flags.append("no_house_number")

        queue.append({
            "store_fk": r["id"], "chain_id": r["chain_id"], "chain": r["chain"], "store_id": r["store_id"],
            "store_name": r["store_name"], "city_canonical": city, "address": addr,
            "lat": r["lat"], "lon": r["lon"], "geo_precision": r["geo_precision"] or "",
            "geo_source": r["geo_source"] or "", "tier": tier, "flags": ";".join(flags),
            "centroid_lat": round(cen[0], 6) if cen else None, "centroid_lon": round(cen[1], 6) if cen else None,
            "n_candidates": len(cands), "suggested": suggested or "",
        })
        cand_out[str(r["id"])] = {"candidates": [p["id"] for p in cands], "suggested": suggested}
        for p in cands:
            used[p["id"]] = {k: p[k] for k in ("source", "id", "name", "brand", "chain_id", "lat", "lon", "addr")}

    with open(out / "queue.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=QUEUE_COLUMNS)
        w.writeheader()
        w.writerows(queue)
    (out / "candidates.json").write_text(json.dumps({
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "licence": "OpenStreetMap: (c) OpenStreetMap contributors, ODbL. Overture places: CDLA Permissive 2.0 "
                   "(Foursquare Apache 2.0, AllThePlaces CC0).",
        "points": used, "stores": cand_out}, ensure_ascii=False), encoding="utf-8")
    for name in ("queue.csv", "candidates.json"):
        os.chmod(out / name, 0o600)

    print(f"\nqueue: {len(queue)} stores (live physical, not manual) -> {out / 'queue.csv'}")
    print("by tier:", dict(Counter(q["tier"] for q in queue)))
    per = defaultdict(Counter)
    for q in queue:
        per[q["chain"]][q["tier"]] += 1
    for ch, c in sorted(per.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"  {ch}: {dict(c)}")
    nc = Counter(min(q["n_candidates"], 2) for q in queue)
    print(f"candidates per store: 0 -> {nc[0]}, 1 -> {nc[1]}, 2+ -> {nc[2]} | suggested (strong) {sum(1 for q in queue if q['suggested'])}")
    print("flags:", dict(Counter(f for q in queue for f in q["flags"].split(";") if f)))
    print(f"points kept (same chain, in some store's city): {len(used)} "
          f"({dict(Counter(p['source'] for p in used.values()))})")


if __name__ == "__main__":
    main()
