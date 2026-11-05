"""SU11A-62 promo search and list cleanup against a real Postgres:
  * relevance (SU11A-65 follow-up order): name starts with the text > name
    contains it > only the description matches > only in a flavour phrase
    ("טעם שמנת"), a category the text names first
    (low-confidence labels at department level only); the matching product is a
    promotion's example (public מבצעים מקודמים and the admin search), with the
    matching-product count;
  * SU11A-63 H2: wildcards are literal, text under 2 real characters is no
    search, and an unfiltered list is [] without touching the DB;
  * the cleanup rules ("-0%" rows, coupon / threshold basket rows) on the lists
    only, with the diagnostic counts;
  * the admin pin coverage (cities where a pin shows).

Data: the SU11A-58 fixture (tests/test_promo_curation_su11a58_pg.py) plus the
rows below, all in chain A's live branches. SKIPPED unless SCRP_TEST_PG_URL is set.
"""
import re

import pytest
from sqlalchemy import text

from tests.test_promo_curation_su11a58_pg import (  # noqa: F401  (fixtures)
    FUTURE, H, PG_URL, client, engine, pin, server,
)

pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

FLAVOUR = re.compile(r"(^|\s)ו?ב?(טעם|טעמי|טעמים)(\s.*)?$")


def tier(row: dict, q: str) -> int:
    """The SQL rank (db.query.promo_match_sql) without a category boost; the
    SU11A-65 follow-up order: barcode, name starts, name contains, description
    only, flavour only."""
    name, desc = row.get("product_name") or "", row.get("promo_description") or ""
    if row["item_code"] == q:
        return 0
    if name.startswith(q):
        return 2
    if q in FLAVOUR.sub("", name):
        return 4
    return 8 if q in name else 6


def code(n: int) -> str:
    return f"72999100000{n:02d}"


# (item, name, promotion, description, min_qty, rate, price): shelf price 10.
ROWS = [
    (1, "שמנת מתוקה 38% תנובה", "S1", "מבצע ס1", 1, None, 9),                    # starts: 10%
    (2, "גבינת שמנת 30%", "S2", "מבצע ס2", 1, None, 8),                           # contains, category: 20%
    (3, "רוטב פטריות שמנת", "S3", "מבצע ס3", 1, None, 7),                         # contains, low label: 30%
    (4, "בייגלה שטוחים טעם שמנת בצל אסם 270 גרם", "S4", "מבצע ס4", 1, None, 4),   # flavour: 60%
    (5, "חטיף תירס", "S4", "מבצע ס4", 1, None, 3),                                # same promotion, no match: 70%
    (6, "ג'לילנד גלידה בטעמי שמנת ותות", "S5", "מבצע ס5", 1, None, 5),            # flavour: 50%
    (7, "חמאה 82%", "S6", "מבצע שמנת וחמאה", 1, None, 9.5),                       # description: 5%
    (8, "שמנת חמוצה 15%", "S7", "מבצע ס7", 1, None, 8),                           # two matches in S7
    (9, "תן צאפ טבעות בטעם שמנת בצל 50 גרם", "S7", "מבצע ס7", 1, None, 2),        # ... the flavour one cheaper
    # cleanup
    (20, "ניקויבדיקה אפס", "Z1", "מבצע אפס", 1, None, 10),                        # -0%: hidden
    (21, "ניקויבדיקה קופון", "Z2", "קופון איש 50 מעל 249", 1, None, None),          # coupon basket: hidden
    (22, "ניקויבדיקה מעל", "Z3", "מעל ₪100 הנחה 20", 1, None, None),               # threshold basket: hidden
    (23, "ניקויבדיקה מותנה", "Z4", "מבצע מותנה", 1, None, None),                  # basket, no coupon: kept
    (24, "ניקויבדיקה קופון אמיתי", "Z5", "קופון 30% הנחה", 1, None, 7),           # coupon text, real 30%: kept
    # wildcards
    (30, "קוד ab%1", "W1", "מבצע w1", 1, None, 8),
    (31, "קוד abc1", "W2", "מבצע w2", 1, None, 8),
    (32, "קוד x_y", "W3", "מבצע w3", 1, None, 8),
    (33, "קוד xzy", "W4", "מבצע w4", 1, None, 8),
]


@pytest.fixture(scope="module")
def eng(engine):  # noqa: F811
    return load_rows(engine)


