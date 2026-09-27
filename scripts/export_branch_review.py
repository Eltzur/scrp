"""Branch review export for manual correction (SU10S-18). READ-ONLY.

    python3 -m scripts.export_branch_review [--out ~/branch_review.xlsx]

Population: stores that are SERVING (hold prices), LIVE (db/query.py
live_store_clause - loaded within 3 days of their chain's latest load) and
PHYSICAL. One row per store; a store can carry several issues:

    NO_CITY            city_canonical NULL
    NO_ADDRESS         effective address NULL / empty
    PLACEHOLDER        effective address is a placeholder ("unknown", "לא ידוע", "-" ...)
    NO_HOUSE_NUMBER    effective address has no digit
    GEOCODE_REJECTED   Nominatim answered, geocoder refused it (amenity/*, other
                       unrecognised class, or > 25 km from the city centroid)
    GEOCODE_FLAGGED    Nominatim answered shop/* - centroid kept, logged for review
    GEOCODE_NO_MATCH   Nominatim returned nothing for the address (not in the brief;
                       same "check this address" signal, so surfaced too)
    MAYBE_ONLINE       name/address suggests online / delivery / fulfilment

"Effective address" = COALESCE(NULLIF(btrim(address_override), ''), address),
the same expression scripts/geo_nominatim.py geocodes.

GEOCODE_* ARE REPLAYED, NOT STORED: the geocoder persists only accepted
results. Every answer it ever got is in its on-disk cache, and its accept rules
(classify(), MAX_CENTROID_KM) are deterministic, so this replays them against
the cache. It NEVER calls Nominatim - an uncached query is reported as
"not geocoded yet" instead.

Sheets: "לבדיקה" (manual list) and "Shufersal-bulk". Shufersal publishes no
address for any branch; those rows wait for StoresFull ingestion rather than
hand entry, so Shufersal NO_ADDRESS lives only on the bulk sheet. A Shufersal
branch with some OTHER issue still appears on the manual list for that issue.

The four trailing columns are for the reviewer; the apply session reads them:
    correct_city     -> scraper/city_names.py STORE_CITY_OVERRIDES (durable)
    correct_address  -> stores.address_override
    is_physical=no   -> stores.is_physical = false
then a targeted re-geocode.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import text

from db.db import connect
from db.query import live_store_clause
from scripts.geo_nominatim import (
    CACHE_PATH,
    EFFECTIVE_ADDRESS_SQL,
    MAX_CENTROID_KM,
    build_geo_input,
    classify,
    haversine_km,
)

SHUFERSAL = "7290027600007"
BULK_LABEL = "BULK — awaiting StoresFull ingestion"

ISSUE_ORDER = ["NO_CITY", "NO_ADDRESS", "PLACEHOLDER", "NO_HOUSE_NUMBER",
               "GEOCODE_REJECTED", "GEOCODE_FLAGGED", "GEOCODE_NO_MATCH", "MAYBE_ONLINE"]

_PLACEHOLDERS = {"unknown", "none", "null", "n/a", "na", "-", "--", "---", ".", "0",
                 "לא ידוע", "לא ידועה", "אין", "אין כתובת", "לא קיים", "כללי", "?"}

_ONLINE_RE = re.compile(
    r"אונליין|online|אינטרנט|internet|משלוח|delivery|פיק\s*-?\s*אפ|pick\s*-?\s*up|"
    r"מחסן|לוגיסטי|מרלו\"?ג|fulfil|e-?commerce|דיגיטל|digital|וירטואל|virtual|"
    r"הזמנות|סיטונאות|wholesale",
    re.IGNORECASE,
)

COLUMNS = ["stores.id", "chain", "store_id", "store_name", "city_canonical", "raw city",
           "address", "geo_precision", "issues", "issue_detail",
           "correct_address", "correct_city", "is_physical", "notes"]
REVIEWER_COLS = {"correct_address", "correct_city", "is_physical", "notes"}

_POP_SQL = """
    SELECT s.id, s.chain_id, c.name AS chain, s.store_id, s.store_name,
           s.city_canonical, s.city, {eff} AS address, s.geo_precision,
           s.lat, s.lon
    FROM stores s
    LEFT JOIN chains c ON c.chain_id = s.chain_id
    WHERE s.is_physical
      AND EXISTS (SELECT 1 FROM prices p WHERE p.store_fk = s.id)
      {live}
    ORDER BY c.name, s.store_id
"""


def load_cache() -> dict:
    try:
        return json.loads(Path(CACHE_PATH).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cache_get(cache: dict, params: dict):
    """Exactly the geocoder's cache key; None = never asked."""
    return cache.get(json.dumps(params, sort_keys=True, ensure_ascii=False))


def replay_geocode(r: dict, cache: dict) -> tuple[str | None, str]:
    """(issue or None, detail) for a row the geocoder would target."""
    addr, city, geo_input = build_geo_input(r["address"], r["city_canonical"])
    hits = _cache_get(cache, {"street": addr, "city": city})
    if hits is None:
        return None, "not geocoded yet (next scrp-geocode run)"
    if not hits:
        hits = _cache_get(cache, {"q": f"{addr}, {city}"})
        if hits is None:
            return None, "not geocoded yet (next scrp-geocode run)"
    if not hits:
        return "GEOCODE_NO_MATCH", f"no Nominatim result for '{geo_input}'"
    hit = hits[0]
    precision, reason = classify(hit)
    if precision is None:
        return ("GEOCODE_FLAGGED" if reason.startswith("shop") else "GEOCODE_REJECTED"), reason
    if r["lat"] is not None:
        dist = haversine_km(float(hit["lat"]), float(hit["lon"]), r["lat"], r["lon"])
        if dist > MAX_CENTROID_KM:
            return "GEOCODE_REJECTED", f"{dist:.1f} km from city centroid (> {MAX_CENTROID_KM:.0f})"
    return None, ""


