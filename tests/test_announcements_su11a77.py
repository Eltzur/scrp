"""SU11A-77: app notices (validation, version bump, the public endpoint, its
cache, admin auth and audit) and the has_image flag on results. No database
server needed (SQLite, the SU11A-57 fixtures).
    python -m pytest tests/test_announcements_su11a77.py -q
"""
import json

import pytest
from sqlalchemy import text

from api import product_images as PI
from api.routers import announcements as public
from db import announcements as A
from tests.test_categories_su11a57 import (  # noqa: F401 - fixtures
    ADMIN, ADMIN_EMAIL, USER, admin, client, engine, q, tok,
)

DDL = ("CREATE TABLE app_announcements (id INTEGER PRIMARY KEY, platform TEXT NOT NULL UNIQUE, "
       "title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '', active BOOLEAN NOT NULL DEFAULT 0, "
       "version INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT (now()), updated_by_hash TEXT)")
OK_TITLE = "עדכון חשוב"
OK_BODY = "המחירים מתעדכנים כל יום. תודה שאתם איתנו."


@pytest.fixture
def ann(engine, monkeypatch):
    with engine.begin() as c:
        c.execute(text(DDL))
        for p in A.PLATFORMS:
            c.execute(text("INSERT INTO app_announcements (platform) VALUES (:p)"), {"p": p})
    opens = []

    def _open():
        opens.append(1)
        return engine.connect()
    monkeypatch.setattr(public, "_open", _open)
    A.invalidate()
    yield opens
    A.invalidate()


# ------------------------------------------------------------------ validation
@pytest.mark.parametrize("word", ["בהרצה", "בטא", "ניסיון", "beta", "BETA", "Trial", "test version", "Test  Version"])
@pytest.mark.parametrize("platform", ["ios", "both"])
@pytest.mark.parametrize("field", ["title", "body"])
def test_beta_words_rejected_for_ios_and_both(word, platform, field):
    t, b = (f"X {word}", OK_BODY) if field == "title" else (OK_TITLE, f"האתר {word} עכשיו")
    with pytest.raises(A.AnnouncementError) as e:
        A.validate(platform, t, b)
    assert (e.value.code, e.value.field) == ("beta_wording_not_allowed_ios", field)


def test_hebrew_words_match_inside_a_word_and_android_may_use_them():
    for w in ("בבטא", "הניסיון", "שבהרצה"):
        assert A.forbidden_word(f"משהו {w}") is not None
    assert A.forbidden_word("alphabetical betaine trials") is None        # Latin: whole words only
    assert A.validate("android", "גרסת בטא", "האתר בהרצה") == ("גרסת בטא", "האתר בהרצה")


@pytest.mark.parametrize("bad", [
    "https://pay.example.com", "http://x.co", "www.xxl.co.il", "ראו xxl.co.il/pay", "pay.com", "mailto:a@b.co",
    "כתבו ל-info@xxl.co.il", "tel:+97231234567", "example.org", "shop.store",
])
def test_links_rejected_on_every_platform(bad):
    for platform in A.PLATFORMS:
        with pytest.raises(A.AnnouncementError) as e:
            A.validate(platform, OK_TITLE, f"{OK_BODY} {bad}")
        assert e.value.code == "links_not_allowed"


@pytest.mark.parametrize("bad", ["<b>כותרת</b>", "a > b", "<script>"])
def test_markup_rejected(bad):
    with pytest.raises(A.AnnouncementError) as e:
        A.validate("android", bad, OK_BODY)
    assert e.value.code == "markup_not_allowed"


def test_lengths_and_cleaning():
    with pytest.raises(A.AnnouncementError) as e:
        A.validate("ios", "", OK_BODY)
    assert (e.value.code, e.value.field) == ("empty", "title")
    with pytest.raises(A.AnnouncementError) as e:
        A.validate("ios", "  \n ", OK_BODY)
    assert e.value.code == "empty"
    with pytest.raises(A.AnnouncementError) as e:
        A.validate("ios", "א" * 61, OK_BODY)
    assert (e.value.code, e.value.field) == ("too_long", "title")
    with pytest.raises(A.AnnouncementError) as e:
        A.validate("ios", OK_TITLE, "א" * 601)
    assert (e.value.code, e.value.field) == ("too_long", "body")
    assert A.validate("ios", "  " + "א" * 60 + "  ", "שורה  אחת\r\n  שורה שתיים ") == ("א" * 60, "שורה אחת\nשורה שתיים")
    with pytest.raises(A.AnnouncementError):
        A.validate("web", OK_TITLE, OK_BODY)


