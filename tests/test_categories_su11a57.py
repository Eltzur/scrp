"""SU11A-57: categories for users, user category suggestions, and the admin
console's category endpoints.

Same approach as tests/test_admin_su11a54.py: an in-memory SQLite copy of the
tables stands in for Postgres (now() and to_char() registered as functions),
token verification is a lookup table. The Postgres-only parts (the migration
twice, the partial unique index, jsonb) are in tests/test_categories_su11a57_pg.py.
    python -m pytest tests/test_categories_su11a57.py -q
"""
import datetime as dt
import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

import api.auth as auth
import api.routers.admin as A
import api.supabase_admin as supa
from api import categories as cats
from api.dependencies import get_db
from api.main import app
from api.terms import TERMS_VERSION
from scripts.catalog import store

USER = "11111111-0000-4000-8000-000000000001"
OTHER = "22222222-0000-4000-8000-000000000002"
ADMIN = "44444444-0000-4000-8000-000000000004"
ADMIN_EMAIL = "admin@example.test"
ITEM, ITEM2, ITEM3, NOLABEL = "7290000000011", "7290000000028", "7290000000035", "7290000000042"

_TS = "strftime('%Y-%m-%d %H:%M:%f','now')"
SCHEMA = [
    "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, display_name TEXT, tier TEXT, "
    "terms_version TEXT NULL, terms_accepted_at TEXT NULL, banned_at TEXT NULL)",
    "CREATE TABLE items (item_code TEXT PRIMARY KEY, item_name TEXT)",
    "CREATE TABLE search_items (item_code TEXT PRIMARY KEY, name_norm TEXT NOT NULL DEFAULT '', "
    "is_pseudo BOOLEAN NOT NULL DEFAULT 0, chains_live INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE categories (id TEXT PRIMARY KEY, parent_id TEXT NULL REFERENCES categories(id), "
    "level INTEGER NOT NULL, name_he TEXT NOT NULL, name_en TEXT NOT NULL DEFAULT '', "
    "sort_order INTEGER NOT NULL DEFAULT 0, attributes TEXT NOT NULL DEFAULT '', "
    "active BOOLEAN NOT NULL DEFAULT 1, taxonomy_version TEXT NOT NULL)",
    "CREATE TABLE item_categories (item_code TEXT PRIMARY KEY, category_id TEXT NOT NULL REFERENCES categories(id), "
    "confidence TEXT NOT NULL, source TEXT NOT NULL, detail TEXT NULL, model TEXT NULL, "
    f"taxonomy_version TEXT NOT NULL, decided_at TEXT NOT NULL DEFAULT ({_TS}), reviewed BOOLEAN NOT NULL DEFAULT 0)",
    "CREATE TABLE category_suggestions (id INTEGER PRIMARY KEY, item_code TEXT NOT NULL, "
    "user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
    "current_category_id TEXT NULL REFERENCES categories(id), "
    "suggested_category_id TEXT NOT NULL REFERENCES categories(id), "
    "comment TEXT NULL CHECK (comment IS NULL OR length(comment) <= 200), "
    "comment_blocked BOOLEAN NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'open' "
    "CHECK (status IN ('open', 'accepted', 'rejected')), "
    f"created_at TEXT NOT NULL DEFAULT ({_TS}), decided_at TEXT NULL)",
    "CREATE UNIQUE INDEX uq_category_suggestions_open ON category_suggestions (user_id, item_code) "
    "WHERE status = 'open'",
    "CREATE TABLE rating_blacklist (id INTEGER PRIMARY KEY, term TEXT)",
    "CREATE TABLE ratings (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
    "item_code TEXT NOT NULL, rating INTEGER NOT NULL, comment TEXT, status TEXT NOT NULL DEFAULT 'active', "
    f"created_at TEXT NOT NULL DEFAULT ({_TS}), updated_at TEXT NOT NULL DEFAULT ({_TS}), reviewed_at TEXT NULL)",
    "CREATE TABLE rating_reports (id INTEGER PRIMARY KEY, rating_id INTEGER NOT NULL, reporter_user_id TEXT, "
    f"reason TEXT, source TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL DEFAULT ({_TS}))",
    "CREATE TABLE deleted_accounts (user_id TEXT PRIMARY KEY, "
    "requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, auth_deleted_at TIMESTAMP NULL, "
    "attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT NULL)",
    "CREATE TABLE flights.alerts (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL)",
    "CREATE TABLE flights.saved_searches (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL)",
    "CREATE TABLE admin_audit (id INTEGER PRIMARY KEY, "
    f"at TEXT NOT NULL DEFAULT ({_TS}), actor_hash TEXT NOT NULL, action TEXT NOT NULL, "
    "target_type TEXT, target_id TEXT, detail TEXT, ip_hash TEXT)",
]
# id, parent, level, name_he, active
NODES = [
    ("D01", None, 1, "פירות וירקות", 1), ("D01.C01", "D01", 2, "ירקות", 1), ("D01.C02", "D01", 2, "פירות", 1),
    ("D07", None, 1, "מזווה", 1), ("D07.C08", "D07", 2, "שימורים", 1),
    ("D07.C08.S01", "D07.C08", 3, "חמוצים וזיתים בשימורים", 1), ("D07.C99", "D07", 2, "ישן", 0),
]

