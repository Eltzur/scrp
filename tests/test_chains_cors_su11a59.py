"""SU11A-59 without a database: the /chains cache (hit, invalidation by the
search build stamp, max age, a failing database serves the last value) and the
CORS preflight of every call the admin console makes (allowed from
https://admin.xxl.co.il only; PATCH only from there)."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import db.query as Q

ROOT = Path(__file__).resolve().parent.parent
ADMIN_ORIGIN = "https://admin.xxl.co.il"
ROWS_1 = [{"chain_id": "1", "name": "א", "total_barcodes": 5, "total_stores_loaded": 2}]
ROWS_2 = [{"chain_id": "1", "name": "א", "total_barcodes": 6, "total_stores_loaded": 2}]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeConn:
    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def chains(monkeypatch):
    """fetch_chains with a fake clock, stamp and query; returns the state dict."""
    st = {"stamp": ("b1", "b1", True), "rows": ROWS_1, "queries": 0, "stamps": 0, "fail": False}
    clock = Clock()

    def stamp(conn):
        st["stamps"] += 1
        if st["fail"]:
            raise RuntimeError("db down")
        return st["stamp"]

    def raw(conn, with_build):
        st["queries"] += 1
        st["with_build"] = with_build
        if st["fail"]:
            raise RuntimeError("db down")
        return st["rows"]

    monkeypatch.setattr(Q.time, "monotonic", clock)
    monkeypatch.setattr(Q, "_chains_stamp", stamp)
    monkeypatch.setattr(Q, "_fetch_chains_raw", raw)
    Q.invalidate_chains()
    st["clock"] = clock
    yield st
    Q.invalidate_chains()


def test_cache_hit_within_stamp_ttl(chains):
    conn = FakeConn()
    assert Q.fetch_chains(conn) == ROWS_1
    chains["clock"].t += 30
    assert Q.fetch_chains(conn) == ROWS_1
    assert chains["queries"] == 1 and chains["stamps"] == 1   # no database work on a hit


def test_same_stamp_keeps_value_new_stamp_refetches(chains):
    conn = FakeConn()
    Q.fetch_chains(conn)
    chains["rows"] = ROWS_2
    chains["clock"].t += Q.CHAINS_STAMP_TTL_S + 1
    assert Q.fetch_chains(conn) == ROWS_1                      # stamp re-read, unchanged
    assert chains["stamps"] == 2 and chains["queries"] == 1
    chains["stamp"] = ("b2", "b2", True)                       # the next build
    chains["clock"].t += Q.CHAINS_STAMP_TTL_S + 1
    assert Q.fetch_chains(conn) == ROWS_2
    assert chains["queries"] == 2


def test_max_age_refetches_without_a_new_stamp(chains):
    conn = FakeConn()
    Q.fetch_chains(conn)
    chains["rows"] = ROWS_2
    chains["clock"].t += Q.CHAINS_MAX_AGE_S + 1
    assert Q.fetch_chains(conn) == ROWS_2


def test_no_build_tables_uses_the_store_only_query(chains):
    chains["stamp"] = (None, None, False)
    Q.fetch_chains(FakeConn())
    assert chains["with_build"] is False


def test_db_failure_serves_the_cached_value(chains):
    conn = FakeConn()
    Q.fetch_chains(conn)
    chains["fail"] = True
    chains["clock"].t += Q.CHAINS_STAMP_TTL_S + 1
    assert Q.fetch_chains(conn) == ROWS_1
    assert conn.rollbacks == 1
    chains["clock"].t += 5                                     # no retry storm while it fails
    assert Q.fetch_chains(conn) == ROWS_1
    assert chains["stamps"] == 2


def test_db_failure_on_a_cold_worker_raises(chains):
    chains["fail"] = True
    with pytest.raises(RuntimeError):
        Q.fetch_chains(FakeConn())


def test_route_serves_cache_when_db_fails(chains):
    from api.dependencies import get_db
    from api.main import app

    def _get_db():
        yield FakeConn()

    app.dependency_overrides[get_db] = _get_db
    try:
        c = TestClient(app)
        assert c.get("/chains").json() == ROWS_1
        chains["fail"] = True
        chains["clock"].t += Q.CHAINS_STAMP_TTL_S + 1
        r = c.get("/chains")
        assert r.status_code == 200 and r.json() == ROWS_1
    finally:
        app.dependency_overrides.clear()


def test_chains_sql_reads_no_big_tables():
    for sql in (Q._CHAINS_SQL, Q._CHAINS_SQL_NO_BUILD):
        assert not re.search(r"\b(prices|promos)\b", sql)


# --------------------------------------------------------------------------- CORS

def _console_calls() -> set[tuple[str, str]]:
    """(METHOD, path) of every http.<method>() call in web/src/admin/api.ts."""
    src = (ROOT / "web" / "src" / "admin" / "api.ts").read_text(encoding="utf-8")
    calls = set()
    for m, path in re.findall(r"http\.(get|post|put|patch|delete)\b[^(]*\(\s*[`']([^`']+)[`']", src):
        calls.add((m.upper(), re.sub(r"\$\{[^}]*\}", "1", path).split("?")[0]))
    return calls


CALLS = sorted(_console_calls())


def test_console_calls_found():
    methods = {m for m, _ in CALLS}
    assert {"GET", "POST", "PUT", "PATCH", "DELETE"} <= methods
    assert ("PATCH", "/admin/promos/curation/1") in CALLS


@pytest.fixture(scope="module")
def api():
    from api.main import app
    return TestClient(app)


def _preflight(api, origin, method, path):
    return api.options(path, headers={"Origin": origin, "Access-Control-Request-Method": method,
                                      "Access-Control-Request-Headers": "authorization,content-type"})


@pytest.mark.parametrize("method,path", CALLS)
def test_admin_origin_preflight_ok(api, method, path):
    r = _preflight(api, ADMIN_ORIGIN, method, path)
    assert r.status_code == 200, r.text
    assert r.headers["access-control-allow-origin"] == ADMIN_ORIGIN
    allowed = {m.strip() for m in r.headers["access-control-allow-methods"].split(",")}
    assert method in allowed and "*" not in allowed


@pytest.mark.parametrize("method,path", CALLS)
def test_other_origin_refused(api, method, path):
    r = _preflight(api, "https://evil.example", method, path)
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers


def test_public_origin_has_no_patch(api):
    from api.main import ALLOWED_ORIGINS
    public = next(o for o in ALLOWED_ORIGINS if o != ADMIN_ORIGIN)
    ok = _preflight(api, public, "DELETE", "/favorites/1")
    assert ok.status_code == 200
    assert "PATCH" not in ok.headers["access-control-allow-methods"]
    no = _preflight(api, public, "PATCH", "/admin/promos/curation/1")
    assert no.status_code == 400 and no.text == "Disallowed CORS method"
    assert int(no.headers["content-length"]) == len(no.content)
