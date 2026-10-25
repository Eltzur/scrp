"""Admin console: categories (SU11A-57). Same gate as every /admin/* endpoint
(api/auth.py require_admin_mfa: token + ADMIN_USER_EMAILS + aal2) and, like
SU11A-54, no user identity ever leaves these endpoints: a user suggestion is
shown as its category, comment and date, never by who made it.

Every write is a manual label (api/categories.write_manual: source manual,
reviewed true, so no automated import or build overwrites it) and records an
admin_audit row with the old and new label in detail, on the same connection
before the commit.

GET  /admin/categories/items?q=                 search by name or barcode
GET  /admin/categories/items/{code}             label, source, confidence, chains_live, audit
PUT  /admin/categories/items/{code}             {category_id} -> manual row
POST /admin/categories/items/{code}/confirm     reviewed = true, label unchanged
POST /admin/categories/bulk                     {item_codes (<= 100), category_id}
POST /admin/categories/revert/{audit_id}        write the audited old label back
GET  /admin/categories/queue/{kind}             low | disagreements | unclassified | suggestions,
                                                paged (limit / offset), chains_live desc
POST /admin/category-suggestions/{code}/accept  {category_id}: manual row, all open -> accepted
POST /admin/category-suggestions/{code}/reject  all open -> rejected
"""
from __future__ import annotations

import re
from collections import Counter
from functools import partial
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from api import admin_audit
from api import categories as cats
from api.auth import ApiCodeError, require_admin_mfa
from api.dependencies import get_db
from db.search_norm import normalize

router = APIRouter(tags=["Admin"], dependencies=[Depends(require_admin_mfa)])

_TS = "'YYYY-MM-DD\"T\"HH24:MI:SSOF'"
BULK_MAX = 100
COMMENTS_PER_ITEM = 5
_DISAGREES = re.compile(r"DISAGREES with (ai|rule|gs1) ([A-Z0-9.]+)")


def _recorder(conn, request: Request, admin: dict):
    return partial(admin_audit.record, conn, actor_id=admin["id"], ip=admin_audit.client_ip(request))


def _item(conn, code: str) -> dict | None:
    row = conn.execute(text("""
        SELECT i.item_code, i.item_name, s.chains_live
        FROM items i LEFT JOIN search_items s ON s.item_code = i.item_code
        WHERE i.item_code = :c
    """), {"c": code}).mappings().first()
    return None if row is None else dict(row)


def _require_category(conn, category_id: str) -> None:
    if cats.active_node(conn, category_id) is None:
        raise ApiCodeError(422, "invalid_category")


def _label_out(conn, lab: dict | None) -> dict | None:
    if lab is None:
        return None
    return {**{k: lab[k] for k in cats.LABEL_FIELDS}, "path_he": cats.path_he(conn, lab["category_id"])}


def _row_out(conn, r) -> dict:
    """A list row: item, chains_live and the current label (null when none)."""
    out = {"item_code": r["item_code"], "item_name": r.get("item_name"), "chains_live": r.get("chains_live")}
    if r.get("category_id"):
        out["label"] = {"category_id": r["category_id"], "confidence": r["confidence"], "source": r["source"],
                        "reviewed": bool(r["reviewed"]), "path_he": cats.path_he(conn, r["category_id"])}
        if r.get("detail") is not None:
            out["label"]["detail"] = r["detail"]
    else:
        out["label"] = None
    return out


# --------------------------------------------------------------------------- search / detail
@router.get("/admin/categories/items", summary="Search items by name or barcode (admin + 2FA)")
def search_items(q: str = Query(..., min_length=2, max_length=80), limit: int = Query(30, ge=1, le=100),
                 conn: Connection = Depends(get_db)):
    """Digits: barcode prefix. Otherwise every word of the normalized query in
    search_items.name_norm (trigram index). Live non-pseudo items, chains_live desc."""
    q = q.strip()
    params: dict = {"limit": limit}
    if q.isdigit():
        where = "s.item_code LIKE :code"
        params["code"] = f"{q}%"
    else:
        words = [w for w in normalize(q).split() if w][:5]
        if not words:
            return {"count": 0, "items": []}
        where = " AND ".join(f"s.name_norm LIKE :w{k}" for k in range(len(words)))
        params.update({f"w{k}": f"%{w}%" for k, w in enumerate(words)})
    rows = conn.execute(text(f"""
        SELECT s.item_code, i.item_name, s.chains_live,
               ic.category_id, ic.confidence, ic.source, ic.reviewed
        FROM search_items s
        LEFT JOIN items i ON i.item_code = s.item_code
        LEFT JOIN item_categories ic ON ic.item_code = s.item_code
        WHERE NOT s.is_pseudo AND {where}
        ORDER BY s.chains_live DESC, s.item_code
        LIMIT :limit
    """), params).mappings().all()
    conn.rollback()
    items = [_row_out(conn, dict(r)) for r in rows]
    return {"count": len(items), "items": items}