sqlite3.register_adapter(
    dt.datetime, lambda d: d.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"))


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _on_connect(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys = ON")
        dbapi_conn.execute("ATTACH DATABASE ':memory:' AS flights")
        dbapi_conn.create_function("to_char", 2, lambda v, _fmt: v)
        dbapi_conn.create_function(
            "now", 0, lambda: dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"))

    @event.listens_for(eng, "before_cursor_execute", retval=True)
    def _pg_to_sqlite(_conn, _cur, statement, params, _ctx, _many):
        return statement.replace("CAST(? AS uuid)", "?").replace("CAST(? AS jsonb)", "?"), params

    with eng.begin() as c:
        for ddl in SCHEMA:
            c.execute(text(ddl))
        for k, (nid, parent, level, name, active) in enumerate(NODES):
            c.execute(text("INSERT INTO categories (id, parent_id, level, name_he, name_en, sort_order, active, "
                           "taxonomy_version) VALUES (:i, :p, :l, :n, :e, :k, :a, 'v1.2')"),
                      {"i": nid, "p": parent, "l": level, "n": name, "e": nid, "k": k, "a": active})
        for uid in (USER, OTHER):
            c.execute(text("INSERT INTO users (id, email, terms_version) VALUES (:u, :e, :t)"),
                      {"u": uid, "e": f"{uid[:4]}@example.test", "t": TERMS_VERSION})
        for code, name, chains in ((ITEM, "מלפפון", 5), (ITEM2, "זיתים ירוקים יכין 560 גרם", 9),
                                   (ITEM3, "תפוח עץ", 2), (NOLABEL, "מוצר חדש", 7)):
            c.execute(text("INSERT INTO items VALUES (:c, :n)"), {"c": code, "n": name})
            c.execute(text("INSERT INTO search_items (item_code, name_norm, chains_live) VALUES (:c, :n, :k)"),
                      {"c": code, "n": name, "k": chains})
        label(c, ITEM, "D01.C01", "high", "rule", "rule: מלפפון")
        label(c, ITEM2, "D07.C08.S01", "low", "ai", "ai: olives | DISAGREES with rule D01.C02")
        label(c, ITEM3, "D01.C02", "medium", "gs1", "gs1")
    return eng


def label(c, code, cid, conf, src, detail, reviewed=False):
    c.execute(text("INSERT INTO item_categories (item_code, category_id, confidence, source, detail, model, "
                   "taxonomy_version, reviewed) VALUES (:c, :cid, :conf, :src, :d, NULL, 'v1.2', :r)"),
              {"c": code, "cid": cid, "conf": conf, "src": src, "d": detail, "r": reviewed})


@pytest.fixture
def client(engine, monkeypatch):
    def _get_db():
        with engine.connect() as conn:
            yield conn

    tokens = {}
    monkeypatch.setattr(auth, "_decode", lambda tok: tokens.get(tok))
    monkeypatch.setenv("ADMIN_USER_EMAILS", ADMIN_EMAIL)
    cats.reset_tree_cache()
    A.reset_status_cache()
    app.dependency_overrides[get_db] = _get_db
    c = TestClient(app)
    c.tokens = tokens
    yield c
    app.dependency_overrides.clear()
    cats.reset_tree_cache()
    A.reset_status_cache()


def tok(client, uid, email=None, aal=None, iat=None):
    payload = {"sub": uid, "email": email or f"{uid[:4]}@example.test"}
    if aal:
        payload["aal"] = aal
    if iat:
        payload["iat"] = iat
    t = f"tok-{len(client.tokens)}"
    client.tokens[t] = payload
    return {"Authorization": f"Bearer {t}"}


def admin(client):
    return tok(client, ADMIN, ADMIN_EMAIL, "aal2")


def q(engine, sql, **p):
    with engine.connect() as c:
        return c.execute(text(sql), p).scalar()


def rows(engine, sql, **p):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), p).mappings()]


