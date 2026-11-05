"""Admin console: promo pins and hides (SU11A-58, table promo_curation in
db/migrations/su11a58_promo_curation.sql). Same gate as every /admin/* endpoint
(api/auth.py require_admin_mfa: token + ADMIN_USER_EMAILS + aal2).

A promotion is (chain_id, promo_id): the chain's PromotionId, which survives the
daily reload (promos.id does not) and covers every store and item of the
promotion. A pin shows it first on the promo lists, in rank order; a hide
leaves it out of them. NEITHER changes search, compare, basket or any price
(db/promo_curation.py): a hidden promo still prices its items.

Every write records an admin_audit row (target_type 'promo', target_id
'<chain_id>:<promo_id>') with the row before and after, plus the other pins
whose rank moved; no email, no user id (the row's actor_hash is the same
pseudonym as admin_audit's). Active pins are kept numbered 1..n: inserting at
rank N shifts the rest down, in the same transaction, under a row lock.

GET    /admin/promos/search?q=&chain=&active_only=     promotions by text, barcode or PromotionId
                                                       (+ the cities where each shows, SU11A-62)
GET    /admin/promos/curation?state=active|expired     pins and hides with their promotion
                                                       (pins: + cities, SU11A-62)
POST   /admin/promos/pins                              {chain_id, promo_id, rank, starts_at, ends_at, sponsored, note}
POST   /admin/promos/hides                             {chain_id, promo_id, reason, starts_at, ends_at}
PATCH  /admin/promos/curation/{id}                     {rank, starts_at, ends_at, sponsored, note}
DELETE /admin/promos/curation/{id}                     remove (active = false)
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api import admin_audit
from api import categories as cats
from api.auth import ApiCodeError, require_admin_mfa
from api.dependencies import get_db
from db import promo_curation
from db.query import clean_promo_q, fetch_promo_coverage, is_gift_coupon, promo_match_sql

router = APIRouter(tags=["Admin"], dependencies=[Depends(require_admin_mfa)])

_TS = "'YYYY-MM-DD\"T\"HH24:MI:SSOF'"
_PTS = "'YYYY-MM-DD\"T\"HH24:MI:SS'"   # promos dates are TIMESTAMP (no zone), as in db/query.py
MAX_PINS = 50
AUDIT_TARGET = "promo"
SNAPSHOT = ("id", "kind", "chain_id", "promo_id", "rank", "starts_at", "ends_at", "sponsored", "note", "active")
_LIVE = "(p.promo_end >= now() OR p.promo_end IS NULL)"


# --------------------------------------------------------------------------- helpers
def place(order: list[int], row_id: int, rank: int) -> list[int]:
    """The pin ids in display order with row_id moved (or inserted) at rank
    (1-based, clamped to 1..len+1). Pure: the caller writes the new ranks."""
    rest = [i for i in order if i != row_id]
    pos = max(1, min(int(rank), len(rest) + 1))
    return rest[:pos - 1] + [row_id] + rest[pos - 1:]


def _iso(v):
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat(timespec="seconds")
    return v


def _snapshot(row) -> dict | None:
    return None if row is None else {k: _iso(row[k]) for k in SNAPSHOT}


def _row(conn, row_id: int, lock: bool = False):
    return conn.execute(text(f"SELECT * FROM promo_curation WHERE id = :id{' FOR UPDATE' if lock else ''}"),
                        {"id": row_id}).mappings().first()


def _ordered_pins(conn) -> list:
    """Active pins not past ends_at, in rank order, locked for this transaction.
    (Rows past ends_at keep their old rank; the read path ignores them.)"""
    return conn.execute(text("""
        SELECT id, rank FROM promo_curation
        WHERE kind = 'pin' AND active AND (ends_at IS NULL OR ends_at > now())
        ORDER BY rank, id
        FOR UPDATE
    """)).mappings().all()


def _renumber(conn, order: list[int], before: dict[int, int]) -> list[dict]:
    """Write ranks 1..n for order; returns the rows whose rank changed."""
    moved = []
    for pos, rid in enumerate(order, start=1):
        if before.get(rid) != pos:
            conn.execute(text("UPDATE promo_curation SET rank = :r, updated_at = now() WHERE id = :id"),
                         {"r": pos, "id": rid})
            if rid in before:
                moved.append({"id": rid, "from": before[rid], "to": pos})
    return moved


def _promotion(conn, chain_id: str, promo_id: str, live_only: bool = True) -> dict | None:
    row = conn.execute(text(f"""
        SELECT count(DISTINCT p.store_fk) AS stores, count(DISTINCT p.item_code) AS items
        FROM promos p JOIN stores s ON s.id = p.store_fk
        WHERE s.chain_id = :c AND p.promo_id = :p {'AND ' + _LIVE if live_only else ''}
    """), {"c": chain_id, "p": promo_id}).mappings().one()
    return dict(row) if row["stores"] else None


def _active_kinds(conn, chain_id: str, promo_id: str) -> set[str]:
    return {r[0] for r in conn.execute(text("""
        SELECT kind FROM promo_curation WHERE active AND chain_id = :c AND promo_id = :p
    """), {"c": chain_id, "p": promo_id})}


def _audit(conn, request: Request, admin: dict, action: str, row_before, row_after, **extra) -> None:
    r = row_after or row_before
    admin_audit.record(conn, actor_id=admin["id"], action=action, target_type=AUDIT_TARGET,
                       target_id=f"{r['chain_id']}:{r['promo_id']}",
                       detail={"before": _snapshot(row_before), "after": _snapshot(row_after), **extra},
                       ip=admin_audit.client_ip(request))


def _check_dates(starts_at: datetime | None, ends_at: datetime | None) -> None:
    now = datetime.now(timezone.utc)
    if ends_at is not None and ends_at <= max(starts_at or now, now):
        raise ApiCodeError(422, "invalid_dates")


def _done(conn) -> None:
    conn.commit()
    promo_curation.invalidate()


# --------------------------------------------------------------------------- reads
_SUMMARY = f"""
    LEFT JOIN LATERAL (
        SELECT count(DISTINCT p.store_fk) AS stores, count(DISTINCT p.item_code) AS items,
               min(p.promo_description) AS promo_description,
               to_char(min(p.promo_start), {_PTS}) AS promo_start,
               to_char(max(p.promo_end), {_PTS}) AS promo_end,
               bool_or({_LIVE}) AS live
        FROM promos p JOIN stores s ON s.id = p.store_fk
        WHERE s.chain_id = m.chain_id AND p.promo_id = m.promo_id {{live}}
    ) g ON TRUE
    LEFT JOIN LATERAL (
        SELECT p.item_code, i.item_name, p.min_qty, p.discount_price, p.discount_rate
        FROM promos p JOIN stores s ON s.id = p.store_fk
        LEFT JOIN items i ON i.item_code = p.item_code
        WHERE s.chain_id = m.chain_id AND p.promo_id = m.promo_id {{live}}
        ORDER BY {{best}}i.item_name IS NULL, p.item_code
        LIMIT 1
    ) x ON TRUE
    LEFT JOIN chains c ON c.chain_id = m.chain_id