@router.get("/admin/categories/items/{item_code}", summary="One item's label and its audit (admin + 2FA)")
def item_detail(item_code: str, conn: Connection = Depends(get_db)):
    it = _item(conn, item_code)
    lab = cats.label(conn, item_code)
    if it is None and lab is None:
        conn.rollback()
        raise ApiCodeError(404, "item_not_found")
    decided = conn.execute(text(f"SELECT to_char(decided_at, {_TS}) FROM item_categories WHERE item_code = :c"),
                           {"c": item_code}).scalar() if lab else None
    open_n = conn.execute(text(
        "SELECT count(*) FROM category_suggestions WHERE item_code = :c AND status = 'open'"
    ), {"c": item_code}).scalar()
    trail = conn.execute(text(f"""
        SELECT id, to_char(at, {_TS}) AS at, action, detail
        FROM admin_audit
        WHERE target_type = :t AND target_id = :c
        ORDER BY id DESC LIMIT 20
    """), {"t": cats.AUDIT_TARGET, "c": item_code}).mappings().all()
    conn.rollback()
    audit = []
    for t in trail:
        d = admin_audit._detail(t["detail"]) or {}
        audit.append({"id": t["id"], "at": t["at"], "action": t["action"],
                      "old_category_id": (d.get("old") or {}).get("category_id"),
                      "new_category_id": (d.get("new") or {}).get("category_id"),
                      "revertible": "old" in d and "new" in d})
    out = _label_out(conn, lab)
    if out is not None:
        out["decided_at"] = decided
    return {"item_code": item_code, "item_name": (it or {}).get("item_name"),
            "chains_live": (it or {}).get("chains_live"), "label": out,
            "open_suggestions": int(open_n or 0), "audit": audit}


# --------------------------------------------------------------------------- writes
class SetIn(BaseModel):
    category_id: str = Field(..., min_length=1, max_length=32)


class BulkIn(BaseModel):
    item_codes: list[str] = Field(..., min_length=1, max_length=BULK_MAX)
    category_id: str = Field(..., min_length=1, max_length=32)

    @field_validator("item_codes")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        out = list(dict.fromkeys(c.strip() for c in v if c and c.strip()))
        if not out:
            raise ValueError("no item codes")
        return out


def _set(conn, record, code: str, category_id: str, action: str, detail: str, **extra) -> dict:
    old, new = cats.write_manual(conn, code, category_id, detail)
    cats.audit_change(record, action, code, old, new, **extra)
    return new


@router.put("/admin/categories/items/{item_code}", summary="Set an item's category: manual row (admin + 2FA)")
def set_category(item_code: str, body: SetIn, request: Request,
                 admin=Depends(require_admin_mfa), conn: Connection = Depends(get_db)):
    _require_category(conn, body.category_id)
    if _item(conn, item_code) is None and cats.label(conn, item_code) is None:
        conn.rollback()
        raise ApiCodeError(404, "item_not_found")
    new = _set(conn, _recorder(conn, request, admin), item_code, body.category_id,
               "category.set", "manual: admin console")
    conn.commit()
    return {"ok": True, "label": _label_out(conn, new)}


@router.post("/admin/categories/items/{item_code}/confirm", summary="Confirm an item's label (admin + 2FA)")
def confirm_category(item_code: str, request: Request,
                     admin=Depends(require_admin_mfa), conn: Connection = Depends(get_db)):
    res = cats.confirm(conn, item_code)
    if res is None:
        conn.rollback()
        raise ApiCodeError(404, "no_label")
    old, new = res
    cats.audit_change(_recorder(conn, request, admin), "category.confirm", item_code, old, new)
    conn.commit()
    return {"ok": True, "label": _label_out(conn, new)}


@router.post("/admin/categories/bulk", summary="Move up to 100 items to one category (admin + 2FA)")
def bulk_set(body: BulkIn, request: Request,
             admin=Depends(require_admin_mfa), conn: Connection = Depends(get_db)):
    """One manual row and one audit row per item (each revertible on its own),
    all in one transaction. Unknown barcodes (no item, no label) are skipped."""
    _require_category(conn, body.category_id)
    known = {r[0] for r in conn.execute(
        text("SELECT item_code FROM items WHERE item_code IN :codes").bindparams(bindparam("codes", expanding=True)),
        {"codes": body.item_codes})}
    known |= {r[0] for r in conn.execute(
        text("SELECT item_code FROM item_categories WHERE item_code IN :codes")
        .bindparams(bindparam("codes", expanding=True)), {"codes": body.item_codes})}
    record = _recorder(conn, request, admin)
    done = [c for c in body.item_codes if c in known]
    for code in done:
        _set(conn, record, code, body.category_id, "category.bulk", "manual: admin console (bulk)", bulk=len(done))
    conn.commit()
    return {"ok": True, "updated": len(done), "skipped": [c for c in body.item_codes if c not in known]}