def suggest(client, h, code=ITEM, cid="D01.C02", comment=None):
    return client.post(f"/items/{code}/category-suggestions", json={"category_id": cid, "comment": comment},
                       headers=h)


# =========================================================================== public reads
def test_tree_is_public_cached_and_active_only(client):
    r = client.get("/categories/tree")
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=3600"
    body = r.json()
    ids = [n["id"] for n in body["nodes"]]
    assert ids == ["D01", "D01.C01", "D01.C02", "D07", "D07.C08", "D07.C08.S01"]   # D07.C99 inactive
    assert body["version"] == "v1.2"
    assert body["nodes"][5] == {"id": "D07.C08.S01", "parent_id": "D07.C08", "level": 3,
                                "name_he": "חמוצים וזיתים בשימורים", "name_en": "D07.C08.S01"}


def test_item_category_full_path(client):
    r = client.get(f"/items/{ITEM}/category").json()
    assert r["category_id"] == "D01.C01" and r["partial"] is False
    assert [p["name_he"] for p in r["path"]] == ["פירות וירקות", "ירקות"]
    assert "source" not in r and "confidence" not in r


def test_low_confidence_shows_the_department_only(client):
    r = client.get(f"/items/{ITEM2}/category").json()
    assert r["partial"] is True and r["category_id"] == "D07"
    assert [p["id"] for p in r["path"]] == ["D07"]
    r = client.get(f"/items/{ITEM3}/category").json()               # medium: full path
    assert r["partial"] is False and [p["id"] for p in r["path"]] == ["D01", "D01.C02"]


def test_item_without_label_has_an_empty_path(client):
    assert client.get(f"/items/{NOLABEL}/category").json() == {
        "item_code": NOLABEL, "category_id": None, "path": [], "partial": False}


# =========================================================================== suggestion gates
def test_anonymous_and_bad_token_get_login_required(client, engine):
    for h in ({}, {"Authorization": "Bearer nope"}):
        r = suggest(client, h)
        assert (r.status_code, r.json()) == (401, {"code": "login_required"})
    assert q(engine, "SELECT count(*) FROM category_suggestions") == 0


def test_terms_not_accepted(client, engine):
    with engine.begin() as c:
        c.execute(text("UPDATE users SET terms_version = '2025-old' WHERE id = :u"), {"u": USER})
    r = suggest(client, tok(client, USER))
    assert (r.status_code, r.json()) == (403, {"code": "terms_required"})
    # A brand-new account (no users row yet, no consent in the token) too.
    r = suggest(client, tok(client, "33333333-0000-4000-8000-000000000003"))
    assert (r.status_code, r.json()) == (403, {"code": "terms_required"})


def test_banned_user(client, engine):
    with engine.begin() as c:
        c.execute(text("UPDATE users SET banned_at = '2026-10-01' WHERE id = :u"), {"u": USER})
    r = suggest(client, tok(client, USER))
    assert (r.status_code, r.json()) == (403, {"code": "account_banned"})


def test_success_records_current_and_suggested(client, engine):
    r = suggest(client, tok(client, USER), comment="  זה פרי  ")
    assert r.status_code == 201 and r.json()["status"] == "open"
    row = rows(engine, "SELECT * FROM category_suggestions")[0]
    assert (row["item_code"], row["user_id"], row["current_category_id"], row["suggested_category_id"],
            row["comment"], row["comment_blocked"], row["status"]) == \
        (ITEM, USER, "D01.C01", "D01.C02", "זה פרי", 0, "open")


def test_profanity_withholds_the_comment_but_answers_the_same(client, engine):
    with engine.begin() as c:
        c.execute(text("INSERT INTO rating_blacklist (term) VALUES ('מילהרעה')"))
    clean = suggest(client, tok(client, OTHER), comment="נראה לי פרי")
    dirty = suggest(client, tok(client, USER), comment="זה מילהרעה ממש")
    assert clean.status_code == dirty.status_code == 201
    assert set(clean.json()) == set(dirty.json()) == {"id", "status"}
    got = {r["user_id"]: r for r in rows(engine, "SELECT * FROM category_suggestions")}
    assert got[USER]["comment"] is None and got[USER]["comment_blocked"] == 1
    assert got[OTHER]["comment"] == "נראה לי פרי" and got[OTHER]["comment_blocked"] == 0


