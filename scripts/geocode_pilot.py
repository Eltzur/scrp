"""Geocoding pilot for the "nearby stores" feature (SU10S-9). READ-ONLY.

Writes ONE CSV to ~/geocode_pilot/<date>.csv and touches nothing else. No
schema change, no writes to any production table. The output is deliberately
outside the repo and must never be committed — it is a sample for sizing the
real job, not a dataset.

    python3 -m scripts.geocode_pilot --limit 60

WHY NOMINATIM AND NOT GOOGLE. Google's terms cap caching of geocodes at 30
days and require the result be shown on a Google map. We need coordinates
stored permanently and rendered in our own UI, so Google is disqualified on
licensing before cost enters it. Nominatim (OSM) permits storing results
under ODbL with attribution.

NOMINATIM USAGE POLICY — these are not suggestions, breaking them gets the
IP blocked and would take the production VPS with it:
  * at most 1 request/second, single-threaded, from one machine;
  * a User-Agent identifying the application and a contact address;
  * cache results and never repeat an identical query.
This script enforces all four: a hard sleep between calls, one thread, the
UA below, and an in-run cache keyed on the exact query string.

CITY CENTROIDS COME FROM CBS, NOT NOMINATIM. data/bycode2024.xlsx — the same
workbook city_canonical is built from — carries a `קואורדינטות` column: a
12-digit concatenated ITM pair (EPSG:2039), first 6 Easting, last 6 Northing.
That gives an authoritative centroid for every locality offline, so the
fallback tier costs zero requests and the wrong-city check has a trustworthy
reference. Converted in-process; pyproj is NOT required (see _itm_to_wgs84).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

from sqlalchemy import text

from db.db import connect

ROOT = Path(__file__).resolve().parent.parent
CBS_XLSX = ROOT / "data" / "bycode2024.xlsx"
OUT_DIR = Path.home() / "geocode_pilot"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
# Identifies the app and gives OSM a way to reach us, as their policy requires.
USER_AGENT = "XXL-super/1.0 (info@xxl.co.il)"
MIN_INTERVAL = 1.1          # > 1 req/s, with margin for clock jitter
TIMEOUT = 20

# Address strings that are not addresses. `unknown` is Yochananof's literal
# sentinel (24 serving stores); treat it as absent rather than geocoding a
# street called "unknown".
_JUNK_ADDRESS = {"", "unknown", "none", "null", "n/a", "-"}


# ---------------------------------------------------------------------------
# CBS city centroids (ITM -> WGS84)
# ---------------------------------------------------------------------------

def _itm_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    """EPSG:2039 (Israeli TM Grid) -> WGS84 lat/lon.

    Closed-form inverse Transverse Mercator with the official Israeli grid
    parameters. Deliberately avoids pyproj: it is a heavy new dependency for
    one conversion, and this was checked against known points (Abu Ghosh ITM
    210524/634814 -> 31.80566, 35.10941, about 10 m from its true centroid).
    """
    a = 6378137.0
    f = 1 / 298.257222101
    e2 = f * (2 - f)
    k0 = 1.0000067
    e0, n0 = 219529.584, 626907.39
    lat0 = math.radians(31 + 44 / 60 + 3.817 / 3600)
    lon0 = math.radians(35 + 12 / 60 + 16.261 / 3600)
    e = math.sqrt(e2)

    def meridional(phi: float) -> float:
        return a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64) * phi
                    - (3 * e2 / 8 + 3 * e2 ** 2 / 32) * math.sin(2 * phi)
                    + (15 * e2 ** 2 / 256) * math.sin(4 * phi))

    m = meridional(lat0) + (northing - n0) / k0
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu))
    c1 = (e2 / (1 - e2)) * math.cos(phi1) ** 2
    t1 = math.tan(phi1) ** 2
    n1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    r1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    d = (easting - e0) / (n1 * k0)
    lat = phi1 - (n1 * math.tan(phi1) / r1) * (d ** 2 / 2 - (5 + 3 * t1 + 10 * c1) * d ** 4 / 24)
    lon = lon0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6) / math.cos(phi1)
    return math.degrees(lat), math.degrees(lon)


def load_city_centroids() -> dict[str, tuple[float, float]]:
    """{city name -> (lat, lon)} from the CBS workbook. No network."""
    if not CBS_XLSX.exists():
        print(f"  WARNING: {CBS_XLSX} missing — city fallback disabled")
        return {}
    z = zipfile.ZipFile(CBS_XLSX)
    shared = re.findall(r"<t[^>]*>([^<]*)</t>",
                        z.read("xl/sharedStrings.xml").decode("utf-8", "replace"))
    sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8", "replace")

    def row_cells(chunk: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for m in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*)>(?:<v>([^<]*)</v>)?', chunk):
            col, attrs, val = m.group(1), m.group(2), m.group(3)
            if val is None:
                continue
            out[col] = shared[int(val)] if 't="s"' in attrs else val
        return out

    rows = re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.S)
    header = row_cells(rows[0])
    name_col = next((k for k, v in header.items() if v.strip() == "שם יישוב"), None)
    coord_col = next((k for k, v in header.items() if "קואורדינ" in v), None)
    if not name_col or not coord_col:
        print("  WARNING: CBS columns not found — city fallback disabled")
        return {}

    out: dict[str, tuple[float, float]] = {}
    for chunk in rows[1:]:
        cells = row_cells(chunk)
        name, raw = cells.get(name_col), cells.get(coord_col)
        if not name or not raw:
            continue
        digits = re.sub(r"\D", "", raw)
        if len(digits) != 12:
            continue
        lat, lon = _itm_to_wgs84(int(digits[:6]), int(digits[6:]))
        out[name.strip()] = (lat, lon)
    return out


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# ---------------------------------------------------------------------------
# Nominatim
# ---------------------------------------------------------------------------

class Nominatim:
    def __init__(self) -> None:
        self._last = 0.0
        self._cache: dict[str, list] = {}
        self.calls = 0

    def _get(self, params: dict) -> list:
        key = json.dumps(params, sort_keys=True, ensure_ascii=False)
        if key in self._cache:          # policy: never repeat a query
            return self._cache[key]
        wait = MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        url = NOMINATIM + "?" + urllib.parse.urlencode(
            {**params, "format": "jsonv2", "countrycodes": "il",
             "accept-language": "he", "limit": 1})
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            print(f"    ! nominatim {type(exc).__name__}: {str(exc)[:80]}")
            data = []
        finally:
            self._last = time.monotonic()
            self.calls += 1
        self._cache[key] = data
        return data

    def structured(self, street: str, city: str) -> list:
        return self._get({"street": street, "city": city})

    def freeform(self, q: str) -> list:
        return self._get({"q": q})


# ---------------------------------------------------------------------------
# Pilot
# ---------------------------------------------------------------------------

_SAMPLE_SQL = """
WITH serving AS (
    SELECT DISTINCT s.id, s.chain_id, s.store_id, s.store_name,
           s.address, s.city, s.city_canonical
    FROM stores s JOIN prices p ON p.store_fk = s.id
),
ranked AS (
    SELECT v.*, c.name AS chain_name,
           ROW_NUMBER() OVER (
               PARTITION BY v.chain_id
               -- Stores WITH a usable address first, so every chain
               -- contributes its best case before its worst.
               ORDER BY (v.address IS NOT NULL AND btrim(v.address) <> ''
                         AND lower(btrim(v.address)) <> 'unknown') DESC,
                        v.id
           ) AS rn
    FROM serving v LEFT JOIN chains c ON c.chain_id = v.chain_id
)
SELECT * FROM ranked WHERE rn <= :per_chain ORDER BY chain_name, rn
"""


def clean_address(raw: str | None) -> str | None:
    if raw is None:
        return None
    a = re.sub(r"\s+", " ", raw).strip().strip(",")
    return None if a.lower() in _JUNK_ADDRESS else a


def main() -> None:
    ap = argparse.ArgumentParser(description="Geocoding pilot (writes a CSV, nothing else)")
    ap.add_argument("--limit", type=int, default=60, help="max stores to sample")
    ap.add_argument("--per-chain", type=int, default=6, help="stores per chain")
    args = ap.parse_args()

    print("loading CBS city centroids …")
    centroids = load_city_centroids()
    print(f"  {len(centroids):,} localities with coordinates")

    conn = connect()
    rows = conn.execute(text(_SAMPLE_SQL), {"per_chain": args.per_chain}).mappings().all()
    conn.close()
    rows = list(rows)[: args.limit]
    print(f"sampling {len(rows)} stores across "
          f"{len({r['chain_id'] for r in rows})} chains")

    geo = Nominatim()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{date.today().isoformat()}.csv"

    fields = ["store_fk", "chain_name", "store_name", "raw_address", "city",
              "query_kind", "query", "lat", "lon", "osm_class", "osm_type",
              "importance", "centroid_km", "tier", "reject_reason"]

    with out_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()

        for i, r in enumerate(rows, 1):
            addr = clean_address(r["address"])
            city = (r["city_canonical"] or r["city"] or "").strip() or None
            centroid = centroids.get(city) if city else None

            rec = {f: "" for f in fields}
            rec.update(store_fk=r["id"], chain_name=r["chain_name"],
                       store_name=r["store_name"], raw_address=r["address"] or "",
                       city=city or "")

            hit, kind, query = None, "", ""
            if addr and city:
                query, kind = f"{addr} | {city}", "structured"
                res = geo.structured(addr, city)
                if res:
                    hit = res[0]
                else:
                    query, kind = f"{addr}, {city}", "freeform"
                    res = geo.freeform(query)
                    hit = res[0] if res else None

            if hit:
                lat, lon = float(hit["lat"]), float(hit["lon"])
                dist = haversine_km((lat, lon), centroid) if centroid else None
                osm_class, osm_type = hit.get("category") or hit.get("class", ""), hit.get("type", "")
                # street-level vs house-level, per what OSM says it matched
                tier = "address" if osm_type in ("house", "building") or hit.get("address", {}).get("house_number") \
                    else "street"
                rec.update(query_kind=kind, query=query, lat=f"{lat:.6f}", lon=f"{lon:.6f}",
                           osm_class=osm_class, osm_type=osm_type,
                           importance=hit.get("importance", ""),
                           centroid_km="" if dist is None else f"{dist:.2f}",
                           tier=tier)
            elif centroid:
                rec.update(query_kind="city_centroid", query=city or "",
                           lat=f"{centroid[0]:.6f}", lon=f"{centroid[1]:.6f}",
                           osm_class="cbs", osm_type="centroid",
                           centroid_km="0.00", tier="city")
            else:
                rec.update(tier="rejected",
                           reject_reason="no usable address and no city centroid")

            w.writerow(rec)
            print(f"  [{i:>3}/{len(rows)}] {str(r['chain_name'])[:12]:<14} "
                  f"{rec['tier']:<9} {rec.get('centroid_km',''):>7} km  "
                  f"{(addr or '(no addr)')[:32]}")

    print(f"\nwrote {out_path}  ({geo.calls} nominatim calls)")
    print("NOTE: this CSV is sample output. Do not commit it.")


if __name__ == "__main__":
    main()
