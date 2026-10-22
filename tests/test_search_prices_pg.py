"""search_item_prices (SU11A-47) against a real Postgres: the build's fill SQL and
the v2 read path, compared with the live price fetch on the same fixture data.

Needs a throwaway Postgres server; SKIPPED unless SCRP_TEST_PG_URL is set, e.g.
    SCRP_TEST_PG_URL=postgresql://postgres:@127.0.0.1:5432/postgres
The test creates (and drops) its own database, su11a47_test, on that server and
never touches any other. No pg_trgm needed.
    python -m pytest tests/test_search_prices_pg.py -q
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PG_URL = os.environ.get("SCRP_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

ROOT = Path(__file__).resolve().parent.parent
DB = "su11a47_test"
EILAT = "אילת"
FUTURE, PAST = "2099-01-01 00:00:00", "2001-01-01 00:00:00"

SCHEMA = """
CREATE TABLE chains (chain_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '');
CREATE TABLE stores (id SERIAL PRIMARY KEY, chain_id TEXT NOT NULL REFERENCES chains(chain_id),
    sub_chain_id TEXT NOT NULL DEFAULT '1', store_id TEXT NOT NULL, store_name TEXT, city TEXT,
    city_canonical TEXT, address TEXT, last_loaded_at timestamptz);
CREATE TABLE items (item_code TEXT PRIMARY KEY, item_type INTEGER, item_name TEXT, manufacturer_name TEXT,
    unit_qty TEXT, quantity DOUBLE PRECISION, is_weighted INTEGER, unit_of_measure TEXT);
CREATE TABLE prices (id SERIAL PRIMARY KEY, store_fk INTEGER NOT NULL REFERENCES stores(id),
    item_code TEXT NOT NULL, price_update_date TEXT, item_price DOUBLE PRECISION NOT NULL,
    unit_of_measure_price DOUBLE PRECISION, UNIQUE (store_fk, item_code));
CREATE TABLE item_chain_names (item_code TEXT NOT NULL, chain_id TEXT NOT NULL, item_name TEXT,
    manufacturer_name TEXT, PRIMARY KEY (item_code, chain_id));
CREATE TABLE promos (id SERIAL PRIMARY KEY, store_fk INTEGER NOT NULL, item_code TEXT NOT NULL,
    promo_id TEXT, promo_description TEXT, min_qty NUMERIC, discount_rate NUMERIC,
    discount_price NUMERIC, promo_end TIMESTAMP);
