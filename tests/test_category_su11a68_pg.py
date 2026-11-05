"""SU11A-68 against a real Postgres (the SU11A-67 fixture: the SU11A-50 search
build + the su11a52 catalog with labels of every source x confidence):

  * sort=cheapest with a city orders by the city's own lowest live price (the
    price the card shows), checked against db.query.fetch_prices;
  * q inside a category: search v2's matcher restricted to the category's
    visible live items, relevance first, escaping, the 2-character minimum and
    the 100-character cap;
  * category on /search and /compare on every engine path (v2, filtered, old):
    only visibly labelled items under the node, tobacco / unknown -> 422, and
    without the parameter the answer is unchanged;
  * GET /categories/dominant.

SKIPPED unless SCRP_TEST_PG_URL is set.
"""
import pytest
from sqlalchemy import text

from tests.test_category_browse_su11a67_pg import (  # noqa: F401  (fixtures)
    CITIES, LIVE, PG_URL, VISIBLE, _pages, _visible, api, engine, eng,
)

pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")


@pytest.fixture(scope="module")
def trgm(eng):
    """pg_trgm for search v2's typo round (a query with no match runs it); None when the server lacks it."""
    try:
        with eng.begin() as c:
            c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        return True
    except Exception:  # noqa: BLE001
        return None


@pytest.fixture
def api2(api, monkeypatch, trgm):
    import db.category_browse as B
    if not trgm:
        pytest.skip("pg_trgm not available on this server (search v2's typo round needs it)")
    B.reset_city_cache()
    B.reset_codes_cache()
    monkeypatch.setattr(B, "CITY_CHEAPEST_BATCHES", (3, 5, 400))   # many walk steps
    yield api
    B.reset_city_cache()
    B.reset_codes_cache()


def _city_prices(eng, codes, city, chain=None):
    import db.query as Q
    with eng.connect() as c:
        return Q.group_by_product(Q.fetch_prices(c, sorted(codes), city=[city], chain_id=[chain] if chain else None,
                                                 page=True))


# ------------------------------------------------------------------ 1. cheapest in a city

@pytest.mark.parametrize("city", CITIES[:3])
def test_city_cheapest_is_the_city_price_order(api2, eng, city):
    want = _visible(eng, "D01")
    live = _city_prices(eng, want, city)
    items, last = _pages(api2, "D01", city=city, sort="cheapest")
    codes = [p["product"]["item_code"] for p in items]
    assert set(codes) == set(live) and len(codes) == len(set(codes))
    # the card's price, as the page shows it, is non-decreasing ...
    shown = [p["cheapest_price"] for p in items]
    assert shown == sorted(shown), (city, shown)
    # ... and equals the live price of the city for every item (ties by name)
    assert codes == sorted(codes, key=lambda k: (live[k]["cheapest_price"], want[k]["name_norm"], k))
    assert last["total_exact"] and last["total"] == len(codes)


def test_city_cheapest_with_chain_and_promo(api2, eng):
    city = CITIES[0]
    want = _visible(eng, "D01")
    live = _city_prices(eng, want, city, chain="A")
    items, _ = _pages(api2, "D01", city=city, sort="cheapest", chain="A")
    assert {p["product"]["item_code"] for p in items} == set(live)
    assert [p["cheapest_price"] for p in items] == sorted(p["cheapest_price"] for p in items)
    promo, _ = _pages(api2, "D01", city=city, sort="cheapest", on_promo="true")
    assert [p["cheapest_price"] for p in promo] == sorted(p["cheapest_price"] for p in promo)
    assert {p["product"]["item_code"] for p in promo} <= set(_city_prices(eng, want, city))


def test_city_cheapest_pages_reuse_one_walk(api2, eng, monkeypatch):
    import db.category_browse as B
    calls = []
    real = B._city_price_filter

    def counting(conn, fks, best):
        f = real(conn, fks, best)

        def run(codes):
            calls.append(len(codes))
            return f(codes)
        return run
    monkeypatch.setattr(B, "_city_price_filter", counting)
    _pages(api2, "D01", city=CITIES[0], sort="cheapest", limit=3)
    n = len(calls)
    _pages(api2, "D01", city=CITIES[0], sort="cheapest", limit=3)
    assert n > 0 and len(calls) == n            # the second walk came from the cache


# ------------------------------------------------------------------ 2. q in a category

def _v2_matches(eng, q):
    import db.search_v2 as V
    with eng.connect() as c:
        aliases, _ = V._lexicon(c)
        ranked, _ = V.ranked_candidates(c, q, aliases)
        return {r["item_code"]: r for r in ranked.take(10_000)}


def test_q_uses_search_v2_matcher_inside_the_category(api2, eng):
    want = _visible(eng, "D01")
    with eng.connect() as c:
        priced = {r[0] for r in c.execute(text("SELECT DISTINCT item_code FROM search_item_prices"))}
    for q in ("חלב", "שוקולד", "תנובה", "במבה 80", "לחם מלא"):
        matches = _v2_matches(eng, q)
        items, last = _pages(api2, "D01", q=q)
        codes = [p["product"]["item_code"] for p in items]
        assert set(codes) == set(matches) & set(want) & priced, q
        assert last["q"] == q and last["total_exact"]
        # relevance first, then the sort (popular)
        keyed = sorted(codes, key=lambda k: (matches[k]["tier"], -want[k]["chains_live"], want[k]["name_norm"], k))
        assert codes == keyed, q
        named, _ = _pages(api2, "D01", q=q, sort="name")
        nc = [p["product"]["item_code"] for p in named]
        assert nc == sorted(nc, key=lambda k: (matches[k]["tier"], want[k]["name_norm"], k))


