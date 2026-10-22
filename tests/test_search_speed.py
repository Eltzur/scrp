"""Search speed (SU11A-47): precomputed page prices, the response cache,
Server-Timing / Cache-Control, and /suggest. No database: the SQL-facing
helpers are replaced with fakes. The SQL itself (fill + read, byte-identical
to the live fetch) is tested against a real Postgres in test_search_prices_pg.py.
    python -m pytest tests/test_search_speed.py -q
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import api.routers.search as R
import db.search_v2 as V
from api.dependencies import get_db
from api.main import app
from api.response_cache import ResponseCache

BUILT = datetime.now(timezone.utc) - timedelta(hours=2)


def _cand(code, name, chains=2, pseudo=False):
    return {"item_code": code, "name_norm": name, "manufacturer_norm": "", "chains_live": chains,
            "popularity": 0, "promo_only": False, "is_pseudo": pseudo}


CATALOG = [_cand("7290000000001", "חלב 3%"), _cand("7290000000002", "חלב 1%"),
           _cand("7290000000003", "שוקו חלב", chains=1)]


def _row(code, chain, fk, price):
    return {"item_code": code, "chain_id": chain, "chain_name": chain, "store_id": str(fk), "store_name": "s",
            "city": "c", "store_fk": fk, "item_name": "n", "canonical_item_name": "N", "manufacturer_name": "m",
            "unit_of_measure": "u", "is_weighted": 0, "item_price": price, "unit_of_measure_price": price,
            "price_update_date": "d", "promo_unit_price": None, "promo_min_qty": None,
            "promo_description": None, "promo_end": None}


@pytest.fixture
def v2(monkeypatch):
    calls = {"live": 0, "pre": 0, "run": 0}
    V._cache.built_at = V._cache.lexicon = V._cache.prices_built_at = None
    monkeypatch.setattr(V, "_built_at", lambda conn: BUILT)
    monkeypatch.setattr(V, "_lexicon", lambda conn: ({}, frozenset({100})))
    monkeypatch.setattr(V, "_ranked", lambda conn, groups, q_norm, *_: V.Ranked.from_list([
        dict(c) for c in CATALOG if all(any(a in c["name_norm"] for a in g.alts) for g in groups)],
        groups, q_norm))
    monkeypatch.setattr(V, "_barcode", lambda conn, codes: [dict(c) for c in CATALOG if c["item_code"] in codes])
    monkeypatch.setattr(V, "_correct", lambda conn, groups: None)

    def live(conn, codes, **kw):
        calls["live"] += 1
        return [r for c in codes for r in (_row(c, "x", 1, 5.0), _row(c, "e", 100, 1.0))]
    monkeypatch.setattr(V, "fetch_prices", live)

    def pre(conn, codes):
        calls["pre"] += 1
        return calls.get("pre_rows", lambda codes: [_row(c, "x", 1, 5.0) for c in codes])(codes)
    monkeypatch.setattr(V, "_try_precomputed", pre)
    return calls


# --------------------------------------------------------------------------- run(): price source
def test_run_reads_precomputed_prices_for_the_page(v2):
    r = V.run(None, "חלב", limit=2)
    assert r.prices_source == "precomputed" and v2["pre"] == 1 and v2["live"] == 0
    assert [p["item_code"] for p in r.products] == ["7290000000001", "7290000000002"]
    assert set(r.timings_ms) >= {"candidates", "rank", "prices", "total"}


def test_run_falls_back_to_live_when_precomputed_is_unusable(v2):
    v2["pre_rows"] = lambda codes: None          # missing / empty / stale / ended promo / item missing
    r = V.run(None, "חלב", limit=2)
    assert r.prices_source == "live" and v2["live"] == 1
    assert all([q["store_fk"] for q in p["quotes"]] == [1] for p in r.products)   # Eilat rule still applied


def test_run_live_when_forced_or_city(v2):
    assert V.run(None, "חלב", precomputed=False).prices_source == "live"
    assert V.run(None, "חלב", city=["תל אביב"]).prices_source == "live"
    assert v2["pre"] == 0


def test_try_precomputed_swallows_errors(monkeypatch, caplog):
    class Conn:
        def begin_nested(self):
            raise RuntimeError("relation search_item_prices does not exist")
    assert V._try_precomputed(Conn(), ["1"]) is None
    assert "live price fetch" in caplog.text


def test_precomputed_rows_needs_the_same_build(monkeypatch):
    monkeypatch.setattr(V, "_built_at", lambda conn: BUILT)
    for stamp in (None, BUILT - timedelta(days=1)):
        monkeypatch.setattr(V, "_prices_built_at", lambda conn, s=stamp: s)
        assert V._precomputed_rows(object(), ["1"]) is None      # no query is run


# --------------------------------------------------------------------------- ResponseCache
def test_cache_hit_miss_and_query_echo():
    c = ResponseCache()
    body = b'{"query":"Milka","total_matches":1}'
    assert c.get(("s", "milka"), 1, "Milka") is None
    c.put(("s", "milka"), 1, "Milka", body)
    assert c.get(("s", "milka"), 1, "Milka") == body
    assert json.loads(c.get(("s", "milka"), 1, "MILKA")) == {"query": "MILKA", "total_matches": 1}
    assert (c.hits, c.misses) == (2, 1)


def test_cache_corrected_answer_only_for_the_same_text():
    c = ResponseCache()
    c.put(("s", "shokolad"), 1, "Shokolad", b'{"query":"Shokolad","corrected_from":"Shokolad"}', exact_only=True)
    assert c.get(("s", "shokolad"), 1, "Shokolad") is not None
    assert c.get(("s", "shokolad"), 1, "shokolad") is None


def test_cache_invalidated_by_a_new_build_and_by_ttl(monkeypatch):
    c = ResponseCache(ttl_s=600)
    c.put(("s", "a"), "build1", "a", b'{"query":"a"}')
    assert c.get(("s", "a"), "build1", "a") is not None
    assert c.get(("s", "a"), "build2", "a") is None and len(c) == 0
    c.put(("s", "a"), "build2", "a", b'{"query":"a"}')
    import api.response_cache as RC
    now = RC.time.monotonic()
    monkeypatch.setattr(RC.time, "monotonic", lambda: now + 601)
    assert c.get(("s", "a"), "build2", "a") is None


def test_cache_bounded_by_entries_and_bytes_lru():
    c = ResponseCache(max_entries=3, max_bytes=10_000)
    for i in range(3):
        c.put(("s", str(i)), 1, str(i), b'{"query":"%d"}' % i)
    c.get(("s", "0"), 1, "0")                          # 0 is now the most recent
    c.put(("s", "3"), 1, "3", b'{"query":"3"}')
    assert c.get(("s", "1"), 1, "1") is None and c.get(("s", "0"), 1, "0") is not None
    big = ResponseCache(max_entries=100, max_bytes=4_000)
    for i in range(10):
        big.put(("s", str(i)), 1, str(i), b'{"query":"%d","x":"' % i + b"y" * 900 + b'"}')
    assert big._bytes <= 4_000 and len(big) == 4
    big.put(("s", "huge"), 1, "huge", b'{"query":"huge","x":"' + b"y" * 2000 + b'"}')
    assert big.get(("s", "huge"), 1, "huge") is None   # over a quarter of the budget: not stored


def test_cache_ignores_bodies_of_another_shape():
    c = ResponseCache()
    c.put(("s", "a"), 1, "a", b'{"total":1,"query":"a"}')
    assert len(c) == 0


# --------------------------------------------------------------------------- HTTP: headers + cache
class _FakeConn:
    def begin_nested(self):
        class _SP:
            def __enter__(self):
                return None

            def __exit__(self, *exc):
                return False
        return _SP()


@pytest.fixture
def client(monkeypatch, v2):
    monkeypatch.setenv("SEARCH_V2", "on")
    monkeypatch.setattr(V, "built_stamp", lambda conn: v2.get("stamp", BUILT))
    R._cache.clear()
    real_run = V.run

    def counted(*a, **kw):
        v2["run"] += 1
        return real_run(*a, **kw)
    monkeypatch.setattr(V, "run", counted)
    monkeypatch.setattr(R, "_build_result", lambda *a, **kw: R.SearchResult(
        query=a[0], total_matches=0, comparable_count=0, has_more=False, items=[]))
    app.dependency_overrides[get_db] = lambda: _FakeConn()
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)
    R._cache.clear()


def test_search_v2_headers_and_cache(client, v2):
    r1 = client.get("/search", params={"q": "חלב", "limit": 2})
    assert r1.status_code == 200 and r1.json()["engine"] == "v2"
    assert r1.headers["cache-control"] == "public, max-age=300"
    st = r1.headers["server-timing"]
    assert "candidates;dur=" in st and "prices;dur=" in st and "desc=precomputed" in st and "total;dur=" in st
    assert "חלב" not in st and "%" not in st
    r2 = client.get("/search", params={"q": "חלב", "limit": 2})
    assert v2["run"] == 1 and r2.content == r1.content and "cache;desc=hit" in r2.headers["server-timing"]
    r3 = client.get("/search", params={"q": "  חלב ", "limit": 2})          # same normalized key
    assert v2["run"] == 1 and r3.json()["query"] == "  חלב "
    client.get("/search", params={"q": "חלב", "limit": 2, "offset": 2})      # another page: miss
    assert v2["run"] == 2
    v2["stamp"] = BUILT + timedelta(days=1)                                  # new build: everything dropped
    client.get("/search", params={"q": "חלב", "limit": 2})
    assert v2["run"] == 3


def test_search_with_authorization_gets_no_cache_control(client):
    r = client.get("/search", params={"q": "חלב"}, headers={"Authorization": "Bearer x"})
    assert r.status_code == 200 and "cache-control" not in r.headers and "server-timing" in r.headers


def test_filtered_search_unchanged_no_public_cache(client, v2):
    r = client.get("/search", params={"q": "חלב", "city": "תל אביב"})
    assert r.status_code == 200 and "engine" not in r.json()
    assert "cache-control" not in r.headers and r.headers["server-timing"].startswith("total;dur=")
    assert v2["run"] == 0


# --------------------------------------------------------------------------- /suggest
@pytest.fixture
def sug(monkeypatch):
    V._cache.built_at = V._cache.lexicon = None
    monkeypatch.setattr(V, "check_ready", lambda conn: None)
    monkeypatch.setattr(V, "_lexicon", lambda conn: ({"milka": "מילקה"}, frozenset()))
    lex = [{"term": "חלב", "kind": "token", "canonical": "חלב", "freq": 900},
           {"term": "חלבה", "kind": "token", "canonical": "חלבה", "freq": 40},
           {"term": "חלה", "kind": "token", "canonical": "חלה", "freq": 30},
           {"term": "חלבי", "kind": "token", "canonical": "חלבי", "freq": 20},
           {"term": "חלב הארץ", "kind": "brand", "canonical": "חלב הארץ", "freq": 25},
           {"term": "milka", "kind": "alias", "canonical": "מילקה", "freq": 60}]
    calls = {"prefix": [], "products": []}

    def prefix(conn, p, kinds, n):
        calls["prefix"].append((p, kinds))
        return sorted([r for r in lex if r["term"].startswith(p) and r["kind"] in kinds],
                      key=lambda r: -r["freq"])[:n]
    monkeypatch.setattr(V, "_lexicon_prefix", prefix)

    items = [_cand("7290000000001", "חלב 3% תנובה"), _cand("7290000000002", "חלב 1%"),
             _cand("7290000000004", "הנ.קופון חלב", pseudo=True)]

    def products(conn, groups, q_norm, n):
        calls["products"].append([g.alts for g in groups])
        return [c for c in items if not c["is_pseudo"]
                and all(any(a in c["name_norm"] for a in g.alts) for g in groups)][:n]
    monkeypatch.setattr(V, "_suggest_products", products)
    monkeypatch.setattr(V, "_product_names", lambda conn, codes: {c: f"שם {c[-1]}" for c in codes})
    monkeypatch.setattr(V, "_barcode", lambda conn, codes: [dict(c) for c in items if c["item_code"] in codes])

    def correct(conn, groups):
        fixed = [V.Group(alts=["חלב"], corrected_from="חלבב") if g.alts[0] == "חלבב" else g for g in groups]
        return fixed if fixed != groups else None
    monkeypatch.setattr(V, "_correct", correct)
    return calls


def test_suggest_mixes_terms_brands_products(sug):
    s = V.suggest(None, "חל", limit=8)
    kinds = [i["kind"] for i in s.items]
    assert kinds == ["term"] * 4 + ["brand"] + ["product"] * 2   # 3 terms + spare slots, 1 brand, 2 products
    assert s.items[0] == {"kind": "term", "text": "חלב", "count": 900}
    assert {"kind": "product", "text": "שם 1", "item_code": "7290000000001"} in s.items
    assert all(i.get("item_code") != "7290000000004" for i in s.items)        # pseudo excluded
    assert len(V.suggest(None, "חל", limit=3).items) == 3


def test_suggest_completes_the_last_word(sug):
    s = V.suggest(None, "גבינה חל", limit=8)
    assert [i["text"] for i in s.items if i["kind"] == "term"][:2] == ["גבינה חלב", "גבינה חלבה"]


def test_suggest_alias_brand_and_typo(sug):
    assert V.suggest(None, "Mil").items[0] == {"kind": "brand", "text": "milka", "count": 60}
    s = V.suggest(None, "חלבב")
    assert s.corrected_from == "חלבב" and s.items[0]["text"] == "חלב"


def test_suggest_barcode_empty_and_one_char(sug):
    assert V.suggest(None, "7290000000001").items == [
        {"kind": "product", "text": "שם 1", "item_code": "7290000000001"}]
    assert V.suggest(None, "7290000000004").items == []          # pseudo
    assert V.suggest(None, "7290000009999").items == []          # unknown
    assert V.suggest(None, "").items == [] and V.suggest(None, "  ").items == []
    s = V.suggest(None, "ח")
    assert sug["products"][-1] == [["ח"]] and s.items[0]["text"] == "חלב"


def test_suggest_endpoint(client, sug, monkeypatch):
    r = client.get("/suggest", params={"q": "חל"})
    body = r.json()
    assert r.status_code == 200 and body["query"] == "חל" and "corrected_from" not in body
    assert body["items"][0] == {"kind": "term", "text": "חלב", "count": 900}
    assert r.headers["cache-control"] == "public, max-age=300" and "חל" not in r.headers["server-timing"]
    n = len(sug["products"])
    r2 = client.get("/suggest", params={"q": "חל"})
    assert len(sug["products"]) == n and r2.content == r.content           # cached
    assert client.get("/suggest", params={"q": "חל"}, headers={"Authorization": "Bearer x"}).headers.get(
        "cache-control") is None
    assert client.get("/suggest", params={"q": ""}).json() == {"query": "", "items": []}
    assert client.get("/suggest", params={"q": "חל", "limit": 11}).status_code == 422
    monkeypatch.setattr(V, "suggest", lambda *a, **kw: (_ for _ in ()).throw(V.V2Unavailable("stale")))
    R._cache.clear()
    r3 = client.get("/suggest", params={"q": "חל"})
    assert r3.status_code == 200 and r3.json()["items"] == [] and "cache-control" not in r3.headers