@router.post("/admin/categories/revert/{audit_id}", summary="Undo one audited category change (admin + 2FA)")
def revert(audit_id: int, request: Request,
           admin=Depends(require_admin_mfa), conn: Connection = Depends(get_db)):
    """Writes the audit row's old label back. 404 when the id is unknown,
    422 not_revertible for a row without old / new labels (e.g. a reject),
    409 changed_since when the label is no longer the audited new one."""
    row = conn.execute(text("SELECT target_type, target_id, detail FROM admin_audit WHERE id = :id"),
                       {"id": audit_id}).mappings().first()
    if row is None:
        conn.rollback()
        raise ApiCodeError(404, "audit_not_found")
    d = admin_audit._detail(row["detail"]) or {}
    if row["target_type"] != cats.AUDIT_TARGET or "old" not in d or "new" not in d:
        conn.rollback()
        raise ApiCodeError(422, "not_revertible")
    code = row["target_id"]
    current = cats.snapshot(cats.label(conn, code))
    if not cats.same_label(current, d["new"]):
        conn.rollback()
        raise ApiCodeError(409, "changed_since")
    old = d["old"]
    if old is not None and cats.tree(conn)["nodes"].get(old.get("category_id")) is None:
        conn.rollback()
        raise ApiCodeError(422, "not_revertible")
    cats.restore(conn, code, old)
    cats.audit_change(_recorder(conn, request, admin), "category.revert", code, current, old,
                      reverted_audit_id=audit_id)
    conn.commit()
    return {"ok": True, "item_code": code, "label": _label_out(conn, old)}


# --------------------------------------------------------------------------- queues
_LABEL_COLS = "ic.category_id, ic.confidence, ic.source, ic.reviewed, ic.detail"
_QUEUE_SQL = {
    "low": f"""
        FROM item_categories ic
        JOIN search_items s ON s.item_code = ic.item_code AND NOT s.is_pseudo
        LEFT JOIN items i ON i.item_code = ic.item_code
        WHERE ic.confidence = 'low' AND NOT ic.reviewed""",
    "disagreements": f"""
        FROM item_categories ic
        JOIN search_items s ON s.item_code = ic.item_code AND NOT s.is_pseudo
        LEFT JOIN items i ON i.item_code = ic.item_code
        WHERE ic.detail LIKE '%DISAGREES with %' AND NOT ic.reviewed""",
    "unclassified": """
        FROM search_items s
        LEFT JOIN item_categories ic ON ic.item_code = s.item_code
        LEFT JOIN items i ON i.item_code = s.item_code
        WHERE NOT s.is_pseudo AND s.chains_live > 0 AND ic.item_code IS NULL""",
}


def _disagreement(r: dict) -> dict | None:
    """The other side of a combine DISAGREEMENT (scripts/catalog/combine.py writes
    '... | DISAGREES with <source> <id>' into detail)."""
    m = _DISAGREES.search(r.get("detail") or "")
    if not m:
        return None
    return {"source": m.group(1), "category_id": m.group(2)}


@router.get("/admin/categories/queue/{kind}", summary="Category review queues (admin + 2FA)")
def queue(kind: Literal["low", "disagreements", "unclassified", "suggestions"],
          limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100_000),
          conn: Connection = Depends(get_db)):
    if kind == "suggestions":
        return _suggestion_queue(conn, limit, offset)
    body = _QUEUE_SQL[kind]
    total = conn.execute(text(f"SELECT count(*) {body}")).scalar()
    rows = conn.execute(text(f"""
        SELECT s.item_code, i.item_name, s.chains_live, {_LABEL_COLS} {body}
        ORDER BY s.chains_live DESC, s.item_code
        LIMIT :limit OFFSET :offset
    """), {"limit": limit, "offset": offset}).mappings().all()
    conn.rollback()
    items = []
    for r in rows:
        out = _row_out(conn, dict(r))
        if kind == "disagreements":
            other = _disagreement(dict(r))
            if other:
                other["path_he"] = cats.path_he(conn, other["category_id"])
            out["other"] = other
        items.append(out)
    nxt = offset + limit if offset + limit < (total or 0) else None
    return {"kind": kind, "total": int(total or 0), "items": items, "next_offset": nxt}


