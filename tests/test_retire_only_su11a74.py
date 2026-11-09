"""SU11A-74: --retire-only in scripts/import_google_coordinates.py (retire listed stores, no
coordinate file) and the cleaned scraper/active_stores.yaml. No database needed.
    python -m pytest tests/test_retire_only_su11a74.py -q
"""
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

import scripts.import_google_coordinates as M
from db.db import _pad_store_id

FKS = [23280, 985, 5172, 18791, 18793, 18807, 18810, 18816, 18818, 18823, 18825, 18826, 18827, 61517, 18832]
REMOVED = {  # chain_id -> store ids removed from the yaml in SU11A-74
    "7290803800003": {"002", "146", "152"},
    "7290058108879": {"335", "337"},
    "7290058134977": {"021", "025", "033", "035", "041", "043", "051", "088"},
    "7290055700007": {"445"},
    "7290058148776": {"007"},
}
TOTALS = {"7290027600007": 321, "7290803800003": 47, "7290058108879": 28, "7290058134977": 20,
          "7290055700007": 145, "7290058148776": 19}


def row(fk, physical=True, last=None, chain_id="7290058134977", store_id="021"):
    return {"id": fk, "chain": "רשת", "chain_id": chain_id, "store_id": store_id, "sub_chain_id": "001",
            "store_name": f"סניף {fk}", "city_canonical": "ירושלים", "is_physical": physical,
            "last_loaded_at": last}


def args(**kw):
    base = dict(apply=False, trial=False, expect=None, session="SU11A-74", retire_closed="1,2,3")
    return SimpleNamespace(**{**base, **kw})


def conn_mock(rowcount=1):
    conn = MagicMock()
    conn.execute.return_value.rowcount = rowcount
    conn.execute.return_value.scalar.return_value = None      # no backup table yet
    return conn


def sqls(conn):
    return [str(c.args[0]) for c in conn.execute.call_args_list]


# ------------------------------------------------------------------ plan
def test_plan_accepts_physical_and_rejects_unknown_twice_and_not_physical():
    rows = [row(1), row(2, physical=False), row(3)]
    ok, bad = M.plan_retire([1, 2, 3, 3, 4], rows)
    assert [r["id"] for r in ok] == [1, 3]
    assert dict(bad) == {2: "is_physical is already false: leave it out", 3: "listed twice", 4: "unknown store_fk"}


# ------------------------------------------------------------------ dry run / trial / apply
def test_dry_run_writes_nothing(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: called.append(a))
    conn = conn_mock()
    ok = M.run_retire_only(args(), conn, [row(1), row(2), row(3)], [1, 2, 3])
    assert len(ok) == 3 and not conn.execute.called and not conn.commit.called and conn.rollback.called
    assert not called
    out = capsys.readouterr().out
    assert "to retire 3" in out and "--apply --expect 3 --session SU11A-74" in out


def test_dry_run_lists_rejections_and_yaml_warning_and_checks(capsys):
    conn = conn_mock()
    M.run_retire_only(args(retire_closed="1,2"), conn, [row(1, last=datetime(2026, 11, 6, 10, 5)), row(2, physical=False)],
                      [1, 2], checks=([("stores_geo_source_chk", "CHECK (...)")], []),
                      in_yaml={("7290058134977", "021")})
    out = capsys.readouterr().out
    assert "REJECT store_fk 2" in out and "WARNING: still in active_stores.yaml" in out
    assert "last loaded 2026-11-06 10:05" in out and "CHECK constraints on stores: 1; user triggers: 0" in out
    assert not conn.commit.called


def test_trial_retires_one_then_rolls_back():
    conn = conn_mock()
    M.run_retire_only(args(trial=True), conn, [row(1), row(2), row(3)], [1, 2, 3])
    assert sqls(conn) == [M.RETIRE_CLOSED_SQL]
    assert conn.execute.call_args.args[1] == {"fk": 1}
    assert conn.rollback.called and not conn.commit.called


@pytest.mark.parametrize("kw", [dict(apply=True, expect=3), dict(trial=True)])
def test_any_rejection_aborts_a_write(kw, monkeypatch):
    monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: pytest.fail("pg_dump must not run"))
    conn = conn_mock()
    with pytest.raises(SystemExit):
        M.run_retire_only(args(**kw), conn, [row(1), row(3)], [1, 2, 3])
    assert not conn.execute.called and not conn.commit.called


@pytest.mark.parametrize("expect", [None, 2, 4])
def test_apply_needs_the_exact_expect(expect, monkeypatch):
    monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: pytest.fail("pg_dump must not run"))
    conn = conn_mock()
    with pytest.raises(SystemExit):
        M.run_retire_only(args(apply=True, expect=expect), conn, [row(1), row(2), row(3)], [1, 2, 3])
    assert not conn.execute.called and not conn.commit.called