def test_comment_over_200_is_rejected(client):
    assert suggest(client, tok(client, USER), comment="א" * 201).status_code == 422


def test_duplicate_open_suggestion_is_409(client, engine):
    h = tok(client, USER)
    assert suggest(client, h).status_code == 201
    r = suggest(client, h, cid="D07.C08")
    assert (r.status_code, r.json()) == (409, {"code": "already_suggested"})
    assert suggest(client, tok(client, OTHER)).status_code == 201          # another user: fine
    # After a decision the same user may suggest again.
    with engine.begin() as c:
        c.execute(text("UPDATE category_suggestions SET status = 'rejected' WHERE user_id = :u"), {"u": USER})
    assert suggest(client, h, cid="D07.C08").status_code == 201


def test_rate_limit_20_per_day(client, engine):
    with engine.begin() as c:
        for k in range(20):
            c.execute(text("INSERT INTO category_suggestions (item_code, user_id, suggested_category_id, status) "
                           "VALUES (:c, :u, 'D01.C02', 'rejected')"), {"c": f"x{k}", "u": USER})
    r = suggest(client, tok(client, USER))
    assert (r.status_code, r.json()) == (429, {"code": "daily_limit"})
    with engine.begin() as c:     # older than 24 h: no longer counted
        c.execute(text("UPDATE category_suggestions SET created_at = '2020-01-01 00:00:00.000000'"))
    assert suggest(client, tok(client, USER)).status_code == 201


@pytest.mark.parametrize("cid,code", [("D99.C01", "invalid_category"), ("D07.C99", "invalid_category"),
                                      ("D01.C01", "same_category")])
def test_bad_or_same_category(client, engine, cid, code):
    r = suggest(client, tok(client, USER), cid=cid)
    assert (r.status_code, r.json()) == (422, {"code": code})
    assert q(engine, "SELECT count(*) FROM category_suggestions") == 0


def test_unknown_item_is_404(client):
    r = suggest(client, tok(client, USER), code="0000000000000")
    assert (r.status_code, r.json()) == (404, {"code": "item_not_found"})


def test_item_without_label_can_be_suggested(client, engine):
    assert suggest(client, tok(client, USER), code=NOLABEL, cid="D07.C08").status_code == 201
    assert q(engine, "SELECT current_category_id FROM category_suggestions") is None


def test_account_deletion_removes_suggestions(client, engine, monkeypatch):
    monkeypatch.setattr(supa, "delete_auth_user", lambda uid: (True, None))
    assert suggest(client, tok(client, USER)).status_code == 201
    assert suggest(client, tok(client, OTHER)).status_code == 201
    r = client.delete("/account", headers=tok(client, USER, iat=time.time()))
    assert r.status_code == 204
    assert [x["user_id"] for x in rows(engine, "SELECT user_id FROM category_suggestions")] == [OTHER]


# =========================================================================== admin: gate
ADMIN_CALLS = [
    ("GET", "/admin/categories/items?q=729", None),
    ("GET", f"/admin/categories/items/{ITEM}", None),
    ("PUT", f"/admin/categories/items/{ITEM}", {"category_id": "D01.C02"}),
    ("POST", f"/admin/categories/items/{ITEM}/confirm", None),
    ("POST", "/admin/categories/bulk", {"item_codes": [ITEM], "category_id": "D01.C02"}),
    ("POST", "/admin/categories/revert/1", None),
    ("GET", "/admin/categories/queue/low", None),
    ("GET", "/admin/categories/queue/disagreements", None),
    ("GET", "/admin/categories/queue/unclassified", None),
    ("GET", "/admin/categories/queue/suggestions", None),
    ("POST", f"/admin/category-suggestions/{ITEM}/accept", {"category_id": "D01.C02"}),
    ("POST", f"/admin/category-suggestions/{ITEM}/reject", None),
]


def call(client, method, path, body, headers):
    return client.request(method, path, json=body, headers=headers)


