"""SU11A-65 against a real Postgres:
  * gift coupons (a free unit + "קופון"): gift_coupon on list / grouped /
    promoted rows and on the admin sample, after every real discount in the
    "discount" sort (the other rows keep their order), their own type chip that
    the other chips exclude, and the count_gift_coupons diagnostic;
  * the indexable search WHERE (db.query.PROMO_MATCH_INDEXED) returns exactly
    the old rows in the old order, with and without the su11a65 indexes;
  * the category boost only re-ranks rows that match the text;
  * the su11a65 migration (twice) and its rollback.

Data: the SU11A-62 fixture (tests/test_promo_search_su11a62_pg.py) plus the
rows below. SKIPPED unless SCRP_TEST_PG_URL is set; the migration test also
needs pg_trgm on that server (skipped otherwise).
"""
import json

import pytest
from sqlalchemy import text

from tests.test_promo_curation_su11a58_pg import (  # noqa: F401  (fixtures)
    FUTURE, H, PG_URL, ROOT, client, engine, pin, server,
)
from tests.test_promo_search_su11a62_pg import code, items, load_rows

pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

# (item, name, promotion, description, min_qty, rate, price): shelf price 10.
GIFT_ROWS = [
    (40, "שמנת חמוצה 15% טרה", "G1", "קופון שמנת חמוצה 15% טרה 1 יח' מתנה", 1, 100, None),   # gift coupon (rate)
    (41, "קוטג' 5% תנובה", "G2", "קופון קוטג' מעל 100 ש\"ח 1 יח' מתנה", 1, 10000, 0),        # gift coupon (bp, price 0)
    (42, "חטיף אגוזים", "G3", "1+1 חטיף אגוזים", 1, 100, 0),                                 # free unit, no coupon
    (43, "מרכך כביסה", "G4", "קופון 50% הנחה מרכך", 1, 50, None),                           # coupon, real 50%
    # SU11A-62 חומוס finding: a legume category; only text matches may appear
    (50, "עדשים כתומות סוגת 500 גרם", "L1", "2ב15 עדשים סוגת", 1, None, 7),                  # category only: never shown
    (51, "חומוס גרגירים סוגת", "L2", "2ב15 קטניות", 1, None, 6),                             # name + category
    (52, "אפונה וגזר לנדא 800 גרם", "L3", "2ב15.90 שדה בשקית חומוס / אפונה", 1, None, 8),   # description only
    (53, "סלט חומוס אחלה", "L4", "מבצע ל4", 1, None, 9),                                     # name, no category
]


@pytest.fixture(scope="module")
def data(engine):  # noqa: F811
    """The SU11A-62 rows (its fixture body) plus GIFT_ROWS and a legume category."""
    load_rows(engine)
    with engine.begin() as c:
        c.execute(text("INSERT INTO categories (id, parent_id, level, name_he, taxonomy_version) "
                       "VALUES ('D92', NULL, 1, 'שימורים', 'v1'), "
                       "('D92.C01', 'D92', 2, 'חומוס, עדשים וקטניות', 'v1') ON CONFLICT DO NOTHING"))
        for n in (50, 51, 52):
            c.execute(text("INSERT INTO item_categories (item_code, category_id, confidence, source, "
                           "taxonomy_version) VALUES (:c, 'D92.C01', 'high', 'rule', 'v1')"), {"c": code(n)})
        for n, name, *_ in GIFT_ROWS:
            c.execute(text("INSERT INTO items VALUES (:c, 1, :n, 'יצרן', '1', 1, 0, 'יחידה')"), {"c": code(n), "n": name})
        for fk in engine.a_live:
            for n, _name, pid, desc, qty, rate, price in GIFT_ROWS:
                c.execute(text("INSERT INTO prices (store_fk, item_code, price_update_date, item_price, "
                               "unit_of_measure_price) VALUES (:f, :c, '2026-10-22 10:00', 10, 10)"),
                          {"f": fk, "c": code(n)})
                c.execute(text("INSERT INTO promos (store_fk, item_code, promo_id, promo_description, min_qty, "
                               "discount_rate, discount_price, promo_end) VALUES (:f, :c, :i, :d, :q, :r, :p, :e)"),
                          {"f": fk, "c": code(n), "i": pid, "d": desc, "q": qty, "r": rate, "p": price, "e": FUTURE})
    return engine


@pytest.fixture(scope="module")
def eng(data):
    return data


@pytest.fixture
def api(data, client):  # noqa: F811
    import api.categories as cats
    cats.reset_tree_cache()
    yield client
    cats.reset_tree_cache()


def _all(api, path="/promos/list", **params):
    out, offset = [], 0
    while True:
        page = api.get(path, params={**params, "limit": 100, "offset": offset}).json()
        out += page
        if len(page) < 100:
            return out
        offset += 100


# ------------------------------------------------------------------ gift coupons

