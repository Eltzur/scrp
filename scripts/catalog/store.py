"""Catalog category storage rules (SU11A-52): precedence and the SQL that enforces it.

Tables: db/migrations/su11a52_catalog.sql (categories, item_categories,
item_attributes). Writers: scripts/catalog/import_categories.py and the
new-barcode hook in scripts/build_search_items.py.

PRECEDENCE (documented in CLAUDE.md and docs/catalog/su11a52_runbook.md):

    manual > ai > gs1 > rule

  - An automated run (rule / gs1 / ai) NEVER overwrites a manual row and never
    downgrades a row to a lower source: it may replace a row of the same or a
    lower source only.
  - A row with reviewed = true is never touched automatically, whatever its source.
  - Manual rows come only from an explicit human file (import --manual); they may
    replace any row and are stored with reviewed = true.

The same rule is checked twice: in Python (may_write, used for the dry-run
counts) and in the upsert's ON CONFLICT ... WHERE (the database decides on
apply, so a row changed between the dry run and the apply is still protected).
"""
from __future__ import annotations

SOURCES = ("rule", "gs1", "ai", "manual")
SOURCE_RANK = {s: i for i, s in enumerate(SOURCES)}
CONFIDENCES = ("high", "medium", "low")
AUTOMATED = frozenset(("rule", "gs1", "ai"))


def may_write(existing: dict | None, new_source: str) -> bool:
    """Whether a write from new_source may replace the existing item_categories row.

    existing: None (no row) or a mapping with at least source and reviewed.
    """
    if new_source not in SOURCE_RANK:
        raise ValueError(f"unknown source {new_source!r}")
    if existing is None:
        return True
    if new_source == "manual":
        return True
    if existing.get("reviewed") or existing.get("source") == "manual":
        return False
    return SOURCE_RANK[existing.get("source") or "rule"] <= SOURCE_RANK[new_source]


def _rank_sql(col: str) -> str:
    return (f"(CASE {col} WHEN 'manual' THEN 3 WHEN 'ai' THEN 2 WHEN 'gs1' THEN 1 "
            f"WHEN 'rule' THEN 0 ELSE -1 END)")


# The guard for automated writes, as a WHERE on the conflicting row (ic = the
# stored row, EXCLUDED = the new one).
AUTOMATED_GUARD_SQL = (f"NOT ic.reviewed AND ic.source <> 'manual' "
                       f"AND {_rank_sql('ic.source')} <= {_rank_sql('EXCLUDED.source')}")

ITEM_CATEGORY_COLS = ["item_code", "category_id", "confidence", "source", "detail", "model",
                      "taxonomy_version", "reviewed"]


def upsert_item_categories_sql(manual: bool = False) -> str:
    """INSERT ... ON CONFLICT for item_categories rows (one statement per batch).

    Automated: the conflicting row is updated only when AUTOMATED_GUARD_SQL holds;
    otherwise the row is left as it is (no error). Manual: always updated.
    A row whose values would not change is not rewritten (decided_at stays).
    """
    cols = ", ".join(ITEM_CATEGORY_COLS)
    vals = ", ".join(f":{c}" for c in ITEM_CATEGORY_COLS)
    changed = ("(ic.category_id, ic.confidence, ic.source, ic.detail, ic.model, ic.taxonomy_version, ic.reviewed) "
               "IS DISTINCT FROM (EXCLUDED.category_id, EXCLUDED.confidence, EXCLUDED.source, EXCLUDED.detail, "
               "EXCLUDED.model, EXCLUDED.taxonomy_version, EXCLUDED.reviewed)")
    guard = changed if manual else f"{AUTOMATED_GUARD_SQL} AND {changed}"
    return f"""
INSERT INTO item_categories AS ic ({cols}, decided_at)
VALUES ({vals}, now())
ON CONFLICT (item_code) DO UPDATE SET
    category_id = EXCLUDED.category_id, confidence = EXCLUDED.confidence, source = EXCLUDED.source,
    detail = EXCLUDED.detail, model = EXCLUDED.model, taxonomy_version = EXCLUDED.taxonomy_version,
    reviewed = EXCLUDED.reviewed, decided_at = now()
WHERE {guard}
"""


# New barcodes only (build hook): never touches an existing row.
INSERT_NEW_ITEM_CATEGORIES_SQL = f"""
INSERT INTO item_categories ({", ".join(ITEM_CATEGORY_COLS)}, decided_at)
VALUES ({", ".join(f":{c}" for c in ITEM_CATEGORY_COLS)}, now())
ON CONFLICT (item_code) DO NOTHING
"""

ITEM_ATTRIBUTE_COLS = ["item_code", "attr_key", "value_text", "value_num", "unit", "source"]


def upsert_item_attributes_sql() -> str:
    """item_attributes upsert. Same precedence by source; attributes have no
    reviewed flag, so only manual rows are protected from automated writes."""
    cols = ", ".join(ITEM_ATTRIBUTE_COLS)
    vals = ", ".join(f":{c}" for c in ITEM_ATTRIBUTE_COLS)
    return f"""
INSERT INTO item_attributes AS ia ({cols})
VALUES ({vals})
ON CONFLICT (item_code, attr_key) DO UPDATE SET
    value_text = EXCLUDED.value_text, value_num = EXCLUDED.value_num, unit = EXCLUDED.unit,
    source = EXCLUDED.source
WHERE ia.source <> 'manual' AND {_rank_sql('ia.source')} <= {_rank_sql('EXCLUDED.source')}
  AND (ia.value_text, ia.value_num, ia.unit, ia.source)
      IS DISTINCT FROM (EXCLUDED.value_text, EXCLUDED.value_num, EXCLUDED.unit, EXCLUDED.source)
"""


def attribute_rows(item_code: str, attrs: dict, source: str) -> list[dict]:
    """extract_attributes() output -> item_attributes rows.

    Numbers go to value_num (size_value with its size_unit as unit), booleans
    to value_text 'true', text as is. size_unit is folded into size_value's row.
    """
    out = []
    unit = attrs.get("size_unit")
    for k, v in attrs.items():
        if k == "size_unit":
            continue
        row = {"item_code": item_code, "attr_key": k, "value_text": None, "value_num": None,
               "unit": None, "source": source}
        if isinstance(v, bool):
            row["value_text"] = "true" if v else "false"
        elif isinstance(v, (int, float)):
            row["value_num"] = v
            if k == "size_value":
                row["unit"] = unit
            elif k.endswith("_pct"):
                row["unit"] = "%"
        else:
            row["value_text"] = str(v)[:200]
        out.append(row)
    return out
