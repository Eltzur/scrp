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


def test_cities_returns_list_of_strings():
    r = client.get("/cities")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        assert isinstance(data[0], str)


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
    assert "items" in body
    assert body["query"] == "במבה"


def test_compare_only_multi_chain():
    r = client.get("/compare", params={"q": "חלב"})
    assert r.status_code == 200
    body = r.json()
    for item in body["items"]:
        assert item["chains_count"] >= 2


def test_search_empty_query_rejected():
    r = client.get("/search", params={"q": ""})
    assert r.status_code == 422


def test_product_invalid_barcode():
    r = client.get("/product/abc")
    assert r.status_code == 400


def test_product_not_found():
    r = client.get("/product/00000000")
    assert r.status_code == 404


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
