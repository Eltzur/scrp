"""SU11A-67 category browse (db/category_browse.py, /categories/browse-tree and
/categories/{id}/items) against a real Postgres.

Data: the SU11A-50 search-build fixture (tests/test_search_filtered_pg.py:
5 chains, 4 cities, dead stores, every promo kind, a real search build with
search_item_prices) plus the su11a52 catalog tables, a small taxonomy (with an
inactive node and tobacco) and labels of every source x confidence.

SKIPPED unless SCRP_TEST_PG_URL is set.
"""
import itertools
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.test_search_filtered_pg import CITIES, LIVE, PG_URL, engine  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

ROOT = Path(__file__).resolve().parent.parent
NODES = [  # id, parent, level, name, active
    ("D01", None, 1, "מוצרי חלב", True),
    ("D01.C01", "D01", 2, "חלב", True),
    ("D01.C01.S01", "D01.C01", 3, "חלב טרי", True),
    ("D01.C01.S02", "D01.C01", 3, "חלב עמיד", True),
    ("D01.C02", "D01", 2, "גבינות", True),
    ("D01.C03", "D01", 2, "קטגוריה ישנה", False),
    ("D10", None, 1, "אלכוהול וטבק", True),
    ("D10.C01", "D10", 2, "יין", True),
    ("D10.C05", "D10", 2, "טבק וסיגריות", True),
]
LABEL_NODES = ["D01.C01", "D01.C01.S01", "D01.C01.S01", "D01.C02", "D10.C01", "D10.C05", "D01.C03", "D01",
               "D01.C01.S02"]
COMBOS = [(s, c) for s in ("manual", "gs1", "rule", "ai") for c in ("high", "medium", "low")]
VISIBLE = {("manual", "high"), ("manual", "medium"), ("manual", "low"), ("gs1", "high"), ("gs1", "medium"),
           ("rule", "high"), ("rule", "medium"), ("ai", "high")}


@pytest.fixture(scope="module")
def eng(engine):  # noqa: F811
    from tests.test_promo_curation_su11a58_pg import _run_sql
    with engine.begin() as c:
        c.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scrp_app') "
                       "THEN CREATE ROLE scrp_app; END IF; END $$"))
    _run_sql(engine, ROOT / "db" / "migrations" / "su11a52_catalog.sql")
    codes = [r[0] for r in engine.connect().execute(text("SELECT item_code FROM items ORDER BY item_code"))]
    labels = {}
    with engine.begin() as c:
        for i, (nid, parent, level, name, active) in enumerate(NODES):
            c.execute(text("INSERT INTO categories (id, parent_id, level, name_he, sort_order, active, taxonomy_version)"
                           " VALUES (:i, :p, :l, :n, :o, :a, 'v1.2')"),
                      {"i": nid, "p": parent, "l": level, "n": name, "o": i, "a": active})
        combos = itertools.cycle(COMBOS)
        for k, code in enumerate(codes):
            if k % 11 == 10:
                continue                                  # some items have no label
            src, conf = next(combos)
            node = LABEL_NODES[k % len(LABEL_NODES)]
            labels[code] = (node, src, conf)
            c.execute(text("INSERT INTO item_categories (item_code, category_id, confidence, source, taxonomy_version)"
                           " VALUES (:c, :n, :cf, :s, 'v1.2')"), {"c": code, "n": node, "cf": conf, "s": src})
    engine.labels = labels
    return engine


@pytest.fixture
def api(eng, monkeypatch):
    from fastapi.testclient import TestClient

    import api.categories as cats
    import db.category_browse as B
    import db.query as Q
    import db.search_filtered as F
    import db.search_v2 as V
    from api.dependencies import get_db
    from api.main import app

    def _get_db():
        with eng.connect() as conn:
            yield conn

    lv = Q.Liveness(live_fks=frozenset(LIVE), dead_pairs=frozenset(), dead_names=frozenset(),
                    live_cities=frozenset(), live_chains=frozenset())
    monkeypatch.setattr(Q, "get_liveness", lambda: lv)
    monkeypatch.setattr(F, "BATCHES", (3, 5, 8, 400))   # many walk steps
    V._cache.built_at = V._cache.prices_built_at = V._cache.lexicon = None
    cats.reset_tree_cache()
    B.reset_cache()
    Q.reset_today_cache()
    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    cats.reset_tree_cache()
    B.reset_cache()