def load_rows(engine):  # noqa: F811
    """The rows above in chain A's live branches (also used by SU11A-65)."""
    from tests.test_promos_page_su11a60_pg import CATALOG
    from tests.test_promo_curation_su11a58_pg import _run_sql
    _run_sql(engine, CATALOG)
    with engine.begin() as c:
        for cid, parent, level, name in (("D90", None, 1, "מוצרי חלב"), ("D90.C01", "D90", 2, "שמנת"),
                                         ("D91", None, 1, "חטיפים")):
            c.execute(text("INSERT INTO categories (id, parent_id, level, name_he, taxonomy_version) "
                           "VALUES (:i, :p, :l, :n, 'v1') ON CONFLICT DO NOTHING"),
                      {"i": cid, "p": parent, "l": level, "n": name})
        for n, cid, conf in ((2, "D90.C01", "high"), (3, "D90.C01", "low")):
            c.execute(text("INSERT INTO item_categories (item_code, category_id, confidence, source, taxonomy_version) "
                           "VALUES (:c, :k, :f, 'rule', 'v1')"), {"c": code(n), "k": cid, "f": conf})
        for n, name, *_ in ROWS:
            c.execute(text("INSERT INTO items VALUES (:c, 1, :n, 'יצרן', '1', 1, 0, 'יחידה')"), {"c": code(n), "n": name})
        for fk in engine.a_live:
            for n, _name, pid, desc, qty, rate, price in ROWS:
                c.execute(text("INSERT INTO prices (store_fk, item_code, price_update_date, item_price, "
                               "unit_of_measure_price) VALUES (:f, :c, '2026-10-22 10:00', 10, 10)"),
                          {"f": fk, "c": code(n)})
                c.execute(text("INSERT INTO promos (store_fk, item_code, promo_id, promo_description, min_qty, "
                               "discount_rate, discount_price, promo_end) VALUES (:f, :c, :i, :d, :q, :r, :p, :e)"),
                          {"f": fk, "c": code(n), "i": pid, "d": desc, "q": qty, "r": rate, "p": price, "e": FUTURE})
    return engine


@pytest.fixture
def api(eng, client):  # noqa: F811
    import api.categories as cats
    cats.reset_tree_cache()
    yield client
    cats.reset_tree_cache()


def items(rows):
    return [int(r["item_code"][-2:]) for r in rows if r["item_code"].startswith("72999100000")]


# ------------------------------------------------------------------ relevance

def test_list_relevance_order(api):
    """Description, then name start, then contains (category first), flavour
    last; each tier by discount. The 60% bagel and 70% snack never lead."""
    rows = api.get("/promos/list", params={"q": "שמנת"}).json()
    # 8 (20%), 1 (10%) start | 2 contains + category | 3 contains (its low label
    # is below a department: no boost) | 7 description only (SU11A-65 follow-up:
    # "חמאה" is not cream) | 9 (80%), 4 (60%), 6 (50%) flavour
    assert items(rows) == [8, 1, 2, 3, 7, 9, 4, 6]
    assert [tier(r, "שמנת") for r in rows] == [2, 2, 4, 4, 6, 8, 8, 8]   # 2 is 3 in SQL (boost)


def test_grouped_relevance_within_each_branch(api, eng):
    rows = api.get("/promos/grouped", params={"q": "שמנת", "chain": "A"}).json()
    for fk in eng.a_live:
        assert items([r for r in rows if r["store_fk"] == fk]) == items(
            api.get("/promos/list", params={"q": "שמנת"}).json())


def test_promoted_example_is_the_best_match(api, eng):
    assert pin(api, "S4", rank=1).status_code == 200
    assert pin(api, "S7", rank=2).status_code == 200
    rows = api.get("/promos/promoted", params={"q": "שמנת"}).json()
    assert [(r["item_code"], r["item_count"]) for r in rows] == [(code(4), 1), (code(8), 2)]
    # without text the example is the best discount, as before
    rows = api.get("/promos/promoted").json()
    assert [r["item_code"] for r in rows] == [code(5), code(9)]


def test_admin_search_relevance_example_and_matches(api):
    r = api.get("/admin/promos/search", params={"q": "שמנת"}, headers=H).json()["items"]
    order = [x["promo_id"] for x in r if x["promo_id"].startswith("S")]
    assert order == ["S1", "S7", "S2", "S3", "S6", "S4", "S5"]   # S6: description only (SU11A-65 follow-up)
    by = {x["promo_id"]: x for x in r}
    assert by["S4"]["sample"]["item_code"] == code(4) and by["S4"]["matches"] == 1   # not the 70% snack
    assert by["S7"]["sample"]["item_code"] == code(8) and by["S7"]["matches"] == 2   # start beats flavour
    assert by["S6"]["sample"]["item_code"] == code(7)
    chain_only = api.get("/admin/promos/search", params={"chain": "A"}, headers=H).json()["items"]
    assert chain_only and all(x["matches"] is None for x in chain_only)


