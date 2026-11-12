"""SU11A-80: public /stats from a single-flight TTL cache (SU11A-79 C1), the
cheaper stores count (same number as the old prices sub-scan), and the JSON 500
with CORS headers on every path (SU11A-79 L5). No database server needed
(SQLite); the Postgres equality check runs only with SCRP_TEST_PG_URL.
    python -m pytest tests/test_public_stats_su11a80.py -q
"""
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.main import app
from api.routers import health as H
from db import query as Q

OLD_STORES_SQL = "SELECT COUNT(DISTINCT id) FROM stores WHERE id IN (SELECT store_fk FROM prices)"
ORIGIN = "http://localhost:5173"          # in the default ALLOWED_ORIGINS
BODY = {"chains_count": 2, "stores_count": 3, "items_count": 4, "prices_count": 5,
        "last_fetch_per_chain": {"רשת": "2026-11-12T10:00:00+02:00"}}


class _Conn:
    def __init__(self, opened):
        self.opened = opened
        opened.append(self)
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def fake(monkeypatch):
    """_open and fetch_stats patched: counts connections and loads."""
    state = {"opened": [], "loads": 0, "delay": 0.0}

    def _fetch(conn):
        state["loads"] += 1
        if state["delay"]:
            time.sleep(state["delay"])
        return dict(BODY)
    monkeypatch.setattr(H, "_open", lambda: _Conn(state["opened"]))
    monkeypatch.setattr(H, "fetch_stats", _fetch)
    H.invalidate()
    yield state
    H.invalidate()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ------------------------------------------------------------------ the cache
def test_second_call_is_served_from_cache_with_identical_body(client, fake):
    a = client.get("/stats")
    b = client.get("/stats")
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json() == BODY
    assert fake["loads"] == 1 and len(fake["opened"]) == 1
    assert all(c.closed for c in fake["opened"])
    assert a.headers["cache-control"] == "public, max-age=300"
    assert b.headers["cache-control"] == "public, max-age=300"


def test_reloads_after_the_ttl_only(fake):
    H.cached_stats(now=1000.0)
    H.cached_stats(now=1000.0 + H.STATS_TTL_S - 1)
    assert fake["loads"] == 1
    H.cached_stats(now=1000.0 + H.STATS_TTL_S + 1)
    assert fake["loads"] == 2
    assert H.STATS_TTL_S == 600.0


def test_concurrent_misses_load_once(fake):
    fake["delay"] = 0.3
    results, start = [], threading.Barrier(12)

    def worker():
        start.wait()
        results.append(H.cached_stats())
    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert fake["loads"] == 1 and len(fake["opened"]) == 1
    assert len(results) == 12 and all(r == BODY for r in results)


def test_a_failed_load_is_not_cached_and_answers_json_500(client, fake, monkeypatch):
    def boom(conn):
        raise RuntimeError("SELECT secret_sql FROM prices")
    monkeypatch.setattr(H, "fetch_stats", boom)
    r = client.get("/stats")
    assert r.status_code == 500 and r.json() == {"code": "server_error"}
    assert "secret_sql" not in r.text
    assert all(c.closed for c in fake["opened"])
    monkeypatch.setattr(H, "fetch_stats", lambda conn: dict(BODY))
    assert client.get("/stats").json() == BODY           # nothing poisoned the cache


# ------------------------------------------------------- same stores number
def _seed(conn):
    conn.execute(text("CREATE TABLE stores (id INTEGER PRIMARY KEY, chain_id TEXT)"))
    conn.execute(text("CREATE TABLE prices (id INTEGER PRIMARY KEY, store_fk INTEGER NOT NULL, "
                      "item_code TEXT NOT NULL, UNIQUE (store_fk, item_code))"))
    conn.execute(text("INSERT INTO stores (id, chain_id) VALUES (1,'A'),(2,'A'),(3,'B'),(4,'B'),(5,'C')"))
    # store 1: many prices, 2: one, 3: none, 4: many, 5: none
    rows = [(1, f"72900{i}") for i in range(40)] + [(2, "7290001")] + [(4, f"8{i}") for i in range(7)]
    for fk, code in rows:
        conn.execute(text("INSERT INTO prices (store_fk, item_code) VALUES (:f, :c)"), {"f": fk, "c": code})


def _both(conn):
    return (conn.execute(text(OLD_STORES_SQL)).scalar(),
            conn.execute(text(Q.STORES_WITH_PRICES_SQL)).scalar())


def test_stores_count_equals_the_old_sub_scan_sqlite():
    eng = create_engine("sqlite://")
    with eng.begin() as c:
        _seed(c)
        assert _both(c) == (3, 3)
        c.execute(text("DELETE FROM prices"))
        assert _both(c) == (0, 0)


def test_new_stores_sql_never_reads_prices_without_the_store_key():
    sql = Q.STORES_WITH_PRICES_SQL
    assert "EXISTS" in sql and "p.store_fk = s.id" in sql and "IN (SELECT" not in sql


def test_stores_count_equals_the_old_sub_scan_postgres():
    pg = pytest.importorskip("tests.test_promo_curation_su11a58_pg")
    if not pg.PG_URL:
        pytest.skip("SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")
    eng = create_engine(pg.PG_URL)
    with eng.connect() as c:
        c.execute(text("CREATE TEMP TABLE stores (id INTEGER PRIMARY KEY, chain_id TEXT)"))
        c.execute(text("CREATE TEMP TABLE prices (id SERIAL PRIMARY KEY, store_fk INTEGER NOT NULL, "
                       "item_code TEXT NOT NULL, UNIQUE (store_fk, item_code))"))
        c.execute(text("INSERT INTO stores (id, chain_id) VALUES (1,'A'),(2,'A'),(3,'B'),(4,'B'),(5,'C')"))
        c.execute(text("INSERT INTO prices (store_fk, item_code) "
                       "SELECT fk, 'c' || g FROM (VALUES (1),(2),(4)) v(fk), generate_series(1, 25) g"))
        assert _both(c) == (3, 3)


# --------------------------------------------------- JSON 500 on every path
def test_unhandled_error_on_a_public_path_is_json_500_with_cors(client, fake, monkeypatch, caplog):
    def boom():
        raise ValueError("Traceback secret_sql q=חלב")
    monkeypatch.setattr(H, "cached_stats", boom)
    r = client.get("/stats?q=hidden", headers={"Origin": ORIGIN})
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {"code": "server_error"}
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    assert "secret_sql" not in r.text and "Traceback" not in r.text
    logged = " ".join(rec.getMessage() for rec in caplog.records)
    assert "/stats" in logged and "ValueError" in logged
    assert "secret_sql" not in logged and "hidden" not in logged and "חלב" not in logged


def test_unknown_origin_gets_no_cors_header_on_the_500(client, fake, monkeypatch):
    monkeypatch.setattr(H, "cached_stats", lambda: 1 / 0)
    r = client.get("/stats", headers={"Origin": "https://evil.example"})
    assert r.status_code == 500 and r.json() == {"code": "server_error"}
    assert "access-control-allow-origin" not in r.headers