def test_gift_coupon_rule(api):
    by = {int(r["item_code"][-2:]): r for r in _all(api, chain="A") if r["item_code"].startswith("72999100000")}
    assert by[40]["gift_coupon"] and by[41]["gift_coupon"]
    assert not by[42]["gift_coupon"]   # 1+1 without a coupon: unchanged
    assert not by[43]["gift_coupon"] and by[43]["discount_pct"] == 50   # a coupon with a real %
    assert all(not r["gift_coupon"] for n, r in by.items() if n not in (40, 41))
    # by the numbers they read 100%: that is exactly what the card must not show
    assert by[40]["discount_pct"] == 100 and by[41]["discount_pct"] == 100


def test_python_rule_matches_sql():
    from db.query import is_gift_coupon
    for n, _name, _pid, desc, qty, rate, price in GIFT_ROWS:
        assert is_gift_coupon(desc, qty, price, rate) == (n in (40, 41)), n
    assert not is_gift_coupon("קופון", 30, None, 100)   # min_qty > 24 = a spend: a basket row


def test_discount_sort_puts_gift_coupons_after_real_discounts(api):
    rows = _all(api, chain="A", sort="discount")
    kinds = [2 if r["discount_pct"] is None else 1 if r["gift_coupon"] else 0 for r in rows]
    assert kinds == sorted(kinds) and 1 in kinds
    real = [r["discount_pct"] for r in rows if not r["gift_coupon"] and r["discount_pct"] is not None]
    assert real == sorted(real, reverse=True)
    # without gift coupons the order is the pre-SU11A-65 one (discount_pct DESC NULLS LAST, then the keys)
    rest = [r for r in rows if not r["gift_coupon"]]
    old = sorted(rest, key=lambda r: (r["discount_pct"] is None, -(r["discount_pct"] or 0)))
    assert [r["discount_pct"] for r in rest] == [r["discount_pct"] for r in old]
    # the other sorts are unchanged: a gift coupon's savings is the shelf price, and it sorts as such
    sav = _all(api, chain="A", sort="savings")
    vals = [r["savings"] for r in sav if r["savings"] is not None]
    assert vals == sorted(vals, reverse=True)


def test_grouped_and_promoted_carry_the_flag(api, eng):
    grouped = [r for r in _all(api, "/promos/grouped", chain="A") if r["item_code"] == code(40)]
    assert grouped and all(r["gift_coupon"] for r in grouped)
    for fk in eng.a_live:   # within each branch: after the real discounts
        br = [r for r in _all(api, "/promos/grouped", chain="A") if r["store_fk"] == fk]
        k = [2 if r["discount_pct"] is None else 1 if r["gift_coupon"] else 0 for r in br]
        assert k == sorted(k)
    assert pin(api, "G1", rank=1).status_code == 200
    rows = api.get("/promos/promoted").json()
    assert [(r["item_code"], r["gift_coupon"]) for r in rows] == [(code(40), True)]


def test_type_chip(api):
    only = _all(api, chain="A", promo_type="gift_coupon")
    assert sorted(set(items(only))) == [40, 41] and all(r["gift_coupon"] for r in only)
    gift = items(_all(api, chain="A", promo_type="gift"))
    assert 42 in gift and 41 not in gift            # 41 is shape 'gift', but a gift coupon
    disc = items(_all(api, chain="A", promo_type="discount"))
    assert 43 in disc and 40 not in disc            # 40 is shape 'discount' (rate 100), but a gift coupon
    both = items(_all(api, chain="A", promo_type="gift,gift_coupon"))
    assert {40, 41, 42} <= set(both)
    assert _all(api, chain="A", promo_type="nonsense")   # unknown values are ignored, as before


def test_admin_sample_flag(api):
    hits = api.get("/admin/promos/search", params={"q": "קופון"}, headers=H).json()["items"]
    by = {x["promo_id"]: x["sample"] for x in hits}
    assert by["G1"]["gift_coupon"] and by["G2"]["gift_coupon"]
    assert not by["G4"]["gift_coupon"]


def test_count_gift_coupons_and_report(api, eng, monkeypatch, capsys):
    import db.query as Q
    import tests.test_search_filtered_pg as F0
    from scripts import su11a65_promo_report as R
    lv = Q.Liveness(live_fks=frozenset(F0.LIVE), dead_pairs=frozenset(), dead_names=frozenset(),
                    live_cities=frozenset(), live_chains=frozenset())
    monkeypatch.setattr(Q, "get_liveness", lambda: lv)
    with eng.connect() as c:
        out = Q.count_gift_coupons(c, examples=10)
        n = len(eng.a_live)
        assert out["counts"]["gift_coupon_rows"] == 2 * n
        assert out["counts"]["gift_coupon_promotions"] == 2
        assert out["counts"]["gift_coupon_cards"] == 2
        assert out["counts"]["free_unit_without_coupon_rows"] >= n   # row 42
        assert [r["chain_id"] for r in out["by_chain"]] == ["A"]
        assert {r["item_code"] for r in out["examples"]} == {code(40), code(41)}
        R.gifts(c)
        R.why(c, "חומוס", None)
    printed = capsys.readouterr().out
    assert "gift_coupon_rows: " in printed and "שמנת חמוצה 15% טרה" in printed
    assert "NO TEXT MATCH" not in printed and "עדשים כתומות" not in printed


