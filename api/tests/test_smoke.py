"""Smoke tests for the Israeli Price Comparison API."""
import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_stats_shape():
    r = client.get("/stats")
    assert r.status_code == 200
    body = r.json()
    for key in ("chains_count", "stores_count", "items_count", "prices_count", "last_fetch_per_chain"):
        assert key in body


def test_chains_returns_list():
    r = client.get("/chains")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        assert "chain_id" in data[0]
        assert "name" in data[0]


def test_cities_returns_city_info_shape():
    r = client.get("/cities")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        city = data[0]
        assert "city" in city
        assert "chain_count" in city
        assert "store_count" in city
        assert isinstance(city["chain_count"], int)
        assert city["store_count"] > 0


def test_stores_returns_list():
    r = client.get("/stores")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_search_returns_result_shape():
    r = client.get("/search", params={"q": "במבה"})
    assert r.status_code == 200
    body = r.json()
    assert "query" in body
    assert "total_matches" in body
    assert "comparable_count" in body
    assert "has_more" in body
    assert "items" in body
    assert body["query"] == "במבה"


def test_search_has_more_and_pagination():
    r1 = client.get("/search", params={"q": "חלב", "limit": 5, "offset": 0})
    assert r1.status_code == 200
    b1 = r1.json()
    if b1["total_matches"] > 5:
        assert b1["has_more"] is True
        r2 = client.get("/search", params={"q": "חלב", "limit": 5, "offset": 5})
        assert r2.status_code == 200
        b2 = r2.json()
        ids1 = {i["product"]["item_code"] for i in b1["items"]}
        ids2 = {i["product"]["item_code"] for i in b2["items"]}
        assert ids1.isdisjoint(ids2), "Offset pages should not overlap"


def test_search_group_by_store_returns_more():
    r_chain = client.get("/search", params={"q": "חלב", "limit": 100, "group_by": "chain"})
    r_store = client.get("/search", params={"q": "חלב", "limit": 100, "group_by": "store"})
    assert r_chain.status_code == 200
    assert r_store.status_code == 200
    # store-level returns at least as many rows as chain-level
    assert r_store.json()["total_matches"] >= r_chain.json()["total_matches"]


def test_compare_only_multi_chain():
    r = client.get("/compare", params={"q": "חלב"})
    assert r.status_code == 200
    body = r.json()
    for item in body["items"]:
        # Compare mode returns 2+-chain products PLUS single-source promo-only
        # deals (every quote a promo, no shelf price) — an intentional exemption
        # (SU10A-6). Any single-chain item that appears must be promo-only.
        if item["chains_count"] < 2:
            assert item["quotes"]
            assert all(q["promo_kind"] == "promo_only" for q in item["quotes"])


def test_compare_has_more_field():
    r = client.get("/compare", params={"q": "מים", "limit": 5})
    assert r.status_code == 200
    assert "has_more" in r.json()


def test_search_empty_query_rejected():
    r = client.get("/search", params={"q": ""})
    assert r.status_code == 422


def test_product_invalid_barcode():
    r = client.get("/product/abc")
    assert r.status_code == 400


def test_product_not_found():
    r = client.get("/product/00000000")
    assert r.status_code == 404


def test_search_chain_filter_no_duplicates():
    """group_by=chain must return unique item_codes even when filtered to one chain."""
    chains = client.get("/chains").json()
    if not chains:
        pytest.skip("no chains loaded")
    chain_id = chains[0]["chain_id"]
    r = client.get("/search", params={"q": "חלב", "chain": chain_id, "group_by": "chain", "limit": 50})
    assert r.status_code == 200
    items = r.json()["items"]
    codes = [i["product"]["item_code"] for i in items]
    dupes = [c for c in set(codes) if codes.count(c) > 1]
    assert len(dupes) == 0, f"Duplicate item_codes: {dupes}"


def test_product_valid_barcode_shape():
    chains = client.get("/chains").json()
    if not chains:
        pytest.skip("no chains loaded")
    r = client.get("/search", params={"q": "במבה", "limit": 1})
    items = r.json().get("items", [])
    if not items:
        pytest.skip("no search results")
    barcode = items[0]["product"]["item_code"]
    r2 = client.get(f"/product/{barcode}")
    assert r2.status_code == 200
    body = r2.json()
    assert "product" in body
    assert "quotes" in body
    assert "chains_count" in body
