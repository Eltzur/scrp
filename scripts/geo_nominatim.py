"""Upgrade store coordinates from city centroid to street/house level (SU10S-10).

    python3 -m scripts.geo_nominatim [--limit N] [--dry-run]
                                     [--ids-file F] [--report X.xlsx] [--include-overrides]

Runs AFTER scripts/geo_centroids.py. Every target already has a city-centroid
coordinate, so this can only improve a row — and a rejected result simply
leaves the coordinate in place.

NOMINATIM USAGE POLICY — not suggestions. Breaking them gets the IP blocked,
which would take the production VPS with it:
  * <= 1 request/second, single-threaded, one machine;
  * a User-Agent naming the app with a contact address;
  * cache results; never repeat an identical query.
All four are enforced here. The cache is ON DISK, so a re-run after a crash
costs zero requests for anything already asked.

ACCEPTANCE RULES (SU10S-25) judge a result by WHETHER IT MATCHES THE INPUT
ADDRESS, not by its OSM place type. SU10S-10 rejected amenity/* and flagged
shop/* outright, which threw away exact hits: Osher Ad 011 (id 849) came back
as "Supermarket Osher Ad, 11, HaKishon, Bnei Brak" with addr:street=הקישון,
addr:housenumber=11 — the right building. A dentist at the input's street and
number is in the same building as the store, so the type says nothing.

We ask for up to QUERY_PARAMS["limit"] candidates with addressdetails and
test each one:

    ADDRESS_MATCH   road == input street (normalize_street) AND house_number
                    == input number AND returned city == city_canonical AND
                    <= MAX_CENTROID_KM from the CBS centroid  -> 'address'
    STREET_MATCH    road matches, the candidate has NO house number (a street
                    centreline), same city and distance checks  -> 'street'
    CITY_MISMATCH   road (and maybe number) match, but Nominatim puts it in a
                    different city than city_canonical. Never accepted — this
                    is how a wrong city_canonical surfaces.
    >25km           matched, same city name, but too far from the centroid.
    NO_MATCH        nothing matched the input street.

Street precision REQUIRES a road match: SU10S-10's "any place/* -> street"
leniency (a neighbourhood hit counted as a street) is gone.

Among several ADDRESS_MATCH candidates, prefer a shop whose name/brand
contains the chain name, then a building/house, then anything else.

THE ADDRESS IT GEOCODES (SU10S-18) is the EFFECTIVE address,
    COALESCE(NULLIF(btrim(address_override), ''), address)
`address` is owned by the nightly store upsert and is overwritten from the
feed (or blanked to '' by binaprojects) every night; a hand correction lives
in `address_override`, which no scraper writes.

WHEN A ROW IS RE-GEOCODED. Anything below house level is retried every run
(the on-disk cache makes that free). A house-level ('address') row is retried
only when the input changed: its stored geo_input differs from the input this
run would build - i.e. an override was set, or the feed address moved.
--include-overrides additionally forces every house-level row that carries an
address_override, input changed or not; without it they are left alone.

geo_source = 'manual' ROWS ARE NEVER RE-GEOCODED (SU10S-25), by any path:
the coordinate was placed by hand, so no Nominatim answer outranks it.

WHY 25 KM AND NOT SOMETHING TIGHTER. The pilot measured legitimate results
3-6 km from their city centroid — Jerusalem's Talpiot and Givat Shaul, Tel
Aviv's northern edge — because big municipalities are simply large. A 5 km
cap would reject real stores. This is a COARSE guard measured from the CBS
city centroid (scripts/geo_centroids.py), not from the store's current pin,
which for a re-geocoded house-level row is its old, possibly wrong, location.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import text

from db.db import connect
from scraper.city_names import CITY_CANONICAL_OVERRIDES, normalize_city
from scripts.geo_centroids import load_cbs_centroids

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "XXL-super/1.0 (info@xxl.co.il)"
MIN_INTERVAL = 1.1
TIMEOUT = 20
MAX_CENTROID_KM = 25.0

# Part of every query AND of its cache key: SU10S-10 entries (limit=1, no
# addressdetails) have different keys and are never reused for this rule.
QUERY_PARAMS = {"limit": 5, "addressdetails": 1, "namedetails": 1, "extratags": 1}

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


def cache_key(params: dict) -> str:
    return json.dumps({**params, **QUERY_PARAMS}, sort_keys=True, ensure_ascii=False)


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
        key = cache_key(params)
        if key in self._cache:
            return self._cache[key]
        wait = MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        url = NOMINATIM + "?" + urllib.parse.urlencode(
            {**params, **QUERY_PARAMS, "format": "jsonv2", "countrycodes": "il",
             "accept-language": "he"})
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            print(f"    ! {type(exc).__name__}: {str(exc)[:80]}")
            # Not cached: a network failure is not an answer.
            self._last = time.monotonic()
            self.calls += 1
            return []
        self._last = time.monotonic()
        self.calls += 1
        self._cache[key] = data
        if self.calls % 25 == 0:
            self.save()
        return data


def classify(hit: dict) -> tuple[str | None, str]:
    """SU10S-10 type-based rule. Superseded by evaluate(); kept only because
    scripts/export_branch_review.py still replays it."""
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


# ---------------------------------------------------------------------------
# Matching (SU10S-25)
# ---------------------------------------------------------------------------

_QUOTES = re.compile(r"[\"'`׳״’‘”“]")
_PUNCT = re.compile(r"[-־–—.,:;()/\\]")
_STREET_PREFIX = re.compile(
    r"^(?:רחוב|רח|שדרות|שדרת|שד|דרך|סמטת|סמ|"
    r"rehov|rechov|sderot|derech|street|st|road|rd|avenue|ave|blvd)\s+")
_STREET_SUFFIX = re.compile(r"\s+(?:street|st|road|rd|avenue|ave|blvd)$")


def _fold(s: str) -> str:
    """Spelling-insensitive key: no spaces, יי->י, וו->ו."""
    return s.replace(" ", "").replace("יי", "י").replace("וו", "ו")


def normalize_street(s: str | None) -> str:
    """Drop רחוב/רח'/שד'/שדרות/דרך (and English St/Rd/Ave), quotes, punctuation."""
    if not s:
        return ""
    s = _QUOTES.sub("", s.lower())
    s = re.sub(r"\s+", " ", _PUNCT.sub(" ", s)).strip()
    prev = None
    while prev != s:
        prev = s
        s = _STREET_PREFIX.sub("", s)
        s = _STREET_SUFFIX.sub("", s)
    return s.strip()


def streets_match(a: str | None, b: str | None) -> bool:
    ka, kb = _fold(normalize_street(a)), _fold(normalize_street(b))
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    # הקישון / קישון, HaKishon / Kishon: the definite article is optional.
    strip = lambda k: k[1:] if k.startswith("ה") and len(k) > 2 else (k[2:] if k.startswith("ha") and len(k) > 3 else k)
    return strip(ka) == strip(kb)


_NUM = re.compile(r"(?<![\d])(\d{1,4})(?:\s*-\s*(\d{1,4}))?\s*([א-ת](?![א-ת])|[a-z](?![a-z]))?", re.I)


def parse_address(addr: str) -> tuple[str | None, int | None, str | None]:
    """(street, house_number, letter) from e.g. "רח' הקישון 11א, קומה 2".

    Takes the first comma-separated part that has both a number and a
    street name; the LAST number in it is the house number ("שד' 26 באוקטובר
    3" is rare, "הרצל 12" is the norm).
    """
    for part in addr.split(","):
        nums = list(_NUM.finditer(part))
        if not nums:
            continue
        m = nums[-1]
        # "הקישון 11 בני ברק": the street is what comes BEFORE the number;
        # only a number-first address ("11 הקישון") takes the text after it.
        street = part[:m.start()].strip() or part[m.end():].strip()
        if re.search(r"[A-Za-zא-ת]{2,}", street):
            return street, int(m.group(1)), (m.group(3) or "").lower() or None
    return None, None, None


def house_matches(num: int | None, letter: str | None, hn: str | None) -> bool:
    """Input number equals the candidate's; a range "7-9" covers 7..9. A
    letter only has to agree when BOTH sides carry one."""
    if num is None or not hn:
        return False
    m = _NUM.search(hn.strip())
    if not m:
        return False
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    if not lo <= num <= hi:
        return False
    cand_letter = (m.group(3) or "").lower() or None
    return not (letter and cand_letter and letter != cand_letter)


_CITY_KEYS = ("city", "town", "village", "municipality", "hamlet")


class CityResolver:
    """Returned city -> canonical name, the way city_canonical was built
    (scripts/build_city_canonical.py): exact CBS name, then the canonical and
    variant override tables, then a >= 0.85 fuzzy match on CBS names."""

    def __init__(self, cbs_names: list[str]) -> None:
        self._cbs = {re.sub(r"\s+", " ", n.strip()): n for n in cbs_names}
        self._names = list(self._cbs.values())
        self._memo: dict[str, str] = {}

    def canonical(self, raw: str) -> str:
        # Nominatim writes "תל־אביב–יפו": a maqaf and an en dash, not "-".
        n = re.sub(r"\s*[-־–—]\s*", "-", re.sub(r"\s+", " ", raw.strip()))
        if n in self._memo:
            return self._memo[n]
        out = self._cbs.get(n) or CITY_CANONICAL_OVERRIDES.get(n)
        if out is None:
            v = normalize_city(n)
            out = self._cbs.get(v) or CITY_CANONICAL_OVERRIDES.get(v)
        if out is None:
            best = max(self._names, key=lambda c: SequenceMatcher(None, n, c).ratio(), default=None)
            out = best if best and SequenceMatcher(None, n, best).ratio() >= 0.85 else n
        self._memo[n] = out
        return out

    def same(self, returned: str, city_canonical: str) -> bool:
        k = lambda s: _fold(_PUNCT.sub("", _QUOTES.sub("", s)))
        return (k(returned) == k(city_canonical)
                or k(self.canonical(returned)) == k(self.canonical(city_canonical)))


def _chain_in(hit: dict, chain: str | None) -> bool:
    if not chain:
        return False
    key = _fold(_QUOTES.sub("", chain.lower()))
    names = list((hit.get("namedetails") or {}).values()) + [hit.get("name") or ""]
    tags = hit.get("extratags") or {}
    names += [v for k, v in tags.items() if k.startswith(("brand", "operator"))]
    return any(key and key in _fold(_QUOTES.sub("", str(n).lower())) for n in names)


def _pref(hit: dict, chain: str | None) -> int:
    cls = (hit.get("category") or hit.get("class") or "").lower()
    typ = (hit.get("type") or "").lower()
    if cls == "shop" and _chain_in(hit, chain):
        return 0
    if cls == "building" or (cls == "place" and typ == "house"):
        return 1
    return 2


def evaluate(hits: list, addr: str, city_canonical: str, centroid, chain: str | None,
             cities: CityResolver) -> dict:
    """The store's outcome over all candidates.

    Keys: precision ('address'/'street'/None), reason, hit (the candidate
    shown), dist_km, road, house_number, city.
    """
    street, num, letter = parse_address(addr)
    ranked = {"ADDRESS_MATCH": [], "STREET_MATCH": [], "CITY_MISMATCH": [], ">25km": []}
    for h in hits:
        a = h.get("address") or {}
        cls = (h.get("category") or h.get("class") or "").lower()
        roads = [a.get(k) for k in ("road", "pedestrian", "footway", "square", "place") if a.get(k)]
        if cls == "highway":
            roads += [h.get("name")] + list((h.get("namedetails") or {}).values())
        if not street or not any(streets_match(street, r) for r in roads):
            continue
        if house_matches(num, letter, a.get("house_number")):
            kind = "ADDRESS_MATCH"
        elif not a.get("house_number"):
            kind = "STREET_MATCH"
        else:
            continue            # same street, a different house: not evidence
        ret_cities = [a[k] for k in _CITY_KEYS if a.get(k)]
        dist = (haversine_km(float(h["lat"]), float(h["lon"]), *centroid)
                if centroid else None)
        if ret_cities and not any(cities.same(c, city_canonical) for c in ret_cities):
            ranked["CITY_MISMATCH"].append((h, dist))
        elif dist is not None and dist > MAX_CENTROID_KM:
            ranked[">25km"].append((h, dist))
        else:
            ranked[kind].append((h, dist))

    ranked["ADDRESS_MATCH"].sort(key=lambda hd: _pref(hd[0], chain))   # stable: Nominatim order next
    for reason, precision in (("ADDRESS_MATCH", "address"), ("STREET_MATCH", "street"),
                              ("CITY_MISMATCH", None), (">25km", None)):
        if ranked[reason]:
            h, dist = ranked[reason][0]
            break
    else:
        reason, precision = "NO_MATCH", None
        h = hits[0] if hits else None
        dist = (haversine_km(float(h["lat"]), float(h["lon"]), *centroid)
                if h and centroid else None)
    a = (h or {}).get("address") or {}
    road = a.get("road") or a.get("pedestrian")
    if not road and h and (h.get("category") or h.get("class")) == "highway":
        road = h.get("name")
    return {
        "precision": precision, "reason": reason, "hit": h, "dist_km": dist,
        "road": road,
        "house_number": a.get("house_number"),
        "city": next((a[k] for k in _CITY_KEYS if a.get(k)), None),
    }


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

# The effective address (see module doc). Also the only expression the
# address filters below may test, or override-only stores would be skipped.
EFFECTIVE_ADDRESS_SQL = "COALESCE(NULLIF(btrim(address_override), ''), address)"

_ROW_COLS = f"""
    s.id, s.chain_id, c.name AS chain, s.store_id, s.store_name,
    COALESCE(NULLIF(btrim(s.address_override), ''), s.address) AS address,
    NULLIF(btrim(s.address_override), '') IS NOT NULL AS has_override,
    s.city_canonical, s.lat, s.lon, s.geo_precision, s.geo_input, s.geo_source
"""

_GEOCODABLE = f"""
      {EFFECTIVE_ADDRESS_SQL} IS NOT NULL AND btrim({EFFECTIVE_ADDRESS_SQL}) <> ''
      AND lower(btrim({EFFECTIVE_ADDRESS_SQL})) NOT IN ('unknown','none','null','n/a','-')
      AND {EFFECTIVE_ADDRESS_SQL} ~ '[0-9]'
      AND city_canonical IS NOT NULL AND btrim(city_canonical) <> ''
"""

_TARGETS_SQL = f"""
    SELECT {_ROW_COLS}
    FROM stores s LEFT JOIN chains c ON c.chain_id = s.chain_id
    WHERE s.is_physical AND s.id IN (
        SELECT id FROM stores WHERE {_GEOCODABLE})
      AND s.geo_source IS DISTINCT FROM 'manual'
    ORDER BY s.id
"""

_BY_IDS_SQL = f"""
    SELECT {_ROW_COLS}, s.id IN (SELECT id FROM stores WHERE {_GEOCODABLE}) AS geocodable
    FROM stores s LEFT JOIN chains c ON c.chain_id = s.chain_id
    WHERE s.id = ANY(:ids)
    ORDER BY s.id
"""


def build_geo_input(address: str, city_canonical: str) -> tuple[str, str, str]:
    """(addr, city, geo_input) exactly as geocoded and as stored in geo_input.

    The single definition: the query sent to Nominatim, the value written to
    stores.geo_input, and the "did the input change?" test all come from here,
    so they cannot drift apart.
    """
    addr = re.sub(r"\s+", " ", address).strip().strip(",")
    city = city_canonical.strip()
    return addr, city, f"{addr} | {city}"


def needs_geocode(r, include_overrides: bool = False) -> bool:
    """Below house level, or the input changed, or (flag) an overridden
    house-level row. Never a hand-placed (geo_source='manual') row."""
    if r["geo_source"] == "manual":
        return False
    if r["geo_precision"] != "address":
        return True
    if r["geo_input"] != build_geo_input(r["address"], r["city_canonical"])[2]:
        return True
    return include_overrides and r["has_override"]


def select_targets(conn, include_overrides: bool = False) -> list:
    """Rows to geocode this run."""
    return [r for r in conn.execute(text(_TARGETS_SQL)).mappings().all()
            if needs_geocode(r, include_overrides)]


# ---------------------------------------------------------------------------
# Report (dry run)
# ---------------------------------------------------------------------------

REPORT_COLUMNS = ["stores.id", "chain", "store_id", "input address", "city_canonical",
                  "old precision", "new precision", "reason", "matched display_name",
                  "returned road", "returned house_number", "returned city",
                  "lat", "lon", "km from centroid", "sheet"]


def write_report(path: str, rows: list[list]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "dry-run SU10S-25"
    ws.sheet_view.rightToLeft = True
    ws.append(REPORT_COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(row)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    widths = [8, 13, 9, 32, 15, 11, 11, 15, 60, 22, 10, 15, 11, 11, 10, 10]
    for idx, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = w
    wb.save(path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Upgrade store coordinates via Nominatim")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ids-file", help="only these stores.id (one per line, optional "
                                       "second tab-separated column = sheet label)")
    ap.add_argument("--report", help="write a per-store xlsx (RTL) of the outcome")
    ap.add_argument("--include-overrides", action="store_true",
                    help="also re-geocode house-level rows that carry an address_override")
    args = ap.parse_args(argv)

    centroids = load_cbs_centroids()
    cities = CityResolver(list(centroids))

    conn = connect()
    labels: dict[int, str] = {}
    if args.ids_file:
        for line in Path(args.ids_file).read_text(encoding="utf-8").splitlines():
            if line.strip():
                sid, _, label = line.partition("\t")
                labels[int(sid)] = label.strip()
        rows = conn.execute(text(_BY_IDS_SQL), {"ids": list(labels)}).mappings().all()
    else:
        rows = select_targets(conn, args.include_overrides)
    if args.limit:
        rows = rows[: args.limit]
    print(f"targets: {len(rows)} stores\n")

    geo = Nominatim()
    stats: dict[str, int] = {}
    report: list[list] = []

    for i, r in enumerate(rows, 1):
        old = r["geo_precision"]
        base = [r["id"], r["chain"], r["store_id"], r["address"], r["city_canonical"], old]
        label = labels.get(r["id"], "")

        if args.ids_file and not r["geocodable"]:
            reason = "NOT_GEOCODABLE"
        elif args.ids_file and not needs_geocode(r, args.include_overrides):
            reason = ("SKIPPED_MANUAL" if r["geo_source"] == "manual"
                      else "SKIPPED_OVERRIDE" if r["has_override"] else "ALREADY_ADDRESS")
        else:
            reason = None
        if reason:
            stats[reason] = stats.get(reason, 0) + 1
            report.append(base + [old, reason] + [None] * 7 + [label])
            continue

        addr, city, geo_input = build_geo_input(r["address"], r["city_canonical"])
        hits = geo._get({"street": addr, "city": city})
        if not hits:
            hits = geo._get({"q": f"{addr}, {city}"})
        centroid = centroids.get(city)
        if centroid is None and r["lat"] is not None:
            centroid = (r["lat"], r["lon"])      # no CBS entry: fall back to the stored pin
        res = evaluate(hits, addr, city, centroid, r["chain"], cities)
        stats[res["reason"]] = stats.get(res["reason"], 0) + 1

        h = res["hit"]
        new = res["precision"] or old
        report.append(base + [
            new, res["reason"], (h or {}).get("display_name"), res["road"],
            res["house_number"], res["city"],
            float(h["lat"]) if h else None, float(h["lon"]) if h else None,
            round(res["dist_km"], 2) if res["dist_km"] is not None else None, label])

        if res["precision"] and not args.dry_run:
            conn.execute(text("""
                UPDATE stores
                SET lat = :lat, lon = :lon, geo_precision = :p,
                    geo_source = 'nominatim', geo_input = :gi, geocoded_at = now()
                WHERE id = :id
            """), {"lat": float(h["lat"]), "lon": float(h["lon"]),
                   "p": res["precision"], "gi": geo_input, "id": r["id"]})

        if i % 25 == 0 or i == len(rows):
            if not args.dry_run:
                conn.commit()
            print(f"  [{i}/{len(rows)}] {stats}  ({geo.calls} calls)")

    if not args.dry_run:
        conn.commit()
    else:
        conn.rollback()
    geo.save()
    conn.close()

    if args.report:
        write_report(args.report, report)
        print(f"\nreport: {args.report}")

    print("\n=== done" + (" (DRY RUN — no DB writes)" if args.dry_run else "") + " ===")
    for k, v in sorted(stats.items()):
        print(f"  {k:<18}{v:>5}")
    print(f"  nominatim calls: {geo.calls}")


if __name__ == "__main__":
    main()
