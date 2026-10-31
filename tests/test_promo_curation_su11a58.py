"""SU11A-58 promo curation without Postgres: the aal2 matrix on every new admin
endpoint (the gate answers before any promo SQL runs), the rank placement, the
SQL fragments, the read-time marking and the fail-open loader.

The database behaviour (migration twice, pins / hides / expiry, rank shifting,
audit, byte-identical pricing) is in tests/test_promo_curation_su11a58_pg.py.
    python -m pytest tests/test_promo_curation_su11a58.py -q
"""
import pytest
from sqlalchemy import text

from api.routers.admin_promos import place
from db import promo_curation as PC
from tests.test_categories_su11a57 import (  # noqa: F401 - fixtures
    ADMIN, ADMIN_EMAIL, USER, client, engine, q, tok,
)

ADMIN_CALLS = [
    ("GET", "/admin/promos/search?q=חלב", None),
    ("GET", "/admin/promos/curation", None),
    ("GET", "/admin/promos/curation?state=expired", None),
    ("POST", "/admin/promos/pins", {"chain_id": "A", "promo_id": "P1", "rank": 1}),
    ("POST", "/admin/promos/hides", {"chain_id": "A", "promo_id": "P1", "reason": "x"}),
    ("PATCH", "/admin/promos/curation/1", {"rank": 2}),
    ("DELETE", "/admin/promos/curation/1", None),
]


@pytest.mark.parametrize("method,path,body", ADMIN_CALLS)
def test_aal2_matrix_on_every_new_admin_endpoint(client, engine, method, path, body):
    cases = [
        ({}, "admin_required"),
        ({"Authorization": "Bearer not-a-token"}, "admin_required"),
        (tok(client, USER, aal="aal2"), "admin_required"),
        (tok(client, ADMIN, ADMIN_EMAIL, "aal1"), "mfa_required"),
        (tok(client, ADMIN, ADMIN_EMAIL), "mfa_required"),
    ]
    for h, code in cases:
        r = client.request(method, path, json=body, headers=h)
        assert (r.status_code, r.json()) == (403, {"code": code}), (path, h, r.text)
    assert q(engine, "SELECT count(*) FROM admin_audit") == 0


def test_place_inserts_moves_and_clamps():
    assert place([], 9, 1) == [9]
    assert place([1, 2, 3], 9, 1) == [9, 1, 2, 3]
    assert place([1, 2, 3], 9, 2) == [1, 9, 2, 3]
    assert place([1, 2, 3], 9, 50) == [1, 2, 3, 9]          # past the end: last
    assert place([1, 2, 3], 3, 1) == [3, 1, 2]              # a move
    assert place([1, 2, 3], 1, 3) == [2, 3, 1]
    assert place([1, 2, 3], 2, 0) == [2, 1, 3]              # below 1: first


CUR = PC.Curation(pins=(PC.Pin("A", "p2", True), PC.Pin("B", "p1", False)),
                  hides=frozenset({("A", "x"), ("C", "y")}))


def test_sql_fragments_are_empty_without_curation():
    assert PC.hide_sql(PC.EMPTY, "s.chain_id", "p.promo_id") == ("", {})
    assert PC.pin_rank_sql(PC.EMPTY, "s.chain_id", "p.promo_id") == ("", {})
    assert not PC.EMPTY


def test_sql_fragments_bind_every_value():
    sql, params = PC.hide_sql(CUR, "s.chain_id", "p.promo_id")
    assert sql == (" AND (p.promo_id IS NULL OR (s.chain_id, p.promo_id) NOT IN "
                   "((:cur_hc0, :cur_hp0), (:cur_hc1, :cur_hp1)))")
    assert params == {"cur_hc0": "A", "cur_hp0": "x", "cur_hc1": "C", "cur_hp1": "y"}
    sql, params = PC.pin_rank_sql(CUR, "s.chain_id", "p.promo_id")
    assert sql == ("CASE WHEN s.chain_id = :cur_pc0 AND p.promo_id = :cur_pp0 THEN 1 "
                   "WHEN s.chain_id = :cur_pc1 AND p.promo_id = :cur_pp1 THEN 2 END")
    assert params == {"cur_pc0": "A", "cur_pp0": "p2", "cur_pc1": "B", "cur_pp1": "p1"}


