"""SU11A-59 /chains against a real Postgres: the new small-table query returns
the same chains (ids, names, order) and the same store counts as the old
prices scan; total_barcodes is the chain's live items from the search build.

Data: the SU11A-58 fixture (the SU11A-50 generated chains, live and dead
stores, a real search build) plus a chain with no stores. SKIPPED unless
SCRP_TEST_PG_URL is set (see tests/test_promo_curation_su11a58_pg.py).
"""
import pytest
from sqlalchemy import text

from tests.test_promo_curation_su11a58_pg import PG_URL, engine, server  # noqa: F401  (fixtures)

pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

OLD_SQL = """
    SELECT c.chain_id, c.name,
           COUNT(DISTINCT p.item_code) AS total_barcodes,
           COUNT(DISTINCT s.id)        AS total_stores_loaded
    FROM chains c
    LEFT JOIN stores s ON s.chain_id = c.chain_id
    LEFT JOIN prices p ON p.store_fk = s.id
    GROUP BY c.chain_id, c.name
    ORDER BY c.name
"""


@pytest.fixture(scope="module")
def eng(engine):  # noqa: F811
    with engine.begin() as c:
        c.execute(text("INSERT INTO chains VALUES ('Z', 'רשת בלי סניפים') ON CONFLICT DO NOTHING"))
    return engine


def _rows(eng, sql):
    with eng.connect() as c:
        return [dict(r) for r in c.execute(text(sql)).mappings().all()]


def test_same_chains_and_store_counts_as_old(eng):
    import db.query as Q
    old, new = _rows(eng, OLD_SQL), _rows(eng, Q._CHAINS_SQL)
    assert len(old) >= 3
    key = lambda r: (r["chain_id"], r["name"], r["total_stores_loaded"])  # noqa: E731
    assert [key(r) for r in new] == [key(r) for r in old]
    z = next(r for r in new if r["chain_id"] == "Z")
    assert z["total_barcodes"] == 0 and z["total_stores_loaded"] == 0


def test_total_barcodes_is_the_live_build(eng):
    import db.query as Q
    old = {r["chain_id"]: r["total_barcodes"] for r in _rows(eng, OLD_SQL)}
    with eng.connect() as c:
        built = dict(c.execute(text("SELECT chain_id, COUNT(DISTINCT item_code) FROM search_item_prices GROUP BY 1")).all())
    for r in _rows(eng, Q._CHAINS_SQL):
        assert r["total_barcodes"] == built.get(r["chain_id"], 0)
        assert r["total_barcodes"] <= old[r["chain_id"]]            # the build drops dead stores only
    assert sum(built.values()) > 0


def test_no_build_variant_same_chains(eng):
    import db.query as Q
    old, new = _rows(eng, OLD_SQL), _rows(eng, Q._CHAINS_SQL_NO_BUILD)
    assert [(r["chain_id"], r["total_stores_loaded"]) for r in new] == [(r["chain_id"], r["total_stores_loaded"]) for r in old]
    assert all(r["total_barcodes"] == 0 for r in new)


def test_endpoint_and_stamp_invalidation(eng):
    from fastapi.testclient import TestClient
    import db.query as Q
    from api.dependencies import get_db
    from api.main import app

    def _get_db():
        with eng.connect() as conn:
            yield conn

    Q.invalidate_chains()
    app.dependency_overrides[get_db] = _get_db
    try:
        c = TestClient(app)
        first = c.get("/chains")
        assert first.status_code == 200
        assert [r["chain_id"] for r in first.json()] == [r["chain_id"] for r in _rows(eng, OLD_SQL)]
        with eng.connect() as conn:
            stamp = Q._chains_stamp(conn)
        assert stamp[0] is not None and stamp[2] is True
        # A new build: the cached list goes once the stamp is re-read.
        with eng.begin() as conn:
            conn.execute(text("UPDATE search_items SET built_at = built_at + interval '1 day'"))
            conn.execute(text("DELETE FROM search_item_prices WHERE chain_id = (SELECT MIN(chain_id) FROM search_item_prices)"))
        assert c.get("/chains").json() == first.json()              # inside the stamp TTL: cached
        Q._chains_cache.stamp_at = float("-inf")
        assert c.get("/chains").json() != first.json()
    finally:
        app.dependency_overrides.clear()
        Q.invalidate_chains()