def test_category_boost_and_low_rule():
    """Unit: the boost ids (a category named by the text, its subtree) and the
    low-confidence ids (only under a matched department)."""
    import api.categories as cats

    class Conn:
        def rollback(self):
            pass

    nodes = {"D90": {"id": "D90", "parent_id": None, "level": 1, "name_he": "מוצרי חלב", "active": True},
             "D90.C01": {"id": "D90.C01", "parent_id": "D90", "level": 2, "name_he": "חלב ומשקאות חלב",
                         "active": True},
             "D90.C02": {"id": "D90.C02", "parent_id": "D90", "level": 2, "name_he": "שמנת", "active": True},
             "D91": {"id": "D91", "parent_id": None, "level": 1, "name_he": "חלב", "active": False}}
    orig = cats.tree
    cats.tree = lambda conn: {"nodes": nodes, "version": "v1"}
    try:
        s = cats.promo_search(Conn(), "חלב")
        # the department's name has the word too, but the category below it is
        # more specific; the inactive D91 is ignored
        assert s.boost_ids == ("D90.C01",) and s.boost_low_ids == ()
        s = cats.promo_search(Conn(), "שמנת")
        assert s.boost_ids == ("D90.C02",) and s.boost_low_ids == ()
        s = cats.promo_search(Conn(), "מוצרי חלב")
        assert set(s.boost_ids) == {"D90", "D90.C01", "D90.C02"} and set(s.boost_low_ids) == set(s.boost_ids)
        assert cats.promo_search(Conn(), "7290000000001").boost_ids == ()
        assert cats.promo_search(Conn(), "%") is None
    finally:
        cats.tree = orig


# ------------------------------------------------------------------ SU11A-63 H2

@pytest.mark.parametrize("q", ["%", " ", "_", "%%", "a%", "  _ ", "\\", "a_"])
@pytest.mark.parametrize("path", ["/promos/list", "/promos/grouped"])
def test_wildcard_or_blank_text_is_no_search_and_no_query(api, monkeypatch, path, q):
    import api.routers.promos as R

    def boom(*a, **k):
        raise AssertionError("no DB access for an unfiltered list")

    monkeypatch.setattr(R, "get_curation", boom)
    monkeypatch.setattr(R, "fetch_flat_promos", boom)
    monkeypatch.setattr(R, "fetch_grouped_promos", boom)
    r = api.get(path, params={"q": q})
    assert (r.status_code, r.json()) == (200, [])


def test_percent_25_and_wildcards_match_literally(api):
    # "%25" as sent by a browser is "%" (above); the literal text "%25" is a search that matches nothing here
    assert api.get("/promos/list", params={"q": "%25"}).json() == []
    assert items(api.get("/promos/list", params={"q": "ab%"}).json()) == [30]
    assert items(api.get("/promos/list", params={"q": "x_y"}).json()) == [32]
    assert items(api.get("/promos/list", params={"q": "abc"}).json()) == [31]
    assert items(api.get("/promos/grouped", params={"q": "ab%", "chain": "A"}).json()) == [30] * 2
    r = api.get("/promos/list", params={"q": "x" * 101})
    assert r.status_code == 422


def test_admin_search_wildcards(api):
    for q in ("%", "%%", " _ ", "a%"):
        r = api.get("/admin/promos/search", params={"q": q}, headers=H)
        assert (r.status_code, r.json()) == (422, {"code": "query_required"}), q
    assert [x["promo_id"] for x in api.get("/admin/promos/search", params={"q": "ab%"}, headers=H
                                           ).json()["items"]] == ["W1"]
    assert [x["promo_id"] for x in api.get("/admin/promos/search", params={"q": "x_y"}, headers=H
                                           ).json()["items"]] == ["W3"]


def test_normal_text_still_searches(api):
    assert items(api.get("/promos/list", params={"q": "  גבינת   שמנת "}).json()) == [2]
    assert items(api.get("/promos/list", params={"q": code(1)}).json()) == [1]


# ------------------------------------------------------------------ cleanup