def _fake_dump(tmp_path, monkeypatch):
    monkeypatch.setattr(M.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u@h/db")

    def run(cmd, **_):
        Path(cmd[cmd.index("-f") + 1]).write_bytes(b"dump")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(M.subprocess, "run", run)


def test_apply_dumps_backs_up_retires_and_commits(tmp_path, monkeypatch, capsys):
    _fake_dump(tmp_path, monkeypatch)
    conn = conn_mock()
    M.run_retire_only(args(apply=True, expect=3), conn, [row(1), row(2), row(3)], [1, 2, 3])
    q = sqls(conn)
    assert q[0].startswith("SELECT to_regclass") and q[1] == "CREATE TABLE stores_bak_su11a_74 AS SELECT * FROM stores"
    assert q[2:] == [M.RETIRE_CLOSED_SQL] * 3
    assert conn.commit.called and not conn.rollback.called
    assert list((tmp_path / "backups").glob("pre-SU11A-74-stores-*.dump"))
    assert "COMMITTED: 3 stores retired" in capsys.readouterr().out


def test_apply_rolls_back_when_a_row_is_not_updated(tmp_path, monkeypatch):
    _fake_dump(tmp_path, monkeypatch)
    conn = conn_mock(rowcount=0)
    with pytest.raises(SystemExit):
        M.run_retire_only(args(apply=True, expect=3), conn, [row(1), row(2), row(3)], [1, 2, 3])
    assert conn.rollback.called and not conn.commit.called


def test_apply_refuses_an_existing_backup_table(tmp_path, monkeypatch):
    _fake_dump(tmp_path, monkeypatch)
    conn = conn_mock()
    conn.execute.return_value.scalar.return_value = "stores_bak_su11a_74"
    with pytest.raises(SystemExit):
        M.run_retire_only(args(apply=True, expect=3), conn, [row(1), row(2), row(3)], [1, 2, 3])
    assert not conn.commit.called and M.RETIRE_CLOSED_SQL not in sqls(conn)


def test_retire_sql_and_rollback_cover_this_session():
    # Only is_physical (NOT NULL boolean) and last_loaded_at (nullable) are written: no CHECK on stores
    # touches either (tests/test_import_google_coordinates.py checks the coordinate constraints).
    assert M.RETIRE_CLOSED_SQL == "UPDATE stores SET is_physical = false, last_loaded_at = NULL WHERE id = :fk"
    conn = MagicMock()
    conn.execute.return_value.scalar.return_value = "stores_bak_su11a_74"
    conn.execute.return_value.rowcount = 15
    M.rollback("SU11A-74", conn)
    restore = sqls(conn)[-1]
    assert "is_physical = b.is_physical, last_loaded_at = b.last_loaded_at" in restore
    assert "FROM stores_bak_su11a_74 b" in restore and "IS DISTINCT FROM b.is_physical" in restore
    assert conn.commit.called


@pytest.mark.parametrize("argv", [
    ["--retire-only"],
    ["--retire-only", "--retire-closed", "1", "--exact", "x.csv"],
    ["--retire-only", "--retire-closed", "1", "--mark-online", "2"],
    ["--retire-only", "--retire-closed", "1", "--session", "bad"],
])
def test_cli_guards(argv, monkeypatch):
    monkeypatch.setattr("sys.argv", ["import_google_coordinates", *argv])
    with pytest.raises(SystemExit):
        M.main()


# ------------------------------------------------------------------ the yaml
def _yaml():
    cfg = yaml.safe_load((Path(M.__file__).resolve().parent.parent / "scraper" / "active_stores.yaml")
                         .read_text(encoding="utf-8"))
    return {e["chain_id"]: [_pad_store_id(str(x)) for x in e.get("store_ids", [])] for e in cfg["chains"]}


def test_yaml_totals_and_removed_ids():
    ids = _yaml()
    for cid, n in TOTALS.items():
        assert len(ids[cid]) == n, cid
    for cid, gone in REMOVED.items():
        assert not gone & set(ids[cid]), (cid, gone & set(ids[cid]))
    assert ids["7290027600007"].count("413") == 1          # the real Shufersal 413 stays, once
    assert sum(len(v) for v in ids.values()) == 920
    assert len(set(FKS)) == 15 == sum(len(v) for v in REMOVED.values())


def test_yaml_has_no_duplicates_in_any_chain():
    for cid, ids in _yaml().items():
        assert not {k: v for k, v in Counter(ids).items() if v > 1}, cid


def test_yaml_pairs_matches_the_file():
    pairs = M.yaml_pairs()
    assert ("7290027600007", "413") in pairs and ("7290058134977", "021") not in pairs
    assert len(pairs) == 920
