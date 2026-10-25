"""SU11A-57 against a real Postgres: the su11a57 migration (twice, after su11a52),
its prerequisite check, the partial unique index, the FK cascade on account
deletion, and the category endpoints whose SQL SQLite cannot check (jsonb audit
detail, timestamptz, to_char, the grouped suggestion queue, the name search; the trigram
index is not needed for LIKE, so the test server needs no pg_trgm).

Needs a throwaway Postgres server; SKIPPED unless SCRP_TEST_PG_URL is set, e.g.
    SCRP_TEST_PG_URL=postgresql://postgres:@127.0.0.1:5432/postgres
Creates (and drops) its own databases su11a57_test and su11a57_noprereq on that
server and never touches any other.
"""
import os
import time
from pathlib import Path

import pytest

PG_URL = os.environ.get("SCRP_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

ROOT = Path(__file__).resolve().parent.parent
DB, DB_BARE = "su11a57_test", "su11a57_noprereq"
CATALOG = ROOT / "db" / "migrations" / "su11a52_catalog.sql"
MIGRATION = ROOT / "db" / "migrations" / "su11a57_category_suggestions.sql"
AUDIT = ROOT / "db" / "migrations" / "su11a54_admin.sql"
USER = "11111111-0000-4000-8000-000000000001"
OTHER = "22222222-0000-4000-8000-000000000002"
ADMIN = "44444444-0000-4000-8000-000000000004"
ITEM, ITEM2 = "7290000000011", "7290000000028"

SCHEMA = """
CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, banned_at TIMESTAMPTZ NULL,
    terms_version TEXT NULL, terms_accepted_at TIMESTAMPTZ NULL);
CREATE TABLE items (item_code TEXT PRIMARY KEY, item_name TEXT);
CREATE TABLE search_items (item_code TEXT PRIMARY KEY, name_norm TEXT NOT NULL DEFAULT '',
    is_pseudo BOOLEAN NOT NULL DEFAULT false, chains_live SMALLINT NOT NULL DEFAULT 0,
    built_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE rating_blacklist (id SERIAL PRIMARY KEY, term TEXT);
CREATE TABLE ratings (id SERIAL PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_code TEXT, rating SMALLINT, comment TEXT, status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), reviewed_at TIMESTAMPTZ);
CREATE TABLE rating_reports (id SERIAL PRIMARY KEY, rating_id INTEGER, reporter_user_id TEXT, reason TEXT,
    source TEXT NOT NULL DEFAULT 'user', created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE deleted_accounts (user_id UUID PRIMARY KEY, requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    auth_deleted_at TIMESTAMPTZ NULL, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT NULL);
CREATE SCHEMA flights;
CREATE TABLE flights.alerts (id SERIAL PRIMARY KEY, user_id UUID NOT NULL);
CREATE TABLE flights.saved_searches (id SERIAL PRIMARY KEY, user_id UUID NOT NULL);
"""
NODES = [("D01", None, 1, "פירות וירקות"), ("D01.C01", "D01", 2, "ירקות"), ("D01.C02", "D01", 2, "פירות"),
         ("D07", None, 1, "מזווה"), ("D07.C08", "D07", 2, "שימורים")]


def _run_sql(eng, path, times=1):
    raw = eng.raw_connection()
    try:
        cur = raw.cursor()
        for _ in range(times):
            cur.execute(path.read_text(encoding="utf-8"))
        raw.commit()
    finally:
        raw.close()


@pytest.fixture(scope="module")
def server():
    from sqlalchemy import create_engine, text
    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        for db in (DB, DB_BARE):
            c.execute(text(f"DROP DATABASE IF EXISTS {db}"))
            c.execute(text(f"CREATE DATABASE {db}"))
        c.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scrp_app') "
                       "THEN CREATE ROLE scrp_app; END IF; END $$"))
    yield admin
    with admin.connect() as c:
        for db in (DB, DB_BARE):
            c.execute(text(f"DROP DATABASE IF EXISTS {db}"))
    admin.dispose()