def test_q_with_city(api2, eng):
    want = _visible(eng, "D01")
    city = CITIES[1]
    matches = _v2_matches(eng, "חלב")
    live = _city_prices(eng, set(want) & set(matches), city)
    items, _ = _pages(api2, "D01", q="חלב", city=city)
    assert {p["product"]["item_code"] for p in items} == set(live)
    cheap, _ = _pages(api2, "D01", q="חלב", city=city, sort="cheapest")
    codes = [p["product"]["item_code"] for p in cheap]
    assert codes == sorted(codes, key=lambda k: (matches[k]["tier"], live[k]["cheapest_price"], want[k]["name_norm"], k))


@pytest.mark.parametrize("q", ["%", "  ", "ח", "%_", "\\\\", "_ח"])
def test_q_under_two_real_characters_is_ignored(api2, q):
    plain = api2.get("/categories/D01/items").json()
    got = api2.get("/categories/D01/items", params={"q": q}).json()
    assert got["q"] is None
    assert [i["product"]["item_code"] for i in got["items"]] == [i["product"]["item_code"] for i in plain["items"]]


def test_q_is_escaped(api2):
    some = api2.get("/categories/D01/items", params={"q": "חל"}).json()["items"]
    assert some
    # an unescaped LIKE would read % and _ as wildcards and match "חל..."
    for q in ("ח%ל", "ח_ל"):
        assert api2.get("/categories/D01/items", params={"q": q}).json()["items"] == [], q


def test_q_length_cap(api2):
    assert api2.get("/categories/D01/items", params={"q": "א" * 101}).status_code == 422
    assert api2.get("/categories/D01/items", params={"q": "א" * 100}).status_code == 200


# ------------------------------------------------------------------ 3. category on /search and /compare

PATHS = [  # (endpoint, env SEARCH_V2, env SEARCH_V2_FILTERED, extra params)
    ("/search", "on", "off", {}),                                   # v2
    ("/search", "off", "off", {}),                                  # old path
    ("/search", "on", "on", {"city": CITIES[0], "engine": "v2"}),   # filtered
    ("/search", "on", "off", {"city": CITIES[0]}),                  # old path, city
    ("/compare", "on", "off", {}),                                  # old compare
    ("/compare", "on", "on", {"engine": "v2"}),                     # filtered compare
]


@pytest.mark.parametrize("path,v2,filtered,extra", PATHS)
def test_search_category_filter_every_path(api2, eng, monkeypatch, path, v2, filtered, extra):
    import api.routers.search as R
    monkeypatch.setenv("SEARCH_V2", v2)
    monkeypatch.setenv("SEARCH_V2_FILTERED", filtered)
    R._cache.clear() if hasattr(R._cache, "clear") else None
    under = {code for code, (node, s, c) in eng.labels.items()
             if (s, c) in VISIBLE and (node == "D01" or node.startswith("D01."))}
    checked = 0
    for q in ("חלב", "שוקולד", "לחם"):
        allp = api2.get(path, params={"q": q, "limit": 100, **extra}).json()["items"]
        got = api2.get(path, params={"q": q, "limit": 100, "category": "D01", **extra})
        assert got.status_code == 200, got.text
        codes = [i["product"]["item_code"] for i in got.json()["items"]]
        assert set(codes) <= under, (path, q)
        # exactly the unfiltered answer's items that are in the category, same order
        assert codes == [i["product"]["item_code"] for i in allp if i["product"]["item_code"] in under] \
            or path == "/search" and v2 == "on" and filtered == "off" and not extra and \
            set(codes) == {i["product"]["item_code"] for i in allp} & under, (path, q)
        checked += len(codes)
    assert checked > 0


@pytest.mark.parametrize("cat", ["D10.C05", "D99", "D01.C03", "x", "D01.C01.S01.Z"])
@pytest.mark.parametrize("path", ["/search", "/compare"])
def test_search_category_422(api2, path, cat):
    r = api2.get(path, params={"q": "חלב", "category": cat})
    assert r.status_code == 422 and r.json()["code"] == "unknown_category"


def test_search_without_category_is_unchanged(api2, monkeypatch):
    """The answer without the parameter is byte-identical whatever the cache saw."""
    monkeypatch.setenv("SEARCH_V2", "on")
    first = api2.get("/search", params={"q": "חלב"}).content
    api2.get("/search", params={"q": "חלב", "category": "D01"})
    assert api2.get("/search", params={"q": "חלב"}).content == first


# ------------------------------------------------------------------ 4. dominant

def test_dominant_category(api2, eng):
    lab = eng.labels
    vis = [c for c, (n, s, cf) in lab.items() if (s, cf) in VISIBLE]
    cheese = [c for c in vis if lab[c][0] == "D01.C02"][:6]
    r = api2.get("/categories/dominant", params={"code": cheese}).json()["category"]
    assert r["id"] == "D01.C02" and r["share"] == 1.0
    milk = [c for c in vis if lab[c][0].startswith("D01.C01")][:3]
    mixed = api2.get("/categories/dominant", params={"code": cheese[:3] + milk}).json()["category"]
    assert mixed["id"] == "D01"                              # only the department is shared by 60%
    assert api2.get("/categories/dominant", params={"code": cheese[:3]}).json()["category"] is None   # < 4
    hidden = [c for c, (n, s, cf) in lab.items() if (s, cf) not in VISIBLE and n == "D01.C02"][:6]
    assert api2.get("/categories/dominant", params={"code": hidden}).json()["category"] is None
    tob = [c for c in vis if lab[c][0] == "D10.C05"][:6]
    assert api2.get("/categories/dominant", params={"code": tob}).json()["category"] is None
    assert api2.get("/categories/dominant", params={"code": ["1"] * 61}).status_code == 422
