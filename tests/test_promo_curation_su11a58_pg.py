"""SU11A-58 promo curation against a real Postgres: the migration (twice, and its
prerequisite check), the admin promo endpoints (search, list, pin, hide, update,
remove, rank shifting, audit before/after without identities), the public read
path (pins first within each branch, hides left out, expiry by date and by a
promotion that left the data) and the HARD RULE: search, compare, basket,
/product, /promos/bulk and the search build are byte-identical with and without
pins / hides.

Data: the SU11A-50 generated fixture (tests/test_search_filtered_pg.py: 5 chains,
dead stores, every promo kind) plus three test promotions that really change
prices, so a hide that leaked into pricing would show.

Needs a throwaway Postgres server; SKIPPED unless SCRP_TEST_PG_URL is set, e.g.
    SCRP_TEST_PG_URL=postgresql://postgres:@127.0.0.1:5432/postgres
Creates (and drops) its own databases su11a58_test and su11a58_noprereq.
"""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PG_URL = os.environ.get("SCRP_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

ROOT = Path(__file__).resolve().parent.parent
DB, DB_BARE = "su11a58_test", "su11a58_noprereq"
MIGRATION = ROOT / "db" / "migrations" / "su11a58_promo_curation.sql"
AUDIT = ROOT / "db" / "migrations" / "su11a54_admin.sql"
ADMIN = "44444444-0000-4000-8000-000000000004"
USER = "11111111-0000-4000-8000-000000000001"
FUTURE = "2099-01-01 00:00:00"
T1, T2, T3 = "7299900000001", "7299900000002", "7299900000003"

EXTRA_SCHEMA = """
ALTER TABLE promos ADD COLUMN promo_type INTEGER, ADD COLUMN allow_multiple_discounts BOOLEAN,
    ADD COLUMN reward_type INTEGER, ADD COLUMN min_purchase_amount NUMERIC, ADD COLUMN promo_start TIMESTAMP,
    ADD COLUMN created_at TIMESTAMP DEFAULT now(), ADD CONSTRAINT promos_uq UNIQUE (store_fk, item_code, promo_id);
CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, banned_at TIMESTAMPTZ NULL,
    terms_version TEXT NULL, terms_accepted_at TIMESTAMPTZ NULL);
CREATE TABLE deleted_accounts (user_id UUID PRIMARY KEY, requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    auth_deleted_at TIMESTAMPTZ NULL, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT NULL);
"""


def _run_sql(eng, path, times=1):
    raw = eng.raw_connection()
    try:
        cur = raw.cursor()
        for _ in range(times):
            cur.execute(path.read_text(encoding="utf-8"))
        raw.commit()
    finally:
        raw.close()


def _fixture_data():
    import tests.test_search_filtered_pg as F0
    a_live = [i for i, s in F0.STORES.items() if s[0] == "A" and s[2]][:2]
    b_live = [i for i, s in F0.STORES.items() if s[0] == "B" and s[2]][:1]
    return F0, a_live, b_live


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
    import tests.test_search_prices_pg as T
    F0, a_live, b_live = _fixture_data()
    eng = create_engine(PG_URL.rsplit("/", 1)[0] + "/" + DB)
    mig = (ROOT / "db" / "migrations" / "su11a47_search_prices.sql").read_text(encoding="utf-8")
    mig = "\n".join(ln for ln in mig.splitlines()
                    if not ln.startswith(("BEGIN", "COMMIT", "ALTER TABLE")) and not ln.startswith("--"))
    now = datetime.now(timezone.utc)
    with eng.begin() as c:
        c.execute(text(T.SCHEMA))
        c.execute(text(mig))
        c.exec_driver_sql(EXTRA_SCHEMA)
        for ch in F0.CHAINS:
            c.execute(text("INSERT INTO chains VALUES (:c, :n)"), {"c": ch, "n": f"רשת {ch}"})
        for sid, (ch, city, live) in F0.STORES.items():
            c.execute(text("INSERT INTO stores (id, chain_id, store_id, store_name, city, city_canonical, address, "
                           "last_loaded_at) VALUES (:i, :c, :s, :n, :city, :city, :a, :t)"),
                      {"i": sid, "c": ch, "s": str(100 + sid), "n": f"סניף {sid}", "city": city, "a": f"רחוב {sid}",
                       "t": now if live else now - timedelta(days=30)})
        items = dict(F0.ITEMS)
        items.update({T1: ("מוצר בדיקה אחד", "יצרן"), T2: ("מוצר בדיקה שתיים", "יצרן"),
                      T3: ("מוצר בדיקה שלוש", "יצרן")})
        for code, (name, mfr) in items.items():
            c.execute(text("INSERT INTO items VALUES (:c, 1, :n, :m, '1', 1, 0, 'יחידה')"),
                      {"c": code, "n": name, "m": mfr})
        prices = list(F0.PRICES) + [(fk, T1, 10.0) for fk in a_live] + [(fk, T2, 10.0) for fk in a_live] \
            + [(fk, T3, 10.0) for fk in b_live]
        c.execute(text("INSERT INTO prices (store_fk, item_code, price_update_date, item_price, unit_of_measure_price) "
                       "VALUES (:f, :c, '2026-10-22 10:00', :p, :p)"),
                  [{"f": f, "c": code, "p": p} for f, code, p in prices])
        icn = set(F0.ICN) | {(T1, "A"), (T2, "A"), (T3, "B")}
        c.execute(text("INSERT INTO item_chain_names VALUES (:c, :ch, :n, :m)"),
                  [{"c": code, "ch": ch, "n": f"{items[code][0]} ({ch})", "m": items[code][1]}
                   for code, ch in sorted(icn)])
        promos = list(F0.PROMOS)
        promos += [(fk, T1, "PA", "מבצע א ב-6", 1, None, 6, FUTURE) for fk in a_live]   # 40% off
        promos += [(fk, T2, "PB", "מבצע ב ב-8", 1, None, 8, FUTURE) for fk in a_live]   # 20% off
        promos += [(fk, T3, "PC", "מבצע ג ב-5", 1, None, 5, FUTURE) for fk in b_live]
        c.execute(text("INSERT INTO promos (store_fk, item_code, promo_id, promo_description, min_qty, "
                       "discount_rate, discount_price, promo_end) VALUES (:f, :c, :i, :d, :q, :r, :p, :e)"),
                  [dict(zip("fcidqrpe", p)) for p in promos])
    _run_sql(eng, AUDIT)
    _run_sql(eng, MIGRATION, times=2)                      # idempotent
    F0._build(eng)
    eng.a_live, eng.b_live = a_live, b_live
    yield eng
    eng.dispose()


@pytest.fixture
def client(engine, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    import api.auth as auth
    import api.routers.admin as A
    import db.query as Q
    from api.dependencies import get_db
    from api.main import app
    from db import promo_curation
    import tests.test_search_filtered_pg as F0

    def _get_db():
        with engine.connect() as conn:
            yield conn

    toks = {"admin": {"sub": ADMIN, "email": "admin@example.test", "aal": "aal2"},
            "user": {"sub": USER, "email": "1111@example.test"}}
    monkeypatch.setattr(auth, "_decode", lambda tok: toks.get(tok))
    monkeypatch.setenv("ADMIN_USER_EMAILS", "admin@example.test")
    monkeypatch.setenv("SEARCH_V2", "test")
    monkeypatch.setenv("SEARCH_V2_FILTERED", "test")
    lv = Q.Liveness(live_fks=frozenset(F0.LIVE), dead_pairs=frozenset(), dead_names=frozenset(),
                    live_cities=frozenset(), live_chains=frozenset())
    monkeypatch.setattr(Q, "get_liveness", lambda: lv)
    with engine.begin() as c:
        c.execute(text("DELETE FROM promo_curation"))
        c.execute(text("DELETE FROM admin_audit"))
    promo_curation.invalidate()
    A.reset_status_cache()
    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    promo_curation.invalidate()
    A.reset_status_cache()


H = {"Authorization": "Bearer admin"}


def pin(client, promo_id, rank=1, chain="A", **kw):
    return client.post("/admin/promos/pins", json={"chain_id": chain, "promo_id": promo_id, "rank": rank, **kw},
                       headers=H)


def hide(client, promo_id, chain="A", reason="נתונים שגויים", **kw):
    return client.post("/admin/promos/hides", json={"chain_id": chain, "promo_id": promo_id, "reason": reason, **kw},
                       headers=H)


def q(engine, sql, **p):
    from sqlalchemy import text
    with engine.connect() as c:
        return c.execute(text(sql), p).scalar()


def rows(engine, sql, **p):
    from sqlalchemy import text
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), p).mappings()]


