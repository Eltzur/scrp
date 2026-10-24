"""Tests for the admin console API (SU11A-54): the three-check gate on every
/admin/* endpoint, the audit log, history / detail / status / audit endpoints,
the /admin/* response headers, CORS for admin.xxl.co.il and the in-process
counters.

Same approach as tests/test_ugc_blocks.py: an in-memory SQLite copy of the
tables involved stands in for Postgres, token verification is a lookup table.
Postgres-only status sections (pg_stat_user_tables, pg_database_size) are
missing on SQLite and must come back as null.
    python -m pytest tests/test_admin_su11a54.py -q
"""
import datetime as dt
import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

import api.auth as auth
import api.routers.admin as A
import api.routers.ratings as R
from api import admin_audit, metrics
from api.dependencies import get_db
from api.main import ADMIN_ORIGIN, ALLOWED_ORIGINS, app

ROOT = Path(__file__).resolve().parent.parent
AUTHOR = "11111111-0000-4000-8000-000000000001"
READER = "22222222-0000-4000-8000-000000000002"
ADMIN = "44444444-0000-4000-8000-000000000004"
ADMIN_EMAIL = "admin@example.test"
ITEM = "7290004131074"

_TS = "strftime('%Y-%m-%d %H:%M:%f','now')"
SCHEMA = [
    "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, display_name TEXT, tier TEXT, "
    "terms_version TEXT NULL, terms_accepted_at TEXT NULL, banned_at TEXT NULL)",
    "CREATE TABLE items (item_code TEXT PRIMARY KEY, item_name TEXT)",
    "CREATE TABLE ratings (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
    "item_code TEXT NOT NULL, rating INTEGER NOT NULL, comment TEXT, status TEXT NOT NULL DEFAULT 'active', "
    f"created_at TEXT NOT NULL DEFAULT ({_TS}), updated_at TEXT NOT NULL DEFAULT ({_TS}), "
    "reviewed_at TEXT NULL, UNIQUE (user_id, item_code))",
    "CREATE TABLE rating_reports (id INTEGER PRIMARY KEY, rating_id INTEGER NOT NULL "
    "REFERENCES ratings(id) ON DELETE CASCADE, reporter_user_id TEXT REFERENCES users(id) ON DELETE SET NULL, "
    "reason TEXT, source TEXT NOT NULL DEFAULT 'user', "
    f"created_at TEXT NOT NULL DEFAULT ({_TS}))",
    "CREATE TABLE deleted_accounts (user_id TEXT PRIMARY KEY)",
    "CREATE TABLE admin_audit (id INTEGER PRIMARY KEY, "
    f"at TEXT NOT NULL DEFAULT ({_TS}), actor_hash TEXT NOT NULL, action TEXT NOT NULL, "
    "target_type TEXT, target_id TEXT, detail TEXT, ip_hash TEXT)",
]

