"""SU11A-66 Part B against a real Postgres: customer-compensation coupons
("קופון פיצוי לקוח ...") are left out of /promos/list, /promos/grouped and
/promos/promoted (the SU11A-62 cleanup layer, db.query CLEANUP_RULES), the
admin search still lists them flagged `compensation`, the gift-coupon chip
no longer shows them, nothing else on the lists moves, and pricing
(/promos/bulk) still sees them.

Data: the SU11A-62 fixture (tests/test_promo_search_su11a62_pg.py) plus the
rows below. SKIPPED unless SCRP_TEST_PG_URL is set.
"""
import pytest
from sqlalchemy import text

from tests.test_promo_curation_su11a58_pg import (  # noqa: F401  (fixtures)
    FUTURE, H, PG_URL, ROOT, client, engine, pin, server,
)
from tests.test_promo_search_su11a62_pg import code, items, load_rows

pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

# (item, name, promotion, description, min_qty, rate, price): shelf price 10.
COMP_ROWS = [
    (60, "וופל שסטוביץ", "K1", "קופון פיצוי לקוח 20שח מוצרי שסטוביץ", 1, 100, None),   # free unit: was a gift coupon
    (61, "עוגיות שסטוביץ", "K1", "קופון פיצוי לקוח 20שח מוצרי שסטוביץ", 1, 100, None),
    (62, "תפוגן צ'יפס", "K2", "קופון פיצוי לקוח 2 יחידות תפוגן", 2, 100, 0),          # gift shape, price 0
    (63, "פריניר שוקולד", "K3", "35ש\"ח-קופון פיצוי פריניר", 1, None, 5),             # a fixed price: a "real" 50%
    (64, "מגבונים לחים", "K4", "פצוי ללקוח מגבונים", 1, None, 6),                     # defective spelling, no קופון
    (65, "פיצוחים מעורבים", "N1", "מבצע פיצוחים 2ב20", 1, None, 8),                  # look-alike: stays
    (66, "פיצה משפחתית", "N2", "פיצה משפחתית ב-30", 1, None, 7),                     # look-alike: stays
    (67, "קפה נמס", "N3", "קופון שמנת 1 יח' מתנה", 1, 100, None),                     # a gift coupon: stays
]
COMP_PROMOS = {"K1", "K2", "K3", "K4"}
COMP_ITEMS = {60, 61, 62, 63, 64}


@pytest.fixture(scope="module")
def data(engine):  # noqa: F811
    load_rows(engine)
    with engine.begin() as c:
        for n, name, *_ in COMP_ROWS:
            c.execute(text("INSERT INTO items VALUES (:c, 1, :n, 'יצרן', '1', 1, 0, 'יחידה')"), {"c": code(n), "n": name})
        for fk in engine.a_live:
            for n, _name, pid, desc, qty, rate, price in COMP_ROWS:
                c.execute(text("INSERT INTO prices (store_fk, item_code, price_update_date, item_price, "
                               "unit_of_measure_price) VALUES (:f, :c, '2026-10-22 10:00', 10, 10)"),
                          {"f": fk, "c": code(n)})
                c.execute(text("INSERT INTO promos (store_fk, item_code, promo_id, promo_description, min_qty, "
                               "discount_rate, discount_price, promo_end) VALUES (:f, :c, :i, :d, :q, :r, :p, :e)"),
                          {"f": fk, "c": code(n), "i": pid, "d": desc, "q": qty, "r": rate, "p": price, "e": FUTURE})
    return engine


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


def _key(r):
    return (r["item_code"], r.get("store_fk"), r["promo_description"])


def test_lists_leave_compensation_out(api):
    for path in ("/promos/list", "/promos/grouped"):
        rows = _all(api, path, chain="A")
        got = set(items(rows))
        assert not got & COMP_ITEMS, path
        assert {65, 66, 67} <= got, path   # the look-alikes and a real gift coupon stay
        assert all("פיצוי" not in (r["promo_description"] or "") for r in rows)
    # with search text too (the description and the product name match)
    assert not set(items(_all(api, chain="A", q="שסטוביץ")))
    assert set(items(_all(api, chain="A", q="פיצוחים"))) == {65}


def test_gift_chip_no_longer_shows_compensation(api):
    only = _all(api, chain="A", promo_type="gift_coupon")
    assert 67 in items(only) and not set(items(only)) & COMP_ITEMS


def test_promoted_leaves_a_pinned_compensation_out(api):
    assert pin(api, "K3", rank=1).status_code == 200
    assert pin(api, "N1", rank=2).status_code == 200
    rows = api.get("/promos/promoted").json()
    assert [r["item_code"] for r in rows] == [code(65)]


