"""Fill store coordinates from CBS city centroids (SU10S-10). No network.

    python3 -m scripts.geo_centroids [--dry-run]

data/bycode2024.xlsx — the same workbook city_canonical is built from —
carries a `קואורדינטות` column holding a 12-digit concatenated ITM pair
(EPSG:2039): first 6 digits Easting, last 6 Northing. SU10S-9 found it unused.
That gives an authoritative centroid for every locality with no external
request at all, which is why this runs before any geocoding: it puts a usable
coordinate on every store that has a city, and street-level geocoding then
becomes an accuracy upgrade rather than a prerequisite.

MATCHING IS ON city_canonical, exact. city_canonical was itself built from
this workbook (scripts/build_city_canonical.py), so the names already agree —
re-fuzzy-matching here would be a second, independent guess that could
silently disagree with the one the rest of the app uses.

Only fills rows where lat IS NULL, so it never overwrites a Nominatim result.
"""
from __future__ import annotations

import argparse
import math
import re
import zipfile
from pathlib import Path

from sqlalchemy import text

from db.db import connect
from scripts.geo_guard import has_coord_source, protected_sql

ROOT = Path(__file__).resolve().parent.parent
CBS_XLSX = ROOT / "data" / "bycode2024.xlsx"


def itm_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    """EPSG:2039 (Israeli TM Grid) -> WGS84 lat/lon.

    Closed-form inverse Transverse Mercator with the official Israeli grid
    parameters. pyproj is deliberately NOT a dependency — it is heavy for one
    conversion, and this is checked against known points below.
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


def _self_check() -> None:
    """Verification points carried over from the SU10S-9 pilot.

    If a future edit breaks the projection maths, this fails loudly here
    rather than quietly placing 1,100 stores in the sea.
    """
    cases = [
        ("Abu Ghosh", 210524, 634814, 31.8057, 35.1094),
        ("Tel Aviv",  178000, 663000, 32.0591, 34.7647),
        ("Beer Sheva", 180000, 572000, 31.2385, 34.7896),
    ]
    for name, e, n, want_lat, want_lon in cases:
        lat, lon = itm_to_wgs84(e, n)
        assert abs(lat - want_lat) < 0.001 and abs(lon - want_lon) < 0.001, \
            f"ITM conversion drifted for {name}: got {lat:.4f},{lon:.4f}"


def load_cbs_centroids() -> dict[str, tuple[float, float]]:
    z = zipfile.ZipFile(CBS_XLSX)
    raw_ss = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
    # One shared string per <si>, NOT per <t>: a rich-text cell holds several
    # <t> runs inside one <si>, and a flat findall shifts every later index.
    shared = ["".join(re.findall(r"<t[^>]*>([^<]*)</t>", si))
              for si in re.findall(r"<si>(.*?)</si>", raw_ss, re.S)]
    sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8", "replace")

    def row_cells(chunk: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for m in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*)>(?:<v>([^<]*)</v>)?', chunk):
            col, attrs, val = m.group(1), m.group(2), m.group(3)
            if val is not None:
                out[col] = shared[int(val)] if 't="s"' in attrs else val
        return out

    rows = re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.S)
    header = row_cells(rows[0])
    name_col = next(k for k, v in header.items() if v.strip() == "שם יישוב")
    coord_col = next(k for k, v in header.items() if "קואורדינ" in v)

    out: dict[str, tuple[float, float]] = {}
    for chunk in rows[1:]:
        cells = row_cells(chunk)
        name, raw = cells.get(name_col), cells.get(coord_col)
        if not name or not raw:
            continue
        digits = re.sub(r"\D", "", raw)
        if len(digits) != 12:
            continue
        out[name.strip()] = itm_to_wgs84(int(digits[:6]), int(digits[6:]))
    return out


def target_sql(with_coord_source: bool = False) -> str:
    """Physical stores with no coordinate that the geocoders may write (SU11A-23 guard)."""
    return f"""
        SELECT id, city_canonical
        FROM stores
        WHERE is_physical AND lat IS NULL AND {protected_sql("", with_coord_source)}
        ORDER BY id
    """


def main() -> None:
    ap = argparse.ArgumentParser(description="Fill store coordinates from CBS city centroids")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    _self_check()
    centroids = load_cbs_centroids()
    print(f"CBS localities with coordinates: {len(centroids):,}")

    conn = connect()
    # Never a manual or Google-loaded row (scripts/geo_guard.py, SU11A-23); lat IS NULL already
    # excludes them today - this is the explicit guard should one ever lose its coordinate.
    targets = conn.execute(text(target_sql(has_coord_source(conn)))).mappings().all()
    print(f"physical stores without coordinates: {len(targets):,}")

    filled = 0
    no_city = 0
    unmatched: dict[str, int] = {}

    for r in targets:
        city = (r["city_canonical"] or "").strip()
        if not city:
            no_city += 1
            continue
        hit = centroids.get(city)
        if hit is None:
            unmatched[city] = unmatched.get(city, 0) + 1
            continue
        if not args.dry_run:
            conn.execute(text("""
                UPDATE stores
                SET lat = :lat, lon = :lon,
                    geo_precision = 'city', geo_source = 'cbs_centroid',
                    geo_input = :city, geocoded_at = now()
                WHERE id = :id AND lat IS NULL AND COALESCE(geo_source, '') NOT IN ('manual', 'google')
            """), {"lat": hit[0], "lon": hit[1], "city": city, "id": r["id"]})
        filled += 1

    if not args.dry_run:
        conn.commit()

    print()
    print(f"  filled with a city centroid : {filled:,}")
    print(f"  no city_canonical at all    : {no_city:,}")
    print(f"  city not found in CBS        : {sum(unmatched.values()):,} "
          f"across {len(unmatched)} distinct names")
    for name, n in sorted(unmatched.items(), key=lambda x: -x[1])[:15]:
        print(f"      {n:>4}x  {name}")
    if args.dry_run:
        print("\n  DRY RUN — nothing written")
    conn.close()


if __name__ == "__main__":
    main()