sqlite3.register_adapter(
    dt.datetime, lambda d: d.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"))


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _on_connect(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys = ON")
        dbapi_conn.create_function("to_char", 2, lambda v, _fmt: v)

    @event.listens_for(eng, "before_cursor_execute", retval=True)
    def _pg_to_sqlite(_conn, _cur, statement, params, _ctx, _many):
        return statement.replace("CAST(? AS uuid)", "?").replace("CAST(? AS jsonb)", "?"), params

    with eng.begin() as c:
        for ddl in SCHEMA:
            c.execute(text(ddl))
        for uid in (AUTHOR, READER):
            c.execute(text("INSERT INTO users (id, email) VALUES (:u, :e)"),
                      {"u": uid, "e": f"{uid[:4]}@example.test"})
        c.execute(text("INSERT INTO items VALUES (:c, 'Milk 3%')"), {"c": ITEM})
    return eng


@pytest.fixture
def client(engine, monkeypatch):
    def _get_db():
        with engine.connect() as conn:
            yield conn

    tokens = {}
    monkeypatch.setattr(auth, "_decode", lambda tok: tokens.get(tok))
    monkeypatch.setattr(R, "_item_name", lambda rating_id: "test item")
    monkeypatch.setattr(R, "send_email", lambda **kw: True)
    monkeypatch.setenv("ADMIN_USER_EMAILS", f"other@example.test, {ADMIN_EMAIL.upper()}")
    A.reset_status_cache()
    metrics.reset()
    app.dependency_overrides[get_db] = _get_db
    c = TestClient(app)
    c.tokens = tokens
    yield c
    app.dependency_overrides.clear()
    A.reset_status_cache()


def tok(client, uid, email, aal=None):
    payload = {"sub": uid, "email": email}
    if aal is not None:
        payload["aal"] = aal
    t = f"tok-{len(client.tokens)}"
    client.tokens[t] = payload
    return {"Authorization": f"Bearer {t}"}


def admin(client):
    return tok(client, ADMIN, ADMIN_EMAIL, "aal2")


def add_rating(engine, uid, comment="nice", item=ITEM, status="active"):
    with engine.begin() as c:
        return c.execute(text("INSERT INTO ratings (user_id, item_code, rating, comment, status) "
                              "VALUES (:u, :i, 2, :c, :s)"),
                         {"u": uid, "i": item, "c": comment, "s": status}).lastrowid


def q(engine, sql, **p):
    with engine.connect() as c:
        return c.execute(text(sql), p).scalar()


def call(client, method, path, headers):
    if method == "GET":
        return client.get(path, headers=headers)
    body = {"action": "hide"} if path.endswith("/moderate") else {"ban": True}
    return client.post(path, json=body, headers=headers)


ENDPOINTS = [
    ("GET", "/admin/me"),
    ("GET", "/admin/ratings/pending"),
    ("GET", "/admin/ratings/history"),
    ("GET", "/admin/ratings/{rid}"),
    ("GET", "/admin/status"),
    ("GET", "/admin/audit"),
    ("POST", "/admin/ratings/{rid}/moderate"),
    ("POST", "/admin/ratings/{rid}/ban-author"),
]


# --------------------------------------------------------------------------- the gate
@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_three_check_matrix(client, engine, method, path):
    rid = add_rating(engine, AUTHOR)
    p = path.format(rid=rid)
    cases = [
        ({}, "admin_required"),                                            # no token
        ({"Authorization": "Bearer not-a-token"}, "admin_required"),       # invalid token
        (tok(client, READER, "2222@example.test", "aal2"), "admin_required"),  # not listed
        (tok(client, ADMIN, ADMIN_EMAIL, "aal1"), "mfa_required"),          # listed, no TOTP
        (tok(client, ADMIN, ADMIN_EMAIL), "mfa_required"),                  # no aal claim
    ]
    for headers, code in cases:
        r = call(client, method, p, headers)
        assert (r.status_code, r.json()) == (403, {"code": code}), (p, headers, r.text)
    # Nothing changed on the way.
    assert q(engine, "SELECT status FROM ratings WHERE id = :r", r=rid) == "active"
    assert q(engine, "SELECT count(*) FROM admin_audit") == 0
    r = call(client, method, p, admin(client))
    assert r.status_code == 200, (p, r.text)


def test_empty_allowlist_admits_nobody(client, monkeypatch):
    monkeypatch.setenv("ADMIN_USER_EMAILS", " , ")
    r = client.get("/admin/me", headers=admin(client))
    assert (r.status_code, r.json()) == (403, {"code": "admin_required"})
    monkeypatch.delenv("ADMIN_USER_EMAILS")
    assert client.get("/admin/me", headers=admin(client)).status_code == 403


def test_deleted_admin_account_is_refused(client, engine):
    with engine.begin() as c:
        c.execute(text("INSERT INTO deleted_accounts VALUES (:u)"), {"u": ADMIN})
    r = client.get("/admin/me", headers=admin(client))
    assert (r.status_code, r.json()) == (403, {"code": "admin_required"})


def test_me_and_gate_never_write_the_users_row(client, engine):
    r = client.get("/admin/me", headers=admin(client))
    assert r.json() == {"is_admin": True, "mfa": True}
    assert q(engine, "SELECT count(*) FROM users WHERE id = :u", u=ADMIN) == 0


def test_jwks_outage_stays_503(client, monkeypatch):
    from fastapi import HTTPException

    def boom(_tok):
        raise HTTPException(status_code=503, detail="Auth service temporarily unavailable")
    monkeypatch.setattr(auth, "_decode", boom)
    assert client.get("/admin/me", headers={"Authorization": "Bearer x"}).status_code == 503


# --------------------------------------------------------------------------- audit
def test_every_write_is_audited_without_email_or_id(client, engine):
    rid = add_rating(engine, AUTHOR, comment="bad")
    h = {**admin(client), "X-Real-IP": "203.0.113.7"}
    for action in ("hide", "keep", "restore"):
        assert client.post(f"/admin/ratings/{rid}/moderate", json={"action": action}, headers=h).status_code == 200
    assert client.post(f"/admin/ratings/{rid}/ban-author", json={"ban": True}, headers=h).status_code == 200
    assert client.post(f"/admin/ratings/{rid}/ban-author", json={"ban": False}, headers=h).status_code == 200

    with engine.connect() as c:
        rows = [dict(r) for r in c.execute(text("SELECT * FROM admin_audit ORDER BY id")).mappings()]
    assert [r["action"] for r in rows] == ["rating.hide", "rating.keep", "rating.restore",
                                           "rating.ban_author", "rating.unban_author"]
    expected_actor = hashlib.sha256(f"{admin_audit.AUDIT_SALT}actor:{ADMIN}".encode()).hexdigest()
    for r in rows:
        assert r["target_type"] == "rating" and r["target_id"] == str(rid)
        assert r["actor_hash"] == expected_actor
        assert r["ip_hash"] and len(r["ip_hash"]) == 64
        blob = json.dumps(r)
        for secret in (ADMIN, AUTHOR, READER, "@", "203.0.113.7", ADMIN_EMAIL):
            assert secret not in blob, (secret, blob)
    hide = json.loads(rows[0]["detail"])
    assert hide == {"item_code": ITEM, "status_before": "active", "status_after": "hidden"}
    assert json.loads(rows[3]["detail"]) == {"item_code": ITEM, "ratings_hidden": 1}


def test_audit_failure_rolls_the_write_back(client, engine):
    rid = add_rating(engine, AUTHOR)
    with engine.begin() as c:
        c.execute(text("DROP TABLE admin_audit"))
    r = client.post(f"/admin/ratings/{rid}/moderate", json={"action": "hide"}, headers=admin(client))
    assert (r.status_code, r.json()) == (500, {"code": "server_error"})
    assert "Traceback" not in r.text
    assert q(engine, "SELECT status FROM ratings WHERE id = :r", r=rid) == "active"
    assert q(engine, "SELECT reviewed_at FROM ratings WHERE id = :r", r=rid) is None
    r = client.post(f"/admin/ratings/{rid}/ban-author", json={"ban": True}, headers=admin(client))
    assert r.status_code == 500
    assert q(engine, "SELECT banned_at FROM users WHERE id = :u", u=AUTHOR) is None


def test_audit_endpoint_pages_newest_first(client, engine):
    rid = add_rating(engine, AUTHOR)
    for action in ("hide", "restore", "keep"):
        client.post(f"/admin/ratings/{rid}/moderate", json={"action": action}, headers=admin(client))
    r = client.get("/admin/audit?limit=2", headers=admin(client)).json()
    assert [i["action"] for i in r["items"]] == ["rating.keep", "rating.restore"]
    assert r["next_before"] == r["items"][-1]["id"]
    item = r["items"][0]
    assert set(item) == {"id", "at", "actor", "action", "target_type", "target_id", "detail"}
    assert len(item["actor"]) == 10 and item["detail"]["status_after"] == "active"
    r2 = client.get(f"/admin/audit?limit=2&before={r['next_before']}", headers=admin(client)).json()
    assert [i["action"] for i in r2["items"]] == ["rating.hide"] and r2["next_before"] is None
    assert client.get("/admin/audit?limit=500", headers=admin(client)).status_code == 422


# --------------------------------------------------------------------------- history / detail
def test_history_orders_by_decision_and_pages(client, engine):
    a = add_rating(engine, AUTHOR, comment="a")
    b = add_rating(engine, READER, comment="b")
    c_ = add_rating(engine, AUTHOR, comment="c", item="111")
    # A CLI decision: reviewed, not audited.
    with engine.begin() as c:
        c.execute(text("UPDATE ratings SET reviewed_at = '2026-01-01 00:00:00.000000' WHERE id = :r"), {"r": c_})
    client.post(f"/admin/ratings/{a}/moderate", json={"action": "hide"}, headers=admin(client))
    client.post(f"/admin/ratings/{b}/moderate", json={"action": "keep"}, headers=admin(client))

    r = client.get("/admin/ratings/history?limit=2", headers=admin(client)).json()
    assert [i["id"] for i in r["items"]] == [b, a]
    assert [i["last_action"] for i in r["items"]] == ["rating.keep", "rating.hide"]
    assert r["items"][1]["item_name"] == "Milk 3%" and r["items"][1]["status"] == "hidden"
    assert "user_id" not in r["items"][0]
    nxt = r["next"]
    assert nxt["before_id"] == a
    r2 = client.get("/admin/ratings/history", params={"limit": 2, **nxt}, headers=admin(client)).json()
    assert [i["id"] for i in r2["items"]] == [c_]
    assert r2["items"][0]["last_action"] is None and r2["next"] is None


def test_rating_detail_has_reports_but_no_identities(client, engine):
    rid = add_rating(engine, AUTHOR, comment="rude words")
    with engine.begin() as c:
        c.execute(text("INSERT INTO rating_reports (rating_id, reporter_user_id, reason, source) "
                       "VALUES (:r, :u, 'spam', 'user'), (:r, NULL, 'blacklist: x', 'blacklist')"),
                  {"r": rid, "u": READER})
    client.post(f"/admin/ratings/{rid}/moderate", json={"action": "hide"}, headers=admin(client))
    r = client.get(f"/admin/ratings/{rid}", headers=admin(client))
    assert r.status_code == 200
    d = r.json()
    assert d["comment"] == "rude words" and d["status"] == "hidden" and d["item_name"] == "Milk 3%"
    assert sorted(p["source"] for p in d["reports"]) == ["blacklist", "user"]
    assert all(set(p) == {"id", "source", "reason", "created_at"} for p in d["reports"])
    assert d["author"] == {"banned": False, "active_ratings": 0}
    assert [t["action"] for t in d["audit"]] == ["rating.hide"]
    for secret in (AUTHOR, READER, "@example.test"):
        assert secret not in r.text
    assert client.get("/admin/ratings/9999", headers=admin(client)).status_code == 404


def test_no_admin_response_carries_user_identifiers(client, engine):
    rid = add_rating(engine, AUTHOR)
    with engine.begin() as c:
        c.execute(text("INSERT INTO rating_reports (rating_id, reporter_user_id, reason) VALUES (:r, :u, 'x')"),
                  {"r": rid, "u": READER})
    client.post(f"/admin/ratings/{rid}/moderate", json={"action": "keep"}, headers=admin(client))
    for _m, path in ENDPOINTS:
        if _m == "GET":
            body = client.get(path.format(rid=rid), headers=admin(client)).text
            for secret in (AUTHOR, READER, ADMIN, "@example.test"):
                assert secret not in body, (path, secret)


# --------------------------------------------------------------------------- status
def test_status_shape_with_unavailable_sections_null(client, engine, monkeypatch):
    monkeypatch.setattr(A, "fetch_freshness", lambda conn: {"oldest_last_loaded_at": None, "chains": [
        {"chain_name": "Shufersal", "last_loaded_at": dt.datetime(2026, 10, 24, 6, tzinfo=dt.timezone.utc)},
        {"chain_name": "Keshet", "last_loaded_at": None}]})
    monkeypatch.setattr(A, "fetch_coverage", lambda conn: {"chains": [
        {"chain_id": "1", "chain_name": "Shufersal", "stores_configured": 30, "stores_loaded_72h": 28}]})
    add_rating(engine, AUTHOR, status="hidden")
    client.get("/admin/me", headers=admin(client))   # counted when its answer starts
    r = client.get("/admin/status", headers=admin(client))
    assert r.status_code == 200
    s = r.json()
    assert set(s) >= {"generated_at", "chains", "search_items", "search_item_prices", "moderation",
                      "db_size_bytes", "disk", "memory", "process", "counters", "cache_age_s"}
    assert s["chains"][0] == {"chain_name": "Shufersal", "last_loaded_at": "2026-10-24T06:00:00+00:00",
                              "stores_loaded_72h": 28, "stores_configured": 30}
    assert s["chains"][1]["stores_loaded_72h"] is None and s["chains"][1]["last_loaded_at"] is None
    # Postgres-only or missing on SQLite: null, not an error.
    assert s["search_items"] is None and s["search_item_prices"] is None and s["db_size_bytes"] is None
    assert s["moderation"] == {"pending": 1, "hidden_7d": 1, "banned_users": 0}
    assert set(s["memory"]) == {"process_rss_bytes", "system_total_bytes", "system_available_bytes"}
    assert s["disk"] is None or s["disk"]["free_bytes"] > 0
    c = s["counters"]
    assert c["scope"] == "worker" and c["window_hours"] == 24 and c["requests"] >= 1
    assert set(c) >= {"requests", "http_5xx", "query_timeout", "http_429", "pid", "since"}


def test_status_is_cached_30s(client, monkeypatch):
    calls = []
    monkeypatch.setattr(A, "build_status", lambda conn: calls.append(1) or {"chains": None})
    client.get("/admin/status", headers=admin(client))
    client.get("/admin/status", headers=admin(client))
    assert len(calls) == 1
    A.reset_status_cache()
    client.get("/admin/status", headers=admin(client))
    assert len(calls) == 2


def test_status_chain_failure_is_null(client, monkeypatch):
    def boom(conn):
        raise RuntimeError("no view")
    monkeypatch.setattr(A, "fetch_coverage", boom)
    s = client.get("/admin/status", headers=admin(client)).json()
    assert s["chains"] is None and s["moderation"] is not None


# --------------------------------------------------------------------------- headers, CORS
def test_admin_headers_no_store_and_server_timing(client):
    r = client.get("/admin/me", headers=admin(client))
    assert r.headers["cache-control"] == "no-store"
    assert re.fullmatch(r"total;dur=[0-9.]+", r.headers["server-timing"])
    r = client.get("/admin/me")      # the 403 too
    assert r.headers["cache-control"] == "no-store"


def test_cors_allows_admin_origin(client):
    assert ADMIN_ORIGIN == "https://admin.xxl.co.il" and ADMIN_ORIGIN in ALLOWED_ORIGINS
    r = client.options("/admin/me", headers={
        "Origin": ADMIN_ORIGIN, "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == ADMIN_ORIGIN
    # The console can read a 403 and a JSON 500.
    r = client.get("/admin/me", headers={"Origin": ADMIN_ORIGIN})
    assert r.status_code == 403 and r.headers["access-control-allow-origin"] == ADMIN_ORIGIN
    r = client.get("/admin/me", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_nginx_429_cors_map_includes_admin_host():
    conf = (ROOT / "deploy/nginx/xxl-ratelimit-http.conf").read_text(encoding="utf-8")
    m = re.search(r'"~(\^https://[^"]+)"\s+\$http_origin;', conf)
    assert m, "CORS map regex not found"
    rx = re.compile(m.group(1))
    for ok in ("https://xxl.co.il", "https://www.xxl.co.il", "https://super.xxl.co.il",
               "https://admin.xxl.co.il"):
        assert rx.search(ok), ok
    for bad in ("https://evil.co.il", "https://admin.xxl.co.il.evil.com", "http://admin.xxl.co.il",
                "https://fly.xxl.co.il"):
        assert not rx.search(bad), bad


def test_admin_nginx_site_has_the_required_parts():
    conf = (ROOT / "deploy/nginx/admin.xxl.co.il.conf").read_text(encoding="utf-8")
    for needle in ("server_name admin.xxl.co.il;", "return 301 https://$host$request_uri;",
                   "include snippets/xxl-security-headers.conf;", "Content-Security-Policy-Report-Only",
                   "frame-ancestors 'none'", 'X-Robots-Tag "noindex, nofollow"', "Disallow: /",
                   "try_files $uri $uri/ /index.html;", "limit_req zone=xxl_api",
                   "root /var/www/super.xxl.co.il;"):
        assert needle in conf, needle
    csp = re.search(r'Content-Security-Policy-Report-Only "([^"]+)"', conf).group(1)
    assert "https://api-super.xxl.co.il" in csp and "supabase.co" in csp
    assert "googletagmanager" not in csp      # no analytics on the admin host


# --------------------------------------------------------------------------- counters
def test_counters_window_and_statuses():
    metrics.reset()
    t0 = 1_800_000_000.0
    metrics.record_status(200, now=t0)
    metrics.record_status(503, now=t0)
    metrics.record_status(429, now=t0)
    metrics.inc("query_timeout", now=t0)
    s = metrics.snapshot(now=t0)
    assert (s["requests"], s["http_5xx"], s["http_429"], s["query_timeout"]) == (3, 1, 1, 1)
    assert metrics.snapshot(now=t0 + 23 * 3600)["requests"] == 3
    assert metrics.snapshot(now=t0 + 24 * 3600)["requests"] == 0
    metrics.reset()


def test_unhandled_error_outside_admin_keeps_plain_500(client, monkeypatch):
    def boom(conn):
        raise RuntimeError("x")
    monkeypatch.setattr("api.routers.freshness.fetch_freshness", boom)
    with pytest.raises(RuntimeError):
        client.get("/freshness")
    assert metrics.snapshot()["http_5xx"] == 1