@pytest.mark.parametrize("method,path,body", ADMIN_CALLS)
def test_aal2_matrix_on_every_new_admin_endpoint(client, engine, method, path, body):
    suggest(client, tok(client, USER))
    before = rows(engine, "SELECT * FROM item_categories ORDER BY item_code")
    cases = [
        ({}, "admin_required"),
        ({"Authorization": "Bearer not-a-token"}, "admin_required"),
        (tok(client, USER, aal="aal2"), "admin_required"),
        (tok(client, ADMIN, ADMIN_EMAIL, "aal1"), "mfa_required"),
        (tok(client, ADMIN, ADMIN_EMAIL), "mfa_required"),
    ]
    for h, code in cases:
        r = call(client, method, path, body, h)
        assert (r.status_code, r.json()) == (403, {"code": code}), (path, h, r.text)
    assert rows(engine, "SELECT * FROM item_categories ORDER BY item_code") == before
    assert q(engine, "SELECT count(*) FROM admin_audit") == 0
    assert q(engine, "SELECT count(*) FROM category_suggestions WHERE status = 'open'") == 1
    r = call(client, method, path, body, admin(client))
    assert r.status_code in (200, 404), (path, r.text)       # revert/1: no audit row yet -> 404


# =========================================================================== admin: search / detail
def test_search_by_name_and_barcode(client):
    r = client.get("/admin/categories/items", params={"q": "זיתים יכין"}, headers=admin(client)).json()
    assert [i["item_code"] for i in r["items"]] == [ITEM2]
    assert r["items"][0]["label"]["category_id"] == "D07.C08.S01"
    r = client.get("/admin/categories/items", params={"q": "72900000"}, headers=admin(client)).json()
    assert [i["item_code"] for i in r["items"]] == [ITEM2, NOLABEL, ITEM, ITEM3]   # chains_live desc
    assert r["items"][1]["label"] is None


def test_item_detail(client):
    suggest(client, tok(client, USER), code=ITEM2, cid="D07.C08")
    d = client.get(f"/admin/categories/items/{ITEM2}", headers=admin(client)).json()
    assert d["chains_live"] == 9 and d["item_name"].startswith("זיתים")
    assert d["label"]["source"] == "ai" and d["label"]["confidence"] == "low"
    assert d["label"]["path_he"] == "מזווה › שימורים › חמוצים וזיתים בשימורים"
    assert d["open_suggestions"] == 1 and d["audit"] == []
    assert USER not in json.dumps(d)
    r = client.get("/admin/categories/items/0000", headers=admin(client))
    assert (r.status_code, r.json()) == (404, {"code": "item_not_found"})


# =========================================================================== admin: writes + audit
def audit_rows(engine):
    out = rows(engine, "SELECT * FROM admin_audit ORDER BY id")
    for r in out:
        r["detail"] = json.loads(r["detail"]) if r["detail"] else None
    return out


def assert_no_identities(engine):
    blob = json.dumps(rows(engine, "SELECT * FROM admin_audit"), ensure_ascii=False)
    for secret in (USER, OTHER, ADMIN, "@example.test"):
        assert secret not in blob


def test_set_writes_a_manual_reviewed_row_and_audits_old_new(client, engine):
    h = {**admin(client), "X-Real-IP": "203.0.113.9"}
    r = client.put(f"/admin/categories/items/{ITEM}", json={"category_id": "D01.C02"}, headers=h)
    assert r.status_code == 200 and r.json()["label"]["path_he"] == "פירות וירקות › פירות"
    row = rows(engine, "SELECT * FROM item_categories WHERE item_code = :c", c=ITEM)[0]
    assert (row["category_id"], row["source"], row["confidence"], row["reviewed"], row["model"]) == \
        ("D01.C02", "manual", "high", 1, None)
    a = audit_rows(engine)[0]
    assert (a["action"], a["target_type"], a["target_id"]) == ("category.set", "item_category", ITEM)
    assert a["detail"]["old"]["category_id"] == "D01.C01" and a["detail"]["old"]["source"] == "rule"
    assert a["detail"]["new"]["category_id"] == "D01.C02" and a["detail"]["new"]["source"] == "manual"
    assert len(a["ip_hash"]) == 64 and "203.0.113.9" not in json.dumps(a)
    assert_no_identities(engine)


@pytest.mark.parametrize("cid", ["D99", "D07.C99"])
def test_set_refuses_unknown_or_inactive_id(client, engine, cid):
    r = client.put(f"/admin/categories/items/{ITEM}", json={"category_id": cid}, headers=admin(client))
    assert (r.status_code, r.json()) == (422, {"code": "invalid_category"})
    assert q(engine, "SELECT category_id FROM item_categories WHERE item_code = :c", c=ITEM) == "D01.C01"