# ------------------------------------------------------------------ category boost

def test_boost_only_reranks_text_matches(api):
    """q=חומוס: the legume category is boosted; a member whose name and
    description lack the text (lentils, row 50) never appears; the
    description match (52) does, as SU11A-62 designed."""
    rows = _all(api, q="חומוס")
    got = items(rows)
    assert 50 not in got
    assert {51, 52, 53} <= set(got)
    assert got.index(51) < got.index(53)   # same tier (name starts); the boost lifts 51
    for r in rows:
        assert "חומוס" in (r["product_name"] or "") + (r["promo_description"] or "") or r["item_code"] == "חומוס"


def test_boost_never_changes_the_row_set(data, monkeypatch):
    import db.query as Q
    import api.categories as cats
    monkeypatch.setattr(Q, "get_liveness", lambda: None)
    with data.connect() as c:
        cats.reset_tree_cache()
        for q in ("חומוס", "שמנת", "עדשים"):
            s = cats.promo_search(c, q)
            assert s.boost_ids, q   # every one names a fixture category
            with_boost = Q.fetch_flat_promos(c, q=s, limit=500, offset=0)
            no_boost = Q.fetch_flat_promos(c, q=Q.PromoSearch(s.q), limit=500, offset=0)
            key = lambda r: (r["chain_id"], r["item_code"], r["promo_description"])  # noqa: E731
            assert sorted(map(key, with_boost)) == sorted(map(key, no_boost)), q


# ------------------------------------------------------------------ old vs new search WHERE

TERMS = ["שמנת", "חומוס", "עדשים", "קופון", "מבצע", "ab%", "x_y", "קוד", "7299910000040", "2ב15"]


def _snapshot(api, eng):
    out = {}
    for q in TERMS:
        for sort in ("discount", "savings", "ending"):
            out[("list", q, sort)] = _all(api, q=q, sort=sort)
        out[("grouped", q)] = _all(api, "/promos/grouped", q=q, chain="A")
        out[("promoted", q)] = api.get("/promos/promoted", params={"q": q}).json()
        out[("admin", q)] = api.get("/admin/promos/search", params={"q": q}, headers=H).json()
    return json.dumps({"|".join(k): v for k, v in out.items()}, ensure_ascii=False, sort_keys=True, default=str)


def _pins(api):
    for k, pid in enumerate(("S7", "L3", "G1"), 1):
        pin(api, pid, rank=k)


def test_indexed_where_is_identical_to_the_old_one(api, eng, monkeypatch):
    import db.query as Q
    _pins(api)
    new = _snapshot(api, eng)
    monkeypatch.setattr(Q, "PROMO_MATCH_INDEXED", False)
    old = _snapshot(api, eng)
    assert new == old
    assert '"7299910000040"' in new and "עדשים כתומות" in new   # the terms do return rows


def _has_trgm(engine) -> bool:
    with engine.connect() as c:
        return c.execute(text("SELECT count(*) FROM pg_available_extensions WHERE name = 'pg_trgm'")).scalar() > 0


def _psql_file(engine, path):
    """Run a migration file statement by statement in autocommit (as psql does)."""
    sql = "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("--"))
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        for stmt in (s.strip() for s in sql.split(";")):
            if stmt:
                c.exec_driver_sql(stmt)


def test_migration_twice_rollback_and_same_results(api, eng, monkeypatch):
    if not _has_trgm(eng):
        pytest.skip("pg_trgm is not available on this test server")
    import db.query as Q
    _pins(api)
    before = _snapshot(api, eng)
    mig = ROOT / "db" / "migrations" / "su11a65_promo_search.sql"
    _psql_file(eng, mig)
    _psql_file(eng, mig)   # idempotent
    with eng.connect() as c:
        valid = dict(c.execute(text(
            "SELECT c.relname, i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE c.relname IN ('idx_promos_description_trgm', 'idx_items_name_trgm')")).all())
    assert valid == {"idx_promos_description_trgm": True, "idx_items_name_trgm": True}
    # The match itself can use the indexes (a tiny fixture never needs them for
    # the whole query; the production-sized plan is in the SU11A-65 handoff entry).
    where, _, _, mp = Q.promo_match_sql(Q.PromoSearch("שמנת"), "i.item_name", "p.promo_description", "p.item_code")
    with eng.begin() as c:
        c.exec_driver_sql("SET LOCAL enable_seqscan = off")
        plan = " | ".join(r[0] for r in c.execute(text(f"EXPLAIN SELECT p.id FROM promos p WHERE {where}"), mp).all())
    assert "idx_promos_description_trgm" in plan and "BitmapOr" in plan and "idx_items_name_trgm" in plan
    assert _snapshot(api, eng) == before
    monkeypatch.setattr(Q, "PROMO_MATCH_INDEXED", False)
    assert _snapshot(api, eng) == before
    _psql_file(eng, ROOT / "db" / "migrations" / "su11a65_promo_search_rollback.sql")
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM pg_class WHERE relname IN "
                              "('idx_promos_description_trgm', 'idx_items_name_trgm')")).scalar() == 0