def _live(eng) -> dict[str, dict]:
    with eng.connect() as c:
        return {r["item_code"]: dict(r) for r in c.execute(text(
            "SELECT item_code, name_norm, chains_live FROM search_items "
            "WHERE NOT is_pseudo AND chains_live >= 1 AND name_norm <> ''")).mappings()}


def _visible(eng, under: str) -> dict[str, dict]:
    """Expected: visible live items under a node, tobacco left out."""
    live = _live(eng)
    out = {}
    for code, (node, src, conf) in eng.labels.items():
        if code in live and (src, conf) in VISIBLE and (node == under or node.startswith(under + ".")) \
                and not node.startswith("D10.C05"):
            out[code] = {**live[code], "category_id": node}
    return out


def _pages(api, cid, limit=7, **params):
    out, offset = [], 0
    for _ in range(100):
        r = api.get(f"/categories/{cid}/items", params={**params, "limit": limit, "offset": offset})
        assert r.status_code == 200, r.text
        body = r.json()
        out += body["items"]
        if not body["has_more"]:
            return out, body
        offset += limit
    raise AssertionError("no end")


# ------------------------------------------------------------------ the predicate

def test_predicate_python_equals_sql(eng):
    import db.category_browse as B
    for s, c in COMBOS:
        assert B.is_visible(s, c) == ((s, c) in VISIBLE), (s, c)
    with eng.connect() as conn:
        got = {r[0] for r in conn.execute(text(f"SELECT ic.item_code FROM item_categories ic WHERE {B.VISIBLE_SQL}"))}
    want = {code for code, (_n, s, c) in eng.labels.items() if (s, c) in VISIBLE}
    assert got == want
    assert not B.is_visible("ai", "medium") and not B.is_visible("rule", "low") and not B.is_visible("gs1", "low")


# ------------------------------------------------------------------ the tree

def test_browse_tree_counts_links_and_tobacco(api, eng):
    import db.category_browse as B
    tree = api.get("/categories/browse-tree").json()
    assert "_unlinked" not in tree
    depts = {d["id"]: d for d in tree["departments"]}
    assert set(depts) == {"D01", "D10"}
    for d in ("D01", "D10"):
        assert depts[d]["count"] == len(_visible(eng, d)), d
    cats = {c["id"]: c for c in depts["D01"]["children"]}
    assert "D01.C03" not in cats                     # inactive
    assert [c["id"] for c in depts["D10"]["children"]] == (["D10.C01"] if len(_visible(eng, "D10.C01")) >= 5 else [])
    for cid in ("D01.C01", "D01.C02"):
        n = len(_visible(eng, cid))
        assert (cid in cats) == (n >= B.MIN_LINKED)
        if cid in cats:
            assert cats[cid]["count"] == n and cats[cid]["linked"]
    subs = {s["id"]: s["count"] for s in cats.get("D01.C01", {"children": []})["children"]}
    for sid in ("D01.C01.S01", "D01.C01.S02"):
        n = len(_visible(eng, sid))
        assert (sid in subs) == (n >= B.MIN_LINKED), (sid, n)
    assert "D10.C05" not in str(tree)


def test_min_linked_rule_pure():
    import db.category_browse as B
    nodes = {n[0]: {"id": n[0], "parent_id": n[1], "level": n[2], "name_he": n[3], "name_en": "", "active": n[4]}
             for n in NODES}
    t = B.build_tree(nodes, {"D01.C01": 4, "D01.C02": 5, "D01.C01.S01": 1, "D10.C05": 50, "D01.C03": 2})
    d01 = next(d for d in t["departments"] if d["id"] == "D01")
    assert d01["count"] == 4 + 5 + 1 + 2       # an inactive node's labels count for its active ancestor
    assert [c["id"] for c in d01["children"]] == ["D01.C01", "D01.C02"]   # D01.C01: 4 + its sub-category 1 = 5
    assert d01["children"][0]["children"] == []                       # D01.C01.S01: 1 item, not linked
    t2 = B.build_tree(nodes, {"D01.C01": 3, "D01.C01.S01": 2})
    d = next(d for d in t2["departments"] if d["id"] == "D01")
    assert [c["id"] for c in d["children"]] == ["D01.C01"] and d["children"][0]["children"] == []
    d10 = next(d for d in t["departments"] if d["id"] == "D10")
    assert d10["count"] == 0 and d10["children"] == []                 # tobacco counts nowhere


