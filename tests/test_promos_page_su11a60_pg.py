"""SU11A-60 promos page against a real Postgres: the category filter (incl. the
low-confidence department-only rule), the flat cross-chain list (dedupe,
branch_count, sort, exact paging, the unfiltered cap), מבצעים מקודמים (pin
order, city, hidden left out, sponsored) and the /promos/today cache (same
output as the live query, invalidation by the load stamp, the last answer when
the DB fails).

Data: the SU11A-58 fixture (tests/test_promo_curation_su11a58_pg.py) plus a
small taxonomy. SKIPPED unless SCRP_TEST_PG_URL is set.
"""
import pytest
from sqlalchemy import text

from tests.test_promo_curation_su11a58_pg import (  # noqa: F401  (fixtures)
    PG_URL, ROOT, T1, T2, T3, _run_sql, client, engine, pin, server,
)

pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

CATALOG = ROOT / "db" / "migrations" / "su11a52_catalog.sql"


@pytest.fixture(scope="module")
def eng(engine):  # noqa: F811
    _run_sql(engine, CATALOG)
    with engine.begin() as c:
        for cid, parent, level in (("D01", None, 1), ("D01.C01", "D01", 2), ("D01.C01.S01", "D01.C01", 3),
                                   ("D02", None, 1)):
            c.execute(text("INSERT INTO categories (id, parent_id, level, name_he, taxonomy_version) "
                           "VALUES (:i, :p, :l, :i, 'v1')"), {"i": cid, "p": parent, "l": level})
        # T1 (40% off, chain A): a high label on the category; T2 (20%, chain A):
        # a LOW label on the sub-category; T3 (chain B): no label.
        for code, cid, conf in ((T1, "D01.C01", "high"), (T2, "D01.C01.S01", "low")):
            c.execute(text("INSERT INTO item_categories (item_code, category_id, confidence, source, taxonomy_version) "
                           "VALUES (:c, :k, :f, 'rule', 'v1')"), {"c": code, "k": cid, "f": conf})
    return engine


@pytest.fixture
def api(eng, client):  # noqa: F811
    import api.categories as cats
    import db.query as Q
    cats.reset_tree_cache()
    Q.reset_today_cache()
    yield client
    cats.reset_tree_cache()
    Q.reset_today_cache()


def codes(rows):
    return {r["item_code"] for r in rows}


# ------------------------------------------------------------------ category

@pytest.mark.parametrize("path", ["/promos/grouped", "/promos/list"])
def test_category_low_confidence_counts_at_department_only(api, path):
    dept = api.get(path, params={"category": "D01"}).json()
    assert codes(dept) == {T1, T2}                     # the low label counts at department level
    cat = api.get(path, params={"category": "D01.C01"}).json()
    assert codes(cat) == {T1}                          # ... but not below it
    assert api.get(path, params={"category": "D01.C01.S01"}).json() == []
    assert api.get(path, params={"category": "D02"}).json() == []
    assert api.get(path, params={"category": "NOPE"}).json() == []


def test_unlabelled_item_matches_text_search_only(api):
    name = "מוצר בדיקה שלוש"
    assert T3 in codes(api.get("/promos/list", params={"q": name}).json())
    assert api.get("/promos/list", params={"q": name, "category": "D01"}).json() == []


def test_category_combines_with_chain_and_bands(api):
    rows = api.get("/promos/grouped", params={"category": "D01", "chain": "A", "bands": "26-50"}).json()
    assert codes(rows) == {T1}
    assert {r["chain_id"] for r in rows} == {"A"}


# ------------------------------------------------------------------ flat list

def test_flat_list_one_card_per_chain_item_promo(api, eng):
    flat = api.get("/promos/list", params={"category": "D01"}).json()
    assert [r["item_code"] for r in flat] == [T1, T2]  # by discount: 40% then 20%
    assert all(r["branch_count"] == len(eng.a_live) for r in flat)
    assert all(r["store_fk"] in eng.a_live and r["chain_name"] and r["branch"] for r in flat)


def test_flat_matches_grouped_rows(api):
    """Same filters: the flat cards cover exactly the grouped rows' (chain,
    item) pairs, and their branch_counts add up to the grouped row count."""
    grouped = api.get("/promos/grouped", params={"q": "חלב", "limit": 5000}).json()
    flat = api.get("/promos/list", params={"q": "חלב", "limit": 100}).json()
    assert 0 < len(flat) < 100
    assert {(r["chain_id"], r["item_code"]) for r in flat} == {(r["chain_id"], r["item_code"]) for r in grouped}
    assert sum(r["branch_count"] for r in flat) == len(grouped)


@pytest.mark.parametrize("sort,key,desc", [("discount", "discount_pct", True), ("savings", "savings", True),
                                           ("ending", "promo_end", False)])
def test_flat_sort_and_exact_paging(api, sort, key, desc):
    """SU11A-62: with search text the most relevant rows lead; `sort` orders
    the rows WITHIN each relevance tier (tests/test_promo_search_su11a62_pg.py)."""
    from tests.test_promo_search_su11a62_pg import tier
    params = {"q": "חלב", "sort": sort}
    whole = api.get("/promos/list", params={**params, "limit": 100}).json()
    assert len(whole) > 6
    tiers = [tier(r, "חלב") for r in whole]
    assert tiers == sorted(tiers)
    for t in set(tiers):
        group = [r for r, k in zip(whole, tiers) if k == t]
        vals = [r[key] for r in group if r[key] is not None]
        assert vals == sorted(vals, reverse=desc)
        if any(r[key] is None for r in group):          # NULLS LAST
            first_null = next(i for i, r in enumerate(group) if r[key] is None)
            assert all(r[key] is None for r in group[first_null:])
    pages = []
    for off in range(0, len(whole), 4):
        pages += api.get("/promos/list", params={**params, "limit": 4, "offset": off}).json()
    assert [(r["chain_id"], r["item_code"], r["store_fk"]) for r in pages] == \
           [(r["chain_id"], r["item_code"], r["store_fk"]) for r in whole]