@pytest.fixture(scope="module")
def engine(server):
    from sqlalchemy import create_engine, text
    eng = create_engine(PG_URL.rsplit("/", 1)[0] + "/" + DB)
    with eng.begin() as c:
        c.exec_driver_sql(SCHEMA)
    _run_sql(eng, CATALOG)
    _run_sql(eng, AUDIT)
    _run_sql(eng, MIGRATION, times=2)                      # idempotent
    with eng.begin() as c:
        for k, (nid, parent, level, name) in enumerate(NODES):
            c.execute(text("INSERT INTO categories (id, parent_id, level, name_he, sort_order, taxonomy_version) "
                           "VALUES (:i, :p, :l, :n, :k, 'v1.2')"), {"i": nid, "p": parent, "l": level, "n": name, "k": k})
        for uid in (USER, OTHER):
            c.execute(text("INSERT INTO users (id, email, terms_version) VALUES (:u, :e, '2026-10-1')"),
                      {"u": uid, "e": f"{uid[:4]}@example.test"})
        for code, name, chains in ((ITEM, "מלפפון חמוץ", 5), (ITEM2, "זיתים ירוקים", 9)):
            c.execute(text("INSERT INTO items VALUES (:c, :n)"), {"c": code, "n": name})
            c.execute(text("INSERT INTO search_items (item_code, name_norm, chains_live) VALUES (:c, :n, :k)"),
                      {"c": code, "n": name, "k": chains})
        c.execute(text("INSERT INTO item_categories (item_code, category_id, confidence, source, detail, "
                       "taxonomy_version) VALUES (:c, 'D01.C01', 'low', 'ai', 'ai: x | DISAGREES with rule D07.C08', "
                       "'v1.2')"), {"c": ITEM})
    yield eng
    eng.dispose()


@pytest.fixture
def client(engine, monkeypatch):
    from fastapi.testclient import TestClient

    import api.auth as auth
    import api.routers.admin as A
    import api.supabase_admin as supa
    from api import categories as cats
    from api.dependencies import get_db
    from api.main import app

    def _get_db():
        with engine.connect() as conn:
            yield conn

    toks = {"admin": {"sub": ADMIN, "email": "admin@example.test", "aal": "aal2"},
            "user": {"sub": USER, "email": "1111@example.test", "iat": time.time()},
            "other": {"sub": OTHER, "email": "2222@example.test"}}
    monkeypatch.setattr(auth, "_decode", lambda tok: toks.get(tok))
    monkeypatch.setattr(supa, "delete_auth_user", lambda uid: (True, None))
    monkeypatch.setenv("ADMIN_USER_EMAILS", "admin@example.test")
    cats.reset_tree_cache()
    A.reset_status_cache()
    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    cats.reset_tree_cache()
    A.reset_status_cache()


H = {k: {"Authorization": f"Bearer {k}"} for k in ("admin", "user", "other")}


def test_migration_needs_su11a52(server):
    from sqlalchemy import create_engine
    eng = create_engine(PG_URL.rsplit("/", 1)[0] + "/" + DB_BARE)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE TABLE users (id TEXT PRIMARY KEY)")
    with pytest.raises(Exception, match="apply db/migrations/su11a52_catalog.sql first"):
        _run_sql(eng, MIGRATION)
    with eng.connect() as c:
        assert c.exec_driver_sql("SELECT to_regclass('public.category_suggestions')").scalar() is None
    eng.dispose()


def test_table_indexes_owner(engine):
    from sqlalchemy import text
    with engine.connect() as c:
        cols = dict(c.execute(text("SELECT column_name, data_type FROM information_schema.columns "
                                   "WHERE table_name = 'category_suggestions'")).all())
        assert cols == {"id": "bigint", "item_code": "text", "user_id": "text", "current_category_id": "text",
                        "suggested_category_id": "text", "comment": "text", "comment_blocked": "boolean",
                        "status": "text", "created_at": "timestamp with time zone",
                        "decided_at": "timestamp with time zone"}
        idx = {r[0] for r in c.execute(text("SELECT indexname FROM pg_indexes "
                                            "WHERE tablename = 'category_suggestions'"))}
        assert {"uq_category_suggestions_open", "idx_category_suggestions_queue",
                "idx_category_suggestions_user"} <= idx
        assert c.execute(text("SELECT tableowner FROM pg_tables WHERE tablename = 'category_suggestions'")
                         ).scalar() == "scrp_app"
        fk = c.execute(text("""
            SELECT confdeltype FROM pg_constraint
            WHERE conrelid = 'category_suggestions'::regclass AND confrelid = 'users'::regclass""")).scalar()
        assert fk == "c"                                   # ON DELETE CASCADE