def test_cleanup_rules_on_the_lists(api):
    for path, extra in (("/promos/list", {}), ("/promos/grouped", {"chain": "A"})):
        assert set(items(api.get(path, params={"q": "ניקויבדיקה", **extra}).json())) == {23, 24}, path
    assert pin(api, "Z1", rank=1).status_code == 200                       # a pinned "-0%" promotion ...
    assert api.get("/promos/promoted", params={"q": "ניקויבדיקה"}).json() == []   # ... shows nowhere


def test_cleanup_counts(eng):
    import db.query as Q
    import tests.test_search_filtered_pg as F0
    lv = Q.Liveness(live_fks=frozenset(F0.LIVE), dead_pairs=frozenset(), dead_names=frozenset(),
                    live_cities=frozenset(), live_chains=frozenset())
    orig = Q.get_liveness
    Q.get_liveness = lambda: lv
    try:
        with eng.connect() as c:
            out = Q.count_promo_list_cleanup(c, q="ניקויבדיקה")
            assert out["counts"] == {"rows_before_cleanup": 5 * len(eng.a_live), "no_discount": len(eng.a_live),
                                     "coupon": 2 * len(eng.a_live), "compensation": 0}   # SU11A-66 rule
            assert {r["item_code"] for r in out["examples"]["no_discount"]} == {code(20)}
            assert {r["item_code"] for r in out["examples"]["coupon"]} == {code(21), code(22)}
            whole = Q.count_promo_list_cleanup(c, examples=10)
            assert whole["counts"]["no_discount"] >= len(eng.a_live)
            assert all(len(v) <= 10 for v in whole["examples"].values())
    finally:
        Q.get_liveness = orig


def test_report_script_before_and_after(eng, capsys, monkeypatch):
    """scripts/su11a62_promo_report.py on the fixture: "before" is the old
    discount order (the 80% flavour snack first), "after" the new one."""
    import api.categories as cats
    import db.query as Q
    import tests.test_search_filtered_pg as F0
    from scripts import su11a62_promo_report as R
    lv = Q.Liveness(live_fks=frozenset(F0.LIVE), dead_pairs=frozenset(), dead_names=frozenset(),
                    live_cities=frozenset(), live_chains=frozenset())
    monkeypatch.setattr(Q, "get_liveness", lambda: lv)
    cats.reset_tree_cache()
    with eng.connect() as c:
        R.top10(c, "שמנת", None)
        R.cleanup(c)
    out = capsys.readouterr().out
    before, after = out.split(" before:")[1].split(" after:")
    after = after.split("== cleanup")[0]
    assert before.strip().splitlines()[0].split(" | ")[1] == "תן צאפ טבעות בטעם שמנת בצל 50 גרם"   # 80%, flavour
    assert "חמאה 82%" not in before                                         # description matches are new
    after_names = [ln.split(" | ")[1] for ln in after.strip().splitlines()]
    assert after_names[0] == "שמנת חמוצה 15%" and "חמאה 82%" in after_names[1:]   # description only: after names
    assert "no_discount: " in out and "coupon: " in out and "ניקויבדיקה אפס" in out


# ------------------------------------------------------------------ admin coverage

def test_pin_coverage(api, eng):
    import tests.test_search_filtered_pg as F0
    assert pin(api, "PA", rank=1).status_code == 200
    assert pin(api, "Z1", rank=2).status_code == 200
    cur = api.get("/admin/promos/curation", headers=H).json()["items"]
    by = {x["promo"]["promo_id"]: x["promo"] for x in cur}
    assert by["PA"]["cities"] == sorted({F0.STORES[fk][1] for fk in eng.a_live})
    assert by["Z1"]["cities"] == []                                       # only "-0%" rows: shows nowhere
    # the search hit carries the same coverage (the pin form)
    hit = api.get("/admin/promos/search", params={"q": "מבצע א"}, headers=H).json()["items"][0]
    assert hit["cities"] == by["PA"]["cities"]
    # what users see agrees: promoted for each covered city has PA, another city has not
    for city in by["PA"]["cities"]:
        assert "PA" in _promoted_ids(api, city)
    other = next(c for c in F0.CITIES if c not in by["PA"]["cities"])
    assert "PA" not in _promoted_ids(api, other)


def _promoted_ids(api, city):
    import tests.test_promo_curation_su11a58_pg as T
    codes = {r["item_code"] for r in api.get("/promos/promoted", params={"city": city}).json()}
    return {"PA"} if T.T1 in codes else set()
