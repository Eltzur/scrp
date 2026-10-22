"""SU11A-50: the filtered v2 path and the ranked candidate stream, with fakes (no
database). The SQL itself is tested against Postgres in test_search_filtered_pg.py.
"""
import logging
import random

import pytest
from fastapi.testclient import TestClient

import api.routers.search as R
import db.search_filtered as F
import db.search_v2 as V
from api.dependencies import get_db
from api.main import app
from db.search_norm import tokenize


# --------------------------------------------------------------------------- flag
@pytest.mark.parametrize("raw,mode", [(None, "off"), ("", "off"), ("off", "off"), ("test", "test"),
                                      (" ON ", "on"), ("yes", "off"), ("1", "off")])
def test_flag_values(monkeypatch, raw, mode):
    if raw is None:
        monkeypatch.delenv("SEARCH_V2_FILTERED", raising=False)
    else:
        monkeypatch.setenv("SEARCH_V2_FILTERED", raw)
    assert R._filtered_mode() == mode


@pytest.mark.parametrize("mode,engine,want", [
    ("off", None, False), ("off", "v2", False),
    ("test", None, False), ("test", "v2", True), ("test", "v1", False), ("test", "x", False),
    ("on", None, True), ("on", "v2", True), ("on", "v1", False), ("on", "x", True),
])
def test_use_filtered(mode, engine, want):
    assert R._use_filtered(mode, engine) is want


# --------------------------------------------------------------------------- HTTP
class _FakeConn:
    def begin_nested(self):
        class _SP:
            def __enter__(self):
                return None

            def __exit__(self, *exc):
                return False
        return _SP()


def _product(code: str) -> dict:
    return {"item_code": code, "canonical_name": "חלב 3%", "manufacturer": "תנובה", "unit_of_measure": "ליטר",
            "is_weighted": False, "names_per_chain": {"A": "חלב"}, "cheapest_price": 5.0,
            "most_expensive_price": 6.0, "chains_count": 2,
            "quotes": [{"chain_id": c, "chain_name": c, "store_id": "1", "store_name": "s", "city": "רמת גן",
                        "price": p, "unit_price": None, "unit_of_measure": "ליטר", "updated_at": None,
                        "delta_from_cheapest": p - 5.0, "store_fk": 1} for c, p in (("A", 5.0), ("B", 6.0))]}


@pytest.fixture
def http(monkeypatch):
    calls = {"filtered": [], "old": 0}
    monkeypatch.delenv("SEARCH_V2", raising=False)

    def fake_run(conn, q, **kw):
        calls["filtered"].append(kw)
        if calls.get("raise"):
            raise calls["raise"]
        return F.FilteredResult(query=q, total_matches=7, comparable_count=3, has_more=True,
                                products=[_product("7290000000011")], corrected_from=calls.get("corrected"),
                                timings_ms={"candidates": 1.0, "filter": 2.0, "prices": 3.0, "total": 6.0},
                                prices_source="live", mode="stores", walked=200)
    monkeypatch.setattr(F, "run", fake_run)

    def old(*a, **kw):
        calls["old"] += 1
        return R.SearchResult(query=a[0], total_matches=0, comparable_count=0, has_more=False, items=[])
    monkeypatch.setattr(R, "_build_result", old)
    app.dependency_overrides[get_db] = lambda: _FakeConn()
    yield TestClient(app), calls, monkeypatch
    app.dependency_overrides.pop(get_db, None)


def test_flag_off_keeps_the_old_path(http):
    c, calls, mp = http
    mp.delenv("SEARCH_V2_FILTERED", raising=False)
    for path, params in (("/compare", {"q": "חלב", "city": "רמת גן"}), ("/compare", {"q": "חלב", "engine": "v2"}),
                         ("/search", {"q": "חלב", "city": "רמת גן", "engine": "v2"}),
                         ("/search", {"q": "חלב", "chain": "A"}), ("/search", {"q": "חלב", "group_by": "store"})):
        r = c.get(path, params=params)
        assert r.status_code == 200 and "filter;dur" not in r.headers["server-timing"]
    assert calls["old"] == 5 and not calls["filtered"]


def test_flag_test_needs_engine_v2(http):
    c, calls, mp = http
    mp.setenv("SEARCH_V2_FILTERED", "test")
    c.get("/compare", params={"q": "חלב", "city": "רמת גן"})
    assert calls["old"] == 1 and not calls["filtered"]
    r = c.get("/compare", params={"q": "חלב", "city": "רמת גן", "engine": "v2"})
    assert len(calls["filtered"]) == 1 and "filter;dur=" in r.headers["server-timing"]