def test_constraints(engine):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    bad = [
        "INSERT INTO category_suggestions (item_code, user_id, suggested_category_id) VALUES ('x', 'nobody', 'D01')",
        f"INSERT INTO category_suggestions (item_code, user_id, suggested_category_id) VALUES ('x', '{USER}', 'D99')",
        f"INSERT INTO category_suggestions (item_code, user_id, suggested_category_id, comment) "
        f"VALUES ('x', '{USER}', 'D01', repeat('a', 201))",
        f"INSERT INTO category_suggestions (item_code, user_id, suggested_category_id, status) "
        f"VALUES ('x', '{USER}', 'D01', 'maybe')",
    ]
    for sql in bad:
        with pytest.raises(IntegrityError):
            with engine.begin() as c:
                c.execute(text(sql))
    with engine.begin() as c:       # the partial unique index: a second OPEN row fails, a decided one does not
        c.execute(text(f"INSERT INTO category_suggestions (item_code, user_id, suggested_category_id, status) "
                       f"VALUES ('dup', '{USER}', 'D01', 'rejected')"))
        c.execute(text(f"INSERT INTO category_suggestions (item_code, user_id, suggested_category_id) "
                       f"VALUES ('dup', '{USER}', 'D01')"))
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(f"INSERT INTO category_suggestions (item_code, user_id, suggested_category_id) "
                           f"VALUES ('dup', '{USER}', 'D07')"))
    with engine.begin() as c:
        c.execute(text("DELETE FROM category_suggestions"))


def test_end_to_end(client, engine):
    from sqlalchemy import text
    assert client.get(f"/items/{ITEM}/category").json()["path"][0]["id"] == "D01"        # low: dept only
    r = client.post(f"/items/{ITEM}/category-suggestions", json={"category_id": "D07.C08", "comment": "חמוץ"},
                    headers=H["user"])
    assert r.status_code == 201, r.text
    r = client.post(f"/items/{ITEM}/category-suggestions", json={"category_id": "D01.C02"}, headers=H["user"])
    assert (r.status_code, r.json()) == (409, {"code": "already_suggested"})
    assert client.post(f"/items/{ITEM}/category-suggestions", json={"category_id": "D07.C08"},
                       headers=H["other"]).status_code == 201

    s = client.get("/admin/status", headers=H["admin"]).json()
    assert s["category_suggestions"] == {"pending": 2, "pending_items": 1}
    q = client.get("/admin/categories/queue/suggestions", headers=H["admin"]).json()
    assert q["items"][0]["count"] == 2 and q["items"][0]["suggested"][0]["n"] == 2
    assert q["items"][0]["latest_at"] and q["items"][0]["comments"][0]["text"] == "חמוץ"
    for kind in ("low", "disagreements", "unclassified"):
        assert client.get(f"/admin/categories/queue/{kind}", headers=H["admin"]).status_code == 200
    dis = client.get("/admin/categories/queue/disagreements", headers=H["admin"]).json()
    assert dis["items"][0]["other"]["category_id"] == "D07.C08"
    found = client.get("/admin/categories/items", params={"q": "זיתים"}, headers=H["admin"]).json()
    assert [i["item_code"] for i in found["items"]] == [ITEM2]

    r = client.post(f"/admin/category-suggestions/{ITEM}/accept", json={"category_id": "D07.C08"}, headers=H["admin"])
    assert r.status_code == 200 and r.json()["accepted"] == 2
    with engine.connect() as c:
        det = c.execute(text("SELECT detail FROM admin_audit ORDER BY id DESC LIMIT 1")).scalar()
    assert det["old"]["category_id"] == "D01.C01" and det["new"]["source"] == "manual"   # jsonb -> dict

    d = client.get(f"/admin/categories/items/{ITEM}", headers=H["admin"]).json()
    assert d["label"]["decided_at"] and d["audit"][0]["revertible"] is True
    r = client.post(f"/admin/categories/revert/{d['audit'][0]['id']}", headers=H["admin"])
    assert r.status_code == 200, r.text
    with engine.connect() as c:
        row = c.execute(text("SELECT category_id, source, reviewed FROM item_categories WHERE item_code = :c"),
                        {"c": ITEM}).one()
    assert tuple(row) == ("D01.C01", "ai", False)

    assert client.put(f"/admin/categories/items/{ITEM2}", json={"category_id": "D07.C08"},
                      headers=H["admin"]).status_code == 200
    assert client.post("/admin/categories/bulk", json={"item_codes": [ITEM, ITEM2], "category_id": "D01.C02"},
                       headers=H["admin"]).json()["updated"] == 2

    # DELETE /account: the FK cascade removes the user's suggestions.
    with engine.begin() as c:
        c.execute(text("INSERT INTO category_suggestions (item_code, user_id, suggested_category_id) "
                       "VALUES ('z', :u, 'D01')"), {"u": USER})
    assert client.delete("/account", headers=H["user"]).status_code == 204
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM category_suggestions WHERE user_id = :u"), {"u": USER}).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM category_suggestions WHERE user_id = :u"),
                         {"u": OTHER}).scalar() == 1
