"""SU11A-54 admin API against a real Postgres: the migration (twice), its grants,
and the endpoints whose SQL SQLite cannot check (jsonb insert, timestamptz
cursor of the history, pg_stat / pg_database_size in the status).

Needs a throwaway Postgres server; SKIPPED unless SCRP_TEST_PG_URL is set, e.g.
    SCRP_TEST_PG_URL=postgresql://postgres:@127.0.0.1:5432/postgres
The test creates (and drops) its own database, su11a54_test, on that server and
never touches any other.
"""
import os
from pathlib import Path

import pytest

PG_URL = os.environ.get("SCRP_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

ROOT = Path(__file__).resolve().parent.parent
DB = "su11a54_test"
MIGRATION = ROOT / "db" / "migrations" / "su11a54_admin.sql"
AUTHOR = "11111111-0000-4000-8000-000000000001"
ADMIN = "44444444-0000-4000-8000-000000000004"
ITEM = "7290004131074"

SCHEMA = """
CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, banned_at TIMESTAMPTZ NULL,
    terms_version TEXT NULL, terms_accepted_at TIMESTAMPTZ NULL);
CREATE TABLE items (item_code TEXT PRIMARY KEY, item_name TEXT);
CREATE TABLE ratings (id SERIAL PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
    item_code TEXT NOT NULL, rating SMALLINT NOT NULL, comment TEXT,
    status TEXT NOT NULL DEFAULT 'active', created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), reviewed_at TIMESTAMPTZ NULL);
CREATE TABLE rating_reports (id SERIAL PRIMARY KEY, rating_id INTEGER NOT NULL REFERENCES ratings(id),
    reporter_user_id TEXT NULL, reason TEXT, source TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE deleted_accounts (user_id UUID PRIMARY KEY);
CREATE TABLE search_items (item_code TEXT PRIMARY KEY, built_at TIMESTAMPTZ NOT NULL DEFAULT now());
"""


@pytest.fixture(scope="module")
def engine():
    from sqlalchemy import create_engine, text
    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {DB}"))
        c.execute(text(f"CREATE DATABASE {DB}"))
        c.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scrp_app') "
                       "THEN CREATE ROLE scrp_app; END IF; END $$"))
    url = PG_URL.rsplit("/", 1)[0] + "/" + DB
    eng = create_engine(url)
    with eng.begin() as c:
        c.exec_driver_sql(SCHEMA)
        c.execute(text("INSERT INTO users (id, email) VALUES (:u, 'a@example.test')"), {"u": AUTHOR})
        c.execute(text("INSERT INTO items VALUES (:i, 'Milk 3%')"), {"i": ITEM})
        c.execute(text("INSERT INTO search_items (item_code) VALUES (:i)"), {"i": ITEM})
    # The migration twice: idempotent.
    raw = eng.raw_connection()
    try:
        cur = raw.cursor()
        for _ in range(2):
            cur.execute(MIGRATION.read_text(encoding="utf-8"))
        raw.commit()
    finally:
        raw.close()
    yield eng
    eng.dispose()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {DB}"))
    admin.dispose()


@pytest.fixture
def client(engine, monkeypatch):
    from fastapi.testclient import TestClient

    import api.auth as auth
    import api.routers.admin as A
    from api.dependencies import get_db
    from api.main import app

    def _get_db():
        with engine.connect() as conn:
            yield conn

    monkeypatch.setattr(auth, "_decode", lambda tok: {"sub": ADMIN, "email": "admin@example.test",
                                                      "aal": "aal2"} if tok == "ok" else None)
    monkeypatch.setenv("ADMIN_USER_EMAILS", "admin@example.test")
    A.reset_status_cache()
    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    A.reset_status_cache()


H = {"Authorization": "Bearer ok"}


def test_table_index_and_grants(engine):
    from sqlalchemy import text
    with engine.connect() as c:
        cols = dict(c.execute(text("SELECT column_name, data_type FROM information_schema.columns "
                                   "WHERE table_name = 'admin_audit'")).all())
        assert cols == {"id": "bigint", "at": "timestamp with time zone", "actor_hash": "text",
                        "action": "text", "target_type": "text", "target_id": "text",
                        "detail": "jsonb", "ip_hash": "text"}
        idx = {r[0] for r in c.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'admin_audit'"))}
        assert {"idx_admin_audit_at", "idx_admin_audit_target"} <= idx
        priv = {p: c.execute(text("SELECT has_table_privilege('scrp_app', 'admin_audit', :p)"), {"p": p}).scalar()
                for p in ("SELECT", "INSERT", "UPDATE", "DELETE")}
        assert priv == {"SELECT": True, "INSERT": True, "UPDATE": False, "DELETE": False}
        assert c.execute(text("SELECT has_sequence_privilege('scrp_app', 'admin_audit_id_seq', 'USAGE')")).scalar()


def test_writes_audit_history_detail_status(client, engine):
    from sqlalchemy import text
    with engine.begin() as c:
        ids = [c.execute(text("INSERT INTO ratings (user_id, item_code, rating, comment) "
                              "VALUES (:u, :i, 2, :c) RETURNING id"),
                         {"u": AUTHOR, "i": ITEM, "c": f"comment {n}"}).scalar() for n in range(3)]
    for rid in ids:
        assert client.post(f"/admin/ratings/{rid}/moderate", json={"action": "hide"}, headers=H).status_code == 200
    assert client.post(f"/admin/ratings/{ids[0]}/ban-author", json={"ban": True}, headers=H).status_code == 200

    with engine.connect() as c:
        det = c.execute(text("SELECT detail FROM admin_audit WHERE action = 'rating.hide' ORDER BY id LIMIT 1")).scalar()
    assert det["status_before"] == "active" and det["status_after"] == "hidden"

    audit = client.get("/admin/audit?limit=10", headers=H).json()
    assert [i["action"] for i in audit["items"]] == ["rating.ban_author"] + ["rating.hide"] * 3
    assert isinstance(audit["items"][0]["detail"], dict)

    # The ban stamped all three with one timestamp: the (reviewed_at, id) cursor
    # must still page through them without a gap or a repeat.
    seen, params = [], {"limit": 1}
    while True:
        page = client.get("/admin/ratings/history", params=params, headers=H).json()
        seen += [i["id"] for i in page["items"]]
        if not page["next"]:
            break
        params = {"limit": 1, **page["next"]}
    assert sorted(seen) == sorted(ids) and len(seen) == len(set(seen))

    d = client.get(f"/admin/ratings/{ids[1]}", headers=H).json()
    assert d["author"]["banned"] is True and d["status"] == "hidden"
    assert [t["action"] for t in d["audit"]] == ["rating.hide"]

    s = client.get("/admin/status", headers=H).json()
    assert s["search_items"]["built_at"] and s["search_item_prices"] is None
    assert isinstance(s["db_size_bytes"], int) and s["db_size_bytes"] > 0
    assert s["moderation"]["banned_users"] == 1 and s["moderation"]["hidden_7d"] == 3