def test_fragments_on_sqlite(engine):
    """The row-value NOT IN and the CASE run as written (SQLite >= 3.15), and a
    NULL promo_id is never hidden."""
    with engine.begin() as c:
        c.execute(text("CREATE TABLE t (chain_id TEXT, promo_id TEXT)"))
        c.execute(text("INSERT INTO t VALUES ('A','x'), ('A','p2'), ('B','p1'), ('C','y'), ('A', NULL)"))
        hs, hp = PC.hide_sql(CUR, "chain_id", "promo_id")
        ps, pp = PC.pin_rank_sql(CUR, "chain_id", "promo_id")
        got = c.execute(text(f"SELECT chain_id, promo_id, {ps} AS pin_rank FROM t WHERE 1 = 1 {hs} "
                             f"ORDER BY COALESCE(pin_rank, {PC.NO_PIN}), chain_id"), {**hp, **pp}).all()
    assert [tuple(r) for r in got] == [("A", "p2", 1), ("B", "p1", 2), ("A", None, None)]


def test_mark_sets_pinned_and_sponsored():
    rows = [{"x": 1, "pin_rank": 1}, {"x": 2, "pin_rank": 2}, {"x": 3, "pin_rank": None}, {"x": 4}]
    assert PC.mark(rows, CUR) == [{"x": 1, "pinned": True, "sponsored": True},
                                  {"x": 2, "pinned": True, "sponsored": False},
                                  {"x": 3, "pinned": False, "sponsored": False},
                                  {"x": 4, "pinned": False, "sponsored": False}]


def test_loader_fails_open_without_the_table(engine):
    PC.invalidate()
    with engine.connect() as c:
        assert PC.get_curation(c) == PC.EMPTY
        assert c.execute(text("SELECT 1")).scalar() == 1   # the connection is still usable
    PC.invalidate()


def test_loader_reads_only_rows_in_force_and_hide_wins(engine):
    with engine.begin() as c:
        c.execute(text("CREATE TABLE promo_curation (id INTEGER PRIMARY KEY, kind TEXT, chain_id TEXT, "
                       "promo_id TEXT, rank INTEGER, starts_at TEXT, ends_at TEXT, sponsored BOOLEAN, active BOOLEAN)"))
        ins = ("INSERT INTO promo_curation (kind, chain_id, promo_id, rank, starts_at, ends_at, sponsored, active) "
               "VALUES (:k, :c, :p, :r, :s, :e, :sp, :a)")
        past, future = "2000-01-01 00:00:00", "2999-01-01 00:00:00"
        for row in [("pin", "A", "p3", 3, past, None, 0, 1),
                    ("pin", "A", "p1", 1, past, future, 1, 1),
                    ("pin", "A", "gone", 2, past, past, 0, 1),        # past ends_at
                    ("pin", "A", "later", 4, future, None, 0, 1),     # not started
                    ("pin", "A", "off", 5, past, None, 0, 0),         # removed
                    ("pin", "B", "both", 6, past, None, 0, 1),
                    ("hide", "B", "both", None, past, None, 0, 1),
                    ("hide", "C", "h", None, past, None, 0, 1)]:
            c.execute(text(ins), dict(zip(("k", "c", "p", "r", "s", "e", "sp", "a"), row)))
    PC.invalidate()
    with engine.connect() as c:
        cur = PC.get_curation(c)
    PC.invalidate()
    assert cur.pins == (PC.Pin("A", "p1", True), PC.Pin("A", "p3", False))
    assert cur.hides == frozenset({("B", "both"), ("C", "h")})
