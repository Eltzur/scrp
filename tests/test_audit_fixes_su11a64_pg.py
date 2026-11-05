"""SU11A-64: the SU11A-63 audit fixes against a real Postgres.
  * H1  POST /promos/bulk: store / barcode caps (422), the row limit (422
        too_many_rows), item_codes keeps exactly those items' rows, a normal
        size is unchanged. The SU11A-58 byte-identical pricing test (which
        posts every fixture store) stays as it is.
  * M1  /promos/today: unknown city / chain 422 before they become a cache key,
        single-flight per key, bounded cache.
  * M2  the users upsert when a new account id brings an email an old row
        still holds: 200, the old row tombstoned, nothing moved; same id unchanged.
  * L2  the app's synced basket (__xxl_mobile_basket__): listed, created and
        updated as before; delete / rename 409; normal baskets unaffected.

Data: the SU11A-58 fixture (tests/test_promo_curation_su11a58_pg.py) plus the
real users / saved_baskets migration and users_email_key. SKIPPED unless
SCRP_TEST_PG_URL is set.
"""
import logging
import threading
import time

import pytest
from sqlalchemy import text

from tests.test_promo_curation_su11a58_pg import (  # noqa: F401  (fixtures)
    PG_URL, ROOT, T1, T2, T3, USER, _run_sql, client, engine, server,
)

pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

U = {"Authorization": "Bearer user"}
RESERVED = "__xxl_mobile_basket__"


@pytest.fixture(scope="module")
def eng(engine):  # noqa: F811
    _run_sql(engine, ROOT / "db" / "migrations" / "add_users_saved_baskets.sql")   # saved_baskets (users exists)
    with engine.begin() as c:
        c.execute(text("ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email)"))
    return engine


@pytest.fixture
def api(eng, client):  # noqa: F811
    import db.query as Q
    Q.reset_today_cache()
    with eng.begin() as c:
        c.execute(text("DELETE FROM saved_baskets"))
    yield client
    Q.reset_today_cache()


def all_stores():
    import tests.test_search_filtered_pg as F0
    return [{"chain_id": s[0], "store_id": str(100 + i)} for i, s in F0.STORES.items()]


# =========================================================================== H1
def test_bulk_store_cap(api):
    import api.routers.promos as R
    many = [{"chain_id": "A", "store_id": str(i)} for i in range(R.BULK_MAX_STORES + 1)]
    r = api.post("/promos/bulk", json={"stores": many})
    assert r.status_code == 422 and "at most 300" in r.text
    assert api.post("/promos/bulk", json={"stores": many[:-1]}).status_code == 200
    r = api.post("/promos/bulk", json={"stores": many[:1], "item_codes": ["1"] * (R.BULK_MAX_ITEMS + 1)})
    assert r.status_code == 422
    assert api.post("/promos/bulk", json={"stores": [{"chain_id": "A", "store_id": "x" * 33}]}).status_code == 422


def test_bulk_normal_size_unchanged_and_item_codes_filter(api):
    full = api.post("/promos/bulk", json={"stores": all_stores()}).json()
    assert full and any(T1 in {p["item_code"] for p in v} for v in full.values())
    codes = [T1, T3]
    part = api.post("/promos/bulk", json={"stores": all_stores(), "item_codes": codes}).json()
    expect = {k: [p for p in v if p["item_code"] in codes] for k, v in full.items()}
    assert part == {k: v for k, v in expect.items() if v}        # same rows, nothing else
    assert api.post("/promos/bulk", json={"stores": all_stores(), "item_codes": []}).json() == {}


def test_bulk_row_limit(api, monkeypatch):
    import api.routers.promos as R
    full = api.post("/promos/bulk", json={"stores": all_stores()}).json()
    n = sum(len(v) for v in full.values())
    monkeypatch.setattr(R, "BULK_MAX_ROWS", n)            # exactly at the limit: served
    assert api.post("/promos/bulk", json={"stores": all_stores()}).json() == full
    monkeypatch.setattr(R, "BULK_MAX_ROWS", n - 1)
    r = api.post("/promos/bulk", json={"stores": all_stores()})
    assert r.status_code == 422 and r.json()["detail"].startswith("too_many_rows")
    r = api.post("/promos/bulk", json={"stores": all_stores(), "item_codes": [T1]})
    assert r.status_code == 200                             # a barcode list keeps it small


# =========================================================================== M1
def test_today_unknown_city_or_chain_is_422(api):
    import tests.test_search_filtered_pg as F0
    import db.query as Q
    for params, code in (({"city": "לא-עיר"}, "unknown_city"), ({"city": ""}, "unknown_city"),
                         ({"chain_id": "nope"}, "unknown_chain")):
        r = api.get("/promos/today", params=params)
        assert (r.status_code, r.json()) == (422, {"code": code}), params
    assert not Q._today_cache                               # no key was made for them
    assert api.get("/promos/today", params={"city": F0.CITIES[0]}).status_code == 200
    assert api.get("/promos/today", params={"chain_id": "A"}).status_code == 200
    assert api.get("/promos/today").status_code == 200


def test_today_key_check_fails_open(api, monkeypatch):
    import db.query as Q
    monkeypatch.setattr(Q, "today_key_values", lambda conn: None)
    import api.routers.promos as R
    monkeypatch.setattr(R, "today_key_values", lambda conn: None)
    assert api.get("/promos/today", params={"city": "לא-עיר"}).status_code == 200