def _suggestion_queue(conn, limit: int, offset: int) -> dict:
    """Open suggestions grouped by item: how many, which ids (with counts), the
    latest comments (blacklisted ones were never stored). No user ids."""
    total = conn.execute(text(
        "SELECT count(DISTINCT item_code) FROM category_suggestions WHERE status = 'open'")).scalar()
    page = conn.execute(text(f"""
        SELECT g.item_code, g.n, g.latest_at, i.item_name, s.chains_live,
               {_LABEL_COLS}
        FROM (SELECT item_code, count(*) AS n, max(created_at) AS latest
                     , to_char(max(created_at), {_TS}) AS latest_at
              FROM category_suggestions WHERE status = 'open' GROUP BY item_code) g
        LEFT JOIN items i ON i.item_code = g.item_code
        LEFT JOIN search_items s ON s.item_code = g.item_code
        LEFT JOIN item_categories ic ON ic.item_code = g.item_code
        ORDER BY COALESCE(s.chains_live, 0) DESC, g.n DESC, g.latest DESC, g.item_code
        LIMIT :limit OFFSET :offset
    """), {"limit": limit, "offset": offset}).mappings().all()
    codes = [r["item_code"] for r in page]
    detail: dict[str, list] = {c: [] for c in codes}
    if codes:
        for r in conn.execute(text(f"""
            SELECT item_code, suggested_category_id, comment, to_char(created_at, {_TS}) AS created_at
            FROM category_suggestions
            WHERE status = 'open' AND item_code IN :codes
            ORDER BY created_at DESC, id DESC
        """).bindparams(bindparam("codes", expanding=True)), {"codes": codes}).mappings():
            detail[r["item_code"]].append(dict(r))
    conn.rollback()
    items = []
    for r in page:
        rows = detail[r["item_code"]]
        counts = Counter(x["suggested_category_id"] for x in rows)
        out = _row_out(conn, dict(r))
        out.update({
            "count": int(r["n"]), "latest_at": r["latest_at"],
            "suggested": [{"category_id": cid, "n": n, "path_he": cats.path_he(conn, cid)}
                          for cid, n in counts.most_common()],
            "comments": [{"text": x["comment"], "category_id": x["suggested_category_id"], "at": x["created_at"]}
                         for x in rows if x["comment"]][:COMMENTS_PER_ITEM],
        })
        items.append(out)
    nxt = offset + limit if offset + limit < (total or 0) else None
    return {"kind": "suggestions", "total": int(total or 0), "items": items, "next_offset": nxt}


# --------------------------------------------------------------------------- suggestions
def _open_counts(conn, code: str) -> Counter:
    return Counter({r[0]: int(r[1]) for r in conn.execute(text("""
        SELECT suggested_category_id, count(*) FROM category_suggestions
        WHERE item_code = :c AND status = 'open' GROUP BY suggested_category_id
    """), {"c": code})})


def _decide(conn, code: str, status: str) -> int:
    return conn.execute(text("""
        UPDATE category_suggestions SET status = :s, decided_at = now()
        WHERE item_code = :c AND status = 'open'
    """), {"s": status, "c": code}).rowcount


@router.post("/admin/category-suggestions/{item_code}/accept",
             summary="Accept an item's open suggestions with a chosen category (admin + 2FA)")
def accept_suggestions(item_code: str, body: SetIn, request: Request,
                       admin=Depends(require_admin_mfa), conn: Connection = Depends(get_db)):
    """Writes the chosen category as a manual row (it need not be one of the
    suggested ids) and marks every open suggestion for the item accepted."""
    _require_category(conn, body.category_id)
    counts = _open_counts(conn, item_code)
    if not counts:
        conn.rollback()
        raise ApiCodeError(404, "no_open_suggestions")
    n = _decide(conn, item_code, "accepted")
    new = _set(conn, _recorder(conn, request, admin), item_code, body.category_id, "category_suggestion.accept",
               f"manual: user suggestions ({n})", suggestions=n, suggested=dict(counts))
    conn.commit()
    return {"ok": True, "accepted": n, "label": _label_out(conn, new)}


@router.post("/admin/category-suggestions/{item_code}/reject",
             summary="Reject an item's open suggestions (admin + 2FA)")
def reject_suggestions(item_code: str, request: Request,
                       admin=Depends(require_admin_mfa), conn: Connection = Depends(get_db)):
    counts = _open_counts(conn, item_code)
    if not counts:
        conn.rollback()
        raise ApiCodeError(404, "no_open_suggestions")
    n = _decide(conn, item_code, "rejected")
    admin_audit.record(conn, actor_id=admin["id"], action="category_suggestion.reject",
                       target_type=cats.AUDIT_TARGET, target_id=item_code,
                       detail={"item_code": item_code, "suggestions": n, "suggested": dict(counts)},
                       ip=admin_audit.client_ip(request))
    conn.commit()
    return {"ok": True, "rejected": n}
