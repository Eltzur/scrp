"""Upgrade store coordinates from city centroid to street/house level (SU10S-10).

    python3 -m scripts.geo_nominatim [--limit N] [--dry-run]

Runs AFTER scripts/geo_centroids.py. Every target already has a city-centroid
coordinate, so this can only improve a row — and a rejected result simply
leaves the centroid in place. It NEVER downgrades an existing precision.

NOMINATIM USAGE POLICY — not suggestions. Breaking them gets the IP blocked,
which would take the production VPS with it:
  * <= 1 request/second, single-threaded, one machine;
  * a User-Agent naming the app with a contact address;
  * cache results; never repeat an identical query.
All four are enforced here. The cache is ON DISK, so a re-run after a crash
costs zero requests for anything already asked.

ACCEPTANCE RULES, taken from the SU10S-9 pilot rather than invented:

    highway/*          -> 'street'   (street centreline — the common good case)
    place/house,
    building/*         -> 'address'  (house-level)
    amenity/*          -> REJECT     Nominatim matched a BUSINESS whose name
                                     resembles the street. The pilot's two
                                     amenity hits were a dentist and a
                                     pharmacy, and one was its worst outlier.
    shop/*             -> KEEP CENTROID, log for review. Might genuinely be
                                     the supermarket, might be a different
                                     shop on that street; not worth guessing.

    > MAX_CENTROID_KM from the city centroid -> REJECT.

WHY 25 KM AND NOT SOMETHING TIGHTER. The pilot measured legitimate results
3-6 km from their city centroid — Jerusalem's Talpiot and Givat Shaul, Tel
Aviv's northern edge — because big municipalities are simply large. A 5 km
cap would reject real stores. This is a COARSE WRONG-CITY GUARD, not an
accuracy filter: it catches "same street name, different city", which lands
tens of km away. Precision comes from the class rules above.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from sqlalchemy import text

from db.db import connect

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "XXL-super/1.0 (info@xxl.co.il)"
MIN_INTERVAL = 1.1
TIMEOUT = 20
MAX_CENTROID_KM = 25.0

CACHE_PATH = Path.home() / ".cache" / "xxl_geocode" / "nominatim.json"

# Yochananof publishes the literal string "unknown" as an address for 24 of
# its stores. Geocoding a street called "unknown" is worse than admitting we
# have no address.
_JUNK = {"", "unknown", "none", "null", "n/a", "-"}


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class Nominatim:
    def __init__(self) -> None:
        self._last = 0.0
        self.calls = 0
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            self._cache = {}
        print(f"cache: {len(self._cache)} entries at {CACHE_PATH}")

    def save(self) -> None:
        CACHE_PATH.write_text(json.dumps(self._cache, ensure_ascii=False), encoding="utf-8")

    def _get(self, params: dict) -> list:
        key = json.dumps(params, sort_keys=True, ensure_ascii=False)
        if key in self._cache:
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
            print(f"    ! {type(exc).__name__}: {str(exc)[:80]}")
            data = []
        finally:
            self._last = time.monotonic()
            self.calls += 1
        self._cache[key] = data
        if self.calls % 25 == 0:
            self.save()
        return data


def classify(hit: dict) -> tuple[str | None, str]:
    """(precision, reason). precision None means reject / keep centroid."""
    cls = (hit.get("category") or hit.get("class") or "").lower()
    typ = (hit.get("type") or "").lower()
    if cls == "amenity":
        return None, f"amenity/{typ} — POI name collision, not an address"
    if cls == "shop":
        return None, f"shop/{typ} — possibly the store itself, flagged for review"
    if cls == "building" or typ in ("house", "residential") and cls == "place":
        return "address", f"{cls}/{typ}"
    if cls == "place" and typ == "house":
        return "address", f"{cls}/{typ}"
    if cls == "highway":
        return "street", f"{cls}/{typ}"
    if cls == "place":
        return "street", f"{cls}/{typ}"
    return None, f"{cls}/{typ} — unrecognised class"


_TARGETS_SQL = """
    SELECT id, chain_id, store_name, address, city_canonical, lat, lon, geo_precision
    FROM stores
    WHERE is_physical
      AND address IS NOT NULL AND btrim(address) <> ''
      AND lower(btrim(address)) NOT IN ('unknown','none','null','n/a','-')
      AND address ~ '[0-9]'
      AND city_canonical IS NOT NULL AND btrim(city_canonical) <> ''
      AND (geo_precision IS DISTINCT FROM 'address')
    ORDER BY id
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Upgrade store coordinates via Nominatim")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = connect()
    rows = conn.execute(text(_TARGETS_SQL)).mappings().all()
    if args.limit:
        rows = rows[: args.limit]
    print(f"targets: {len(rows)} stores with a real address\n")

    geo = Nominatim()
    stats = {"address": 0, "street": 0, "rejected": 0, "no_hit": 0, "too_far": 0, "shop": 0}
    flagged: list[str] = []

    for i, r in enumerate(rows, 1):
        addr = re.sub(r"\s+", " ", r["address"]).strip().strip(",")
        city = r["city_canonical"].strip()
        geo_input = f"{addr} | {city}"

        hits = geo._get({"street": addr, "city": city})
        if not hits:
            hits = geo._get({"q": f"{addr}, {city}"})
        if not hits:
            stats["no_hit"] += 1
            continue

        hit = hits[0]
        precision, reason = classify(hit)
        lat, lon = float(hit["lat"]), float(hit["lon"])
        dist = haversine_km(lat, lon, r["lat"], r["lon"]) if r["lat"] is not None else 0.0

        if precision is None:
            stats["shop" if reason.startswith("shop") else "rejected"] += 1
            if reason.startswith("shop"):
                flagged.append(f"    id={r['id']} {reason}  {geo_input}")
            continue
        if dist > MAX_CENTROID_KM:
            stats["too_far"] += 1
            print(f"  [{i}/{len(rows)}] id={r['id']} REJECT {dist:.1f} km from centroid — {geo_input}")
            continue

        if not args.dry_run:
            conn.execute(text("""
                UPDATE stores
                SET lat = :lat, lon = :lon, geo_precision = :p,
                    geo_source = 'nominatim', geo_input = :gi, geocoded_at = now()
                WHERE id = :id
            """), {"lat": lat, "lon": lon, "p": precision, "gi": geo_input, "id": r["id"]})
        stats[precision] += 1

        if i % 25 == 0 or i == len(rows):
            if not args.dry_run:
                conn.commit()
            print(f"  [{i}/{len(rows)}] {stats}  ({geo.calls} calls)")

    if not args.dry_run:
        conn.commit()
    geo.save()
    conn.close()

    print("\n=== done ===")
    for k, v in stats.items():
        print(f"  {k:<10}{v:>5}")
    print(f"  nominatim calls: {geo.calls}")
    if flagged:
        print(f"\n  shop/* flagged for review ({len(flagged)}) — centroid kept:")
        for line in flagged:
            print(line)


if __name__ == "__main__":
    main()