"""


def _promo_out(r) -> dict:
    return {
        "chain_id": r["chain_id"], "chain_name": r["chain_name"], "promo_id": r["promo_id"],
        "promo_description": r["promo_description"], "stores": int(r["stores"] or 0),
        "items": int(r["items"] or 0), "promo_start": r["promo_start"], "promo_end": r["promo_end"],
        "live": bool(r["live"]),
        "sample": None if r["item_code"] is None else {
            "item_code": r["item_code"], "item_name": r["item_name"],
            "min_qty": None if r["min_qty"] is None else float(r["min_qty"]),
            "discount_price": None if r["discount_price"] is None else float(r["discount_price"]),
            "discount_rate": None if r["discount_rate"] is None else float(r["discount_rate"]),
            # SU11A-65: a free unit with a coupon reads "מתנה בקופון", never "100% הנחה".
            "gift_coupon": is_gift_coupon(r["promo_description"], r["min_qty"], r["discount_price"],
                                          r["discount_rate"]),
        },
    }


@router.get("/admin/promos/search", summary="Search promotions (admin + 2FA)")
def search_promos(q: str | None = Query(None, max_length=80), chain: str | None = Query(None, max_length=32),
                  active_only: bool = Query(True), limit: int = Query(30, ge=1, le=100),
                  conn: Connection = Depends(get_db)):
    """By barcode (7+ digits: exact item_code), PromotionId (exact) or text
    (promo description or product name, substring). q or chain is required.
    One row per promotion with its curation.

    SU11A-62: text results rank as the public promos search (db.query.
    promo_match_sql: description > name starts with the text > name contains
    it > only in a flavour phrase, an item in a category the text names
    first); the widest (most stores) next. `sample` is the best-matching
    product, `matches` the matching products (null without text). The text is
    escaped, and under 2 characters besides wildcards and spaces is no text
    (SU11A-63 H2). `cities`: where the promotion shows on the public lists."""
    text_q = clean_promo_q(q)
    if text_q is None and not chain:
        raise ApiCodeError(422, "query_required")
    where, params = "", {"limit": limit}
    rel, matches, best = "0", "NULL::bigint", ""
    if chain:
        where += " AND s.chain_id = :chain"
        params["chain"] = chain
    if active_only:
        where += f" AND {_LIVE}"
    if text_q and text_q.isdigit() and len(text_q) >= 7:
        where += " AND (p.item_code = :q OR p.promo_id = :q)"
        params["q"] = text_q
    elif text_q:
        match, rank, name_tier, mp = promo_match_sql(cats.promo_search(conn, text_q), "i.item_name",
                                                    "p.promo_description", "p.item_code")
        where += f" AND ({match} OR p.promo_id = :q)"
        params.update(mp, q=text_q)
        rel = f"min(CASE WHEN p.promo_id = :q THEN -1 ELSE {rank} END)"
        matches = "count(DISTINCT p.item_code)"
        best = f"{rank}, {name_tier}, "
    live = f"AND {_LIVE}" if active_only else ""
    rows = conn.execute(text(f"""
        WITH m AS (
            SELECT s.chain_id, p.promo_id, count(DISTINCT p.store_fk) AS n,
                   {rel} AS rel, {matches} AS matches
            FROM promos p
            JOIN stores s ON s.id = p.store_fk
            LEFT JOIN items i ON i.item_code = p.item_code
            WHERE p.promo_id IS NOT NULL {where}
            GROUP BY s.chain_id, p.promo_id
            ORDER BY rel, n DESC, s.chain_id, p.promo_id
            LIMIT :limit
        )
        SELECT m.chain_id, m.promo_id, m.n, m.rel, m.matches, c.name AS chain_name, g.*, x.*,
               (SELECT pc.id FROM promo_curation pc WHERE pc.active AND pc.kind = 'pin'
                  AND pc.chain_id = m.chain_id AND pc.promo_id = m.promo_id) AS pin_id,
               (SELECT pc.rank FROM promo_curation pc WHERE pc.active AND pc.kind = 'pin'
                  AND pc.chain_id = m.chain_id AND pc.promo_id = m.promo_id) AS pin_rank,
               (SELECT pc.id FROM promo_curation pc WHERE pc.active AND pc.kind = 'hide'
                  AND pc.chain_id = m.chain_id AND pc.promo_id = m.promo_id) AS hide_id
        FROM m {_SUMMARY.format(live=live, best=best)}
        ORDER BY m.rel, m.n DESC, m.chain_id, m.promo_id
    """), params).mappings().all()
    conn.rollback()
    cover = fetch_promo_coverage(conn, [(r["chain_id"], r["promo_id"]) for r in rows])
    conn.rollback()
    items = []
    for r in rows:
        out = _promo_out(r)
        out["matches"] = None if r["matches"] is None else int(r["matches"])
        out["cities"] = cover.get((r["chain_id"], r["promo_id"]), [])
        out["curation"] = {"pin_id": r["pin_id"], "pin_rank": r["pin_rank"], "hide_id": r["hide_id"]}
        items.append(out)
    return {"count": len(items), "items": items}


@router.get("/admin/promos/curation", summary="Promo pins and hides (admin + 2FA)")
def list_curation(state: str = Query("active", pattern="^(active|expired)$"), conn: Connection = Depends(get_db)):
    """active: not removed, not past ends_at and the promotion is still in the
    data (includes scheduled rows whose starts_at is ahead). expired ("פג
    תוקף"): not removed, but past ends_at or the promotion is gone. Pins in rank
    order, then hides newest first. No identities (actor_hash is not returned)."""
    rows = conn.execute(text(f"""
        SELECT pc.id, pc.kind, pc.rank, pc.sponsored, pc.note,
               to_char(pc.starts_at, {_TS}) AS starts_at, to_char(pc.ends_at, {_TS}) AS ends_at,
               to_char(pc.created_at, {_TS}) AS created_at,
               (pc.starts_at > now()) AS scheduled,
               (pc.ends_at IS NOT NULL AND pc.ends_at <= now()) AS past_end,
               m.chain_id, m.promo_id, c.name AS chain_name, g.*, x.*
        FROM promo_curation pc
        CROSS JOIN LATERAL (SELECT pc.chain_id, pc.promo_id) m
        {_SUMMARY.format(live='AND ' + _LIVE, best='')}
        WHERE pc.active
        ORDER BY pc.kind DESC, pc.rank NULLS LAST, pc.created_at DESC, pc.id
    """)).mappings().all()
    conn.rollback()
    cover = fetch_promo_coverage(conn, [(r["chain_id"], r["promo_id"]) for r in rows if r["kind"] == "pin"])
    conn.rollback()
    items = []
    for r in rows:
        missing = not r["stores"]
        expired = bool(r["past_end"]) or missing
        if expired != (state == "expired"):
            continue
        promo = _promo_out(r)
        if r["kind"] == "pin":
            promo["cities"] = cover.get((r["chain_id"], r["promo_id"]), [])
        items.append({
            "id": r["id"], "kind": r["kind"], "rank": r["rank"], "sponsored": bool(r["sponsored"]),
            "note": r["note"], "starts_at": r["starts_at"], "ends_at": r["ends_at"], "created_at": r["created_at"],
            "status": ("expired_missing" if missing else "expired_date") if expired
            else ("scheduled" if r["scheduled"] else "active"),
            "promo": promo,
        })
    return {"state": state, "count": len(items), "items": items}


# --------------------------------------------------------------------------- writes
class _Target(BaseModel):
    chain_id: str = Field(..., min_length=1, max_length=32)
    promo_id: str = Field(..., min_length=1, max_length=64)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        return v if v is None or v.tzinfo else v.replace(tzinfo=timezone.utc)


class PinIn(_Target):
    rank: int = Field(1, ge=1, le=MAX_PINS)
    sponsored: bool = False
    note: str | None = Field(None, max_length=200)


class HideIn(_Target):
    reason: str = Field(..., min_length=1, max_length=200)


class UpdateIn(BaseModel):
    rank: int | None = Field(None, ge=1, le=MAX_PINS)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    clear_ends_at: bool = False
    sponsored: bool | None = None
    note: str | None = Field(None, max_length=200)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        return v if v is None or v.tzinfo else v.replace(tzinfo=timezone.utc)


def _guard_new(conn, body: _Target, kind: str) -> None:
    _check_dates(body.starts_at, body.ends_at)
    if _promotion(conn, body.chain_id, body.promo_id, live_only=(kind == "pin")) is None:
        conn.rollback()
        raise ApiCodeError(404, "promo_not_found")
    kinds = _active_kinds(conn, body.chain_id, body.promo_id)
    if kind in kinds:
        conn.rollback()
        raise ApiCodeError(409, "already_curated")
    if kinds:   # the other kind: a promotion is either pinned or hidden
        conn.rollback()
        raise ApiCodeError(409, "pinned" if kind == "hide" else "hidden")


def _insert(conn, kind: str, body: _Target, admin: dict, rank, sponsored: bool, note) -> int:
    return conn.execute(text("""
        INSERT INTO promo_curation (kind, chain_id, promo_id, rank, starts_at, ends_at, sponsored, note, actor_hash)
        VALUES (:kind, :c, :p, :rank, COALESCE(:starts, now()), :ends, :sp, :note, :actor)
        RETURNING id
    """), {"kind": kind, "c": body.chain_id, "p": body.promo_id, "rank": rank, "starts": body.starts_at,
           "ends": body.ends_at, "sp": sponsored, "note": (note or "").strip() or None,
           "actor": admin_audit.actor_hash(admin["id"])}).scalar()


@router.post("/admin/promos/pins", summary="Pin a promotion at a rank (admin + 2FA)")
def create_pin(body: PinIn, request: Request, admin=Depends(require_admin_mfa), conn: Connection = Depends(get_db)):
    """404 promo_not_found (not in the current data), 409 already_curated /
    hidden, 409 pins_full at 50 active pins, 422 invalid_dates."""
    _guard_new(conn, body, "pin")
    pins = _ordered_pins(conn)
    if len(pins) >= MAX_PINS:
        conn.rollback()
        raise ApiCodeError(409, "pins_full")
    rid = _insert(conn, "pin", body, admin, min(body.rank, len(pins) + 1), body.sponsored, body.note)
    before = {p["id"]: p["rank"] for p in pins}
    moved = _renumber(conn, place([p["id"] for p in pins], rid, body.rank), before)
    after = _row(conn, rid)
    _audit(conn, request, admin, "promo.pin", None, after, shifted=moved)
    _done(conn)
    return {"ok": True, "id": rid, "rank": after["rank"], "shifted": moved}


@router.post("/admin/promos/hides", summary="Hide a promotion from the promo lists (admin + 2FA)")
def create_hide(body: HideIn, request: Request, admin=Depends(require_admin_mfa), conn: Connection = Depends(get_db)):
    """Leaves the promotion out of /promos/grouped and /promos/today. Its prices
    in search, compare and basket do NOT change. 409 pinned: remove the pin first."""
    _guard_new(conn, body, "hide")
    rid = _insert(conn, "hide", body, admin, None, False, body.reason)
    _audit(conn, request, admin, "promo.hide", None, _row(conn, rid))
    _done(conn)
    return {"ok": True, "id": rid}


@router.patch("/admin/promos/curation/{row_id:int}", summary="Change a pin's rank / dates / label (admin + 2FA)")
def update_curation(row_id: int, body: UpdateIn, request: Request,
                    admin=Depends(require_admin_mfa), conn: Connection = Depends(get_db)):
    """rank and sponsored are for pins only (422 not_a_pin on a hide). A rank
    change moves the pin and renumbers the others in one transaction."""
    old = _row(conn, row_id, lock=True)
    if old is None or not old["active"]:
        conn.rollback()
        raise ApiCodeError(404, "curation_not_found")
    if old["kind"] != "pin" and (body.rank is not None or body.sponsored is not None):
        conn.rollback()
        raise ApiCodeError(422, "not_a_pin")
    if old["kind"] == "hide" and body.note is not None and not body.note.strip():
        conn.rollback()
        raise ApiCodeError(422, "reason_required")
    starts = body.starts_at or old["starts_at"]
    ends = None if body.clear_ends_at else (body.ends_at or old["ends_at"])
    if body.starts_at is not None or body.ends_at is not None:
        try:
            _check_dates(starts if body.starts_at else None, ends)
        except ApiCodeError:
            conn.rollback()
            raise
    conn.execute(text("""
        UPDATE promo_curation
        SET starts_at = :s, ends_at = :e, sponsored = :sp, note = :note, updated_at = now()
        WHERE id = :id
    """), {"s": starts, "e": ends, "id": row_id,
           "sp": old["sponsored"] if body.sponsored is None else body.sponsored,
           "note": old["note"] if body.note is None else (body.note.strip() or None)})
    moved = []
    if old["kind"] == "pin" and body.rank is not None:
        pins = _ordered_pins(conn)
        before = {p["id"]: p["rank"] for p in pins}
        if row_id in before:
            moved = _renumber(conn, place([p["id"] for p in pins], row_id, body.rank), before)
        else:   # past ends_at: not in the live order; just record the rank
            conn.execute(text("UPDATE promo_curation SET rank = :r WHERE id = :id"), {"r": body.rank, "id": row_id})
    new = _row(conn, row_id)
    _audit(conn, request, admin, "promo.update", old, new, shifted=[m for m in moved if m["id"] != row_id])
    _done(conn)
    return {"ok": True, "id": row_id, "rank": new["rank"], "shifted": moved}


@router.delete("/admin/promos/curation/{row_id:int}", summary="Remove a pin or hide (admin + 2FA)")
def remove_curation(row_id: int, request: Request, admin=Depends(require_admin_mfa), conn: Connection = Depends(get_db)):
    """active = false (the row stays for the record); the pins below move up."""
    old = _row(conn, row_id, lock=True)
    if old is None or not old["active"]:
        conn.rollback()
        raise ApiCodeError(404, "curation_not_found")
    conn.execute(text("UPDATE promo_curation SET active = false, updated_at = now() WHERE id = :id"), {"id": row_id})
    moved = []
    if old["kind"] == "pin":
        pins = _ordered_pins(conn)
        moved = _renumber(conn, [p["id"] for p in pins], {p["id"]: p["rank"] for p in pins})
    _audit(conn, request, admin, "promo.remove", old, _row(conn, row_id), shifted=moved)
    _done(conn)
    return {"ok": True, "id": row_id, "shifted": moved}
