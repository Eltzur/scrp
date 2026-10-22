"""SU11A-49 security fixes from the SU11A-48 review. No database: fakes only.

F-01  old-path candidate cap, API-only statement_timeout, timeout -> 503
F-05  JWKS refetch throttle
    python -m pytest tests/test_security_su11a49.py -q
"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, ProgrammingError

import api.auth as A
import api.routers.search as R
from api.dependencies import get_db
from api.main import API_STATEMENT_TIMEOUT_MS, app
from db import db as D

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# F-01: statement_timeout only for the API
# ---------------------------------------------------------------------------

@pytest.fixture
def timeout_state():
    saved = D._statement_timeout_ms
    yield
    D._statement_timeout_ms = saved


def test_engine_kwargs_without_timeout_has_no_options(timeout_state):
    D._statement_timeout_ms = None
    kw = D.engine_kwargs()
    assert "connect_args" not in kw
    assert kw["pool_pre_ping"] is True


def test_engine_kwargs_with_timeout_sets_startup_option(timeout_state):
    D.set_statement_timeout(15000)
    assert D.engine_kwargs()["connect_args"] == {"options": "-c statement_timeout=15000"}
    D.set_statement_timeout(0)
    assert "connect_args" not in D.engine_kwargs()


def test_set_statement_timeout_drops_an_existing_engine(timeout_state, monkeypatch):
    disposed = []

    class FakeEngine:
        def dispose(self):
            disposed.append(True)

    monkeypatch.setattr(D, "_engine", FakeEngine())
    D.set_statement_timeout(15000)
    assert disposed == [True] and D._engine is None


def _timeout_in_fresh_process(code: str) -> str:
    env = {k: v for k, v in os.environ.items()
           if k not in ("DATABASE_URL", "api_statement_timeout_ms", "API_STATEMENT_TIMEOUT_MS")}
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                         env=env, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    return out.stdout.strip().splitlines()[-1]


def test_scripts_and_timers_get_no_timeout():
    # What the timers and ops scripts import (incl. the sweep and the moderation
    # CLI, which import api modules but never api.main).
    code = ("import scripts.build_search_items, scripts.sweep_account_deletes, scripts.moderation, "
            "scripts.compare_search_v2, api.routers.account, api.moderation\n"
            "from db import db; print(db._statement_timeout_ms, 'connect_args' in db.engine_kwargs())")
    assert _timeout_in_fresh_process(code) == "None False"


def test_api_process_gets_the_timeout():
    code = "import api.main\nfrom db import db; print(db.engine_kwargs()['connect_args']['options'])"
    assert _timeout_in_fresh_process(code) == "-c statement_timeout=15000"
    assert API_STATEMENT_TIMEOUT_MS == 15000


# ---------------------------------------------------------------------------
# F-01: timeout -> 503 query_timeout
# ---------------------------------------------------------------------------

class _PgErr(Exception):
    def __init__(self, pgcode):
        super().__init__("canceling statement due to statement timeout")
        self.pgcode = pgcode


def _no_db():
    yield None


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = _no_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def test_timeout_maps_to_503_without_sql(client, monkeypatch, caplog):
    def boom(*a, **kw):
        raise OperationalError("SELECT secret_sql FROM prices WHERE q = %(q)s", {"q": "חלב"}, _PgErr("57014"))

    monkeypatch.setattr(R, "_build_result", boom)
    r = client.get("/compare", params={"q": "חלב"})
    assert r.status_code == 503
    assert r.json() == {"code": "query_timeout"}
    assert r.headers["retry-after"] == "5"
    assert "secret_sql" not in r.text
    logged = " ".join(rec.getMessage() for rec in caplog.records)
    assert "query timeout" in logged and "/compare" in logged
    assert "חלב" not in logged and "secret_sql" not in logged


def test_other_db_errors_stay_500(client, monkeypatch):
    def boom(*a, **kw):
        raise ProgrammingError("SELECT secret_sql", {}, _PgErr("42P01"))

    monkeypatch.setattr(R, "_build_result", boom)
    r = client.get("/compare", params={"q": "חלב"})
    assert r.status_code == 500
    assert "secret_sql" not in r.text


# ---------------------------------------------------------------------------
# F-01: candidate cap on the old path
# ---------------------------------------------------------------------------

def _row(code, chain, fk, price):
    return {"item_code": code, "chain_id": chain, "chain_name": chain, "store_id": str(fk), "store_name": "s",
            "city": "c", "store_fk": fk, "item_name": "n", "canonical_item_name": "N", "manufacturer_name": "m",
            "unit_of_measure": "u", "is_weighted": 0, "item_price": price, "unit_of_measure_price": price,
            "price_update_date": "d", "promo_unit_price": None, "promo_min_qty": None,
            "promo_description": None, "promo_end": None}


class _RankConn:
    """search_items rank rows for cap_candidates; raises when `missing`."""

    def __init__(self, info=None, missing=False):
        self.info, self.missing, self.calls = info or {}, missing, 0

    def begin_nested(self):
        conn = self

        class _Ctx:
            def __enter__(self):
                return conn

            def __exit__(self, *exc):
                return False
        return _Ctx()

    def execute(self, stmt, params):
        self.calls += 1
        if self.missing:
            raise ProgrammingError("x", {}, _PgErr("42P01"))
        wanted = set(params["codes"])
        rows = [dict(item_code=c, **v) for c, v in self.info.items() if c in wanted]

        class _Res:
            def mappings(self):
                return rows
        return _Res()


def _codes(n):
    return [f"729{i:010d}" for i in range(n)]


def test_cap_keeps_small_sets_untouched():
    conn = _RankConn()
    codes = _codes(10)
    assert R.cap_candidates(conn, codes, {}) is codes
    assert conn.calls == 0


def test_cap_orders_like_v2_and_puts_unbuilt_items_last():
    codes = _codes(6)
    tiers = {c: 0 for c in codes}
    tiers[codes[5]] = 2
    info = {
        codes[0]: {"name_norm": "aaaa", "chains_live": 1, "popularity": 0},
        codes[1]: {"name_norm": "aaaa", "chains_live": 5, "popularity": 0},
        codes[2]: {"name_norm": "aa", "chains_live": 5, "popularity": 0},
        codes[3]: {"name_norm": "aaaa", "chains_live": 3, "popularity": 9},
        codes[5]: {"name_norm": "a", "chains_live": 9, "popularity": 99},   # worse tier
    }
    got = R.cap_candidates(_RankConn(info), codes, tiers, cap=5)
    # tier 0, 2+ chains, popularity, chains, shorter name; then tier 2; codes[4]
    # is not in search_items and drops off the end.
    assert got == [codes[3], codes[2], codes[1], codes[0], codes[5]]


def test_cap_falls_back_to_tier_then_code_without_search_items():
    codes = _codes(5)[::-1]
    tiers = {c: (1 if i % 2 else 0) for i, c in enumerate(codes)}
    got = R.cap_candidates(_RankConn(missing=True), codes, tiers, cap=3)
    want = sorted(codes, key=lambda c: (tiers[c], c))[:3]
    assert got == want


@pytest.fixture
def old_path(monkeypatch):
    priced = []

    def setup(n):
        codes = _codes(n)
        monkeypatch.setattr(R, "find_barcodes_with_relevance", lambda conn, words: (codes, {c: 0 for c in codes}))
        monkeypatch.setattr(R, "cap_candidates", lambda conn, cs, tiers, cap=R.OLD_PATH_CAP: cs[:cap])

        def fetch(conn, barcodes, city=None, chain_id=None):
            priced.append(list(barcodes))
            return [r for i, c in enumerate(barcodes)
                    for r in (_row(c, "A", 1, 5 + i / 1000), _row(c, "B", 2, 6 + i / 1000))]
        monkeypatch.setattr(R, "fetch_prices", fetch)
        return codes
    return setup, priced


def test_old_path_prices_at_most_the_cap(old_path):
    setup, priced = old_path
    setup(1500)
    res = R._build_result("ab", None, 30, 0, ["עיר"], None, compare_only=True)
    assert len(priced[0]) == R.OLD_PATH_CAP == 1000
    assert res.total_matches == 1500           # the true match count
    assert res.comparable_count == 1000
    assert res.has_more is True and len(res.items) == 30


def test_old_path_ends_at_the_cap(old_path):
    setup, _ = old_path
    setup(1500)
    last = R._build_result("ab", None, 30, 990, None, None, compare_only=False)
    assert len(last.items) == 10 and last.has_more is False
    past = R._build_result("ab", None, 30, 1000, None, None, compare_only=False)
    assert past.items == [] and past.has_more is False and past.total_matches == 1500


def test_old_path_below_the_cap_is_unchanged(old_path):
    setup, priced = old_path
    setup(50)
    res = R._build_result("ab", None, 30, 0, None, None, compare_only=False)
    assert len(priced[0]) == 50
    assert res.total_matches == 50 and res.has_more is True


def test_old_path_store_grouping_reports_the_true_count(old_path):
    setup, _ = old_path
    setup(1200)
    res = R._build_result("ab", None, 10, 0, None, None, compare_only=False, group_by="store")
    assert res.total_matches == 1200


# ---------------------------------------------------------------------------
# F-05: JWKS refetch throttle
# ---------------------------------------------------------------------------

def _token(kid):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{b64({'alg': 'ES256', 'kid': kid, 'typ': 'JWT'})}.{b64({'sub': 'x'})}.c2ln"


@pytest.fixture
def jwks(monkeypatch):
    clock = {"t": 1000.0}
    fetches = []
    state = {"fail": False, "keys": {"good": {"kid": "good"}}}

    def fetch():
        fetches.append(clock["t"])
        if state["fail"]:
            raise RuntimeError("supabase down")
        return dict(state["keys"])

    monkeypatch.setattr(A, "_fetch_jwks", fetch)
    monkeypatch.setattr(A.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(A, "_jwks_cache", {})
    monkeypatch.setattr(A, "_jwks_ok_at", None)
    monkeypatch.setattr(A, "_jwks_fail_at", None)
    return clock, fetches, state


def test_unknown_kids_fetch_once_per_window(jwks):
    clock, fetches, _ = jwks
    assert A._get_jwk("good") == {"kid": "good"}
    assert len(fetches) == 1
    for i in range(50):                      # forged kids inside the window
        assert A._get_jwk(f"forged-{i}") is None
    assert len(fetches) == 1
    clock["t"] += A.JWKS_MIN_REFRESH_S
    assert A._get_jwk("forged-x") is None
    assert len(fetches) == 2
    assert A._get_jwk("good") == {"kid": "good"}   # cached: no fetch
    assert len(fetches) == 2


def test_rotated_key_is_picked_up_after_the_window(jwks):
    clock, fetches, state = jwks
    A._get_jwk("good")
    state["keys"]["new"] = {"kid": "new"}
    assert A._get_jwk("new") is None          # inside the window
    clock["t"] += A.JWKS_MIN_REFRESH_S + 1
    assert A._get_jwk("new") == {"kid": "new"}
    assert len(fetches) == 2


def test_failed_fetch_backs_off_and_answers_503(jwks):
    clock, fetches, state = jwks
    state["fail"] = True
    with pytest.raises(RuntimeError):
        A._get_jwk("good")
    for _ in range(20):
        with pytest.raises(RuntimeError):
            A._get_jwk("other")
    assert len(fetches) == 1
    # _decode maps the failure to 503, as before.
    with pytest.raises(A.HTTPException) as exc:
        A._decode(_token("good"))
    assert exc.value.status_code == 503
    clock["t"] += A.JWKS_FAIL_BACKOFF_S
    state["fail"] = False
    assert A._get_jwk("good") == {"kid": "good"}
    assert len(fetches) == 2


def test_soft_auth_never_raises_and_does_not_fetch_forged_kids(jwks):
    _, fetches, state = jwks
    A._get_jwk("good")

    class Req:
        def __init__(self, token):
            self.headers = {"authorization": f"Bearer {token}"}

    for i in range(10):
        assert A.get_user_id_soft(Req(_token(f"forged-{i}"))) is None
    assert len(fetches) == 1
    state["fail"] = True
    A._jwks_ok_at = None                      # force a fetch attempt that fails
    assert A.get_user_id_soft(Req(_token("forged-y"))) is None
    assert A.get_user_id_soft(Req(_token("forged-z"))) is None   # in backoff
    assert len(fetches) == 2


def test_strict_auth_answers_401_for_forged_kid(jwks, client):
    A._get_jwk("good")
    r = client.get("/me/terms", headers={"Authorization": f"Bearer {_token('forged')}"})
    assert r.status_code == 401