# ------------------------------------------------------------------ public endpoint
def test_unknown_platform_is_400(client, ann):
    for p in ("both", "web", "IOS", ""):
        r = client.get(f"/announcements/active?platform={p}")
        assert (r.status_code, r.json()) == (400, {"code": "unknown_platform"}), p
    assert client.get("/announcements/active").status_code == 422


def test_204_while_inactive_and_platform_filter(client, engine, ann):
    r = client.get("/announcements/active?platform=ios")
    assert r.status_code == 204 and r.content == b"" and r.headers["cache-control"] == "public, max-age=300"
    h = admin(client)
    assert client.put("/admin/announcements/android", json={"title": OK_TITLE, "body": OK_BODY}, headers=h).status_code == 200
    assert client.post("/admin/announcements/android/active", json={"active": True}, headers=h).status_code == 200
    a = client.get("/announcements/active?platform=android")
    assert a.status_code == 200
    assert a.json() == {"id": 2, "version": 1, "title": OK_TITLE, "body": OK_BODY}
    assert client.get("/announcements/active?platform=ios").status_code == 204    # android-only
    # 'both' reaches iOS; the platform's own row wins over 'both'
    client.put("/admin/announcements/both", json={"title": "לכולם", "body": OK_BODY}, headers=h)
    client.post("/admin/announcements/both/active", json={"active": True}, headers=h)
    assert client.get("/announcements/active?platform=ios").json()["title"] == "לכולם"
    assert client.get("/announcements/active?platform=android").json()["title"] == OK_TITLE
    assert set(a.json()) == {"id", "version", "title", "body"}                  # nothing else, no identifiers


def test_cache_reads_the_db_once_per_ttl(client, ann, monkeypatch):
    for _ in range(5):
        client.get("/announcements/active?platform=ios")
    assert len(ann) == 1                                                         # one connection for 5 calls
    t = [1000.0]
    monkeypatch.setattr(A.time, "monotonic", lambda: t[0])
    A.invalidate()
    client.get("/announcements/active?platform=ios")
    t[0] += A.CACHE_TTL_S - 1
    client.get("/announcements/active?platform=ios")
    assert len(ann) == 2
    t[0] += 2
    client.get("/announcements/active?platform=ios")
    assert len(ann) == 3


def test_missing_table_is_no_notice_and_cached(client, engine, monkeypatch):
    calls = []
    monkeypatch.setattr(public, "_open", lambda: calls.append(1) or engine.connect())
    A.invalidate()
    assert client.get("/announcements/active?platform=ios").status_code == 204
    assert client.get("/announcements/active?platform=ios").status_code == 204
    assert len(calls) == 1
    A.invalidate()


# ------------------------------------------------------------------ admin
ADMIN_CALLS = [
    ("GET", "/admin/announcements", None),
    ("PUT", "/admin/announcements/ios", {"title": OK_TITLE, "body": OK_BODY}),
    ("POST", "/admin/announcements/ios/active", {"active": True}),
]


@pytest.mark.parametrize("method,path,body", ADMIN_CALLS)
def test_admin_requires_allowlist_and_aal2(client, engine, ann, method, path, body):
    for h, code in (({}, "admin_required"), (tok(client, USER, aal="aal2"), "admin_required"),
                    (tok(client, ADMIN, ADMIN_EMAIL, "aal1"), "mfa_required")):
        r = client.request(method, path, json=body, headers=h)
        assert (r.status_code, r.json()) == (403, {"code": code}), (path, h)
    assert q(engine, "SELECT count(*) FROM admin_audit") == 0


def test_version_bumps_only_on_text_change_and_every_write_is_audited(client, engine, ann):
    h = admin(client)
    lst = client.get("/admin/announcements", headers=h).json()
    assert [i["platform"] for i in lst["items"]] == ["ios", "android", "both"]
    assert lst["rules"] == {"title_max": 60, "body_max": 600}
    v = lambda: q(engine, "SELECT version FROM app_announcements WHERE platform = 'ios'")  # noqa: E731
    assert client.put("/admin/announcements/ios", json={"title": OK_TITLE, "body": OK_BODY}, headers=h).json()["version"] == 1
    client.put("/admin/announcements/ios", json={"title": f"  {OK_TITLE} ", "body": OK_BODY}, headers=h)   # same after trim
    assert v() == 1
    client.post("/admin/announcements/ios/active", json={"active": True}, headers=h)
    client.post("/admin/announcements/ios/active", json={"active": False}, headers=h)
    assert v() == 1                                                              # on / off: no bump
    client.put("/admin/announcements/ios", json={"title": OK_TITLE, "body": OK_BODY + " עוד"}, headers=h)
    assert v() == 2
    rows = [dict(r) for r in engine.connect().execute(text(
        "SELECT action, target_type, target_id, detail, actor_hash FROM admin_audit ORDER BY id")).mappings()]
    assert [r["action"] for r in rows] == ["announcement.update", "announcement.update", "announcement.activate",
                                           "announcement.deactivate", "announcement.update"]
    assert {r["target_type"] for r in rows} == {"announcement"} and {r["target_id"] for r in rows} == {"ios"}
    d = json.loads(rows[-1]["detail"])
    assert d["before"]["version"] == 1 and d["after"]["version"] == 2
    blob = json.dumps(rows, ensure_ascii=False)
    assert ADMIN not in blob and ADMIN_EMAIL not in blob and len(rows[0]["actor_hash"]) == 64
    assert len(q(engine, "SELECT updated_by_hash FROM app_announcements WHERE platform = 'ios'")) == 64


