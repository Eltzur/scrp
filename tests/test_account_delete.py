"""Tests for in-app account deletion (SU11A-28): DELETE /account, the deleted-accounts
check in api/auth.py, api/supabase_admin.py and scripts/sweep_account_deletes.py.

No production database and no network: an in-memory SQLite copy of the user-linked
tables (FK actions as verified on the live schema in SU11A-28) stands in for Postgres,
and the Supabase admin call is replaced by a fake.
    python -m pytest tests/test_account_delete.py -q
"""
import datetime as dt
import logging
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

import api.auth as auth
import api.supabase_admin as admin
from api.dependencies import get_db
from api.main import app
from scripts.sweep_account_deletes import sweep

UID = "8f14e45f-ceea-467a-a4f5-1d3b5c2b9a01"
OTHER = "c9f0f895-fb98-4b91-9c7a-0e5d7b6a1c22"
SECRET = "sb_secret_TESTKEY_must_never_leak_0123456789"
LEGACY = "eyJhbGciOiJIUzI1NiJ9.TESTLEGACYKEY.signature"

SCHEMA = [
    "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, display_name TEXT, tier TEXT)",
    "CREATE TABLE saved_baskets (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL "
    "REFERENCES users(id) ON DELETE CASCADE, name TEXT)",
    "CREATE TABLE favorites (user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, barcode TEXT, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE items (item_code TEXT PRIMARY KEY, item_name TEXT)",
    "CREATE TABLE ratings (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL "
    "REFERENCES users(id) ON DELETE CASCADE, item_code TEXT)",
    "CREATE TABLE rating_reports (id INTEGER PRIMARY KEY, rating_id INTEGER NOT NULL "
    "REFERENCES ratings(id) ON DELETE CASCADE, reporter_user_id TEXT REFERENCES users(id) ON DELETE SET NULL)",
    "CREATE TABLE flights.alerts (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL)",
    "CREATE TABLE flights.saved_searches (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL)",
    "CREATE TABLE deleted_accounts (user_id TEXT PRIMARY KEY, "
    "requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, auth_deleted_at TIMESTAMP NULL, "
    "attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT NULL)",
]


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _on_connect(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys = ON")
        dbapi_conn.execute("ATTACH DATABASE ':memory:' AS flights")

    # SQLite reads CAST(x AS uuid) as a NUMERIC cast and would mangle the id;
    # Postgres needs it. Drop only that cast, only in this test engine.
    @event.listens_for(eng, "before_cursor_execute", retval=True)
    def _strip_uuid_cast(_conn, _cur, statement, params, _ctx, _many):
        return statement.replace("CAST(? AS uuid)", "?"), params

    with eng.begin() as c:
        for ddl in SCHEMA:
            c.execute(text(ddl))
    return eng


def seed(engine, uid=UID):
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (id, email) VALUES (:u, 'x@example.test')"), {"u": uid})
        c.execute(text("INSERT INTO saved_baskets (user_id, name) VALUES (:u, 'b')"), {"u": uid})
        c.execute(text("INSERT INTO favorites (user_id, barcode) VALUES (:u, '729')"), {"u": uid})
        rid = c.execute(text("INSERT INTO ratings (user_id, item_code) VALUES (:u, '729')"), {"u": uid}).lastrowid
        # one report filed BY the user on someone else's rating, one filed AGAINST the user's rating
        c.execute(text("INSERT OR IGNORE INTO users (id) VALUES (:o)"), {"o": OTHER})
        orid = c.execute(text("INSERT INTO ratings (user_id, item_code) VALUES (:o, '111')"), {"o": OTHER}).lastrowid
        c.execute(text("INSERT INTO rating_reports (rating_id, reporter_user_id) VALUES (:r, :u)"), {"r": orid, "u": uid})
        c.execute(text("INSERT INTO rating_reports (rating_id, reporter_user_id) VALUES (:r, :o)"), {"r": rid, "o": OTHER})
        c.execute(text("INSERT INTO flights.alerts (user_id) VALUES (:u)"), {"u": uid})
        c.execute(text("INSERT INTO flights.saved_searches (user_id) VALUES (:u)"), {"u": uid})


def count(engine, sql, **p):
    with engine.connect() as c:
        return c.execute(text(sql), p).scalar()


def user_rows(engine, uid=UID):
    return {t: count(engine, f"SELECT count(*) FROM {t} WHERE {col} = :u", u=uid)
            for t, col in [("users", "id"), ("saved_baskets", "user_id"), ("favorites", "user_id"),
                           ("ratings", "user_id"), ("flights.alerts", "user_id"),
                           ("flights.saved_searches", "user_id"), ("rating_reports", "reporter_user_id")]}


def da_row(engine, uid=UID):
    with engine.connect() as c:
        return c.execute(text("SELECT auth_deleted_at, attempts, last_error FROM deleted_accounts "
                              "WHERE user_id = :u"), {"u": uid}).first()


class FakeAdmin:
    """Stands in for httpx.request inside api.supabase_admin."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes) or [204]
        self.calls = []

    def __call__(self, method, url, headers=None, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "json": json})
        out = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(out, Exception):
            raise out
        return httpx.Response(out, request=httpx.Request(method, url))


@pytest.fixture
def client(engine, monkeypatch):
    def _get_db():
        with engine.connect() as conn:
            yield conn

    tokens = {}
    monkeypatch.setattr(auth, "_decode", lambda tok: tokens.get(tok))
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SECRET)
    monkeypatch.delenv("DELETE_PROTECTED_USER_IDS", raising=False)
    app.dependency_overrides[get_db] = _get_db
    c = TestClient(app)
    c.tokens = tokens
    yield c
    app.dependency_overrides.clear()


def bearer(client, uid=UID, age_s=10, iat=True):
    payload = {"sub": uid, "email": "x@example.test"}
    if iat:
        payload["iat"] = int(time.time()) - age_s
    tok = f"tok-{uid}-{age_s}-{iat}"
    client.tokens[tok] = payload
    return {"Authorization": f"Bearer {tok}"}


def use_admin(monkeypatch, *outcomes):
    fake = FakeAdmin(*outcomes)
    monkeypatch.setattr(admin.httpx, "request", fake)
    return fake


# --------------------------------------------------------------------------- DELETE /account
def test_fresh_token_deletes_rows_calls_admin_once_204(client, engine, monkeypatch):
    seed(engine)
    fake = use_admin(monkeypatch, 204)
    r = client.delete("/account", headers=bearer(client))
    assert r.status_code == 204
    assert user_rows(engine) == {k: 0 for k in user_rows(engine)}
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["method"] == "DELETE"
    assert call["url"] == f"https://example.supabase.test/auth/v1/admin/users/{UID}"
    assert call["json"] == {"should_soft_delete": False}
    assert da_row(engine).auth_deleted_at is not None


def test_report_filed_by_user_is_kept_anonymized_and_report_on_users_rating_removed(client, engine, monkeypatch):
    seed(engine)
    use_admin(monkeypatch, 204)
    assert count(engine, "SELECT count(*) FROM rating_reports") == 2
    assert client.delete("/account", headers=bearer(client)).status_code == 204
    # the report the user filed survives with no reporter; the report on the user's own rating is gone
    assert count(engine, "SELECT count(*) FROM rating_reports") == 1
    assert count(engine, "SELECT count(*) FROM rating_reports WHERE reporter_user_id IS NULL") == 1
    assert count(engine, "SELECT count(*) FROM users WHERE id = :o", o=OTHER) == 1


@pytest.mark.parametrize("kw", [{"age_s": 301}, {"age_s": 3600}, {"iat": False}])
def test_stale_or_missing_iat_is_reauth_required_and_nothing_deleted(client, engine, monkeypatch, kw):
    seed(engine)
    fake = use_admin(monkeypatch, 204)
    r = client.delete("/account", headers=bearer(client, **kw))
    assert r.status_code == 401 and r.json() == {"code": "reauth_required"}
    assert user_rows(engine)["users"] == 1 and user_rows(engine)["ratings"] == 1
    assert not fake.calls and da_row(engine) is None


@pytest.mark.parametrize("outcome,code", [(500, "http_500"), (401, "http_401"),
                                          (httpx.ConnectTimeout("t"), "timeout"),
                                          (httpx.ConnectError("c"), "network")])
def test_admin_failure_is_202_pending_and_app_data_already_gone(client, engine, monkeypatch, outcome, code):
    seed(engine)
    use_admin(monkeypatch, outcome)
    r = client.delete("/account", headers=bearer(client))
    assert r.status_code == 202 and r.json() == {"code": "deletion_pending"}
    assert user_rows(engine)["users"] == 0 and user_rows(engine)["favorites"] == 0
    row = da_row(engine)
    assert row.auth_deleted_at is None and row.attempts == 1 and row.last_error == code


def test_missing_admin_key_is_202_pending_config(client, engine, monkeypatch):
    seed(engine)
    fake = use_admin(monkeypatch, 204)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY")
    r = client.delete("/account", headers=bearer(client))
    assert r.status_code == 202 and not fake.calls
    assert da_row(engine).last_error == "config"


def test_repeat_after_202_reaches_admin_and_ends_204(client, engine, monkeypatch):
    seed(engine)
    fake = use_admin(monkeypatch, 503, 204)
    assert client.delete("/account", headers=bearer(client)).status_code == 202
    # the user id is now in deleted_accounts, yet DELETE /account still gets through
    r = client.delete("/account", headers=bearer(client))
    assert r.status_code == 204 and len(fake.calls) == 2
    row = da_row(engine)
    assert row.auth_deleted_at is not None and row.attempts == 1 and row.last_error is None


def test_repeat_when_supabase_says_404_counts_as_success(client, engine, monkeypatch):
    seed(engine)
    use_admin(monkeypatch, 204)
    assert client.delete("/account", headers=bearer(client)).status_code == 204
    use_admin(monkeypatch, 404)
    assert client.delete("/account", headers=bearer(client)).status_code == 204


def test_deleted_user_rejected_on_normal_endpoint_and_row_not_recreated(client, engine, monkeypatch):
    seed(engine)
    use_admin(monkeypatch, 500)
    assert client.delete("/account", headers=bearer(client)).status_code == 202
    r = client.get("/favorites", headers=bearer(client))
    assert r.status_code == 401 and r.json() == {"code": "account_deleted"}
    assert user_rows(engine)["users"] == 0


def test_deleted_user_is_anonymous_on_optional_auth_and_row_not_recreated(engine, monkeypatch, client):
    with engine.begin() as c:
        c.execute(text("INSERT INTO deleted_accounts (user_id) VALUES (:u)"), {"u": UID})
    with engine.connect() as conn:
        creds = auth.HTTPAuthorizationCredentials(scheme="Bearer", credentials="t")
        client.tokens["t"] = {"sub": UID, "email": "x@example.test", "iat": int(time.time())}
        assert auth.get_current_user_optional(creds, conn) is None
    assert user_rows(engine)["users"] == 0


def test_normal_user_still_upserted(client, engine):
    r = client.get("/favorites", headers=bearer(client, uid=OTHER))
    assert r.status_code == 200
    assert count(engine, "SELECT count(*) FROM users WHERE id = :o", o=OTHER) == 1


def test_protected_user_is_403_and_nothing_deleted(client, engine, monkeypatch):
    seed(engine)
    fake = use_admin(monkeypatch, 204)
    monkeypatch.setenv("DELETE_PROTECTED_USER_IDS", f" {OTHER} , {UID.upper()} ")
    r = client.delete("/account", headers=bearer(client))
    assert r.status_code == 403 and r.json() == {"code": "account_protected"}
    assert user_rows(engine)["users"] == 1 and not fake.calls and da_row(engine) is None


def test_flights_rows_deleted_and_other_users_flights_rows_kept(client, engine, monkeypatch):
    seed(engine)
    with engine.begin() as c:
        c.execute(text("INSERT INTO flights.alerts (user_id) VALUES (:o)"), {"o": OTHER})
    use_admin(monkeypatch, 204)
    assert client.delete("/account", headers=bearer(client)).status_code == 204
    assert user_rows(engine)["flights.alerts"] == 0 and user_rows(engine)["flights.saved_searches"] == 0
    assert count(engine, "SELECT count(*) FROM flights.alerts") == 1


def test_no_token_is_401(client):
    assert client.delete("/account").status_code == 401


# --------------------------------------------------------------------------- secrecy
@pytest.mark.parametrize("outcome", [204, 404, 500, httpx.ConnectTimeout("t"),
                                     httpx.ConnectError(f"boom {SECRET}")])
def test_admin_key_never_in_logs_responses_or_errors(client, engine, monkeypatch, caplog, outcome):
    seed(engine)
    use_admin(monkeypatch, outcome)
    caplog.set_level(logging.DEBUG)
    r = client.delete("/account", headers=bearer(client))
    assert SECRET not in caplog.text and SECRET not in r.text
    assert SECRET not in str(da_row(engine))


def test_missing_key_error_text_has_no_value(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.test")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(admin.AdminConfigError) as ei:
        admin.delete_auth_user(UID)
    assert "SUPABASE_SERVICE_ROLE_KEY is not set" in str(ei.value)


# --------------------------------------------------------------------------- header rule
def test_header_rule_apikey_always_bearer_only_for_legacy_jwt_key():
    assert admin.admin_headers(SECRET) == {"apikey": SECRET}
    assert admin.admin_headers(LEGACY) == {"apikey": LEGACY, "Authorization": f"Bearer {LEGACY}"}


@pytest.mark.parametrize("key,bearer_expected", [(SECRET, False), (LEGACY, True)])
def test_header_rule_on_the_wire(monkeypatch, key, bearer_expected):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.test/")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", key)
    fake = use_admin(monkeypatch, 200)
    assert admin.delete_auth_user(UID) == (True, None)
    h = fake.calls[0]["headers"]
    assert h["apikey"] == key and ("Authorization" in h) is bearer_expected
    assert fake.calls[0]["url"] == f"https://example.supabase.test/auth/v1/admin/users/{UID}"


# --------------------------------------------------------------------------- sweep
def test_sweep_retries_pending_and_purges_old_completed(engine, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SECRET)
    p_ok, p_fail = "11a1a1a1-0000-4000-8000-000000000001", "22b2b2b2-0000-4000-8000-000000000002"
    old_done, new_done = "33c3c3c3-0000-4000-8000-000000000003", "44d4d4d4-0000-4000-8000-000000000004"
    with engine.begin() as c:
        c.execute(text("INSERT INTO deleted_accounts (user_id, attempts) VALUES (:a, 1), (:b, 2)"),
                  {"a": p_ok, "b": p_fail})
        c.execute(text("INSERT INTO deleted_accounts (user_id, auth_deleted_at) VALUES "
                       "(:o, '2026-09-01 00:00:00'), (:n, '2026-10-08 00:00:00')"), {"o": old_done, "n": new_done})
    fake = use_admin(monkeypatch, 204, 500)
    lines = []
    with engine.connect() as conn:
        rep = sweep(conn, now=dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc), out=lines.append)
    assert rep == {"pending": 2, "retried_ok": 1, "retried_failed": 1, "purged": 1}
    assert len(fake.calls) == 2
    assert da_row(engine, p_ok).auth_deleted_at is not None
    assert da_row(engine, p_fail).attempts == 3 and da_row(engine, p_fail).last_error == "http_500"
    assert da_row(engine, old_done) is None and da_row(engine, new_done) is not None
    assert not any(SECRET in line for line in lines)


def test_sweep_dry_run_changes_nothing_and_calls_nothing(engine, monkeypatch):
    with engine.begin() as c:
        c.execute(text("INSERT INTO deleted_accounts (user_id) VALUES (:u)"), {"u": UID})
        c.execute(text("INSERT INTO deleted_accounts (user_id, auth_deleted_at) VALUES "
                       "(:o, '2026-09-01 00:00:00')"), {"o": OTHER})
    fake = use_admin(monkeypatch, 204)
    lines = []
    with engine.connect() as conn:
        rep = sweep(conn, dry_run=True, now=dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc), out=lines.append)
    assert rep["pending"] == 1 and not fake.calls
    assert any("would retry" in line and UID in line for line in lines)
    assert any("would purge 1" in line for line in lines)
    assert da_row(engine).attempts == 0 and da_row(engine, OTHER) is not None


@pytest.mark.parametrize("second,want", [(204, 0), (500, 1)])
def test_sweep_main_exit_code_is_nonzero_while_a_retry_still_fails(engine, monkeypatch, second, want):
    # SU11A-32: the systemd unit relies on this to show a failed run.
    import db.db
    from scripts.sweep_account_deletes import main
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SECRET)
    with engine.begin() as c:
        c.execute(text("INSERT INTO deleted_accounts (user_id) VALUES (:a), (:b)"), {"a": UID, "b": OTHER})
    use_admin(monkeypatch, 204, second)
    monkeypatch.setattr(db.db, "connect", engine.connect)
    assert main([]) == want