def test_manual_write_survives_rule_and_ai_imports(client, engine):
    client.put(f"/admin/categories/items/{ITEM}", json={"category_id": "D01.C02"}, headers=admin(client))
    client.post(f"/admin/categories/items/{ITEM3}/confirm", headers=admin(client))
    with engine.begin() as c:                      # what import_categories --apply runs
        for src in ("rule", "gs1", "ai"):
            for code in (ITEM, ITEM3):
                c.execute(text(store.upsert_item_categories_sql(manual=False)),
                          {"item_code": code, "category_id": "D07.C08", "confidence": "high", "source": src,
                           "detail": f"{src}: import", "model": None, "taxonomy_version": "v1.2", "reviewed": False})
        c.execute(text(store.INSERT_NEW_ITEM_CATEGORIES_SQL),       # the build hook
                  {"item_code": ITEM, "category_id": "D07.C08", "confidence": "high", "source": "rule",
                   "detail": "x", "model": None, "taxonomy_version": "v1.2", "reviewed": False})
    got = {r["item_code"]: r for r in rows(engine, "SELECT * FROM item_categories")}
    assert (got[ITEM]["category_id"], got[ITEM]["source"]) == ("D01.C02", "manual")
    assert (got[ITEM3]["category_id"], got[ITEM3]["source"], got[ITEM3]["reviewed"]) == ("D01.C02", "gs1", 1)
    # A not-reviewed automated row is still updated (the guard is not too strict).
    with engine.begin() as c:
        c.execute(text(store.upsert_item_categories_sql(manual=False)),
                  {"item_code": ITEM2, "category_id": "D07.C08", "confidence": "high", "source": "ai",
                   "detail": "ai: x", "model": "m", "taxonomy_version": "v1.2", "reviewed": False})
    assert q(engine, "SELECT category_id FROM item_categories WHERE item_code = :c", c=ITEM2) == "D07.C08"


def test_confirm_marks_reviewed_without_change(client, engine):
    r = client.post(f"/admin/categories/items/{ITEM3}/confirm", headers=admin(client))
    assert r.status_code == 200
    row = rows(engine, "SELECT * FROM item_categories WHERE item_code = :c", c=ITEM3)[0]
    assert (row["category_id"], row["source"], row["confidence"], row["reviewed"]) == ("D01.C02", "gs1", "medium", 1)
    a = audit_rows(engine)[0]
    assert a["action"] == "category.confirm"
    assert a["detail"]["old"]["reviewed"] is False and a["detail"]["new"]["reviewed"] is True
    r = client.post(f"/admin/categories/items/{NOLABEL}/confirm", headers=admin(client))
    assert (r.status_code, r.json()) == (404, {"code": "no_label"})


def test_bulk_moves_and_audits_each_item(client, engine):
    r = client.post("/admin/categories/bulk", headers=admin(client),
                    json={"item_codes": [ITEM, ITEM3, NOLABEL, ITEM, "0000"], "category_id": "D07.C08"})
    assert r.json() == {"ok": True, "updated": 3, "skipped": ["0000"]}
    assert {r["item_code"]: r["category_id"] for r in rows(engine, "SELECT * FROM item_categories")} == {
        ITEM: "D07.C08", ITEM2: "D07.C08.S01", ITEM3: "D07.C08", NOLABEL: "D07.C08"}
    a = audit_rows(engine)
    assert [x["action"] for x in a] == ["category.bulk"] * 3
    assert {x["target_id"]: (x["detail"]["old"] or {}).get("category_id") for x in a} == {
        ITEM: "D01.C01", ITEM3: "D01.C02", NOLABEL: None}
    over = client.post("/admin/categories/bulk", headers=admin(client),
                       json={"item_codes": [str(k) for k in range(101)], "category_id": "D07.C08"})
    assert over.status_code == 422


def test_revert_restores_the_old_label_and_is_audited(client, engine):
    client.put(f"/admin/categories/items/{ITEM}", json={"category_id": "D01.C02"}, headers=admin(client))
    set_id = audit_rows(engine)[0]["id"]
    r = client.post(f"/admin/categories/revert/{set_id}", headers=admin(client))
    assert r.status_code == 200
    row = rows(engine, "SELECT * FROM item_categories WHERE item_code = :c", c=ITEM)[0]
    assert (row["category_id"], row["source"], row["confidence"], row["reviewed"], row["detail"]) == \
        ("D01.C01", "rule", "high", 0, "rule: מלפפון")
    a = audit_rows(engine)[-1]
    assert a["action"] == "category.revert" and a["detail"]["reverted_audit_id"] == set_id
    assert a["detail"]["old"]["category_id"] == "D01.C02" and a["detail"]["new"]["category_id"] == "D01.C01"
    # Reverting the same change again: the label is no longer its "new".
    r = client.post(f"/admin/categories/revert/{set_id}", headers=admin(client))
    assert (r.status_code, r.json()) == (409, {"code": "changed_since"})
    # The revert itself is revertible (redo).
    assert client.post(f"/admin/categories/revert/{a['id']}", headers=admin(client)).status_code == 200
    assert q(engine, "SELECT source FROM item_categories WHERE item_code = :c", c=ITEM) == "manual"
    d = client.get(f"/admin/categories/items/{ITEM}", headers=admin(client)).json()
    assert [x["action"] for x in d["audit"]] == ["category.revert", "category.revert", "category.set"]
    assert d["audit"][-1]["old_category_id"] == "D01.C01" and d["audit"][-1]["new_category_id"] == "D01.C02"


