"""Tests for UGC stage 2 (SU11A-44): soft auth on the public ratings feed, blocks,
terms consent, bans, the moderation queue / actions and the moderation CLI.

No production database and no network: an in-memory SQLite copy of the tables
involved (columns and FK actions as in su10r1_ratings.sql and
su11a44_ugc_blocks_terms_moderation.sql) stands in for Postgres. Token
verification is replaced by a lookup table, mail and the item-name lookup by fakes.
    python -m pytest tests/test_ugc_blocks.py -q
"""
import base64
import datetime as dt
import json
import logging
import sqlite3

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

import api.auth as auth
import api.routers.ratings as R
from api.dependencies import get_db
from api.main import app
from api.terms import TERMS_VERSION, consent_from_claims

AUTHOR = "11111111-0000-4000-8000-000000000001"
READER = "22222222-0000-4000-8000-000000000002"
OTHER = "33333333-0000-4000-8000-000000000003"
ADMIN = "44444444-0000-4000-8000-000000000004"
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
    "reason TEXT, source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user', 'blacklist', 'block')), "
    f"created_at TEXT NOT NULL DEFAULT ({_TS}))",
    "CREATE TABLE rating_blacklist (id INTEGER PRIMARY KEY, term TEXT NOT NULL UNIQUE)",
    "CREATE TABLE user_blocks (id INTEGER PRIMARY KEY, "
    "blocker_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
    "blocked_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
    "source_rating_id INTEGER NULL REFERENCES ratings(id) ON DELETE SET NULL, "
    f"created_at TEXT NOT NULL DEFAULT ({_TS}), "
    "CONSTRAINT user_blocks_pair_uniq UNIQUE (blocker_id, blocked_id), "
    "CONSTRAINT user_blocks_not_self CHECK (blocker_id <> blocked_id))",
    "CREATE TABLE deleted_accounts (user_id TEXT PRIMARY KEY)",
]