def test_flag_on_and_engine_v1(http):
    c, calls, mp = http
    mp.setenv("SEARCH_V2_FILTERED", "on")
    c.get("/compare", params={"q": "חלב"})
    c.get("/search", params={"q": "חלב", "city": ["רמת גן", "בני ברק"], "chain": "A"})
    c.get("/search", params={"q": "חלב", "group_by": "store"})
    assert calls["old"] == 0 and len(calls["filtered"]) == 3
    assert calls["filtered"][0] == {"limit": 30, "offset": 0, "city": None, "chain": None, "group_by": "chain",
                                    "compare_only": True}
    assert calls["filtered"][1]["city"] == ["רמת גן", "בני ברק"] and calls["filtered"][1]["chain"] == ["A"]
    assert calls["filtered"][2]["group_by"] == "store"
    c.get("/compare", params={"q": "חלב", "engine": "v1"})
    c.get("/search", params={"q": "חלב", "city": "רמת גן", "engine": "v1"})
    assert calls["old"] == 2 and len(calls["filtered"]) == 3


def test_unfiltered_search_is_not_the_filtered_path(http):
    c, calls, mp = http
    mp.setenv("SEARCH_V2_FILTERED", "on")
    mp.setenv("SEARCH_V2", "off")
    c.get("/search", params={"q": "חלב"})
    assert calls["old"] == 1 and not calls["filtered"]


def test_response_shapes_and_server_timing(http):
    c, calls, mp = http
    mp.setenv("SEARCH_V2_FILTERED", "on")
    cmp_ = c.get("/compare", params={"q": "חלב", "city": "רמת גן", "limit": 20})
    assert set(cmp_.json()) == set(R.SearchResult.model_fields)          # /compare: its exact fields
    body = cmp_.json()
    assert (body["total_matches"], body["comparable_count"], body["has_more"]) == (7, 3, True)
    assert body["items"][0]["product"]["item_code"] == "7290000000011"
    st = cmp_.headers["server-timing"]
    for part in ("candidates;dur=1.0", "filter;dur=2.0", "prices;dur=3.0;desc=live", "total;dur="):
        assert part in st
    assert "חלב" not in st and "cache-control" not in cmp_.headers
    calls["corrected"] = "שוקלד"
    s = c.get("/search", params={"q": "שוקלד", "city": "רמת גן"}).json()
    assert s["engine"] == "v2" and s["corrected_from"] == "שוקלד"
    assert set(s) == set(R.SearchResultV2.model_fields)


@pytest.mark.parametrize("exc", [RuntimeError("boom חלב"), V.V2Unavailable("stale"), F.Unsupported("no")])
def test_errors_fall_back_to_the_old_path_without_the_query(http, caplog, exc):
    c, calls, mp = http
    mp.setenv("SEARCH_V2_FILTERED", "on")
    calls["raise"] = exc
    with caplog.at_level(logging.INFO, logger="api.routers.search"):
        r = c.get("/compare", params={"q": "חלב", "city": "רמת גן"})
    assert r.status_code == 200 and calls["old"] == 1
    assert "filter;dur" not in r.headers["server-timing"]
    assert caplog.records and all("חלב" not in rec.getMessage() and rec.exc_info is None
                                  for rec in caplog.records)


# --------------------------------------------------------------------------- the ranked stream
_HEB = "אבגדהוזחטיכלמנסעפצקרשת"


def _cands(rnd, n):
    words = ["חלב", "חלבה", "בחלב", "תנובה", "שוקו", "חלב3"]
    out = []
    for i in range(n):
        ws = [rnd.choice(words + ["".join(rnd.choice(_HEB) for _ in range(3))]) for _ in range(rnd.randint(1, 4))]
        out.append({"item_code": f"{rnd.randint(0, 10**6):07d}{i}", "name_norm": " ".join(ws),
                    "manufacturer_norm": rnd.choice(["תנובה", "חלב הארץ", "עלית", ""]),
                    "chains_live": rnd.randint(1, 4), "popularity": rnd.choice([0, 0, 3]),
                    "promo_only": False, "is_pseudo": False})
    return out


@pytest.mark.parametrize("seed", range(6))
def test_stream_equals_rank_for_any_lower_bound(seed):
    """The merge is exact for ANY coarse tier that never exceeds the real one."""
    rnd = random.Random(seed)
    q = rnd.choice(["חלב", "חלב תנובה", "תנובה"])
    groups = V.apply_aliases(tokenize(q), {})
    cands = _cands(rnd, rnd.randint(0, 400))
    want = V.rank([dict(c) for c in cands], groups, q)
    rows = []
    for c in cands:
        tier = V.assign_tier(c["name_norm"], c["manufacturer_norm"], groups, q)
        rows.append(dict(c, ct=rnd.randint(0, tier)))
    rows.sort(key=lambda r: V.rank_key(r, r["ct"]))
    chunk = rnd.choice([1, 3, 50])

    def fetch(limit, offset):
        return [dict(r) for r in rows[offset:offset + limit]]
    r = V.Ranked(len(rows), 0, fetch, groups, q, first=fetch(chunk, 0), first_limit=chunk)
    got = r.take(rnd.randint(0, 450))
    assert [c["item_code"] for c in got] == [c["item_code"] for c in want][:len(got)]
    assert [c["item_code"] for c in r.take(10_000)] == [c["item_code"] for c in want]
    assert [c["tier"] for c in r.take(10_000)] == [c["tier"] for c in want]