def test_revert_of_a_new_label_deletes_it(client, engine):
    client.put(f"/admin/categories/items/{NOLABEL}", json={"category_id": "D07.C08"}, headers=admin(client))
    aid = audit_rows(engine)[0]["id"]
    assert client.post(f"/admin/categories/revert/{aid}", headers=admin(client)).status_code == 200
    assert q(engine, "SELECT count(*) FROM item_categories WHERE item_code = :c", c=NOLABEL) == 0


def test_revert_refuses_unknown_and_non_revertible(client, engine):
    r = client.post("/admin/categories/revert/999", headers=admin(client))
    assert (r.status_code, r.json()) == (404, {"code": "audit_not_found"})
    suggest(client, tok(client, USER))
    client.post(f"/admin/category-suggestions/{ITEM}/reject", headers=admin(client))
    aid = audit_rows(engine)[0]["id"]
    r = client.post(f"/admin/categories/revert/{aid}", headers=admin(client))
    assert (r.status_code, r.json()) == (422, {"code": "not_revertible"})


def test_audit_failure_rolls_the_write_back(client, engine):
    with engine.begin() as c:
        c.execute(text("DROP TABLE admin_audit"))
    r = client.put(f"/admin/categories/items/{ITEM}", json={"category_id": "D01.C02"}, headers=admin(client))
    assert (r.status_code, r.json()) == (500, {"code": "server_error"})
    assert q(engine, "SELECT category_id FROM item_categories WHERE item_code = :c", c=ITEM) == "D01.C01"


# =========================================================================== admin: queues
def test_queues_sorted_by_chains_live(client, engine):
    r = client.get("/admin/categories/queue/low", headers=admin(client)).json()
    assert r["total"] == 1 and [i["item_code"] for i in r["items"]] == [ITEM2]
    with engine.begin() as c:
        c.execute(text("UPDATE item_categories SET confidence = 'low' WHERE item_code = :c"), {"c": ITEM3})
    r = client.get("/admin/categories/queue/low", params={"limit": 1}, headers=admin(client)).json()
    assert r["total"] == 2 and [i["item_code"] for i in r["items"]] == [ITEM2] and r["next_offset"] == 1
    r = client.get("/admin/categories/queue/low", params={"limit": 1, "offset": 1}, headers=admin(client)).json()
    assert [i["item_code"] for i in r["items"]] == [ITEM3] and r["next_offset"] is None
    client.post(f"/admin/categories/items/{ITEM2}/confirm", headers=admin(client))   # reviewed: out
    r = client.get("/admin/categories/queue/low", headers=admin(client)).json()
    assert [i["item_code"] for i in r["items"]] == [ITEM3]


def test_disagreement_queue_parses_the_other_side(client):
    r = client.get("/admin/categories/queue/disagreements", headers=admin(client)).json()
    assert r["total"] == 1
    it = r["items"][0]
    assert it["item_code"] == ITEM2 and it["label"]["category_id"] == "D07.C08.S01"
    assert it["other"] == {"source": "rule", "category_id": "D01.C02", "path_he": "פירות וירקות › פירות"}


def test_unclassified_queue(client, engine):
    with engine.begin() as c:
        c.execute(text("INSERT INTO items VALUES ('999', 'dead')"))
        c.execute(text("INSERT INTO search_items (item_code, name_norm, chains_live) VALUES ('999', 'dead', 0)"))
        c.execute(text("INSERT INTO search_items (item_code, name_norm, chains_live, is_pseudo) "
                       "VALUES ('888', 'coupon', 4, 1)"))
    r = client.get("/admin/categories/queue/unclassified", headers=admin(client)).json()
    assert [i["item_code"] for i in r["items"]] == [NOLABEL] and r["items"][0]["label"] is None