def test_today_single_flight(eng, monkeypatch):
    import db.query as Q
    Q.reset_today_cache()
    calls = []

    def slow(conn, **kw):
        calls.append(kw)
        time.sleep(0.4)
        return [{"item_code": "x", "item_price": 1}]

    monkeypatch.setattr(Q, "fetch_today_promos_live", slow)
    out, errors = [], []

    def worker():
        try:
            with eng.connect() as c:
                out.append(Q.fetch_today_promos(c, city="X"))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(out) == 6 and all(o == out[0] for o in out)
    assert len(calls) == 1                                  # one rebuild for six concurrent misses
    with eng.connect() as c:
        Q.fetch_today_promos(c, city="Y")                    # another key rebuilds on its own
    assert len(calls) == 2


def test_today_cache_is_bounded(eng, monkeypatch):
    import db.query as Q
    Q.reset_today_cache()
    monkeypatch.setattr(Q, "TODAY_MAX_KEYS", 3)
    monkeypatch.setattr(Q, "fetch_today_promos_live", lambda conn, **kw: [])
    with eng.connect() as c:
        for k in range(8):
            Q.fetch_today_promos(c, chain_id=f"c{k}")
    assert len(Q._today_cache) == 3
    assert set(Q._today_key_locks) <= set(Q._today_cache)


# =========================================================================== M2
def _users(eng):
    with eng.connect() as c:
        return {r[0]: r[1] for r in c.execute(text("SELECT id, email FROM users"))}


def test_email_clash_new_id_gets_a_row_old_one_tombstoned(api, eng, monkeypatch, caplog):
    import api.auth as auth
    old, new, email = "aaaaaaaa-0000-4000-8000-00000000000a", "bbbbbbbb-0000-4000-8000-00000000000b", "re@example.test"
    with eng.begin() as c:
        c.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
        c.execute(text("INSERT INTO users (id, email, terms_version) VALUES (:i, :e, 'v1')"), {"i": old, "e": email})
        c.execute(text("INSERT INTO saved_baskets (user_id, name) VALUES (:i, 'ישן')"), {"i": old})
    monkeypatch.setattr(auth, "_decode", lambda tok: {"sub": new, "email": email})
    with caplog.at_level(logging.WARNING, logger="api.auth"):
        r = api.get("/baskets", headers={"Authorization": "Bearer x"})
    assert (r.status_code, r.json()) == (200, [])            # nothing of the old account
    users = _users(eng)
    assert users[new] == email and users[old] == auth.orphan_email(old)
    with eng.connect() as c:
        assert c.execute(text("SELECT user_id FROM saved_baskets WHERE name = 'ישן'")).scalar() == old
        assert c.execute(text("SELECT terms_version FROM users WHERE id = :i"), {"i": new}).scalar() is None
    logged = " ".join(rec.getMessage() for rec in caplog.records)
    assert old in logged and new in logged and email not in logged
    # the same id again: unchanged, no warning
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="api.auth"):
        assert api.get("/baskets", headers={"Authorization": "Bearer x"}).status_code == 200
    assert _users(eng) == users and not caplog.records


def test_same_id_upsert_unchanged(api, eng):
    assert api.get("/baskets", headers=U).status_code == 200
    before = _users(eng)
    assert api.get("/baskets", headers=U).status_code == 200
    assert _users(eng) == before and before[USER] == "1111@example.test"


# =========================================================================== L2
def _create(api, name, items=()):
    r = api.post("/baskets", json={"name": name, "items": list(items)}, headers=U)
    assert r.status_code == 201
    return r.json()["id"]


def test_reserved_basket_app_path_unchanged(api):
    item = {"barcode": T2, "name": "מוצר", "qty": 1}
    rid = _create(api, RESERVED)                                          # the app creates it
    assert RESERVED in [b["name"] for b in api.get("/baskets", headers=U).json()]   # GET still lists it
    r = api.put(f"/baskets/{rid}", json={"items": [item]}, headers=U)      # the app updates its items
    assert r.status_code == 200 and r.json()["items"] == [item]
    assert api.put(f"/baskets/{rid}", json={"name": RESERVED}, headers=U).status_code == 200
    assert api.get(f"/baskets/{rid}", headers=U).status_code == 200


def test_reserved_basket_cannot_be_deleted_or_renamed(api):
    rid = _create(api, RESERVED)
    for r in (api.delete(f"/baskets/{rid}", headers=U), api.put(f"/baskets/{rid}", json={"name": "x"}, headers=U)):
        assert r.status_code == 409 and r.json()["detail"].startswith("reserved_basket")
    other = _create(api, "שבועי")
    r = api.put(f"/baskets/{other}", json={"name": RESERVED}, headers=U)   # nor take its name
    assert r.status_code == 409
    names = sorted(b["name"] for b in api.get("/baskets", headers=U).json())
    assert names == sorted([RESERVED, "שבועי"])


def test_normal_baskets_unaffected(api):
    bid = _create(api, "שבועי")
    assert api.put(f"/baskets/{bid}", json={"name": "חג"}, headers=U).json()["name"] == "חג"
    assert api.delete(f"/baskets/{bid}", headers=U).status_code == 204
    assert api.delete(f"/baskets/{bid}", headers=U).status_code == 404