def test_stream_stops_early_for_a_page():
    groups = V.apply_aliases(tokenize("חלב"), {})
    rows = [{"item_code": f"{i:05d}", "name_norm": f"חלב {i}", "manufacturer_norm": "", "chains_live": 2,
             "popularity": 0, "promo_only": False, "is_pseudo": False, "ct": 0} for i in range(5000)]
    rows.sort(key=lambda r: V.rank_key(r, 0))
    fetched = []

    def fetch(limit, offset):
        fetched.append((limit, offset))
        return [dict(x) for x in rows[offset:offset + limit]]
    r = V.Ranked(5000, 5000, fetch, groups, "חלב", first=fetch(300, 0), first_limit=300)
    assert len(r.take(31)) == 31 and r.fetched == 300 and r.queries == 0
    assert len(r.take(1000)) == 1000 and fetched == [(300, 0), (2400, 300)]


def test_coarse_tier_sql_is_parameterised():
    groups = V.apply_aliases(tokenize("חלב 3% o'reilly"), {})
    sql, params = V.coarse_tier_sql(groups, "חלב 3% o'reilly")
    assert "חלב" not in sql and "reilly" not in sql
    assert params["cta0"] == "חלב%" and params["ctn0"] == "%חלב%"
    assert any(v == "חלב 3\\% o'reilly%" for v in params.values())


# --------------------------------------------------------------------------- the walk
class _Ranked:
    def __init__(self, n):
        self.total, self.comparable = n, 0
        self._c = [{"item_code": f"{i:04d}"} for i in range(n)]

    def take(self, k):
        return self._c[:k]


def _filter(sold, calls):
    def run(codes):
        calls.append(len(codes))
        return {c: F.Info(chains={"A"}, rows=2, shelf_chains={"A"}) for c in codes if c in sold}
    return run


def test_walk_batches_and_stops_when_the_page_is_full():
    calls = []
    sold = {f"{i:04d}" for i in range(0, 5000, 3)}      # every third item is sold in the city
    w = F.Walk(_Ranked(5000), _filter(sold, calls), lambda inf: F.YES)
    w.ensure(21)
    assert calls == [200] and len(w.items) == 67 and not w.done
    w.ensure(500)
    assert calls == [200, 400, 800, 1600] and w.walked == 3000 and w.done and not w.exhausted


def test_walk_exhausts_small_candidate_lists():
    calls = []
    w = F.Walk(_Ranked(150), _filter({"0001", "0100"}, calls), lambda inf: F.YES)
    w.ensure(5)
    assert calls == [150] and w.exhausted and [it[0]["item_code"] for it in w.items] == ["0001", "0100"]
    assert w.any_items == 2 and w.multi_items == 0


def test_walk_ceiling_and_has_more(monkeypatch):
    """Past the ceiling nothing is listed and has_more is false."""
    monkeypatch.setattr(F, "CEILING", 10)
    monkeypatch.setattr(F, "BATCHES", (4, 4, 4))
    w = F.Walk(_Ranked(100), _filter({f"{i:04d}" for i in range(100)}, []), lambda inf: F.YES)
    w.ensure(50)
    assert w.walked == 10 and w.done and not w.exhausted and len(w.items) == 10


def test_walk_settles_maybes():
    w = F.Walk(_Ranked(6), _filter({f"{i:04d}" for i in range(6)}, []),
               lambda inf: F.MAYBE)
    w.ensure(4)
    assert [it[0]["item_code"] for it in w.maybes(3)] == ["0000", "0001", "0002"]
    w.settle({"0000": False, "0001": True, "0002": False})
    assert [(it[0]["item_code"], it[2]) for it in w.items][:2] == [("0001", F.YES), ("0003", F.MAYBE)]


def test_compare_verdict():
    I = F.Info
    assert F.compare_verdict(I(chains={"A", "B"}, shelf_chains={"A"}, po_chains={"B"})) == F.YES
    assert F.compare_verdict(I(chains={"A"}, po_chains={"A"})) == F.YES          # promo-only, one chain
    assert F.compare_verdict(I(chains={"A"}, shelf_chains={"A"})) == F.NO        # one chain, shelf only
    assert F.compare_verdict(I(chains={"A"}, shelf_chains={"A"}, po_chains={"A"})) == F.MAYBE


def test_run_rejects_compare_with_store_grouping(monkeypatch):
    monkeypatch.setattr(V, "check_ready", lambda conn: None)
    monkeypatch.setattr(V, "_lexicon", lambda conn: ({}, frozenset()))
    with pytest.raises(F.Unsupported):
        F.run(object(), "חלב", limit=5, offset=0, group_by="store", compare_only=True)