def test_admin_search_still_lists_and_flags_them(api):
    hits = api.get("/admin/promos/search", params={"q": "פיצוי"}, headers=H).json()["items"]
    by = {x["promo_id"]: x for x in hits}
    assert {"K1", "K2", "K3"} <= set(by)
    assert all(by[p]["compensation"] for p in ("K1", "K2", "K3"))
    assert by["K3"]["cities"] == []          # not on any public list
    assert api.get("/admin/promos/search", params={"q": "פצוי"}, headers=H).json()["items"][0]["compensation"]
    other = api.get("/admin/promos/search", params={"q": "פיצוחים"}, headers=H).json()["items"]
    assert [x["promo_id"] for x in other] == ["N1"] and other[0]["compensation"] is False
    assert other[0]["cities"]                 # shown on the lists


def test_python_rule_matches_sql():
    from db.query import is_compensation
    for n, _name, pid, desc, *_ in COMP_ROWS:
        assert is_compensation(desc) == (pid in COMP_PROMOS), desc
    assert not is_compensation(None) and not is_compensation("")
    assert is_compensation("פיצויים ללקוחות")


def test_nothing_else_moves(api, monkeypatch):
    """The lists with the rule = the lists without it minus the compensation
    rows, in the same order (three sorts, list and grouped, with text too)."""
    import db.query as Q
    with_rule = {}
    cases = [("/promos/list", {"chain": "A", "sort": s}) for s in ("discount", "savings", "ending")]
    cases += [("/promos/grouped", {"chain": "A"}), ("/promos/list", {"chain": "A", "q": "שמנת"}),
              ("/promos/list", {"chain": "A", "q": "קופון"})]
    for path, p in cases:
        with_rule[(path, tuple(p.items()))] = [_key(r) for r in _all(api, path, **p)]
    monkeypatch.delitem(Q.CLEANUP_RULES, "compensation")
    for path, p in cases:
        old = [_key(r) for r in _all(api, path, **p)]
        assert [k for k in old if not Q.is_compensation(k[2])] == with_rule[(path, tuple(p.items()))], (path, p)
        if "q" not in p:
            assert any(Q.is_compensation(k[2]) for k in old)   # the rule did remove something here


def test_pricing_still_sees_them(api, data):
    with data.connect() as c:
        stores = [{"chain_id": r[0], "store_id": r[1]} for r in c.execute(
            text("SELECT chain_id, store_id FROM stores WHERE id = ANY(:f)"), {"f": list(data.a_live)})]
    res = api.post("/promos/bulk", json={"stores": stores, "item_codes": [code(63)]})
    assert res.status_code == 200
    descs = {p["promo_description"] for rows in res.json().values() for p in rows}
    assert "35ש\"ח-קופון פיצוי פריניר" in descs


def test_count_and_report(api, data, monkeypatch, capsys):
    import db.query as Q
    import tests.test_search_filtered_pg as F0
    from scripts import su11a65_promo_report as R
    lv = Q.Liveness(live_fks=frozenset(F0.LIVE), dead_pairs=frozenset(), dead_names=frozenset(),
                    live_cities=frozenset(), live_chains=frozenset())
    monkeypatch.setattr(Q, "get_liveness", lambda: lv)
    n = len(data.a_live)
    with data.connect() as c:
        out = Q.count_compensation(c, examples=10)
        assert out["counts"] == {"rows": 5 * n, "promotions": 4}
        assert [(r["chain_id"], r["rows"], r["promotions"], r["items"]) for r in out["by_chain"]] == [("A", 5 * n, 4, 5)]
        assert sorted(r["promo_id"] for r in out["examples"]) == sorted(COMP_PROMOS)
        cleanup = Q.count_promo_list_cleanup(c, examples=3)
        assert cleanup["counts"]["compensation"] == 5 * n
        gifts = Q.count_gift_coupons(c, examples=50)   # after the cleanup: N3 yes, K1 / K2 no
        assert code(67) in {r["item_code"] for r in gifts["examples"]}
        assert not {r["item_code"] for r in gifts["examples"]} & {code(i) for i in COMP_ITEMS}
        R.compensation(c)
    printed = capsys.readouterr().out
    assert "rows: " in printed and "שסטוביץ" in printed
    fp, near = printed.split("near misses", 1)
    assert "פצוי ללקוח" in fp.split("possible false positives", 1)[1]
    assert "פיצוחים" in near and "פיצוי" not in near
