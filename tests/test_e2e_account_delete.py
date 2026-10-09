"""Offline checks for scripts/e2e_account_delete.py (SU11A-29): argparse, env handling,
URL normalisation and error formatting. No network, no database.
    python -m pytest tests/test_e2e_account_delete.py -q"""
import httpx
import pytest

import scripts.e2e_account_delete as E


def test_parse_args_defaults_and_required_email():
    a = E.parse_args(["--email", "t+1@example.test"])
    assert a.email == "t+1@example.test" and a.api_base == "https://api-super.xxl.co.il" and not a.dry_run
    assert E.parse_args(["--email", "x@y.z", "--dry-run", "--api-base", "http://h"]).dry_run
    with pytest.raises(SystemExit):
        E.parse_args([])


@pytest.mark.parametrize("flag", ["--password", "--token", "--key"])
def test_no_secret_is_accepted_as_an_argument(flag):
    with pytest.raises(SystemExit):
        E.parse_args(["--email", "x@y.z", flag, "secret"])


def test_help_mentions_throwaway(capsys):
    with pytest.raises(SystemExit):
        E.parse_args(["--help"])
    assert "Throwaway accounts only" in capsys.readouterr().out


def test_missing_env_names_only():
    env = {"SUPABASE_URL": "https://x.supabase.test", "SUPABASE_ANON_KEY": "", "DATABASE_URL": None}
    assert E.missing_env({k: v for k, v in env.items() if v is not None}) == ["SUPABASE_ANON_KEY", "DATABASE_URL"]


def test_run_reports_missing_names_without_values(monkeypatch, capsys):
    monkeypatch.setenv("SUPABASE_URL", "https://VALUE-MUST-NOT-PRINT.supabase.test")
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert E.run(E.parse_args(["--email", "x@y.z", "--dry-run"])) == 1
    out = capsys.readouterr().out
    assert "SUPABASE_ANON_KEY" in out and "DATABASE_URL" in out and "VALUE-MUST-NOT-PRINT" not in out


@pytest.mark.parametrize("url,want", [
    ("postgres://u:p@h:5432/d", "postgresql://u:p@h:5432/d"),
    ("postgresql+asyncpg://u:p@h/d", "postgresql://u:p@h/d"),
    ("postgresql+psycopg2://u:p@h/d", "postgresql://u:p@h/d"),
    ("postgresql://u:p@h/d", "postgresql://u:p@h/d"),
])
def test_normalize_db_url(url, want):
    assert E.normalize_db_url(url) == want


def test_protected_ids_parsing():
    assert E.protected_ids({"DELETE_PROTECTED_USER_IDS": " A-1 , b-2 ,, "}) == {"a-1", "b-2"}
    assert E.protected_ids({}) == set()


@pytest.mark.parametrize("status,body,want", [
    (401, {"code": "account_deleted"}, "HTTP 401 account_deleted"),
    (400, {"code": 400, "error_code": "invalid_credentials", "msg": "x"}, "HTTP 400 invalid_credentials"),
    (401, {"detail": "Invalid or expired token"}, "HTTP 401"),
    (502, None, "HTTP 502"),
])
def test_err_code_is_short_and_safe(status, body, want):
    resp = httpx.Response(status, json=body) if body is not None else httpx.Response(status, text="<html>")
    assert E._err_code(resp) == want


def test_report_counts_failures(capsys):
    r = E.Report()
    r.check("a", True, "ok")
    r.check("b", False, "bad")
    r.skip("c", "n/a")
    assert r.failed == 1 and [s for _, s in r.results] == ["PASS", "FAIL", "SKIP"]
    assert "[FAIL] b: bad" in capsys.readouterr().out
