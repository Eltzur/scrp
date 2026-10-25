"""Load the taxonomy (v1.2 since SU11A-56) and the labels into the su11a52 tables (SU11A-52). Runs on the server.

    venv/bin/python3 -m scripts.catalog.import_categories            # dry run (default)
    venv/bin/python3 -m scripts.catalog.import_categories --apply
    venv/bin/python3 -m scripts.catalog.import_categories --manual REVIEWED.csv [--apply]

What it writes (with --apply, ONE transaction; nothing without it):
  categories       every node of docs/catalog/taxonomy_v1_2.csv (insert or update);
                   ids that are in the table but not in the CSV get active = false
                   (never deleted: ids are not reused)
  item_categories  one row per live, non-pseudo search_items barcode that has a
                   label: the v1.2 rules + GS1 group map computed here from
                   search_items.name_norm and gs1.products, combined with the AI
                   labels in docs/catalog/ai_labels_v1.csv by
                   scripts/catalog/combine.combine_label (the same rule as the
                   local report)
  item_attributes  attributes parsed from the name (+ GS1 brand, items.is_weighted),
                   kept to those the item's category offers
  --manual FILE    rows with a filled correct_category_id (the review CSVs) become
                   source = manual, reviewed = true; they replace any row

PRECEDENCE (scripts/catalog/store.py): manual > ai > gs1 > rule. Automated rows
never overwrite a manual row, never replace a row of a higher source, and never
touch reviewed = true; the upsert's ON CONFLICT ... WHERE enforces it in the
database, the dry run counts it in Python with the same rule.

Read-only by default: the dry run opens a READ ONLY transaction and prints, per
table, how many rows would be inserted / updated / left unchanged / protected,
and the planned rows per source and confidence. Refuses to run (dry or apply)
when the su11a52 migration is missing. statement_timeout 10 min per statement;
writes go in chunks of 2,000 rows.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.catalog.classify_rules as C  # noqa: E402
from scripts.catalog.combine import combine_label  # noqa: E402
from scripts.catalog.store import (ITEM_ATTRIBUTE_COLS, ITEM_CATEGORY_COLS, attribute_rows, manual_row,  # noqa: E402
                                   may_write, upsert_item_attributes_sql, upsert_item_categories_sql)

AI_LABELS = ROOT / "docs" / "catalog" / "ai_labels_v1.csv"
TABLES = ("categories", "item_categories", "item_attributes")
CHUNK = 2000
LEVELS = {"department": 1, "category": 2, "subtype": 3}

ITEMS_SQL = """
SELECT s.item_code, s.name_norm, i.is_weighted
FROM search_items s
LEFT JOIN items i ON i.item_code = s.item_code
WHERE NOT s.is_pseudo
"""
GS1_SQL = """
SELECT DISTINCT ON (gtin) gtin, group_name, brandname
FROM gs1.products
WHERE product_status = 'פעיל' AND gtin = ANY(:codes)
ORDER BY gtin, (full_content IS NOT NULL) DESC, modification_timestamp DESC NULLS LAST, id DESC
"""


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- pure
def category_rows(tax: C.Taxonomy, version: str = C.TAXONOMY_VERSION) -> list[dict]:
    """categories rows in CSV order (parents before children); attributes inherited."""
    return [{"id": n.id, "parent_id": n.parent or None, "level": LEVELS[n.level], "name_he": n.name_he,
             "name_en": n.name_en, "sort_order": k, "attributes": tax.attrs_for(n.id), "active": True,
             "taxonomy_version": version}
            for k, n in enumerate(tax.nodes.values(), start=1)]


def plan_labels(items: list[dict], gs1: dict[str, tuple[str, str]], ai: dict[str, dict], tax: C.Taxonomy,
                gmap: dict, hints: dict) -> tuple[list[dict], list[dict]]:
    """(item_categories rows, item_attributes rows) for the live items. Pure."""
    valid = set(tax.nodes)
    cats, attrs = [], []
    for it in items:
        code, name = it["item_code"], it["name_norm"] or ""
        group, brand = gs1.get(code, ("", ""))
        res = C.classify_rules(tax, name, hints, C.row_features(code, it.get("is_weighted"))) if name else C.Result()
        res = C.combine_gs1(tax, res, gmap.get(group or ""))
        rule = {"category_id": res.category_id, "confidence": res.confidence, "reason": res.reason,
                "keyword": res.keyword, "gs1_group": group, "pinned": res.pinned,
                "storage": res.storage}
        f = combine_label(rule, ai.get(code), valid)
        if not f:
            continue
        cats.append({"item_code": code, "category_id": f["category_id"], "confidence": f["confidence"],
                     "source": f["source"], "detail": f["detail"] or None, "model": f["model"],
                     "taxonomy_version": C.TAXONOMY_VERSION, "reviewed": False})
        a = C.extract_attributes(tax, f["category_id"], name,
                                 {"gs1_brand": brand, "is_weighted": it.get("is_weighted")}, res.brand)
        brand_src = "gs1" if brand else "rule"
        for row in attribute_rows(code, a, "rule"):
            if row["attr_key"] == "brand":
                row["source"] = brand_src
            attrs.append(row)
    return cats, attrs


def manual_rows(path: Path, valid: set[str]) -> tuple[list[dict], list[str]]:
    """Rows of a review CSV with a filled correct_category_id -> manual rows; and bad ids."""
    out, bad = [], []
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            cid = (r.get("correct_category_id") or "").strip()
            if not cid:
                continue
            if cid not in valid:
                bad.append(f"{r.get('item_code')}: {cid}")
                continue
            out.append(manual_row(r["item_code"].strip(), cid, C.TAXONOMY_VERSION, f"manual: {path.name}"))
    return out, bad


def diff_counts(planned: list[dict], existing: dict[str, dict], keys: tuple[str, ...]) -> Counter:
    """insert / update / unchanged / protected, by store.may_write."""
    out = Counter()
    for r in planned:
        old = existing.get(r["item_code"])
        if old is None:
            out["insert"] += 1
        elif not may_write(old, r["source"]):
            out["protected"] += 1
        elif all(old.get(k) == r.get(k) for k in keys):
            out["unchanged"] += 1
        else:
            out["update"] += 1
    return out


# --------------------------------------------------------------------------- db
def _tables_present(conn) -> list[str]:
    from sqlalchemy import text
    return [t for t in TABLES if not conn.execute(text("SELECT to_regclass(:n) IS NOT NULL"),
                                                  {"n": f"public.{t}"}).scalar()]


def read_items(conn) -> tuple[list[dict], dict[str, tuple[str, str]]]:
    from sqlalchemy import text
    items = [dict(r) for r in conn.execute(text(ITEMS_SQL)).mappings()]
    gs1: dict[str, tuple[str, str]] = {}
    if conn.execute(text("SELECT to_regclass('gs1.products') IS NOT NULL")).scalar():
        codes = [i["item_code"] for i in items]
        for k in range(0, len(codes), 20000):
            for r in conn.execute(text(GS1_SQL), {"codes": codes[k:k + 20000]}):
                gs1[r[0]] = (r[1] or "", r[2] or "")
    return items, gs1


def read_existing(conn) -> dict[str, dict]:
    from sqlalchemy import text
    return {r["item_code"]: dict(r) for r in conn.execute(text(
        "SELECT item_code, category_id, confidence, source, detail, model, taxonomy_version, reviewed "
        "FROM item_categories")).mappings()}


def write_all(conn, cats_tax: list[dict], cats: list[dict], manual: list[dict], attrs: list[dict]) -> dict:
    """The --apply writes, in the caller's transaction."""
    from sqlalchemy import text
    t0 = time.perf_counter()
    conn.execute(text("""
        INSERT INTO categories (id, parent_id, level, name_he, name_en, sort_order, attributes, active, taxonomy_version)
        VALUES (:id, :parent_id, :level, :name_he, :name_en, :sort_order, :attributes, :active, :taxonomy_version)
        ON CONFLICT (id) DO UPDATE SET parent_id = EXCLUDED.parent_id, level = EXCLUDED.level,
            name_he = EXCLUDED.name_he, name_en = EXCLUDED.name_en, sort_order = EXCLUDED.sort_order,
            attributes = EXCLUDED.attributes, active = EXCLUDED.active, taxonomy_version = EXCLUDED.taxonomy_version
    """), cats_tax)
    retired = conn.execute(text("UPDATE categories SET active = false WHERE active AND NOT (id = ANY(:ids))"),
                           {"ids": [c["id"] for c in cats_tax]}).rowcount
    auto, man = text(upsert_item_categories_sql(manual=False)), text(upsert_item_categories_sql(manual=True))
    for k in range(0, len(cats), CHUNK):
        conn.execute(auto, cats[k:k + CHUNK])
    for k in range(0, len(manual), CHUNK):
        conn.execute(man, manual[k:k + CHUNK])
    up_attr = text(upsert_item_attributes_sql())
    for k in range(0, len(attrs), CHUNK):
        conn.execute(up_attr, attrs[k:k + CHUNK])
    conn.execute(text("ANALYZE categories"))
    conn.execute(text("ANALYZE item_categories"))
    conn.execute(text("ANALYZE item_attributes"))
    after = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in TABLES}
    by = {f"{r[0]}/{r[1]}": r[2] for r in conn.execute(text(
        "SELECT source, confidence, count(*) FROM item_categories GROUP BY 1, 2 ORDER BY 1, 2"))}
    return {"categories_retired": retired, "rows_after": after, "item_categories_by_source_confidence": by,
            "write_ms": round((time.perf_counter() - t0) * 1000)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write (one transaction); default is a dry run")
    ap.add_argument("--ai-labels", type=Path, default=AI_LABELS)
    ap.add_argument("--manual", type=Path, help="review CSV: rows with correct_category_id become manual")
    ap.add_argument("--no-ai", action="store_true", help="rules + GS1 only")
    ap.add_argument("--out", type=Path, help="also write the result as JSON here")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    from sqlalchemy import text
    import scripts.build_search_items as B
    B._load_env(read_only=not a.apply)
    t0 = time.perf_counter()
    tax, gmap, hints = C.load_taxonomy(), C.load_gs1_map(), C.load_brand_hints()
    conn = B._connect(read_only=not a.apply)
    try:
        missing = _tables_present(conn)
        if missing:
            raise SystemExit(f"tables {missing} are missing - apply db/migrations/su11a52_catalog.sql first; "
                             "nothing written")
        ai = {} if a.no_ai else _read_ai(a.ai_labels)
        items, gs1 = read_items(conn)
        log(f"live non-pseudo items: {len(items)}; with a GS1 record: {len(gs1)}; AI labels: {len(ai)}")
        live = {i["item_code"] for i in items}
        cats_tax = category_rows(tax)
        cats, attrs = plan_labels(items, gs1, ai, tax, gmap, hints)
        manual, bad = manual_rows(a.manual, set(tax.nodes)) if a.manual else ([], [])
        existing = read_existing(conn)
        old_tax = {r["id"]: dict(r) for r in conn.execute(text(
            "SELECT id, parent_id, level, name_he, name_en, sort_order, attributes, active, taxonomy_version "
            "FROM categories")).mappings()}
        tax_diff = Counter("insert" if c["id"] not in old_tax else
                           "unchanged" if all(old_tax[c["id"]].get(k) == v for k, v in c.items()) else "update"
                           for c in cats_tax)
        tax_diff["deactivate"] = sum(1 for k, v in old_tax.items() if v["active"] and k not in tax.nodes)
        result = {
            "session": "SU11A-52", "mode": "apply" if a.apply else "dry-run",
            "live_items": len(items), "items_with_gs1": len(gs1),
            "ai_labels_in_file": len(ai), "ai_labels_for_live_items": sum(1 for c in ai if c in live),
            "categories": {"rows": len(cats_tax), **tax_diff},
            "item_categories_planned": len(cats),
            "planned_by_source_confidence": dict(sorted(Counter(f"{c['source']}/{c['confidence']}"
                                                                for c in cats).items())),
            "unclassified_live_items": len(items) - len(cats),
            "item_categories_changes": dict(diff_counts(cats, existing, tuple(ITEM_CATEGORY_COLS[1:]))),
            "item_categories_existing": len(existing),
            "manual_rows": len(manual), "manual_bad_ids": bad[:20],
            "manual_changes": dict(diff_counts(manual, existing, tuple(ITEM_CATEGORY_COLS[1:]))),
            "item_attributes_planned": len(attrs),
            "item_attributes_by_key": dict(Counter(r["attr_key"] for r in attrs).most_common()),
        }
        if a.apply:
            result["written"] = write_all(conn, cats_tax, cats, manual, attrs)
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()
    result["elapsed_s"] = round(time.perf_counter() - t0, 1)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if a.out:
        a.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def _read_ai(path: Path) -> dict[str, dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["item_code"]: r for r in csv.DictReader(fh)}


if __name__ == "__main__":
    raise SystemExit(main())