sqlite3.register_adapter(
    dt.datetime, lambda d: d.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"))


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _on_connect(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys = ON")
        # Postgres functions the SQL uses; the format argument is irrelevant here.
        dbapi_conn.create_function("to_char", 2, lambda v, _fmt: v)
        dbapi_conn.create_function(
            "now", 0, lambda: dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"))

    @event.listens_for(eng, "before_cursor_execute", retval=True)
    def _pg_to_sqlite(_conn, _cur, statement, params, _ctx, _many):
        return statement.replace("CAST(? AS uuid)", "?").replace("::float", ""), params

    with eng.begin() as c:
        for ddl in SCHEMA:
            c.execute(text(ddl))
        for uid in (AUTHOR, READER, OTHER):
            c.execute(text("INSERT INTO users (id, email) VALUES (:u, :e)"),
                      {"u": uid, "e": f"{uid[:4]}@example.test"})
        c.execute(text("INSERT INTO items VALUES (:c, 'Milk 3%')"), {"c": ITEM})
    return eng


@pytest.fixture
def mails(monkeypatch):
    sent = []
    monkeypatch.setattr(R, "_item_name", lambda rating_id: "test item")
    monkeypatch.setattr(R, "send_email", lambda **kw: sent.append(kw) or True)
    return sent


@pytest.fixture
def client(engine, monkeypatch, mails):
    def _get_db():
        with engine.connect() as conn:
            yield conn

    tokens = {}

    def fake_decode(tok):
        v = tokens.get(tok)
        if isinstance(v, Exception):
            raise v
        return v

    monkeypatch.setattr(auth, "_decode", fake_decode)
    monkeypatch.delenv("RATINGS_REQUIRE_TERMS", raising=False)
    monkeypatch.setenv("ADMIN_USER_EMAILS", "admin@example.test")
    app.dependency_overrides[get_db] = _get_db
    c = TestClient(app)
    c.tokens = tokens
    yield c
    app.dependency_overrides.clear()


def bearer(client, uid, email=None, meta=None):
    payload = {"sub": uid, "email": email or f"{uid[:4]}@example.test"}
    if meta is not None:
        payload["user_metadata"] = meta
    tok = f"tok-{uid}-{len(client.tokens)}"
    client.tokens[tok] = payload
    return {"Authorization": f"Bearer {tok}"}


def admin(client):
    return bearer(client, ADMIN, email="admin@example.test")


def add_rating(engine, uid, comment="nice", rating=3, item=ITEM, status="active"):
    with engine.begin() as c:
        return c.execute(text("INSERT INTO ratings (user_id, item_code, rating, comment, status) "
                              "VALUES (:u, :i, :r, :c, :s)"),
                         {"u": uid, "i": item, "r": rating, "c": comment, "s": status}).lastrowid


def q(engine, sql, **p):
    with engine.connect() as c:
        return c.execute(text(sql), p).scalar()


def feed(client, headers=None):
    r = client.get(f"/items/{ITEM}/ratings", headers=headers or {})
    assert r.status_code == 200
    return r


# --------------------------------------------------------------------------- soft auth
def _jwt_with_kid():
    head = base64.urlsafe_b64encode(json.dumps({"alg": "ES256", "kid": "k1"}).encode()).rstrip(b"=")
    return head.decode() + ".e30.c2ln"


@pytest.mark.parametrize("headers", [
    {},                                              # no header
    {"Authorization": "Bearer x"},                   # garbage
    {"Authorization": "Bearer expired-token"},       # _decode -> None (expired / bad signature)
    {"Authorization": "Basic abc"},                  # not Bearer
    {"Authorization": "Bearer "},                    # empty
])
def test_soft_auth_any_token_problem_is_anonymous(client, engine, headers):
    add_rating(engine, AUTHOR)
    r = feed(client, headers)
    assert [row["is_mine"] for row in r.json()["ratings"]] == [False]


def test_soft_auth_jwks_failure_is_anonymous_not_503(client, engine, monkeypatch):
    add_rating(engine, AUTHOR)
    client.tokens["boom"] = HTTPException(status_code=503)
    assert feed(client, {"Authorization": "Bearer boom"}).json()["count"] == 1

    # And through the real _decode: the JWKS fetch fails.
    monkeypatch.undo()
    monkeypatch.setattr(auth, "_jwks_cache", {})

    def no_jwks():
        raise RuntimeError("jwks down")

    monkeypatch.setattr(auth, "_fetch_jwks", no_jwks)
    assert auth.get_user_id_soft(type("Req", (), {"headers": {"authorization": f"Bearer {_jwt_with_kid()}"}})()) is None


def test_soft_auth_never_creates_a_users_row(client, engine):
    stranger = "55555555-0000-4000-8000-000000000005"
    feed(client, bearer(client, stranger))
    assert q(engine, "SELECT count(*) FROM users WHERE id = :u", u=stranger) == 0


# --------------------------------------------------------------------------- feed
def test_anonymous_feed_shape_unchanged_plus_is_mine_false_and_no_cache_headers(client, engine):
    add_rating(engine, AUTHOR, comment="a")
    r = feed(client)
    body = r.json()
    assert set(body) == {"item_code", "count", "average_pct", "average_raw", "ratings"}
    assert set(body["ratings"][0]) == {"id", "rating", "comment", "created_at", "updated_at", "is_mine"}
    assert body["ratings"][0]["is_mine"] is False
    assert "cache-control" not in r.headers and "vary" not in r.headers


def test_authorized_request_is_private_no_store(client, engine):
    add_rating(engine, AUTHOR)
    for h in (bearer(client, READER), {"Authorization": "Bearer garbage"}):
        r = feed(client, h)
        assert r.headers["cache-control"] == "private, no-store"
        assert "Authorization" in r.headers["vary"]


def test_is_mine(client, engine):
    mine = add_rating(engine, READER, comment="mine")
    add_rating(engine, AUTHOR, comment="theirs")
    rows = {r["id"]: r["is_mine"] for r in feed(client, bearer(client, READER)).json()["ratings"]}
    assert rows[mine] is True and list(rows.values()).count(True) == 1


def test_block_filters_comments_for_blocker_only_and_keeps_aggregate(client, engine, mails):
    bad = add_rating(engine, AUTHOR, comment="rude", rating=1)
    add_rating(engine, OTHER, comment="fine", rating=3)
    before = feed(client).json()
    r = client.post(f"/ratings/{bad}/block-author", headers=bearer(client, READER))
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert AUTHOR not in r.text

    mine = feed(client, bearer(client, READER)).json()
    assert [x["comment"] for x in mine["ratings"]] == ["fine"]
    # A block hides comments, not scores.
    assert (mine["count"], mine["average_pct"]) == (before["count"], before["average_pct"]) == (2, 66.7)
    # Everyone else is unaffected.
    assert len(feed(client, bearer(client, OTHER)).json()["ratings"]) == 2
    assert feed(client).json() == before


def test_block_self_is_400(client, engine):
    rid = add_rating(engine, READER)
    r = client.post(f"/ratings/{rid}/block-author", headers=bearer(client, READER))
    assert r.status_code == 400 and r.json() == {"code": "cannot_block_self"}
    assert q(engine, "SELECT count(*) FROM user_blocks") == 0


def test_block_missing_rating_is_404_and_needs_auth(client):
    assert client.post("/ratings/999/block-author", headers=bearer(client, READER)).status_code == 404
    assert client.post("/ratings/999/block-author").status_code == 401


def test_block_is_idempotent_and_files_one_block_report_and_one_mail(client, engine, mails):
    rid = add_rating(engine, AUTHOR)
    h = bearer(client, READER)
    assert client.post(f"/ratings/{rid}/block-author", headers=h).status_code == 200
    assert client.post(f"/ratings/{rid}/block-author", headers=h).status_code == 200
    assert q(engine, "SELECT count(*) FROM user_blocks") == 1
    assert q(engine, "SELECT count(*) FROM rating_reports WHERE source = 'block' "
                     "AND reporter_user_id = :u AND reason IS NULL", u=READER) == 1
    assert len(mails) == 1 and "block" in mails[0]["subject"]


def test_my_blocks_list_has_labels_and_no_user_ids(client, engine):
    long = "x" * 200
    rid = add_rating(engine, AUTHOR, comment=long)
    client.post(f"/ratings/{rid}/block-author", headers=bearer(client, READER))
    r = client.get("/me/blocks", headers=bearer(client, READER))
    assert r.status_code == 200
    [row] = r.json()
    assert set(row) == {"id", "created_at", "item_code", "item_name", "comment_excerpt"}
    assert row["item_code"] == ITEM and row["item_name"] == "Milk 3%"
    assert row["comment_excerpt"] == "x" * 80
    assert AUTHOR not in r.text and "@" not in r.text


def test_my_blocks_labels_are_null_when_the_rating_is_gone(client, engine):
    rid = add_rating(engine, AUTHOR)
    client.post(f"/ratings/{rid}/block-author", headers=bearer(client, READER))
    with engine.begin() as c:
        c.execute(text("DELETE FROM ratings WHERE id = :r"), {"r": rid})
    [row] = client.get("/me/blocks", headers=bearer(client, READER)).json()
    assert row["item_code"] is None and row["comment_excerpt"] is None


def test_unblock_only_own_rows(client, engine):
    rid = add_rating(engine, AUTHOR, comment="hidden for reader")
    client.post(f"/ratings/{rid}/block-author", headers=bearer(client, READER))
    bid = q(engine, "SELECT id FROM user_blocks")
    assert client.delete(f"/me/blocks/{bid}", headers=bearer(client, OTHER)).status_code == 404
    assert q(engine, "SELECT count(*) FROM user_blocks") == 1
    assert client.delete(f"/me/blocks/{bid}", headers=bearer(client, READER)).status_code == 204
    assert client.delete(f"/me/blocks/{bid}", headers=bearer(client, READER)).status_code == 404
    assert len(feed(client, bearer(client, READER)).json()["ratings"]) == 1


def test_blocks_cascade_when_either_account_is_deleted(engine):
    rid = add_rating(engine, AUTHOR)
    with engine.begin() as c:
        c.execute(text("INSERT INTO user_blocks (blocker_id, blocked_id, source_rating_id) "
                       "VALUES (:a, :b, :r), (:b, :c, NULL)"), {"a": READER, "b": AUTHOR, "c": OTHER, "r": rid})
        c.execute(text("DELETE FROM users WHERE id = :u"), {"u": AUTHOR})
    assert q(engine, "SELECT count(*) FROM user_blocks") == 0


# --------------------------------------------------------------------------- bans
def test_banned_user_gets_403_on_rate_and_report_but_may_block(client, engine):
    rid = add_rating(engine, AUTHOR)
    with engine.begin() as c:
        c.execute(text("UPDATE users SET banned_at = '2026-10-18 10:00:00' WHERE id = :u"), {"u": READER})
    h = bearer(client, READER)
    r = client.post(f"/items/{ITEM}/rating", json={"rating": 2, "comment": "x"}, headers=h)
    assert r.status_code == 403 and r.json() == {"code": "account_banned"}
    r = client.post(f"/ratings/{rid}/report", json={"reason": "x"}, headers=h)
    assert r.status_code == 403 and r.json() == {"code": "account_banned"}
    assert q(engine, "SELECT count(*) FROM ratings WHERE user_id = :u", u=READER) == 0
    assert q(engine, "SELECT count(*) FROM rating_reports") == 0
    assert client.post(f"/ratings/{rid}/block-author", headers=h).status_code == 200


# --------------------------------------------------------------------------- terms
def test_terms_flag_off_allows_rating_without_consent(client, engine):
    r = client.post(f"/items/{ITEM}/rating", json={"rating": 3}, headers=bearer(client, READER))
    assert r.status_code == 200


@pytest.mark.parametrize("flag", ["1", "true", "on", "ON"])
def test_terms_flag_on_requires_consent_then_allows(client, engine, monkeypatch, flag):
    monkeypatch.setenv("RATINGS_REQUIRE_TERMS", flag)
    h = bearer(client, READER)
    r = client.post(f"/items/{ITEM}/rating", json={"rating": 3}, headers=h)
    assert r.status_code == 403 and r.json() == {"code": "terms_required"}

    status = client.get("/me/terms", headers=h).json()
    assert status == {"current_version": TERMS_VERSION, "accepted_version": None,
                      "accepted_at": None, "required": True}
    bad = client.post("/me/terms", json={"version": "1999-1"}, headers=h)
    assert bad.status_code == 400 and bad.json() == {"code": "terms_version_mismatch"}
    assert client.post("/me/terms", json={"version": TERMS_VERSION}, headers=h).status_code == 204
    status = client.get("/me/terms", headers=h).json()
    assert status["accepted_version"] == TERMS_VERSION and status["required"] is False
    assert status["accepted_at"]
    assert client.post(f"/items/{ITEM}/rating", json={"rating": 3}, headers=h).status_code == 200


@pytest.mark.parametrize("flag", ["", "0", "off", "false", "yes"])
def test_terms_flag_values_that_stay_off(client, monkeypatch, flag):
    monkeypatch.setenv("RATINGS_REQUIRE_TERMS", flag)
    r = client.post(f"/items/{ITEM}/rating", json={"rating": 3}, headers=bearer(client, READER))
    assert r.status_code == 200


def test_signup_metadata_is_copied_once_and_never_overwritten(client, engine):
    meta = {"terms_version": TERMS_VERSION, "terms_accepted_at": "2026-10-18T09:00:00.000Z"}
    client.get("/me/terms", headers=bearer(client, OTHER, meta=meta))
    assert q(engine, "SELECT terms_version FROM users WHERE id = :u", u=OTHER) == TERMS_VERSION
    first = q(engine, "SELECT terms_accepted_at FROM users WHERE id = :u", u=OTHER)
    assert first.startswith("2026-10-18 09:00:00")

    later = {"terms_version": "edited-by-user", "terms_accepted_at": "2026-10-19T09:00:00Z"}
    client.get("/me/terms", headers=bearer(client, OTHER, meta=later))
    assert q(engine, "SELECT terms_version FROM users WHERE id = :u", u=OTHER) == TERMS_VERSION
    assert q(engine, "SELECT terms_accepted_at FROM users WHERE id = :u", u=OTHER) == first


def test_no_metadata_leaves_consent_null(client, engine):
    client.get("/me/terms", headers=bearer(client, OTHER))
    assert q(engine, "SELECT terms_version FROM users WHERE id = :u", u=OTHER) is None
    assert q(engine, "SELECT terms_accepted_at FROM users WHERE id = :u", u=OTHER) is None


def test_consent_from_claims_rules():
    now = dt.datetime(2026, 10, 18, 12, tzinfo=dt.timezone.utc)
    ok = consent_from_claims({"user_metadata": {"terms_version": "2026-10-1",
                                                "terms_accepted_at": "2026-10-18T10:00:00Z"}}, now)
    assert ok == ("2026-10-1", dt.datetime(2026, 10, 18, 10, tzinfo=dt.timezone.utc))
    # A future or unparseable timestamp falls back to now.
    assert consent_from_claims({"user_metadata": {"terms_version": "v",
                                                  "terms_accepted_at": "2099-01-01T00:00:00Z"}}, now)[1] == now
    assert consent_from_claims({"user_metadata": {"terms_version": "v",
                                                  "terms_accepted_at": "yesterday"}}, now)[1] == now
    assert consent_from_claims({"user_metadata": {"terms_version": "v"}}, now)[1] == now
    for bad in ({}, {"user_metadata": "x"}, {"user_metadata": {"terms_version": 5}},
                {"user_metadata": {"terms_version": "  "}}, {"user_metadata": {"terms_version": "x" * 33}}):
        assert consent_from_claims(bad, now) == (None, None)


# --------------------------------------------------------------------------- moderation
def _queue(client):
    r = client.get("/admin/ratings/pending", headers=admin(client))
    assert r.status_code == 200
    return {i["id"]: i for i in r.json()["items"]}


def test_queue_needs_admin(client):
    assert client.get("/admin/ratings/pending", headers=bearer(client, READER)).status_code == 404
    assert client.post("/admin/ratings/1/moderate", json={"action": "hide"},
                       headers=bearer(client, READER)).status_code == 404


def test_queue_includes_active_reported_rating_and_keep_drops_it(client, engine):
    rid = add_rating(engine, AUTHOR, comment="disputed")
    assert rid not in _queue(client)
    assert client.post(f"/ratings/{rid}/report", json={"reason": "spam"},
                       headers=bearer(client, READER)).status_code == 201
    item = _queue(client)[rid]
    assert item["status"] == "active" and item["report_count"] == 1
    assert item["report_sources"] == ["user"] and item["report_reasons"] == ["spam"]
    assert item["latest_report_at"] and item["reports"][0]["reason"] == "spam"

    r = client.post(f"/admin/ratings/{rid}/moderate", json={"action": "keep"}, headers=admin(client))
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert rid not in _queue(client)

    # A report filed after the decision puts it back.
    with engine.begin() as c:
        c.execute(text("INSERT INTO rating_reports (rating_id, reporter_user_id, source, created_at) "
                       "VALUES (:r, :u, 'user', '2999-01-01 00:00:00')"), {"r": rid, "u": OTHER})
    assert _queue(client)[rid]["report_count"] == 2


def test_queue_keeps_unreviewed_non_active_ratings(client, engine):
    held = add_rating(engine, AUTHOR, status="hidden")
    assert held in _queue(client)
    client.post(f"/admin/ratings/{held}/moderate", json={"action": "keep"}, headers=admin(client))
    assert held not in _queue(client)


def test_hide_and_restore(client, engine):
    rid = add_rating(engine, AUTHOR)
    assert client.post(f"/admin/ratings/{rid}/moderate", json={"action": "hide"},
                       headers=admin(client)).json()["status"] == "hidden"
    assert feed(client).json()["count"] == 0
    assert client.post(f"/admin/ratings/{rid}/moderate", json={"action": "restore"},
                       headers=admin(client)).json()["status"] == "active"
    assert feed(client).json()["count"] == 1
    assert q(engine, "SELECT reviewed_at FROM ratings WHERE id = :r", r=rid) is not None


def test_moderate_missing_is_404_and_bad_action_422(client, engine):
    assert client.post("/admin/ratings/999/moderate", json={"action": "hide"},
                       headers=admin(client)).status_code == 404
    rid = add_rating(engine, AUTHOR)
    assert client.post(f"/admin/ratings/{rid}/moderate", json={"action": "delete"},
                       headers=admin(client)).status_code == 422


def test_ban_hides_all_active_ratings_of_the_author_and_unban_keeps_them_hidden(client, engine):
    a = add_rating(engine, AUTHOR, comment="one")
    b = add_rating(engine, AUTHOR, comment="two", item="111")
    keep = add_rating(engine, OTHER, comment="other user")
    r = client.post(f"/admin/ratings/{a}/ban-author", json={"ban": True}, headers=admin(client))
    assert r.status_code == 200
    assert r.json() == {"ok": True, "rating_id": a, "banned": True, "ratings_hidden": 2}
    assert AUTHOR not in r.text and "@" not in r.text
    assert q(engine, "SELECT banned_at FROM users WHERE id = :u", u=AUTHOR) is not None
    assert q(engine, "SELECT count(*) FROM ratings WHERE user_id = :u AND status = 'hidden' "
                     "AND reviewed_at IS NOT NULL", u=AUTHOR) == 2
    assert q(engine, "SELECT status FROM ratings WHERE id = :r", r=keep) == "active"
    # The banned author can no longer post.
    assert client.post(f"/items/{ITEM}/rating", json={"rating": 1},
                       headers=bearer(client, AUTHOR)).status_code == 403

    r = client.post(f"/admin/ratings/{b}/ban-author", json={"ban": False}, headers=admin(client))
    assert r.status_code == 200 and r.json()["banned"] is False
    assert q(engine, "SELECT banned_at FROM users WHERE id = :u", u=AUTHOR) is None
    assert q(engine, "SELECT count(*) FROM ratings WHERE user_id = :u AND status = 'hidden'", u=AUTHOR) == 2
    assert client.post("/admin/ratings/999/ban-author", json={"ban": True},
                       headers=admin(client)).status_code == 404


def test_moderation_log_lines_carry_no_email(client, engine, caplog):
    caplog.set_level(logging.DEBUG)
    rid = add_rating(engine, AUTHOR)
    client.post(f"/ratings/{rid}/block-author", headers=bearer(client, READER))
    client.post(f"/ratings/{rid}/report", json={"reason": "x"}, headers=bearer(client, OTHER))
    client.post(f"/admin/ratings/{rid}/moderate", json={"action": "hide"}, headers=admin(client))
    client.post(f"/admin/ratings/{rid}/ban-author", json={"ban": True}, headers=admin(client))
    assert f"rating_id={rid}" in caplog.text
    assert "user block" in caplog.text and "admin hide" in caplog.text and "admin ban-author" in caplog.text
    assert "@" not in caplog.text and AUTHOR not in caplog.text


# --------------------------------------------------------------------------- CLI
def test_cli_dry_run_changes_nothing_and_yes_applies(engine):
    from scripts.moderation import run

    rid = add_rating(engine, AUTHOR, comment="cli")
    with engine.begin() as c:
        c.execute(text("INSERT INTO rating_reports (rating_id, reporter_user_id, reason) "
                       "VALUES (:r, :u, 'spam')"), {"r": rid, "u": READER})
    lines = []
    with engine.connect() as conn:
        assert run(conn, "queue", None, False, out=lines.append) == 0
        assert run(conn, "hide", rid, False, out=lines.append) == 0
        assert run(conn, "ban", rid, False, out=lines.append) == 0
    assert q(engine, "SELECT status FROM ratings WHERE id = :r", r=rid) == "active"
    assert q(engine, "SELECT banned_at FROM users WHERE id = :u", u=AUTHOR) is None
    assert any("dry run" in line for line in lines)
    assert any(f"rating {rid}" in line and "reports 1" in line for line in lines)

    with engine.connect() as conn:
        assert run(conn, "ban", rid, True, out=lines.append) == 0
        assert run(conn, "restore", rid, True, out=lines.append) == 0
        assert run(conn, "hide", 999, True, out=lines.append) == 1
    assert q(engine, "SELECT banned_at FROM users WHERE id = :u", u=AUTHOR) is not None
    assert q(engine, "SELECT status FROM ratings WHERE id = :r", r=rid) == "active"
    text_out = "\n".join(lines)
    assert "@" not in text_out and AUTHOR not in text_out and READER not in text_out
