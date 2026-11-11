"""SU11A-77 against a real Postgres: the migration (twice; its prerequisite check;
the CHECKs; owner scrp_app) and the notice functions on it (update with FOR
UPDATE, version bump, activate, the platform pick, the cache).
Needs a throwaway Postgres server; SKIPPED unless SCRP_TEST_PG_URL is set.
Creates (and drops) its own databases su11a77_test and su11a77_noprereq.
"""
import os
from pathlib import Path

import pytest

PG_URL = os.environ.get("SCRP_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "db" / "migrations" / "su11a77_announcements.sql"
DB, DB_BARE = "su11a77_test", "su11a77_noprereq"
AUDIT_DDL = ("CREATE TABLE admin_audit (id BIGSERIAL PRIMARY KEY, at TIMESTAMPTZ NOT NULL DEFAULT now(), "
             "actor_hash TEXT NOT NULL, action TEXT NOT NULL, target_type TEXT, target_id TEXT, detail JSONB, ip_hash TEXT)")
HASH = "a" * 64


def _url(db):
    return PG_URL.rsplit("/", 1)[0] + "/" + db


def _apply(eng, times=1):
    raw = eng.raw_connection()
    try:
        cur = raw.cursor()
        for _ in range(times):
            cur.execute(MIGRATION.read_text(encoding="utf-8"))
        raw.commit()
    finally:
        raw.close()


@pytest.fixture(scope="module")
def engine():
    from sqlalchemy import create_engine, text
    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        for db in (DB, DB_BARE):
            c.execute(text(f"DROP DATABASE IF EXISTS {db}"))
            c.execute(text(f"CREATE DATABASE {db}"))
        c.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scrp_app') "
                       "THEN CREATE ROLE scrp_app; END IF; END $$"))
    eng = create_engine(_url(DB))
    with eng.begin() as c:
        c.execute(text(AUDIT_DDL))
    _apply(eng, times=2)                                   # idempotent
    yield eng
    eng.dispose()
    with admin.connect() as c:
        for db in (DB, DB_BARE):
            c.execute(text(f"DROP DATABASE IF EXISTS {db}"))
    admin.dispose()


def test_migration_refuses_without_admin_audit(engine):
    from sqlalchemy import create_engine, text
    bare = create_engine(_url(DB_BARE))
    with pytest.raises(Exception, match="admin_audit is missing"):
        _apply(bare)
    with bare.connect() as c:
        assert c.execute(text("SELECT to_regclass('public.app_announcements')")).scalar() is None
    bare.dispose()


def test_migration_twice_three_rows_owner_and_checks(engine):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    with engine.connect() as c:
        rows = c.execute(text("SELECT platform, title, body, active, version FROM app_announcements ORDER BY id")).all()
        assert [tuple(r) for r in rows] == [("ios", "", "", False, 0), ("android", "", "", False, 0), ("both", "", "", False, 0)]
        assert c.execute(text("SELECT tableowner FROM pg_tables WHERE tablename = 'app_announcements'")).scalar() == "scrp_app"
    for sql in ("UPDATE app_announcements SET title = repeat('א', 61) WHERE platform = 'ios'",
                "UPDATE app_announcements SET body = repeat('א', 601) WHERE platform = 'ios'",
                "UPDATE app_announcements SET active = true WHERE platform = 'ios'",          # no text
                "INSERT INTO app_announcements (platform) VALUES ('web')",
                "INSERT INTO app_announcements (platform) VALUES ('ios')",
                "UPDATE app_announcements SET updated_by_hash = 'short' WHERE platform = 'ios'"):
        with pytest.raises(IntegrityError):
            with engine.begin() as c:
                c.execute(text(sql))


def test_functions_on_postgres(engine):
    from db import announcements as A
    opened = []

    def conn():
        c = engine.connect()
        opened.append(c)
        return c
    A.invalidate()
    with engine.begin() as c:
        before, after = A.update_text(c, "ios", "עדכון", "המחירים מתעדכנים כל יום.", HASH)
        assert (before["version"], after["version"]) == (0, 1)
        A.update_text(c, "ios", "עדכון", "המחירים מתעדכנים כל יום.", HASH)
        assert A.row(c, "ios")["version"] == 1
        A.set_active(c, "ios", True, HASH)
        A.update_text(c, "both", "לכולם", "הודעה לשתי הפלטפורמות.", HASH)
        A.set_active(c, "both", True, HASH)
    n = A.active_for(conn, "ios")
    assert (n.title, n.version) == ("עדכון", 1)                       # its own row wins over 'both'
    assert A.active_for(conn, "android").title == "לכולם"
    with engine.begin() as c:
        with pytest.raises(A.AnnouncementError):
            A.update_text(c, "ios", "גרסת beta", "x", HASH)
        A.set_active(c, "ios", False, HASH)
        A.set_active(c, "both", False, HASH)
    A.invalidate()
    assert A.active_for(conn, "ios") is None
    for c in opened:                                    # the router closes its connections the same way
        c.close()