def test_tree_cache_follows_the_build_stamp(api, eng, monkeypatch):
    import db.category_browse as B
    import db.search_v2 as V
    first = api.get("/categories/browse-tree").json()
    live = sorted(set(_live(eng)) - set(eng.labels))
    assert live, "need a live unlabelled item"
    with eng.begin() as c:
        c.execute(text("INSERT INTO item_categories (item_code, category_id, confidence, source, taxonomy_version)"
                       " VALUES (:c, 'D01.C02', 'high', 'manual', 'v1.2')"), {"c": live[0]})
    try:
        monkeypatch.setattr(B, "STAMP_TTL_S", 0.0)
        V._cache.built_at = None
        assert api.get("/categories/browse-tree").json() == first     # same build: cached
        with eng.begin() as c:
            c.execute(text("UPDATE search_items SET built_at = built_at + interval '1 second'"))
            c.execute(text("UPDATE search_item_prices SET built_at = built_at + interval '1 second'"))
        V._cache.built_at = V._cache.prices_built_at = None
        again = api.get("/categories/browse-tree").json()
        d01 = lambda t: next(d for d in t["departments"] if d["id"] == "D01")["count"]  # noqa: E731
        assert d01(again) == d01(first) + 1
        assert again["built_at"] != first["built_at"]
    finally:
        with eng.begin() as c:
            c.execute(text("DELETE FROM item_categories WHERE item_code = :c"), {"c": live[0]})
            c.execute(text("UPDATE search_items SET built_at = built_at - interval '1 second'"))
            c.execute(text("UPDATE search_item_prices SET built_at = built_at - interval '1 second'"))
        V._cache.built_at = V._cache.prices_built_at = None


# ------------------------------------------------------------------ a page, no city

def test_popular_and_name_order_paging_and_counts(api, eng):
    want = _visible(eng, "D01")
    items, last = _pages(api, "D01")
    codes = [p["product"]["item_code"] for p in items]
    assert len(codes) == len(set(codes))
    assert set(codes) <= set(want)
    # every visible item with a build quote is listed (search_item_prices of the build)
    with eng.connect() as c:
        priced = {r[0] for r in c.execute(text("SELECT DISTINCT item_code FROM search_item_prices"))}
    assert set(codes) == set(want) & priced
    keyed = sorted(codes, key=lambda k: (-want[k]["chains_live"], want[k]["name_norm"], k))
    assert codes == keyed
    assert all(p["category_id"] == want[p["product"]["item_code"]]["category_id"] for p in items)
    assert last["total_exact"] and last["category"]["id"] == "D01" and [x["id"] for x in last["path"]] == ["D01"]
    named, _ = _pages(api, "D01", sort="name")
    nc = [p["product"]["item_code"] for p in named]
    assert nc == sorted(nc, key=lambda k: (want[k]["name_norm"], k))


def test_cheapest_order(api, eng):
    items, _ = _pages(api, "D01", sort="cheapest")
    best = [p["cheapest_price"] for p in items]
    assert best == sorted(best), best


def test_chain_filter_and_on_promo_no_city(api, eng):
    items, _ = _pages(api, "D01", chain="A")
    assert items and all(q["chain_id"] == "A" for p in items for q in p["quotes"])
    with eng.connect() as c:
        in_a = {r[0] for r in c.execute(text("SELECT item_code FROM search_item_prices WHERE chain_id = 'A'"))}
        promo = {r[0] for r in c.execute(text(
            "SELECT item_code FROM search_item_prices WHERE promo_unit_price IS NOT NULL "
            "AND (promo_end IS NULL OR CAST(promo_end AS timestamp) >= now())"))}
    assert {p["product"]["item_code"] for p in items} == set(_visible(eng, "D01")) & in_a
    promos, body = _pages(api, "D01", on_promo="true")
    assert {p["product"]["item_code"] for p in promos} == set(_visible(eng, "D01")) & promo
    assert body["total"] == len(promos)
    assert all(any(q["is_promo"] for q in p["quotes"]) for p in promos)