def test_suggestion_queue_groups_without_identities(client, engine):
    with engine.begin() as c:
        c.execute(text("INSERT INTO rating_blacklist (term) VALUES ('מילהרעה')"))
        c.execute(text("INSERT INTO users (id, email, terms_version) VALUES ('u3', 'u3@example.test', :t)"),
                  {"t": TERMS_VERSION})
    suggest(client, tok(client, USER), cid="D01.C02", comment="פרי " + "ארוך " * 30)
    suggest(client, tok(client, OTHER), cid="D01.C02", comment="מילהרעה")
    suggest(client, tok(client, "u3", "u3@example.test"), cid="D07.C08")
    suggest(client, tok(client, USER), code=ITEM2, cid="D07.C08")
    r = client.get("/admin/categories/queue/suggestions", headers=admin(client))
    body = r.json()
    assert body["total"] == 2
    assert [i["item_code"] for i in body["items"]] == [ITEM2, ITEM]          # chains_live 9 before 5
    it = body["items"][1]
    assert it["count"] == 3 and it["label"]["category_id"] == "D01.C01"
    assert it["suggested"][0] == {"category_id": "D01.C02", "n": 2, "path_he": "פירות וירקות › פירות"}
    assert it["suggested"][1]["category_id"] == "D07.C08"
    assert [c["text"][:3] for c in it["comments"]] == ["פרי"]                 # the blacklisted one never stored
    for secret in (USER, OTHER, "u3", "@example.test"):
        assert secret not in r.text


def test_accept_writes_manual_and_closes_all_open(client, engine):
    suggest(client, tok(client, USER), cid="D01.C02")
    suggest(client, tok(client, OTHER), cid="D07.C08")
    r = client.post(f"/admin/category-suggestions/{ITEM}/accept", json={"category_id": "D01.C02"},
                    headers=admin(client))
    assert r.status_code == 200 and r.json()["accepted"] == 2
    assert [x["status"] for x in rows(engine, "SELECT status FROM category_suggestions")] == ["accepted"] * 2
    assert q(engine, "SELECT decided_at IS NOT NULL FROM category_suggestions LIMIT 1") == 1
    row = rows(engine, "SELECT * FROM item_categories WHERE item_code = :c", c=ITEM)[0]
    assert (row["category_id"], row["source"], row["reviewed"]) == ("D01.C02", "manual", 1)
    a = audit_rows(engine)[0]
    assert a["action"] == "category_suggestion.accept"
    assert a["detail"]["old"]["category_id"] == "D01.C01" and a["detail"]["new"]["category_id"] == "D01.C02"
    assert a["detail"]["suggested"] == {"D01.C02": 1, "D07.C08": 1} and a["detail"]["suggestions"] == 2
    assert_no_identities(engine)
    r = client.post(f"/admin/category-suggestions/{ITEM}/accept", json={"category_id": "D01.C02"},
                    headers=admin(client))
    assert (r.status_code, r.json()) == (404, {"code": "no_open_suggestions"})
    s = client.get("/admin/status", headers=admin(client)).json()
    assert s["category_suggestions"] == {"pending": 0, "pending_items": 0}


def test_reject_closes_all_open_and_label_stays(client, engine):
    suggest(client, tok(client, USER), cid="D01.C02")
    r = client.post(f"/admin/category-suggestions/{ITEM}/reject", headers=admin(client))
    assert r.json() == {"ok": True, "rejected": 1}
    assert q(engine, "SELECT status FROM category_suggestions") == "rejected"
    assert q(engine, "SELECT category_id FROM item_categories WHERE item_code = :c", c=ITEM) == "D01.C01"
    a = audit_rows(engine)[0]
    assert a["action"] == "category_suggestion.reject" and a["detail"]["suggested"] == {"D01.C02": 1}
    assert_no_identities(engine)


def test_status_counts_pending_suggestions(client):
    suggest(client, tok(client, USER), cid="D01.C02")
    suggest(client, tok(client, OTHER), cid="D07.C08")
    suggest(client, tok(client, USER), code=ITEM2, cid="D07.C08")
    s = client.get("/admin/status", headers=admin(client)).json()
    assert s["category_suggestions"] == {"pending": 3, "pending_items": 2}


def test_status_suggestions_null_without_the_table(client, engine):
    with engine.begin() as c:
        c.execute(text("DROP TABLE category_suggestions"))
    s = client.get("/admin/status", headers=admin(client)).json()
    assert s["category_suggestions"] is None and s["moderation"] is not None