def test_flat_list_only_live_stores(api, eng):
    import tests.test_search_filtered_pg as F0
    rows = api.get("/promos/list", params={"q": "חלב", "limit": 100}).json()
    assert rows and all(r["store_fk"] in F0.LIVE for r in rows)


@pytest.mark.parametrize("path", ["/promos/list", "/promos/grouped"])
def test_unfiltered_read_is_empty(api, path):
    """SU11A-62 (was the SU11A-60 cap): unfiltered = [] at once; the DB side is
    tested in tests/test_promo_search_su11a62_pg.py (no query at all)."""
    import tests.test_search_filtered_pg as F0
    assert api.get(path, params={"limit": 50}).json() == []
    assert api.get(path, params={"limit": 50, "city": F0.CITIES[0]}).json() == []   # a city alone is a scope
    assert len(api.get(path, params={"limit": 50, "chain": "A"}).json()) > 5        # a chain is a filter


# ------------------------------------------------------------------ promoted

def test_promoted_none_without_pins(api):
    assert api.get("/promos/promoted").json() == []


def test_promoted_order_city_hidden_and_sponsored(api, eng):
    assert pin(api, "PC", chain="B", rank=1, sponsored=True).status_code == 200
    assert pin(api, "PA", chain="A", rank=1).status_code == 200         # PA 1, PC 2
    rows = api.get("/promos/promoted").json()
    assert [(r["chain_id"], r["item_code"]) for r in rows] == [("A", T1), ("B", T3)]
    assert [r["sponsored"] for r in rows] == [False, True]
    assert all(r["pinned"] for r in rows)
    assert rows[0]["branch_count"] == len(eng.a_live) and rows[0]["item_count"] == 1
    assert rows[1]["branch_count"] == len(eng.b_live)

    import tests.test_search_filtered_pg as F0
    city = F0.STORES[eng.a_live[0]][1]
    in_city = [i for i in eng.a_live if F0.STORES[i][1] == city]
    scoped = api.get("/promos/promoted", params={"city": city}).json()
    assert scoped[0]["item_code"] == T1 and scoped[0]["branch_count"] == len(in_city)
    assert (F0.STORES[eng.b_live[0]][1] == city) == any(r["item_code"] == T3 for r in scoped)

    assert api.get("/promos/promoted", params={"category": "D01.C01"}).json()[0]["item_code"] == T1
    assert [r["item_code"] for r in api.get("/promos/promoted", params={"chain": "B"}).json()] == [T3]

    # The admin API refuses to hide a pinned promotion (409); a row written
    # anyway (or a race) must still win: the hide is the safer reading.
    from db import promo_curation
    with eng.begin() as c:
        c.execute(text("INSERT INTO promo_curation (kind, chain_id, promo_id, note, actor_hash) "
                       "VALUES ('hide', 'A', 'PA', 'x', 'x')"))
    promo_curation.invalidate()
    assert [r["item_code"] for r in api.get("/promos/promoted").json()] == [T3]


def test_promoted_capped(api, monkeypatch):
    import db.query as Q
    monkeypatch.setattr(Q, "PROMOTED_MAX", 2)
    for k, pid in enumerate(("PA", "PB", "PC"), start=1):
        assert pin(api, pid, chain="B" if pid == "PC" else "A", rank=k).status_code == 200
    assert [r["item_code"] for r in api.get("/promos/promoted").json()] == [T1, T2]


# ------------------------------------------------------------------ /promos/today cache

def test_today_cached_output_equals_live(api):
    import db.query as Q
    cold = api.get("/promos/today").json()
    assert cold
    assert api.get("/promos/today").json() == cold         # cached
    Q.reset_today_cache()
    assert api.get("/promos/today").json() == cold         # live again


def test_today_cache_follows_the_load_stamp(api, eng):
    before = api.get("/promos/today", params={"chain_id": "B"}).json()
    assert T3 in codes(before)
    with eng.begin() as c:
        c.execute(text("UPDATE promos SET promo_end = '2001-01-01' WHERE promo_id = 'PC'"))
    try:
        assert api.get("/promos/today", params={"chain_id": "B"}).json() == before       # same stamp: cached
        with eng.begin() as c:
            c.execute(text("UPDATE stores SET last_loaded_at = now() + interval '1 minute' "
                           "WHERE id = :f"), {"f": eng.b_live[0]})
        assert T3 not in codes(api.get("/promos/today", params={"chain_id": "B"}).json())
    finally:
        with eng.begin() as c:
            c.execute(text("UPDATE promos SET promo_end = '2099-01-01' WHERE promo_id = 'PC'"))


def test_today_curation_change_is_a_new_key(api):
    before = api.get("/promos/today", params={"chain_id": "A"}).json()
    assert pin(api, "PB", chain="A", rank=1).status_code == 200
    after = api.get("/promos/today", params={"chain_id": "A"}).json()
    assert after != before and after[0]["item_code"] == T2 and after[0]["pinned"]


def test_today_serves_the_last_answer_when_the_db_fails(api, monkeypatch):
    import db.query as Q
    first = api.get("/promos/today").json()

    def boom(conn):
        raise RuntimeError("db down")

    monkeypatch.setattr(Q, "_load_stamp", boom)
    r = api.get("/promos/today")
    assert r.status_code == 200 and r.json() == first