def audit(engine):
    return rows(engine, "SELECT action, target_type, target_id, detail, actor_hash FROM admin_audit ORDER BY id")


def assert_no_identities(engine):
    blob = json.dumps(rows(engine, "SELECT detail FROM admin_audit"), default=str, ensure_ascii=False)
    blob += json.dumps(rows(engine, "SELECT * FROM promo_curation"), default=str, ensure_ascii=False)
    assert ADMIN not in blob and "admin@example.test" not in blob


def grouped(client, **params):
    r = client.get("/promos/grouped", params={"limit": 5000, **params})
    assert r.status_code == 200
    return r.json()


# =========================================================================== migration
def test_migration_refuses_without_promos(server):
    from sqlalchemy import create_engine
    eng = create_engine(PG_URL.rsplit("/", 1)[0] + "/" + DB_BARE)
    with pytest.raises(Exception, match="promos / stores are missing"):
        _run_sql(eng, MIGRATION)
    with eng.connect() as c:
        assert c.exec_driver_sql("SELECT to_regclass('public.promo_curation')").scalar() is None
    eng.dispose()


def test_table_indexes_owner_constraints(engine):
    from sqlalchemy import text
    with engine.connect() as c:
        idx = {r[0] for r in c.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'promo_curation'"))}
        assert {"uq_promo_curation_active", "idx_promo_curation_read"} <= idx
        assert c.execute(text("SELECT 1 FROM pg_indexes WHERE indexname = 'idx_promos_promo_id'")).scalar() == 1
        assert c.execute(text("SELECT tableowner FROM pg_tables WHERE tablename = 'promo_curation'")
                         ).scalar() == "scrp_app"
    bad = [
        "INSERT INTO promo_curation (kind, chain_id, promo_id, rank, actor_hash) VALUES ('pin', 'A', 'x', 51, 'h')",
        "INSERT INTO promo_curation (kind, chain_id, promo_id, rank, actor_hash) VALUES ('pin', 'A', 'x', NULL, 'h')",
        "INSERT INTO promo_curation (kind, chain_id, promo_id, rank, actor_hash) VALUES ('hide', 'A', 'x', 1, 'h')",
        "INSERT INTO promo_curation (kind, chain_id, promo_id, sponsored, actor_hash) VALUES ('hide','A','x',true,'h')",
        "INSERT INTO promo_curation (kind, chain_id, promo_id, actor_hash) VALUES ('boost', 'A', 'x', 'h')",
        "INSERT INTO promo_curation (kind, chain_id, promo_id, note, actor_hash) VALUES ('hide','A','x',repeat('a',201),'h')",
        "INSERT INTO promo_curation (kind, chain_id, promo_id, starts_at, ends_at, actor_hash) "
        "VALUES ('hide', 'A', 'x', now(), now() - interval '1 day', 'h')",
    ]
    for sql in bad:
        with pytest.raises(Exception):
            with engine.begin() as c:
                c.execute(text(sql))
    with pytest.raises(Exception, match="uq_promo_curation_active"):
        with engine.begin() as c:
            c.execute(text("INSERT INTO promo_curation (kind, chain_id, promo_id, actor_hash) VALUES ('hide','A','y','h')"))
            c.execute(text("INSERT INTO promo_curation (kind, chain_id, promo_id, actor_hash) VALUES ('hide','A','y','h')"))


# =========================================================================== HARD RULE: pricing unchanged
def _pricing_snapshot(client, engine) -> dict:
    """Raw response bytes of every pricing endpoint, plus a hash of the search build."""
    import api.routers.search as S
    import db.search_v2 as V
    import tests.test_search_filtered_pg as F0
    S._cache.clear()
    V._cache.built_at = V._cache.prices_built_at = V._cache.lexicon = None
    out = {}
    for qq in F0.QUERIES + ["בדיקה", "מוצר בדיקה"]:
        for engine_ in ("v1", "v2"):
            out[f"search {qq} {engine_}"] = client.get("/search", params={"q": qq, "engine": engine_}).content
            out[f"compare {qq} {engine_}"] = client.get("/compare", params={"q": qq, "engine": engine_}).content
            out[f"city {qq} {engine_}"] = client.get(
                "/search", params={"q": qq, "engine": engine_, "city": F0.CITIES[0]}).content
            out[f"store {qq} {engine_}"] = client.get(
                "/search", params={"q": qq, "engine": engine_, "group_by": "store", "chain": "A"}).content
    codes = [T1, T2, T3] + sorted(F0.ITEMS)[:25]
    for code in codes:
        out[f"product {code}"] = client.get(f"/product/{code}").content
    out["basket"] = client.post("/basket/compare", json={"items": [{"item_code": c, "quantity": 2} for c in codes]}
                                ).content
    out["basket city"] = client.post("/basket/compare", json={
        "items": [{"item_code": c} for c in codes], "cities": [F0.CITIES[0]]}).content
    stores = [{"chain_id": s[0], "store_id": str(100 + i)} for i, s in F0.STORES.items()]
    out["promos bulk"] = client.post("/promos/bulk", json={"stores": stores}).content
    for fk in engine.a_live:
        out[f"promos store {fk}"] = client.get(f"/promos/{fk}").content
    import tests.test_search_filtered_pg as F0b
    F0b._build(engine)
    built = [{k: v for k, v in r.items() if k != "built_at"}      # the build's own timestamp
             for r in rows(engine, "SELECT * FROM search_item_prices ORDER BY item_code, ord")]
    assert built
    out["build"] = hashlib.sha256(json.dumps(built, default=str).encode()).hexdigest()
    return out


def test_pricing_is_byte_identical_with_and_without_curation(client, engine):
    from db import promo_curation
    before = _pricing_snapshot(client, engine)
    assert b"6.0" in before["product " + T1] or b'"price":6' in before["product " + T1]   # PA prices T1
    # Curate EVERY promotion in the data: half hidden, the rest pinned (incl. sponsored).
    keys = sorted({(r["chain_id"], r["promo_id"]) for r in rows(
        engine, "SELECT DISTINCT s.chain_id, p.promo_id FROM promos p JOIN stores s ON s.id = p.store_fk")})
    hides = [k for k in keys if k[1] in ("PA", "PC")] + keys[::2]
    pins_ = [k for k in keys if k not in hides][:50]
    from sqlalchemy import text
    with engine.begin() as c:
        for ch, pid in set(hides):
            c.execute(text("INSERT INTO promo_curation (kind, chain_id, promo_id, note, actor_hash) "
                           "VALUES ('hide', :c, :p, 'x', 'h')"), {"c": ch, "p": pid})
        for k, (ch, pid) in enumerate(pins_, start=1):
            c.execute(text("INSERT INTO promo_curation (kind, chain_id, promo_id, rank, sponsored, actor_hash) "
                           "VALUES ('pin', :c, :p, :r, :s, 'h')"), {"c": ch, "p": pid, "r": k, "s": k % 2 == 0})
    promo_curation.invalidate()
    # The curation IS in effect on the promo lists ... (SU11A-62: an
    # unfiltered list is empty, so read it chain by chain)
    import tests.test_search_filtered_pg as F0
    g = [r for ch in F0.CHAINS for r in grouped(client, chain=ch)]
    assert not any(r["item_code"] in (T1, T3) for r in g)
    assert any(r["pinned"] for r in g)
    # ... and changes nothing that prices.
    after = _pricing_snapshot(client, engine)
    assert after.keys() == before.keys()
    for k in before:
        assert after[k] == before[k], k


# =========================================================================== public read path
def test_pins_lead_each_branch_in_rank_order_and_hides_are_out(client, engine):
    base = grouped(client, chain="A")
    assert {r["item_code"] for r in base} >= {T1, T2}
    assert all(r["pinned"] is False and r["sponsored"] is False for r in base)
    assert pin(client, "PB", rank=1, sponsored=True).status_code == 200
    assert pin(client, "PA", rank=2).status_code == 200
    g = grouped(client, chain="A")
    for fk in engine.a_live:
        branch = [r for r in g if r["store_fk"] == fk]
        assert [r["item_code"] for r in branch[:2]] == [T2, T1]           # PB (rank 1) then PA, ahead of 40% > 20%
        assert (branch[0]["pinned"], branch[0]["sponsored"]) == (True, True)
        assert (branch[1]["pinned"], branch[1]["sponsored"]) == (True, False)
        assert not any(r["pinned"] for r in branch[2:])
        assert [r["item_code"] for r in branch[2:]] == [r["item_code"] for r in base
                                                         if r["store_fk"] == fk and r["item_code"] not in (T1, T2)]
    # grouping stays the outer order
    keys = [(r["chain_name"], r["city"], r["branch"]) for r in g]
    assert keys == sorted(keys, key=lambda k: (k[0], k[1] is None, k[1] or "", k[2]))
    # hide: gone from the lists, nothing else moves
    pid = client.get("/admin/promos/curation", headers=H).json()["items"]
    assert client.delete(f"/admin/promos/curation/{[x for x in pid if x['promo']['promo_id'] == 'PA'][0]['id']}",
                         headers=H).status_code == 200
    assert hide(client, "PA").status_code == 200
    g2 = grouped(client, chain="A")
    assert T1 not in {r["item_code"] for r in g2}
    assert len(g2) == len(base) - len(engine.a_live)
    unpin = lambda r: {**r, "pinned": False, "sponsored": False}   # noqa: E731
    assert sorted(map(json.dumps, map(unpin, g2))) == sorted(json.dumps(r) for r in base if r["item_code"] != T1)
    # paging over the curated order is exact
    pages, off = [], 0
    while True:
        page = client.get("/promos/grouped", params={"chain": "A", "limit": 7, "offset": off}).json()
        pages += page
        if len(page) < 7:
            break
        off += 7
    assert pages == g2


def test_today_pins_first_and_hides_out(client, engine):
    base = client.get("/promos/today").json()
    assert T1 in {r["item_code"] for r in base}
    assert pin(client, "PB", rank=1, sponsored=True).status_code == 200
    assert hide(client, "PA").status_code == 200
    got = client.get("/promos/today").json()
    assert got[0]["item_code"] == T2 and got[0]["pinned"] and got[0]["sponsored"]
    assert T1 not in {r["item_code"] for r in got}
    assert not any(r["pinned"] for r in got[1:])


def test_expiry_by_date_and_by_missing_promo(client, engine):
    from sqlalchemy import text
    from db import promo_curation
    assert pin(client, "PA", rank=1).status_code == 200
    assert pin(client, "PB", rank=2).status_code == 200
    with engine.begin() as c:          # PA's pin ran out yesterday
        c.execute(text("UPDATE promo_curation SET starts_at = now() - interval '3 days', "
                       "ends_at = now() - interval '1 day' WHERE promo_id = 'PA'"))
    promo_curation.invalidate()
    branch = [r for r in grouped(client, chain="A") if r["store_fk"] == engine.a_live[0]]
    assert branch[0]["item_code"] == T2 and not [r for r in branch if r["item_code"] == T1][0]["pinned"]
    lst = client.get("/admin/promos/curation", params={"state": "expired"}, headers=H).json()["items"]
    assert [(x["promo"]["promo_id"], x["status"]) for x in lst] == [("PA", "expired_date")]
    act = client.get("/admin/promos/curation", headers=H).json()["items"]
    assert [(x["promo"]["promo_id"], x["status"]) for x in act] == [("PB", "active")]
    # PB's promotion leaves the data (ended in the feed)
    with engine.begin() as c:
        c.execute(text("UPDATE promos SET promo_end = '2001-01-01' WHERE promo_id = 'PB'"))
    try:
        promo_curation.invalidate()
        assert not any(r["pinned"] for r in grouped(client, chain="A"))
        lst = client.get("/admin/promos/curation", params={"state": "expired"}, headers=H).json()["items"]
        assert {(x["promo"]["promo_id"], x["status"]) for x in lst} == {("PA", "expired_date"),
                                                                       ("PB", "expired_missing")}
        assert client.get("/admin/promos/curation", headers=H).json()["items"] == []
        s = client.get("/admin/status", headers=H).json()["promo_curation"]
        assert s == {"active_pins": 1, "active_hides": 0, "expired": 1}
    finally:
        with engine.begin() as c:
            c.execute(text(f"UPDATE promos SET promo_end = '{FUTURE}' WHERE promo_id = 'PB'"))


def test_scheduled_pin_waits_for_its_start(client, engine):
    start = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = pin(client, "PA", rank=1, starts_at=start)
    assert r.status_code == 200
    assert not any(r["pinned"] for r in grouped(client, chain="A"))
    act = client.get("/admin/promos/curation", headers=H).json()["items"]
    assert act[0]["status"] == "scheduled"


# =========================================================================== admin writes
def test_rank_shifting_update_and_remove_with_audit(client, engine):
    def order():
        return [(x["promo"]["promo_id"], x["rank"]) for x in client.get("/admin/promos/curation", headers=H
                                                                        ).json()["items"] if x["kind"] == "pin"]
    ids = {}
    for pid in ("PA", "PB"):
        r = pin(client, pid, rank=1)
        assert r.status_code == 200
        ids[pid] = r.json()["id"]
    r = pin(client, "PC", chain="B", rank=2, note="קידום")
    ids["PC"] = r.json()["id"]
    assert order() == [("PB", 1), ("PC", 2), ("PA", 3)]
    assert r.json()["shifted"] == [{"id": ids["PA"], "from": 2, "to": 3}]
    r = client.patch(f"/admin/promos/curation/{ids['PA']}", json={"rank": 1}, headers=H)
    assert r.status_code == 200 and order() == [("PA", 1), ("PB", 2), ("PC", 3)]
    r = client.patch(f"/admin/promos/curation/{ids['PB']}", json={"rank": 50}, headers=H)   # clamps to the end
    assert order() == [("PA", 1), ("PC", 2), ("PB", 3)]
    assert client.delete(f"/admin/promos/curation/{ids['PA']}", headers=H).status_code == 200
    assert order() == [("PC", 1), ("PB", 2)]
    a = audit(engine)
    assert [x["action"] for x in a] == ["promo.pin"] * 3 + ["promo.update"] * 2 + ["promo.remove"]
    assert all(x["target_type"] == "promo" for x in a)
    assert a[2]["target_id"] == "B:PC" and a[2]["detail"]["before"] is None
    assert a[2]["detail"]["after"]["rank"] == 2 and a[2]["detail"]["after"]["note"] == "קידום"
    assert a[3]["detail"]["before"]["rank"] == 3 and a[3]["detail"]["after"]["rank"] == 1
    assert a[5]["detail"]["before"]["active"] is True and a[5]["detail"]["after"]["active"] is False
    assert {m["id"] for m in a[5]["detail"]["shifted"]} == {ids["PB"], ids["PC"]}
    assert "actor_hash" not in a[0]["detail"]["after"]
    from api.admin_audit import actor_hash
    assert {x["actor_hash"] for x in a} == {actor_hash(ADMIN)}
    assert_no_identities(engine)


def test_update_dates_sponsored_note(client, engine):
    rid = pin(client, "PA", rank=1).json()["id"]
    end = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    r = client.patch(f"/admin/promos/curation/{rid}", json={"ends_at": end, "sponsored": True, "note": "שבוע"},
                     headers=H)
    assert r.status_code == 200
    x = client.get("/admin/promos/curation", headers=H).json()["items"][0]
    assert x["sponsored"] is True and x["note"] == "שבוע" and x["ends_at"] is not None
    d = audit(engine)[-1]["detail"]
    assert d["before"]["sponsored"] is False and d["after"]["sponsored"] is True
    r = client.patch(f"/admin/promos/curation/{rid}", json={"clear_ends_at": True}, headers=H)
    assert client.get("/admin/promos/curation", headers=H).json()["items"][0]["ends_at"] is None
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    r = client.patch(f"/admin/promos/curation/{rid}", json={"ends_at": past}, headers=H)
    assert (r.status_code, r.json()) == (422, {"code": "invalid_dates"})
    hid = hide(client, "PC", chain="B").json()["id"]
    r = client.patch(f"/admin/promos/curation/{hid}", json={"rank": 1}, headers=H)
    assert (r.status_code, r.json()) == (422, {"code": "not_a_pin"})
    r = client.patch(f"/admin/promos/curation/{hid}", json={"note": "  "}, headers=H)
    assert (r.status_code, r.json()) == (422, {"code": "reason_required"})


def test_conflicts_and_not_found(client, engine):
    assert pin(client, "PA").status_code == 200
    assert pin(client, "PA").json() == {"code": "already_curated"}
    assert hide(client, "PA").json() == {"code": "pinned"}
    assert hide(client, "PB").status_code == 200
    assert pin(client, "PB").json() == {"code": "hidden"}
    assert hide(client, "PB").json() == {"code": "already_curated"}
    r = pin(client, "NOPE")
    assert (r.status_code, r.json()) == (404, {"code": "promo_not_found"})
    r = pin(client, "PC", chain="A")                                     # PC is chain B's
    assert r.status_code == 404
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r = pin(client, "PC", chain="B", ends_at=past)
    assert (r.status_code, r.json()) == (422, {"code": "invalid_dates"})
    assert client.delete("/admin/promos/curation/999999", headers=H).status_code == 404
    r = client.post("/admin/promos/hides", json={"chain_id": "A", "promo_id": "PA", "reason": ""}, headers=H)
    assert r.status_code == 422
    r = client.post("/admin/promos/pins", json={"chain_id": "A", "promo_id": "PA", "rank": 51}, headers=H)
    assert r.status_code == 422
    assert q(engine, "SELECT count(*) FROM promo_curation") == 2


def test_fifty_pins_then_full(client, engine):
    from sqlalchemy import text
    keys = [(r["chain_id"], r["promo_id"]) for r in rows(engine, """
        SELECT DISTINCT s.chain_id, p.promo_id FROM promos p JOIN stores s ON s.id = p.store_fk
        WHERE p.promo_end >= now() ORDER BY 1, 2""")]
    assert len(keys) > 50
    with engine.begin() as c:
        for k, (ch, pid) in enumerate(keys[:50], start=1):
            c.execute(text("INSERT INTO promo_curation (kind, chain_id, promo_id, rank, actor_hash) "
                           "VALUES ('pin', :c, :p, :r, 'h')"), {"c": ch, "p": pid, "r": k})
    ch, pid = keys[50]
    r = pin(client, pid, chain=ch, rank=3)
    assert (r.status_code, r.json()) == (409, {"code": "pins_full"})
    assert q(engine, "SELECT count(*) FROM promo_curation") == 50


def test_hidden_promo_still_prices_search(client, engine):
    """The HARD RULE spelled out on one item: PA hidden, T1 still costs ₪6."""
    assert hide(client, "PA").status_code == 200
    p = client.get(f"/product/{T1}").json()
    assert min(x["price"] for x in p["quotes"]) == 6.0
    s = client.get("/search", params={"q": "מוצר בדיקה אחד", "engine": "v1"}).json()
    assert s["items"][0]["cheapest_price"] == 6.0


# =========================================================================== admin reads
def test_search_by_text_barcode_promo_id_and_chain(client, engine):
    r = client.get("/admin/promos/search", params={"q": "מבצע א"}, headers=H).json()
    assert [(x["chain_id"], x["promo_id"]) for x in r["items"]] == [("A", "PA")]
    x = r["items"][0]
    assert x["stores"] == len(engine.a_live) and x["items"] == 1 and x["live"] is True
    assert x["chain_name"] == "רשת A" and x["sample"]["item_code"] == T1 and x["sample"]["discount_price"] == 6.0
    assert x["curation"] == {"pin_id": None, "pin_rank": None, "hide_id": None}
    assert [i["promo_id"] for i in client.get("/admin/promos/search", params={"q": T3}, headers=H
                                              ).json()["items"]] == ["PC"]
    assert [i["promo_id"] for i in client.get("/admin/promos/search", params={"q": "PB"}, headers=H
                                              ).json()["items"]] == ["PB"]
    by_name = client.get("/admin/promos/search", params={"q": "בדיקה שתיים"}, headers=H).json()["items"]
    assert [i["promo_id"] for i in by_name] == ["PB"]
    chain_b = client.get("/admin/promos/search", params={"chain": "B"}, headers=H).json()["items"]
    assert chain_b and {i["chain_id"] for i in chain_b} == {"B"}
    pin(client, "PA", rank=1)
    x = client.get("/admin/promos/search", params={"q": "מבצע א"}, headers=H).json()["items"][0]
    assert x["curation"]["pin_rank"] == 1
    # ended promotions only with active_only=false
    from sqlalchemy import text
    with engine.begin() as c:
        c.execute(text("UPDATE promos SET promo_end = '2001-01-01' WHERE promo_id = 'PC'"))
    try:
        assert client.get("/admin/promos/search", params={"q": T3}, headers=H).json()["items"] == []
        old = client.get("/admin/promos/search", params={"q": T3, "active_only": "false"}, headers=H).json()
        assert [(i["promo_id"], i["live"]) for i in old["items"]] == [("PC", False)]
        r = hide(client, "PC", chain="B")                     # a hide may target an ended promotion
        assert r.status_code == 200
        r = pin(client, "PC", chain="B")                      # ... a pin may not
        assert (r.status_code, r.json()) == (404, {"code": "promo_not_found"})
    finally:
        with engine.begin() as c:
            c.execute(text(f"UPDATE promos SET promo_end = '{FUTURE}' WHERE promo_id = 'PC'"))
    r = client.get("/admin/promos/search", params={"q": "a"}, headers=H)
    assert (r.status_code, r.json()) == (422, {"code": "query_required"})


def test_status_counts(client, engine):
    pin(client, "PA")
    hide(client, "PB")
    s = client.get("/admin/status", headers=H).json()
    assert s["promo_curation"] == {"active_pins": 1, "active_hides": 1, "expired": 0}