def geocodable(address: str | None, city: str | None) -> bool:
    """Mirror of geo_nominatim._TARGETS_SQL's address/city filters."""
    a = (address or "").strip()
    return (bool(a) and a.lower() not in {"unknown", "none", "null", "n/a", "-"}
            and bool(re.search(r"[0-9]", a)) and bool((city or "").strip()))


def issues_for(r: dict, cache: dict) -> tuple[list[str], list[str]]:
    issues, detail = [], []
    addr = (r["address"] or "").strip()
    if not r["city_canonical"]:
        issues.append("NO_CITY")
    if not addr:
        issues.append("NO_ADDRESS")
    elif addr.lower() in _PLACEHOLDERS:
        issues.append("PLACEHOLDER")
        detail.append(f"address = '{addr}'")
    elif not re.search(r"[0-9]", addr):
        issues.append("NO_HOUSE_NUMBER")
        if addr in {(r["city"] or "").strip(), (r["city_canonical"] or "").strip()}:
            detail.append("address is just the city name")
    if geocodable(r["address"], r["city_canonical"]):
        g, why = replay_geocode(r, cache)
        if g:
            issues.append(g)
        if why:
            detail.append(why)
    blob = f"{r['store_name'] or ''} {addr}"
    m = _ONLINE_RE.search(blob)
    if m:
        issues.append("MAYBE_ONLINE")
        detail.append(f"matched '{m.group(0)}'")
    return issues, detail


def to_row(r: dict, issues: list[str], detail: list[str]) -> list:
    # The last four are the reviewer's columns and must start empty.
    return [r["id"], r["chain"], r["store_id"], r["store_name"], r["city_canonical"],
            r["city"], r["address"], r["geo_precision"], ", ".join(issues),
            "; ".join(detail), None, None, None, None]


def write_sheet(ws, rows: list[list]) -> None:
    ws.sheet_view.rightToLeft = True
    ws.append(COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(row)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    widths = {"stores.id": 8, "chain": 13, "store_id": 9, "store_name": 30, "city_canonical": 15,
              "raw city": 15, "address": 32, "geo_precision": 11, "issues": 30, "issue_detail": 45,
              "correct_address": 30, "correct_city": 16, "is_physical": 11, "notes": 30}
    fill = PatternFill("solid", fgColor="FFF6D5")
    for idx, name in enumerate(COLUMNS, 1):
        letter = ws.cell(row=1, column=idx).column_letter
        ws.column_dimensions[letter].width = widths[name]
        if name in REVIEWER_COLS:
            for (cell,) in ws.iter_rows(min_row=1, max_row=max(ws.max_row, 2), min_col=idx, max_col=idx):
                cell.fill = fill
    dv = DataValidation(type="list", formula1='"yes,no"', allow_blank=True)
    ws.add_data_validation(dv)
    col = ws.cell(row=1, column=COLUMNS.index("is_physical") + 1).column_letter
    dv.add(f"{col}2:{col}{max(ws.max_row, 2)}")
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=False)


def main() -> None:
    ap = argparse.ArgumentParser(description="Export the branch review workbook (read-only).")
    ap.add_argument("--out", default=str(Path.home() / "branch_review.xlsx"))
    args = ap.parse_args()

    conn = connect()
    try:
        live_sql, live_params = live_store_clause(conn)
        rows = conn.execute(text(_POP_SQL.format(eff=EFFECTIVE_ADDRESS_SQL, live=live_sql)),
                            live_params).mappings().all()
    finally:
        conn.rollback()
        conn.close()

    cache = load_cache()
    manual, bulk = [], []
    cat = Counter()
    per_chain = Counter()
    manual_by_chain_issue = Counter()
    for r in rows:
        issues, detail = issues_for(r, cache)
        for i in issues:
            cat[i] += 1
        if r["chain_id"] == SHUFERSAL and "NO_ADDRESS" in issues:
            bulk.append(to_row(r, ["NO_ADDRESS"], []))
            issues = [i for i in issues if i != "NO_ADDRESS"]
        if issues:
            issues.sort(key=ISSUE_ORDER.index)
            manual.append((r["chain"] or "", ISSUE_ORDER.index(issues[0]), r["store_id"],
                           to_row(r, issues, detail)))
            per_chain[r["chain"]] += 1
            for i in issues:
                manual_by_chain_issue[(r["chain"], i)] += 1

    manual.sort(key=lambda t: t[:3])
    wb = Workbook()
    ws = wb.active
    ws.title = "לבדיקה"
    write_sheet(ws, [t[3] for t in manual])
    ws2 = wb.create_sheet("Shufersal-bulk")
    for row in bulk:
        row[COLUMNS.index("issue_detail")] = BULK_LABEL
    write_sheet(ws2, bulk)
    wb.save(args.out)

    print(f"population (serving + live + physical): {len(rows)}")
    print(f"manual list rows: {len(manual)}   shufersal bulk rows: {len(bulk)}")
    print("stores per issue (whole population, before the bulk split):")
    for i in ISSUE_ORDER:
        print(f"  {i:18} {cat[i]}")
    print("manual list rows per chain:")
    for ch, n in sorted(per_chain.items(), key=lambda kv: -kv[1]):
        parts = ", ".join(f"{i} {manual_by_chain_issue[(ch, i)]}" for i in ISSUE_ORDER
                          if manual_by_chain_issue[(ch, i)])
        print(f"  {ch:14} {n:4}   ({parts})")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