def test_admin_rejections_are_422_and_write_nothing(client, engine, ann):
    h = admin(client)
    r = client.put("/admin/announcements/ios", json={"title": "גרסת בטא", "body": OK_BODY}, headers=h)
    assert r.status_code == 422 and r.json() == {"code": "beta_wording_not_allowed_ios", "field": "title", "word": "בטא"}
    r = client.put("/admin/announcements/android", json={"title": OK_TITLE, "body": "שלמו ב-https://pay.example"}, headers=h)
    assert (r.status_code, r.json()["code"]) == (422, "links_not_allowed")
    r = client.post("/admin/announcements/ios/active", json={"active": True}, headers=h)   # still empty
    assert (r.status_code, r.json()["code"]) == (422, "empty")
    r = client.put("/admin/announcements/web", json={"title": OK_TITLE, "body": OK_BODY}, headers=h)
    assert r.status_code == 422
    assert client.post("/admin/announcements/web/active", json={"active": True}, headers=h).status_code == 422
    assert q(engine, "SELECT count(*) FROM admin_audit") == 0
    assert q(engine, "SELECT max(version) FROM app_announcements") == 0
    assert client.get("/announcements/active?platform=ios").status_code == 204


def test_saving_drops_the_public_cache(client, ann):
    h = admin(client)
    assert client.get("/announcements/active?platform=android").status_code == 204
    client.put("/admin/announcements/android", json={"title": OK_TITLE, "body": OK_BODY}, headers=h)
    client.post("/admin/announcements/android/active", json={"active": True}, headers=h)
    assert client.get("/announcements/active?platform=android").status_code == 200   # no 5-minute wait here


# ------------------------------------------------------------------ has_image
def test_image_index_one_listing_per_refresh(tmp_path, monkeypatch):
    (tmp_path / "7290000000017.jpg").write_bytes(b"\xff\xd8\xff")
    (tmp_path / "7290000000024.png").write_bytes(b"x")
    (tmp_path / "7290000000031.jpg").mkdir()
    calls = []
    real = PI._list
    monkeypatch.setattr(PI, "_list", lambda d: calls.append(d) or real(d))
    monkeypatch.setattr(PI, "IMAGE_DIR", tmp_path)
    PI.reset()
    assert PI.image_codes(now=0.0) == frozenset({"7290000000017"})
    assert PI.image_codes(now=PI.REFRESH_S - 1) == frozenset({"7290000000017"})
    assert len(calls) == 1
    (tmp_path / "7290000000048.jpg").write_bytes(b"\xff\xd8\xff")
    assert "7290000000048" in PI.image_codes(now=PI.REFRESH_S + 1)
    assert len(calls) == 2
    PI.reset()


def test_has_image_unknown_when_the_directory_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(PI, "IMAGE_DIR", tmp_path / "nope")
    PI.reset()
    assert PI.has_image("7290000000017") is None
    PI.reset()


def test_search_items_carry_has_image(tmp_path, monkeypatch):
    from api.routers.search import _to_model
    (tmp_path / "7290000000017.jpg").write_bytes(b"\xff\xd8\xff")
    monkeypatch.setattr(PI, "IMAGE_DIR", tmp_path)
    PI.reset()
    p = {"item_code": "7290000000017", "canonical_name": "חלב", "manufacturer": None, "unit_of_measure": None,
         "is_weighted": False, "names_per_chain": {}, "quotes": [], "cheapest_price": None,
         "most_expensive_price": None, "chains_count": 0}
    assert _to_model(p).product.has_image is True
    assert _to_model({**p, "item_code": "7290000000024"}).product.has_image is False
    assert '"has_image":true' in _to_model(p).model_dump_json()
    PI.reset()
