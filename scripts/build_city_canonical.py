"""Build city_canonical values from Israel CBS settlement list (9d-8).

Reads data/bycode2024.xlsx, matches each store's city against CBS names
using a 4-layer strategy, and writes data/city_canonical_review.csv for
human review. Does NOT write to DB.

Layers:
  L1 — exact match of normalized city/city_norm against CBS name
  L2 — STORE_CITY_OVERRIDES (per-store) or CITY_CANONICAL_OVERRIDES (per-city)
  L3 — difflib best match >= 0.85 against all CBS names
  NULL — no match found
"""
import csv
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import openpyxl
from sqlalchemy import text

from db.db import get_engine
from scraper.city_names import CITY_CANONICAL_OVERRIDES, STORE_CITY_OVERRIDES

XLSX_PATH = ROOT / "data" / "bycode2024.xlsx"
OUT_CSV = ROOT / "data" / "city_canonical_review.csv"
FUZZY_THRESHOLD = 0.85


def _norm(s) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s).strip())


def load_cbs(xlsx_path: Path) -> dict[str, str]:
    """Return {norm(name): canonical_name} from CBS settlement list."""
    wb = openpyxl.load_workbook(str(xlsx_path), read_only=True, data_only=True)
    ws = wb.active
    col_idx = None
    result = {}

    for row in ws.iter_rows(values_only=True):
        if col_idx is None:
            for i, cell in enumerate(row):
                if _norm(cell) == "שם יישוב":
                    col_idx = i
                    break
            continue
        if col_idx is None or col_idx >= len(row):
            continue
        val = row[col_idx]
        if val:
            canonical = _norm(val)
            if canonical:
                result[canonical] = canonical

    wb.close()
    return result


def best_fuzzy(city: str, cbs_names: list[str]) -> tuple[str | None, float]:
    best_name, best_ratio = None, 0.0
    for name in cbs_names:
        r = SequenceMatcher(None, city, name).ratio()
        if r > best_ratio:
            best_ratio = r
            best_name = name
    if best_ratio >= FUZZY_THRESHOLD:
        return best_name, best_ratio
    return None, best_ratio


def main() -> None:
    if not XLSX_PATH.exists():
        print(f"ERROR: {XLSX_PATH} not found. Place bycode2024.xlsx in data/ first.")
        sys.exit(1)

    print("Loading CBS settlement list...")
    cbs = load_cbs(XLSX_PATH)
    cbs_names = list(cbs.values())
    print(f"  {len(cbs)} CBS settlements loaded.")

    with get_engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT id, chain_id, store_id, store_name, city, city_norm FROM stores"
        )).fetchall()

    print(f"  {len(rows)} stores to process.")

    counts = {"L1": 0, "L2": 0, "L3": 0, "NULL": 0}
    out_rows = []

    for store_pk, chain_id, store_id, store_name, city, city_norm in rows:
        proposed = None
        layer = None
        confidence = None

        # Layer 1: exact match on city or city_norm
        for raw in (city, city_norm):
            n = _norm(raw)
            if n and n in cbs:
                proposed = cbs[n]
                layer = "L1"
                confidence = 1.0
                break

        # Layer 2: STORE_CITY_OVERRIDES or CITY_CANONICAL_OVERRIDES
        if proposed is None:
            # 2a: per-store override → re-try Layer 1 against CBS
            override = STORE_CITY_OVERRIDES.get(
                (str(chain_id), str(store_id).zfill(3))
            )
            if override:
                n = _norm(override)
                if n in cbs:
                    proposed = cbs[n]
                    layer = "L2"
                    confidence = 1.0

            # 2b: city-level canonical override (raw city string match)
            if proposed is None:
                for raw in (city, city_norm):
                    n = _norm(raw)
                    if n and n in CITY_CANONICAL_OVERRIDES:
                        proposed = CITY_CANONICAL_OVERRIDES[n]
                        layer = "L2"
                        confidence = 1.0
                        break

        # Layer 3: fuzzy match on city/city_norm
        if proposed is None:
            candidates = [_norm(v) for v in (city, city_norm) if v]
            for candidate in candidates:
                match, ratio = best_fuzzy(candidate, cbs_names)
                if match:
                    proposed = match
                    layer = "L3"
                    confidence = round(ratio, 3)
                    break

        # Layer 4: NULL
        if proposed is None:
            layer = "NULL"
            confidence = 0.0

        counts[layer] += 1
        out_rows.append({
            "store_id": store_pk,
            "store_name": store_name or "",
            "city": city or "",
            "city_norm": city_norm or "",
            "proposed_canonical": proposed or "",
            "match_layer": layer,
            "confidence": confidence,
        })

    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "store_id", "store_name", "city", "city_norm",
            "proposed_canonical", "match_layer", "confidence",
        ])
        writer.writeheader()
        writer.writerows(out_rows)

    total = len(rows)
    print(f"\nSummary ({total} stores):")
    print(f"  L1 (exact match):    {counts['L1']:>4}")
    print(f"  L2 (override+exact): {counts['L2']:>4}")
    print(f"  L3 (fuzzy >=0.85):   {counts['L3']:>4}")
    print(f"  NULL (no match):     {counts['NULL']:>4}")
    print(f"\nReview CSV written: {OUT_CSV}")


if __name__ == "__main__":
    main()
