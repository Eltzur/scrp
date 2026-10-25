"""Catalog categories for the API (SU11A-57): the taxonomy tree, an item's label,
and the admin writes. Shared by api/routers/categories.py (users) and
api/routers/admin_categories.py (admin console).

Precedence lives in scripts/catalog/store.py and is not repeated here: every
admin write is a manual row (store.manual_row + the manual upsert), which the
automated import and the build hook never overwrite (manual, reviewed = true).

Display rule: a LOW-confidence label never shows a specific category to users;
public_path() cuts it to the department. The admin endpoints see the full label.

Every admin write records an admin_audit row on the same connection before the
commit (api/admin_audit.py): target_type "item_category", target_id the barcode,
detail {"item_code", "old": row | null, "new": row | null, ...}. old / new are the
item_categories rows (no user data), so POST /admin/categories/revert/{audit_id}
can write the old row back exactly.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from sqlalchemy import text

from scripts.catalog import store

TREE_TTL_S = 600.0
_tree_lock = threading.Lock()
_tree_cache: tuple[float, dict] | None = None

LABEL_FIELDS = ("category_id", "confidence", "source", "detail", "model", "taxonomy_version", "reviewed")
AUDIT_TARGET = "item_category"


# --------------------------------------------------------------------------- tree
def _load_tree(conn) -> dict:
    rows = conn.execute(text("""
        SELECT id, parent_id, level, name_he, name_en, sort_order, active, taxonomy_version
        FROM categories ORDER BY sort_order, id
    """)).mappings().all()
    conn.rollback()
    nodes = {r["id"]: dict(r) for r in rows}
    versions = sorted({r["taxonomy_version"] for r in rows if r["active"]})
    return {"nodes": nodes, "version": versions[-1] if versions else None}


def tree(conn) -> dict:
    """{"nodes": {id: row}, "version"} for every node (inactive ones too, so an old
    label still has a path). Cached TREE_TTL_S per worker: the taxonomy changes
    only with an import."""
    global _tree_cache
    now = time.monotonic()
    with _tree_lock:
        cached = _tree_cache
    if cached is None or now - cached[0] >= TREE_TTL_S:
        cached = (now, _load_tree(conn))
        with _tree_lock:
            _tree_cache = cached
    return cached[1]


def reset_tree_cache() -> None:
    """Tests, and after a write that could make a cached tree wrong (none today)."""
    global _tree_cache
    with _tree_lock:
        _tree_cache = None


def public_tree(conn) -> dict:
    """GET /categories/tree: the ACTIVE nodes, parents before children."""
    t = tree(conn)
    return {"version": t["version"], "nodes": [
        {"id": n["id"], "parent_id": n["parent_id"], "level": n["level"],
         "name_he": n["name_he"], "name_en": n["name_en"]}
        for n in t["nodes"].values() if n["active"]]}


def active_node(conn, category_id: str | None) -> dict | None:
    n = tree(conn)["nodes"].get(category_id or "")
    return n if n and n["active"] else None


def path(conn, category_id: str | None) -> list[dict]:
    """Department first. [] for an unknown id."""
    nodes = tree(conn)["nodes"]
    out, cur, seen = [], category_id, set()
    while cur and cur in nodes and cur not in seen:
        seen.add(cur)
        n = nodes[cur]
        out.append({"id": n["id"], "name_he": n["name_he"], "name_en": n["name_en"], "level": n["level"]})
        cur = n["parent_id"]
    return out[::-1]


def path_he(conn, category_id: str | None) -> str:
    return " › ".join(p["name_he"] for p in path(conn, category_id))


def public_path(conn, label: dict | None) -> dict:
    """What a user may see of a label: the full path, or the department only when
    the confidence is low (partial = true). No label: an empty path."""
    if not label:
        return {"category_id": None, "path": [], "partial": False}
    p = path(conn, label["category_id"])
    if label["confidence"] == "low" and len(p) > 1:
        return {"category_id": p[0]["id"], "path": p[:1], "partial": True}
    return {"category_id": p[-1]["id"] if p else None, "path": p, "partial": False}


# --------------------------------------------------------------------------- labels
def label(conn, item_code: str) -> dict | None:
    row = conn.execute(text(
        "SELECT item_code, " + ", ".join(LABEL_FIELDS) + " FROM item_categories WHERE item_code = :c"
    ), {"c": item_code}).mappings().first()
    return None if row is None else {**dict(row), "reviewed": bool(row["reviewed"])}


def snapshot(row: dict | None) -> dict | None:
    """The audited form of a label row: exactly the columns a revert writes back."""
    return None if row is None else {k: row.get(k) for k in LABEL_FIELDS}


def _bool(v) -> bool:
    return bool(v) if v is not None else False


def same_label(a: dict | None, b: dict | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return all((_bool(a.get(k)) == _bool(b.get(k))) if k == "reviewed" else a.get(k) == b.get(k)
               for k in LABEL_FIELDS)


def write_manual(conn, item_code: str, category_id: str, detail: str) -> tuple[dict | None, dict]:
    """Set the label to a manual row (store's manual upsert). Returns (old, new)
    snapshots. Does not commit."""
    old = label(conn, item_code)
    node = tree(conn)["nodes"][category_id]
    row = store.manual_row(item_code, category_id, node["taxonomy_version"], detail)
    conn.execute(text(store.upsert_item_categories_sql(manual=True)), row)
    return snapshot(old), snapshot(row)


def confirm(conn, item_code: str) -> tuple[dict, dict] | None:
    """Mark the label reviewed without changing it. None when there is no label."""
    old = label(conn, item_code)
    if old is None:
        return None
    conn.execute(text(store.CONFIRM_ITEM_CATEGORY_SQL), {"item_code": item_code})
    return snapshot(old), {**snapshot(old), "reviewed": True}


def restore(conn, item_code: str, row: dict | None) -> None:
    """Write an audited snapshot back (or delete the label when it was None)."""
    if row is None:
        conn.execute(text(store.DELETE_ITEM_CATEGORY_SQL), {"item_code": item_code})
    else:
        conn.execute(text(store.RESTORE_ITEM_CATEGORY_SQL), {"item_code": item_code, **snapshot(row)})


def audit_change(record: Callable[..., None], action: str, item_code: str,
                 old: dict | None, new: dict | None, **extra) -> None:
    """One admin_audit row for a label change; `record` is admin_audit.record bound
    to the connection, actor and IP."""
    record(action=action, target_type=AUDIT_TARGET, target_id=item_code,
           detail={"item_code": item_code, "old": old, "new": new, **extra})