# ------------------------------------------------------------------ a city

def test_city_page_equals_live_prices(api, eng):
    import db.query as Q
    want = _visible(eng, "D01")
    for city in CITIES[:3]:
        items, last = _pages(api, "D01", city=city)
        codes = [p["product"]["item_code"] for p in items]
        with eng.connect() as c:
            live = Q.group_by_product(Q.fetch_prices(c, sorted(want), city=[city], page=True))
        assert set(codes) == set(live), city
        assert codes == sorted(codes, key=lambda k: (-want[k]["chains_live"], want[k]["name_norm"], k))
        for p in items:
            assert all(q["city"] == city for q in p["quotes"])
        assert last["total_exact"] and last["total"] == len(codes)
        promo, _ = _pages(api, "D01", city=city, on_promo="true")
        with eng.connect() as c:
            fks = [r[0] for r in c.execute(text("SELECT id FROM stores WHERE city_canonical = :c"), {"c": city})
                   if r[0] in LIVE]                          # live branches only, as the page
            has = {r[0] for r in c.execute(text(
                "SELECT DISTINCT item_code FROM promos WHERE store_fk = ANY(:f) "
                "AND (promo_end >= now() OR promo_end IS NULL)"), {"f": fks})}
        assert {p["product"]["item_code"] for p in promo} == set(live) & has, city
        chain_a, _ = _pages(api, "D01", city=city, chain="A")
        assert all(q["chain_id"] == "A" and q["city"] == city for p in chain_a for q in p["quotes"])


# ------------------------------------------------------------------ errors and caps

@pytest.mark.parametrize("cid", ["D99", "D01.C03", "D10.C05", "x", "D01.C01.S01.Z1"])
def test_404(api, cid):
    r = api.get(f"/categories/{cid}/items")
    assert r.status_code == 404 and r.json()["code"] == "category_not_found"


def test_tobacco_left_out_of_d10(api, eng):
    items, _ = _pages(api, "D10")
    assert all(not (eng.labels[p["product"]["item_code"]][0]).startswith("D10.C05") for p in items)


@pytest.mark.parametrize("params,code", [
    ({"city": "עיר שאינה קיימת"}, "unknown_city"),
    ({"chain": "Z"}, "unknown_chain"),
])
def test_422_city_chain(api, params, code):
    r = api.get("/categories/D01/items", params=params)
    assert r.status_code == 422 and r.json()["code"] == code


@pytest.mark.parametrize("params", [{"offset": 2001}, {"limit": 61}, {"limit": 0}, {"sort": "price"},
                                    {"offset": -1}])
def test_422_caps(api, params):
    assert api.get("/categories/D01/items", params=params).status_code == 422


def test_offset_cap_edge(api):
    assert api.get("/categories/D01/items", params={"offset": 2000, "limit": 60}).status_code == 200


def test_unlinked_page_still_answers(api, eng):
    r = api.get("/categories/D01.C01.S02/items")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(_visible(eng, "D01.C01.S02"))


def test_nginx_snippet_has_both_locations():
    conf = (ROOT / "deploy" / "nginx" / "xxl-ratelimit-api.conf").read_text(encoding="utf-8")
    heavy = conf.split("location ~ ^/categories/[A-Za-z0-9.]+/items$ {", 1)[1].split("}", 1)[0]
    assert "zone=xxl_heavy" in heavy and "zone=xxl_api" in heavy and "xxl-api-proxy.conf" in heavy
    tree = conf.split("location = /categories/browse-tree {", 1)[1].split("}", 1)[0]
    assert "zone=xxl_api" in tree and "xxl_heavy" not in tree and "xxl-api-proxy.conf" in tree