CREATE TABLE search_items (item_code TEXT PRIMARY KEY, name_norm TEXT NOT NULL DEFAULT '',
    manufacturer_norm TEXT NOT NULL DEFAULT '', is_pseudo BOOLEAN NOT NULL DEFAULT false,
    chains_live SMALLINT NOT NULL DEFAULT 0, stores_live INTEGER NOT NULL DEFAULT 0,
    promo_only BOOLEAN NOT NULL DEFAULT false, popularity INTEGER NOT NULL DEFAULT 0,
    built_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE search_lexicon (term TEXT PRIMARY KEY, kind TEXT NOT NULL, canonical TEXT NOT NULL,
    freq INTEGER NOT NULL DEFAULT 0);
"""

# id: (chain, store_id, city, live)
STORES = {1: ("A", "1", "תל אביב", True), 2: ("A", "2", "חיפה", True), 3: ("A", "3", EILAT, True),
          4: ("B", "4", "תל אביב", True), 5: ("B", "5", EILAT, True), 6: ("C", "6", "ירושלים", True),
          7: ("C", "7", "ירושלים", False), 8: ("D", "8", "תל אביב", True), 9: ("D", "9", "חיפה", True)}

# item_code: (name, manufacturer)
ITEMS = {
    "7290000000011": ("חלב 3%", "תנובה"),            # ties, promos, Eilat cheapest, dead cheapest
    "7290000000022": ("שוקולד מריר", "עלית"),         # promo-only quotes (tie between two stores)
    "7290000000033": ("דג מלוח", "אילת דגים"),        # Eilat-only
    "7290000000044": ("הנ.קופון שוקו", "תנובה"),     # coupon pseudo item
    "7290000000055": ("אבוקדו", None),               # a ₪0 shelf price
    "7290000000066": ("לחם אחיד", "אנג'ל"),           # expired promo; tie across chains, names differ
    "7290000000077": ("קוטג' 5%", "תנובה"),           # chain with shelf + promo-only; cross-chain tie
    "7290000000088": ("במבה", "אסם"),                # bundle 3 for 10 (numeric unit price)
    "7290000000099": ("ביסלי", "אסם"),               # two equal promos at one store
}

# (store_fk, item_code, shelf price)
PRICES = [
    (1, "7290000000011", 10.0), (2, "7290000000011", 10.0), (3, "7290000000011", 8.0),
    (4, "7290000000011", 10.0), (6, "7290000000011", 12.0), (7, "7290000000011", 5.0),
    (4, "7290000000022", 6.0),
    (3, "7290000000033", 3.0), (5, "7290000000033", 3.5),
    (1, "7290000000044", 0.01), (4, "7290000000044", 0.01),
    (1, "7290000000055", 0.0), (4, "7290000000055", 4.0),
    (1, "7290000000066", 7.0), (4, "7290000000066", 7.0),
    (1, "7290000000077", 5.0), (4, "7290000000077", 4.0),
    (4, "7290000000088", 5.0), (1, "7290000000088", 3.9),
    (1, "7290000000099", 9.0), (6, "7290000000099", 8.5),
]

# (store_fk, item_code, promo_id, description, min_qty, rate, price, end)
PROMOS = [
    (2, "7290000000011", "p1", "ב-9", 1, None, 9, FUTURE),          # A2 9.0 wins chain A
    (6, "7290000000011", "p2", "10% הנחה", 1, 10, None, FUTURE),     # C6 rate-only: 10.8
    (8, "7290000000022", "p3", "2 ב-10", 2, None, 10, FUTURE),       # promo-only 5.0
    (9, "7290000000022", "p4", "2 ב-10", 2, None, 10, FUTURE),       # promo-only 5.0 (tie, later fk)
    (4, "7290000000022", "p5", "1+1", 1, 100, None, FUTURE),         # 100% rate: never a price
    (1, "7290000000066", "p6", "ב-5", 1, None, 5, PAST),             # ended: ignored
    (2, "7290000000077", "p7", "ב-4", 1, None, 4, FUTURE),           # promo-only at A2 = 4.0
    (8, "7290000000088", "p8", "3 ב-10", 3, None, 10, FUTURE),       # promo-only 3.333...
    (1, "7290000000099", "p9b", "ב-7 ב'", 1, None, 7, FUTURE),       # equal unit price ...
    (1, "7290000000099", "p9a", "ב-7 א'", 1, None, 7, FUTURE),       # ... promo_id decides
]


@pytest.fixture(scope="module")
def engine():
    from sqlalchemy import create_engine, text
    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {DB}"))
        c.execute(text(f"CREATE DATABASE {DB}"))
    eng = create_engine(PG_URL.rsplit("/", 1)[0] + "/" + DB)
    mig = (ROOT / "db" / "migrations" / "su11a47_search_prices.sql").read_text(encoding="utf-8")
    mig = "\n".join(ln for ln in mig.splitlines()
                    if not ln.startswith(("BEGIN", "COMMIT", "ALTER TABLE")) and not ln.startswith("--"))
    with eng.begin() as c:
        c.execute(text(SCHEMA))
        c.execute(text(mig))
        for ch in "ABCD":
            c.execute(text("INSERT INTO chains VALUES (:c, :n)"), {"c": ch, "n": f"רשת {ch}"})
        now = datetime.now(timezone.utc)
        for sid, (ch, store_id, city, live) in STORES.items():
            c.execute(text("INSERT INTO stores (id, chain_id, store_id, store_name, city, city_canonical, address, "
                           "last_loaded_at) VALUES (:i, :c, :s, :n, :city, :city, :a, :t)"),
                      {"i": sid, "c": ch, "s": store_id, "n": f"סניף {sid}", "city": city, "a": f"רחוב {sid}",
                       "t": now if live else now - timedelta(days=30)})
        for code, (name, mfr) in ITEMS.items():
            c.execute(text("INSERT INTO items VALUES (:c, 1, :n, :m, '1', 1, 0, 'יחידה')"),
                      {"c": code, "n": name, "m": mfr})
        for fk, code, price in PRICES:
            c.execute(text("INSERT INTO prices (store_fk, item_code, price_update_date, item_price, "
                           "unit_of_measure_price) VALUES (:f, :c, '2026-10-20 10:00', :p, :p)"),
                      {"f": fk, "c": code, "p": price})
        # Names per chain, for every chain with a shelf price; manufacturer
        # spelled differently per chain so "which chain names the product" shows.
        for code, ch in {(code, STORES[fk][0]) for fk, code, _ in PRICES} | {("7290000000077", "A")}:
            name, mfr = ITEMS[code]
            c.execute(text("INSERT INTO item_chain_names VALUES (:c, :ch, :n, :m)"),
                      {"c": code, "ch": ch, "n": f"{name} ({ch})", "m": f"{mfr} {ch}" if mfr else None})
        for fk, code, pid, desc, qty, rate, price, end in PROMOS:
            c.execute(text("INSERT INTO promos (store_fk, item_code, promo_id, promo_description, min_qty, "
                           "discount_rate, discount_price, promo_end) VALUES (:f, :c, :i, :d, :q, :r, :p, :e)"),
                      {"f": fk, "c": code, "i": pid, "d": desc, "q": qty, "r": rate, "p": price, "e": end})
    yield eng
    eng.dispose()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {DB}"))
    admin.dispose()


@pytest.fixture
def live(monkeypatch):
    import db.query as Q
    live_fks = frozenset(sid for sid, s in STORES.items() if s[3])
    lv = Q.Liveness(live_fks=live_fks, dead_pairs=frozenset(), dead_names=frozenset(),
                    live_cities=frozenset(), live_chains=frozenset())
    monkeypatch.setattr(Q, "get_liveness", lambda: lv)
    return sorted(live_fks)


def _build(engine, live_fks, chunks=3, built_at=None):
    """build_search_items' price fill + swap, on the fixture; returns built_at."""
    import scripts.build_search_items as B
    from sqlalchemy import text
    built_at = built_at or datetime.now(timezone.utc).replace(microsecond=0)
    conn = engine.connect()
    try:
        res = B.fill_prices(conn, {"live_fks": live_fks}, built_at, len(ITEMS), chunks)
        assert res["swapped"], res
        conn.execute(text("ALTER TABLE search_item_prices RENAME TO search_item_prices__swap"))
        conn.execute(text("ALTER TABLE search_item_prices_next RENAME TO search_item_prices"))
        conn.execute(text("ALTER TABLE search_item_prices__swap RENAME TO search_item_prices_next"))
        conn.execute(text("DELETE FROM search_items"))
        for code in ITEMS:
            conn.execute(text("INSERT INTO search_items (item_code, built_at) VALUES (:c, :b)"),
                         {"c": code, "b": built_at})
        conn.commit()
    finally:
        conn.close()
    return built_at


def _reset_v2_cache():
    import db.search_v2 as V
    V._cache.built_at = V._cache.prices_built_at = V._cache.lexicon = None


def _json(products: dict, codes: list[str]) -> list[str]:
    from api.routers.search import _to_model
    return [_to_model(products[c]).model_dump_json() for c in codes if c in products]


def test_fill_rows_one_per_item_and_chain(engine, live):
    from sqlalchemy import text
    _build(engine, live)
    with engine.connect() as c:
        rows = c.execute(text("SELECT item_code, chain_id, store_fk, ord, item_price, promo_unit_price "
                              "FROM search_item_prices ORDER BY item_code, ord")).all()
    got = {(r.item_code, r.chain_id): r for r in rows}
    assert len(got) == len(rows)
    assert got[("7290000000011", "A")].store_fk == 2                 # promo 9.0; Eilat 8.0 dropped (D2)
    assert ("7290000000011", "C") in got and got[("7290000000011", "C")].store_fk == 6   # dead store 7 out
    assert {k[1] for k in got if k[0] == "7290000000033"} == {"A", "B"}          # Eilat-only kept
    assert {k[1] for k in got if k[0] == "7290000000055"} == {"B"}                # ₪0 shelf dropped
    assert got[("7290000000022", "D")].store_fk == 8                 # promo-only tie: lower store_fk
    assert got[("7290000000022", "D")].item_price is None
    assert got[("7290000000077", "B")].ord == 1 and got[("7290000000077", "A")].ord == 2


def test_precomputed_json_is_byte_identical_to_live_fetch(engine, live):
    import db.search_v2 as V
    from db.query import fetch_prices, group_by_product
    _build(engine, live)
    _reset_v2_cache()
    codes = sorted(ITEMS)
    with engine.connect() as c:
        eilat = frozenset(sid for sid, s in STORES.items() if s[2] == EILAT)
        live_rows = V.drop_eilat(fetch_prices(c, codes), eilat)
        pre_rows = V._precomputed_rows(c, codes)
    assert pre_rows is not None
    want = _json(group_by_product(live_rows), codes)
    got = _json(group_by_product(pre_rows), codes)
    assert len(want) == len(ITEMS)
    for w, g in zip(want, got):
        assert g == w, (json.loads(w)["product"]["item_code"], g, w)
    # Spot checks on what the fixture is about.
    by = {json.loads(j)["product"]["item_code"]: json.loads(j) for j in got}
    milk = by["7290000000011"]
    assert [q["store_fk"] for q in milk["quotes"]] == [2, 4, 6]       # Eilat 8.0 and dead 5.0 gone
    assert milk["quotes"][0]["promo_kind"] == "promo" and milk["cheapest_price"] == 9.0
    assert milk["product"]["manufacturer"] == "תנובה A"                 # first chain in live order
    assert by["7290000000088"]["quotes"][0]["price"] == 10 / 3
    assert by["7290000000099"]["quotes"][0]["promo_description"] == "ב-7 א'"   # promo_id p9a < p9b
    assert by["7290000000066"]["quotes"][0]["promo_kind"] == "shelf"          # ended promo ignored


def test_run_uses_precomputed_and_matches_forced_live(engine, live, monkeypatch):
    import db.search_v2 as V
    _build(engine, live)
    _reset_v2_cache()
    page = [{"item_code": c, "name_norm": ITEMS[c][0], "manufacturer_norm": ITEMS[c][1] or "",
             "chains_live": 2, "popularity": 0, "promo_only": False, "is_pseudo": False} for c in sorted(ITEMS)]
    monkeypatch.setattr(V, "_lexicon", lambda conn: ({}, frozenset(s for s, v in STORES.items() if v[2] == EILAT)))
    monkeypatch.setattr(V, "_barcode", lambda conn, codes: [dict(p) for p in page if p["item_code"] in codes])
    with engine.connect() as c:
        a = V.run(c, sorted(ITEMS)[0], limit=1)
        assert a.prices_source == "precomputed"
        monkeypatch.setattr(V, "_ranked", lambda conn, groups, q_norm, *_: V.Ranked.from_list(
            [dict(p) for p in page], groups, q_norm))
        pre = V.run(c, "חלב", limit=30)
        live_ = V.run(c, "חלב", limit=30, precomputed=False)
    assert pre.prices_source == "precomputed" and live_.prices_source == "live"
    codes = [p["item_code"] for p in pre.products]
    assert _json({p["item_code"]: p for p in pre.products}, codes) == \
        _json({p["item_code"]: p for p in live_.products}, codes)


def test_fallbacks_missing_empty_stale_ended(engine, live):
    import db.search_v2 as V
    from sqlalchemy import text
    built = _build(engine, live)
    codes = sorted(ITEMS)
    with engine.connect() as c:
        _reset_v2_cache()
        assert V._precomputed_rows(c, codes) is not None
        _reset_v2_cache()
        assert V._precomputed_rows(c, codes + ["7290000009999"]) is None       # a page item with no row
        # A winning promo that has ended since the build.
        c.execute(text("UPDATE search_item_prices SET promo_end = '2001-01-01T00:00:00' "
                       "WHERE item_code = '7290000000011' AND chain_id = 'A'"))
        _reset_v2_cache()
        assert V._precomputed_rows(c, codes) is None
        assert V._precomputed_rows(c, ["7290000000022"]) is not None           # other pages unaffected
        c.rollback()
        # Stale: built_at differs from search_items.built_at.
        c.execute(text("UPDATE search_items SET built_at = :b"), {"b": built + timedelta(hours=1)})
        _reset_v2_cache()
        assert V._precomputed_rows(c, codes) is None
        c.rollback()
        # Empty.
        c.execute(text("DELETE FROM search_item_prices"))
        _reset_v2_cache()
        assert V._precomputed_rows(c, codes) is None
        c.rollback()
        # Missing (migration not applied): no error, the live fetch answers.
        c.execute(text("ALTER TABLE search_item_prices RENAME TO sip_hidden"))
        _reset_v2_cache()
        assert V._try_precomputed(c, codes) is None
        c.rollback()


def test_build_without_migration_warns_and_skips(engine, live, capsys):
    import scripts.build_search_items as B
    from sqlalchemy import text
    with engine.connect() as c:
        c.execute(text("ALTER TABLE search_item_prices_next RENAME TO sipn_hidden"))
        res = B.fill_prices(c, {"live_fks": live}, datetime.now(timezone.utc), len(ITEMS), 2)
        c.rollback()
    assert res == {"swapped": False, "reason": "tables missing"}
    assert "su11a47_search_prices.sql not applied" in capsys.readouterr().err


def test_suggest_sql_on_postgres(engine, live):
    """/suggest's own SQL (prefix terms / brands, products, names, barcode); the
    typo round needs pg_trgm and is covered with fakes in test_search_speed."""
    import db.search_v2 as V
    from db.search_norm import normalize
    from sqlalchemy import text
    _build(engine, live)
    with engine.begin() as c:
        for code, (name, mfr) in ITEMS.items():
            c.execute(text("UPDATE search_items SET name_norm = :n, manufacturer_norm = :m, chains_live = 2, "
                           "is_pseudo = :p WHERE item_code = :c"),
                      {"n": normalize(name), "m": normalize(mfr), "p": name.startswith("הנ.קופון"), "c": code})
        c.execute(text("DELETE FROM search_lexicon"))
        for term, kind, freq in [("חלב", "token", 50), ("חלבה", "token", 9), ("שוקולד", "token", 30),
                                 ("תנובה", "brand", 40), ("tnuva", "alias", 40), ("100%", "token", 5)]:
            c.execute(text("INSERT INTO search_lexicon VALUES (:t, :k, :t, :f)"), {"t": term, "k": kind, "f": freq})
    _reset_v2_cache()
    with engine.connect() as c:
        s = V.suggest(c, "חל")
        assert [i["text"] for i in s.items if i["kind"] == "term"] == ["חלב", "חלבה"]
        assert {"kind": "product", "text": "חלב 3%", "item_code": "7290000000011"} in s.items
        s = V.suggest(c, "שוקו")
        assert s.items[0] == {"kind": "term", "text": "שוקולד", "count": 30}
        assert all(i.get("item_code") != "7290000000044" for i in s.items)          # pseudo
        assert V.suggest(c, "תנו").items[0] == {"kind": "brand", "text": "תנובה", "count": 40}
        assert V.suggest(c, "TNU").items[0]["text"] == "tnuva"
        assert V.suggest(c, "7290000000022").items == [
            {"kind": "product", "text": "שוקולד מריר", "item_code": "7290000000022"}]
        assert V.suggest(c, "7290000000044").items == []
        assert V.suggest(c, "100%").items[0]["text"] == "100%"                       # LIKE escaping
        assert V.suggest(c, "חלב מ").items[0]["kind"] in ("term", "product")


def test_compare_check_precomputed(engine, live, monkeypatch, capsys):
    """scripts.compare_search_v2 --check-precomputed: 0 mismatches on a fresh
    build, and a tampered row is reported with the differing field."""
    import db.db as D
    import scripts.compare_search_v2 as C
    from sqlalchemy import text
    _build(engine, live)
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(D, "_engine", None)
    assert C.check_precomputed(50, None) == 0
    assert "MISMATCHES 0" in capsys.readouterr().out
    with engine.begin() as c:
        c.execute(text("UPDATE search_item_prices SET item_price = 99 "
                       "WHERE item_code = '7290000000066' AND chain_id = 'B'"))
    assert C.check_precomputed(50, None) == 1
    out = capsys.readouterr().out
    assert "MISMATCHES 1" in out and "7290000000066: /" in out
    D._engine.dispose()


def test_chunk_count_does_not_change_the_rows(engine, live):
    from sqlalchemy import text
    q = "SELECT item_code, chain_id, ord, store_fk, item_price, promo_unit_price FROM search_item_prices ORDER BY 1, 2"
    _build(engine, live, chunks=1)
    with engine.connect() as c:
        one = c.execute(text(q)).all()
    _build(engine, live, chunks=7)
    with engine.connect() as c:
        seven = c.execute(text(q)).all()
    assert one == seven and len(one) > len(ITEMS)


def test_old_path_cap_sql_on_postgres(engine, live):
    """SU11A-49 (F-01): cap_candidates' search_items read (ANY over a text[]),
    the v2 order, unbuilt items last, and the fallback when the table is gone."""
    import api.routers.search as R
    from sqlalchemy import text
    with engine.begin() as c:
        c.execute(text("DELETE FROM search_items"))
        for code, chains, pop, name in [("A1", 1, 0, "x"), ("A2", 3, 0, "xx"), ("A3", 3, 5, "xxx")]:
            c.execute(text("INSERT INTO search_items (item_code, name_norm, chains_live, popularity) "
                           "VALUES (:c, :n, :ch, :p)"), {"c": code, "n": name, "ch": chains, "p": pop})
    codes = ["A1", "A2", "A3", "Z9"]
    tiers = {c: 0 for c in codes}
    with engine.connect() as c:
        assert R.cap_candidates(c, codes, tiers, cap=3) == ["A3", "A2", "A1"]
        assert R.cap_candidates(c, codes + [f"Q{i:05d}" for i in range(3000)], tiers, cap=2) == ["A3", "A2"]
    with engine.begin() as c:
        c.execute(text("ALTER TABLE search_items RENAME TO search_items_gone"))
    try:
        with engine.connect() as c:
            assert R.cap_candidates(c, codes, {"Z9": 0, "A1": 1, "A2": 1, "A3": 1}, cap=2) == ["Z9", "A1"]
            assert c.execute(text("SELECT 1")).scalar() == 1      # savepoint kept the connection usable
    finally:
        with engine.begin() as c:
            c.execute(text("ALTER TABLE search_items_gone RENAME TO search_items"))


def test_api_statement_timeout_on_postgres(engine):
    """SU11A-49 (F-01): the libpq startup option really cancels a long statement
    with SQLSTATE 57014 (what api/main.py maps to 503), and a plain engine
    (scripts, timers) has no timeout."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import DBAPIError
    from db import db as D
    saved = D._statement_timeout_ms
    try:
        D.set_statement_timeout(200)
        timed = create_engine(engine.url, **D.engine_kwargs())
        with timed.connect() as c:
            assert c.execute(text("SHOW statement_timeout")).scalar() == "200ms"
            with pytest.raises(DBAPIError) as exc:
                c.execute(text("SELECT pg_sleep(2)"))
        assert exc.value.orig.pgcode == "57014"
        timed.dispose()
        D.set_statement_timeout(None)
        plain = create_engine(engine.url, **D.engine_kwargs())
        with plain.connect() as c:
            assert c.execute(text("SHOW statement_timeout")).scalar() == "0"
        plain.dispose()
    finally:
        D._statement_timeout_ms = saved
