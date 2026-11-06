"""SU11A-69 statistics against a real Postgres: the migration (twice) and its
rollback, ownership, the CHECK constraints, idempotent replace / upsert,
record_run, GET /admin/stats and the dashboard summary in /admin/status.

SKIPPED unless SCRP_TEST_PG_URL is set, e.g.
    SCRP_TEST_PG_URL=postgresql://postgres@127.0.0.1:55432/postgres
Creates and drops its own database, su11a69_test, and touches no other.
"""
import os
from datetime import date
from pathlib import Path

import pytest

PG_URL = os.environ.get("SCRP_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

ROOT = Path(__file__).resolve().parent.parent
DB = "su11a69_test"
MIG = ROOT / "db" / "migrations" / "su11a69_stats.sql"
ROLLBACK = ROOT / "db" / "migrations" / "su11a69_stats_rollback.sql"
D1, D2, TODAY = date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6)


def _exec_file(eng, path, times=1):
    raw = eng.raw_connection()
    try:
        cur = raw.cursor()
        for _ in range(times):
            cur.execute(path.read_text(encoding="utf-8"))
        raw.commit()
    finally:
        raw.close()


@pytest.fixture(scope="module")
def engine():
    from sqlalchemy import create_engine, text
    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {DB}"))
        c.execute(text(f"CREATE DATABASE {DB}"))
        c.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scrp_app') "
                       "THEN CREATE ROLE scrp_app; END IF; END $$"))
    eng = create_engine(PG_URL.rsplit("/", 1)[0] + "/" + DB)
    _exec_file(eng, MIG, times=2)  # idempotent
    yield eng
    eng.dispose()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {DB}"))
    admin.dispose()


def test_schema_owner_constraints(engine):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    with engine.connect() as c:
        owners = dict(c.execute(text("SELECT tablename, tableowner FROM pg_tables "
                                     "WHERE tablename IN ('stats_daily', 'stats_runs')")).all())
        assert owners == {"stats_daily": "scrp_app", "stats_runs": "scrp_app"}
        cols = {r[0] for r in c.execute(text("SELECT column_name FROM information_schema.columns "
                                             "WHERE table_name = 'stats_daily'"))}
        assert cols == {"source", "metric", "dimension", "day", "value", "updated_at"}  # no ip / ua / url column
    for sql in ("INSERT INTO stats_daily (source, metric, day, value) VALUES ('nginx', 'x', '2026-11-01', 1)",
                "INSERT INTO stats_daily (source, metric, day, value) VALUES ('web', 'x', '2026-11-01', -1)",
                "INSERT INTO stats_runs (source, status) VALUES ('web', 'maybe')"):
        with pytest.raises(IntegrityError), engine.begin() as c:
            c.execute(text(sql))


def test_replace_upsert_record_run(engine):
    from sqlalchemy import text
    from db import stats as S
    rows = [("page_views", "super.xxl.co.il", D1, 10), ("visitors", "super.xxl.co.il", D1, 4),
            ("top_path", "super.xxl.co.il/promos", D1, 6), ("page_views", "super.xxl.co.il", D2, 3)]
    for _ in range(2):
        with engine.begin() as c:
            S.replace_days(c, "web", [D1, D2], rows)
            S.record_run(c, "web", "ok", as_of=D2)
    with engine.begin() as c:
        S.upsert(c, "play", [("installs", "", D1, 5)])
        S.upsert(c, "play", [("installs", "", D1, 7)])  # restated by Play
        S.record_run(c, "play", "error", error="play export: HTTP 403")
    with engine.connect() as c:
        n = c.execute(text("SELECT count(*) FROM stats_daily WHERE source = 'web'")).scalar()
        assert n == 4
        assert c.execute(text("SELECT value FROM stats_daily WHERE source = 'play'")).scalar() == 7
        runs = S.runs(c)
    assert runs["web"]["status"] == "ok" and runs["web"]["as_of"] == "2026-11-05"
    assert runs["play"]["status"] == "error" and runs["play"]["error"] == "play export: HTTP 403"
    assert runs["play"]["last_success_at"] is None and runs["ga4"]["status"] == "never_run"
    with engine.begin() as c:
        S.record_run(c, "play", "ok", as_of=D1)
    with engine.connect() as c:
        r = S.runs(c)["play"]
    assert r["error"] is None and r["last_error_at"] is not None and r["last_success_at"] is not None


def test_admin_stats_and_status_card(engine, monkeypatch):
    from fastapi.testclient import TestClient
    import api.auth as auth
    import api.routers.admin as A
    import api.routers.admin_stats as AS
    from api.dependencies import get_db
    from api.main import app
    from db import stats as S

    with engine.begin() as c:
        S.replace_days(c, "api", [D2], [("calls", "android", D2, 40), ("calls", "web", D2, 60)])

    def _get_db():
        with engine.connect() as conn:
            yield conn
    monkeypatch.setattr(auth, "_decode", lambda tok: {"sub": "a", "email": "admin@example.test", "aal": "aal2"}
                        if tok == "ok" else None)
    monkeypatch.setenv("ADMIN_USER_EMAILS", "admin@example.test")
    monkeypatch.setattr(AS, "_today_il", lambda: TODAY)
    A.reset_status_cache()
    app.dependency_overrides[get_db] = _get_db
    try:
        cl = TestClient(app)
        b = cl.get("/admin/stats?days=30", headers={"Authorization": "Bearer ok"}).json()
        st = cl.get("/admin/status", headers={"Authorization": "Bearer ok"}).json()
        assert cl.get("/admin/stats").status_code == 403
    finally:
        app.dependency_overrides.clear()
        A.reset_status_cache()
    s = {(x["source"], x["metric"], x["dimension"]): x["points"] for x in b["series"]}
    assert s[("web", "page_views", "super.xxl.co.il")] == [["2026-11-04", 10], ["2026-11-05", 3]]
    assert b["top_paths"] == [{"dimension": "super.xxl.co.il/promos", "value": 6}]
    assert "unavailable" not in b
    assert st["stats"] == {"web": {"day": "2026-11-05", "page_views": 3, "visitors": 0},
                           "api": {"day": "2026-11-05", "calls": 100}}


def test_rollback_then_reapply(engine):
    from sqlalchemy import text
    _exec_file(engine, ROLLBACK)
    with engine.connect() as c:
        assert c.execute(text("SELECT to_regclass('stats_daily')")).scalar() is None
    _exec_file(engine, MIG)
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM stats_runs")).scalar() == 0
