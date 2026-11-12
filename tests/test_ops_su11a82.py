"""SU11A-82 (SU11A-79 H2 / H3 / H4): unit-failure alerts, the daily health check,
the encrypted backup script and the CGNAT rate limits.

Pure logic with faked inputs; no server, no SMTP, no database, no rclone.
    python -m pytest tests/test_ops_su11a82.py -q
"""
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import ops_alert as A
from scripts import ops_common as C
from scripts import ops_health_check as H

ROOT = Path(__file__).resolve().parent.parent
SYSTEMD = ROOT / "deploy" / "systemd"
NGINX = ROOT / "deploy" / "nginx"
BACKUP = ROOT / "deploy" / "backup" / "scrp-backup.sh"
NOW = datetime(2026, 11, 13, 6, 15, tzinfo=timezone.utc)      # 08:15 Israel time
GB = 1024 ** 3
SERVICES = ["scrp-stats", "scrp-backup", "scrp-account-sweep", "scrp-cron", "scrp-search-items",
            "scrp-gs1-fetch", "scrp-gs1-images-backup"]


# =================================================================== redaction
@pytest.mark.parametrize("raw, leaked", [
    ("DATABASE_URL=postgresql://scrp_app:Sup3rS3cret@localhost/xxl_super", "Sup3rS3cret"),
    ("connect postgres://u:p4ss@h:5432/db failed", "p4ss"),
    ("smtp_password=hunter22", "hunter22"),
    ("password: 'abc def'", "abc def"),
    ('{"api_key": "AIzaSyA1234567890abcdefghijklmnopqrstuv"}', "AIzaSyA1234567890abcdefghijklmnopqrstuv"),
    ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
    ("token eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlc2ln", "eyJhbGciOiJFUzI1NiJ9"),
    ("key sb_secret_abcdefghijklmnop", "sb_secret_abcdefghijklmnop"),
    ("AWS AKIAABCDEFGHIJKLMNOP used", "AKIAABCDEFGHIJKLMNOP"),
])
def test_redact_masks_credentials(raw, leaked):
    out = C.redact(raw)
    assert leaked not in out
    assert C.redact(out) == out


def test_redact_keeps_ordinary_lines():
    line = "2026-11-13T04:00:12+0200 scrp-backup[123]: upload OK: xxl_super-2026-11-13.dump on b2crypt:daily/"
    assert C.redact(line) == line


def test_settings_defaults_and_overrides(monkeypatch):
    for k in ("ops_host_label", "ops_alert_to", "ops_disk_max_pct"):
        monkeypatch.delenv(k, raising=False)
    assert C.host_label() == "scrp-prod-il" and C.alert_recipient() == "info@xxl.co.il"
    assert C.env_number("ops_disk_max_pct", 85) == 85
    monkeypatch.setenv("ops_disk_max_pct", "90")
    assert C.env_number("ops_disk_max_pct", 85) == 90
    monkeypatch.setenv("ops_disk_max_pct", "lots")
    assert C.env_number("ops_disk_max_pct", 85) == 85


def test_send_alert_redacts_and_uses_the_api_mailer(monkeypatch):
    sent = []
    from api import mailer
    monkeypatch.setattr(mailer, "send_email", lambda s, b, to=None: sent.append((s, b, to)) or True)
    monkeypatch.delenv("ops_alert_to", raising=False)
    assert C.send_alert("[XXL] x", "line smtp_password=hunter22")
    assert sent == [("[XXL] x", "line smtp_password=***", "info@xxl.co.il")]


# =================================================================== ops_alert
@pytest.fixture
def fake_alert(monkeypatch):
    calls = {"cmds": [], "mails": []}

    def run(cmd):
        calls["cmds"].append(cmd)
        if cmd[0] == "journalctl":
            return "04:00 scrp-backup: pg_dump failed\n04:00 DATABASE_URL=postgresql://a:secretpw@h/db"
        return "Result=exit-code\nExecMainStatus=1"
    monkeypatch.setattr(A, "run", run)
    monkeypatch.setattr(A, "send_alert", lambda s, b: calls["mails"].append((s, b)) or True)
    monkeypatch.delenv("ops_host_label", raising=False)
    return calls


def test_alert_subject_body_and_journal_tail(fake_alert):
    assert A.main(["--unit", "scrp-backup.service"]) == 0
    (subject, body), = fake_alert["mails"]
    assert subject == "[XXL] scrp-backup.service failed on scrp-prod-il"
    assert "No new off-site backup today" in body                 # the hint
    assert "pg_dump failed" in body and "Result=exit-code" in body
    assert "secretpw" not in body
    journal = [c for c in fake_alert["cmds"] if c[0] == "journalctl"][0]
    assert journal == ["journalctl", "-u", "scrp-backup.service", "-n", "30", "--no-pager", "-o", "short-iso"]


def test_alert_dry_run_sends_nothing(fake_alert, capsys):
    assert A.main(["--unit", "scrp-cron.service", "--dry-run"]) == 0
    assert fake_alert["mails"] == []
    assert "[XXL] scrp-cron.service failed on scrp-prod-il" in capsys.readouterr().out


def test_alert_refuses_odd_unit_names(fake_alert):
    assert A.main(["--unit", "x; rm -rf /"]) == 2
    assert fake_alert["cmds"] == [] and fake_alert["mails"] == []


def test_alert_exit_1_when_the_mail_fails(fake_alert, monkeypatch):
    monkeypatch.setattr(A, "send_alert", lambda s, b: False)
    assert A.main(["--unit", "scrp-stats.service"]) == 1


def test_alert_run_survives_a_missing_command():
    assert "not available" in A.run(["definitely-not-a-command-su11a82"])


# =============================================================== health checks
def test_disk():
    assert H.check_disk(77 * GB, 100 * GB, 85) == []
    (p,) = H.check_disk(86 * GB, 100 * GB, 85)
    assert "86% used" in p and "14.0 GB free" in p
    assert H.check_disk(1, 0, 85) == ["disk: total size unknown"]


def test_certs():
    certs = [("api-super.xxl.co.il", NOW + timedelta(days=31)),
             ("super.xxl.co.il", NOW + timedelta(days=10)),
             ("old.xxl.co.il", NOW - timedelta(days=1)),
             ("fly.xxl.co.il", None)]
    out = H.check_certs(certs, NOW, 14)
    assert len(out) == 3
    assert any("super.xxl.co.il certificate expires on" in p and "in 10 days" in p for p in out)
    assert any("old.xxl.co.il certificate EXPIRED" in p for p in out)
    assert any("could not read the certificate of fly.xxl.co.il" in p for p in out)
    assert not any("api-super" in p for p in out)


def test_freshness():
    rows = [("7290027600007", "שופרסל", 22.0), ("7290058140886", "רמי לוי", 30.5), ("7290000000001", "חדשה", None)]
    out = H.check_freshness(rows, 26)
    assert out == ["prices: חדשה (7290000000001) has no successful price load at all",
                   "prices: רמי לוי (7290058140886) last loaded 30 h ago (limit 26 h)"]
    assert H.check_freshness([("1", "a", 25.9)], 26) == []


def test_db_size():
    assert H.check_db_size(int(6.5 * GB), 10) == []
    assert H.check_db_size(int(10.5 * GB), 10) == ["db: the database is 10.5 GB, above 10 GB"]


def test_backup():
    ok = NOW - timedelta(hours=2, minutes=12)
    assert H.check_backup("success", ok, NOW, 26) == []
    assert H.check_backup("exit-code", ok, NOW, 26) == ["backup: the last scrp-backup.service run ended with result 'exit-code'"]
    (p,) = H.check_backup("success", NOW - timedelta(hours=27), NOW, 26)
    assert "27 h ago" in p
    assert H.check_backup(None, None, NOW, 26) == ["backup: scrp-backup.service has no finished run on record"]


def test_parse_systemd_unix():
    assert H.parse_systemd_unix("@1763014512") == datetime.fromtimestamp(1763014512, tz=timezone.utc)
    for v in ("", "n/a", "Thu 2026-11-13 04:03:12 IST", "@x"):
        assert H.parse_systemd_unix(v) is None


def test_limits_from_env(monkeypatch):
    monkeypatch.setenv("ops_db_max_gb", "12")
    lim = H.Limits.from_env()
    assert lim.db_max_gb == 12 and lim.disk_max_pct == 85 and lim.backup_max_hours == 26


def test_report_lists_every_problem():
    subject, body = H.build_report(["disk: x", "tls: y"], "scrp-prod-il", NOW)
    assert subject == "[XXL] health check: 2 problems on scrp-prod-il"
    assert "- disk: x" in body and "- tls: y" in body
    assert H.build_report(["a"], "h", NOW)[0] == "[XXL] health check: 1 problem on h"


@pytest.fixture
def healthy(monkeypatch):
    """Every gatherer faked to a healthy server."""
    monkeypatch.setattr(H.shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(100 * GB, 77 * GB, 23 * GB))
    monkeypatch.setattr(H, "gather_certs", lambda hosts: [(h, NOW + timedelta(days=60)) for h in hosts])
    monkeypatch.setattr(H, "gather_backup", lambda: ("success", NOW - timedelta(hours=2)))
    monkeypatch.setattr(H, "active_chain_ids", lambda: {"1", "2"})

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Eng:
        def connect(self): return _Conn()
    import db.db as D
    monkeypatch.setattr(D, "get_engine", lambda: _Eng())
    monkeypatch.setattr(H, "gather_db", lambda conn, active, now: ([(c, c, 20.0) for c in sorted(active)], [], int(6.5 * GB)))
    mails = []
    monkeypatch.setattr(H, "send_alert", lambda s, b: mails.append((s, b)) or True)
    monkeypatch.setattr(H, "datetime", _FixedNow)
    for k in list(os.environ):
        if k.startswith("ops_"):
            monkeypatch.delenv(k)
    return mails


class _FixedNow(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


def test_healthy_server_mails_nothing(healthy, capsys):
    assert H.main([]) == 0
    assert healthy == []
    assert "health check OK" in capsys.readouterr().out


def test_problems_are_mailed_once(healthy, monkeypatch):
    monkeypatch.setattr(H.shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(100 * GB, 90 * GB, 10 * GB))
    monkeypatch.setattr(H, "gather_backup", lambda: ("exit-code", NOW - timedelta(hours=30)))
    assert H.main([]) == 0
    (subject, body), = healthy
    assert subject == "[XXL] health check: 3 problems on scrp-prod-il"
    assert "90% used" in body and "result 'exit-code'" in body and "30 h ago" in body


def test_a_broken_check_is_a_problem_not_silence(healthy, monkeypatch):
    def boom(hosts):
        raise PermissionError("/etc/letsencrypt/live")
    monkeypatch.setattr(H, "gather_certs", boom)
    assert H.main([]) == 0
    (subject, body), = healthy
    assert "tls: could not check (PermissionError)" in body
    assert "/etc/letsencrypt" not in body          # the type only, not the message


def test_dry_run_never_mails_and_mail_failure_is_exit_1(healthy, monkeypatch):
    monkeypatch.setattr(H, "gather_backup", lambda: (None, None))
    assert H.main(["--dry-run"]) == 0 and healthy == []
    monkeypatch.setattr(H, "send_alert", lambda s, b: False)
    assert H.main([]) == 1


def test_test_mail(healthy):
    assert H.main(["--test-mail"]) == 0
    assert healthy[0][0] == "[XXL] test alert from scrp-prod-il"


def test_active_chains_come_from_active_stores_yaml():
    ids = H.active_chain_ids()
    assert len(ids) >= 10 and all(isinstance(i, str) and i for i in ids)


def test_freshness_sql_uses_the_freshness_source():
    sql = " ".join(H.FRESHNESS_SQL.split())
    assert "fr.files_loaded > 0" in sql and "MAX(fr.run_at)" in sql and "c.chain_id IN :ids" in sql
    # SU11A-82b: no date arithmetic in SQL (run_at is TEXT in Postgres) and no Postgres-only ANY().
    assert "now()" not in sql.lower() and "EXTRACT" not in sql and "ANY(" not in sql


# =================================================================== systemd
def _ini(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("unit", SERVICES)
def test_every_scrp_service_has_an_onfailure_dropin(unit):
    f = SYSTEMD / "dropins" / f"{unit}.service.d" / "xxl-onfailure.conf"
    lines = [l.strip() for l in _ini(f).splitlines() if l.strip() and not l.startswith("#")]
    assert lines == ["[Unit]", "OnFailure=xxl-alert@%n.service"]
    assert "\r" not in f.read_bytes().decode("utf-8")


def test_dropins_cover_exactly_the_scrp_services():
    found = sorted(p.name.removesuffix(".service.d") for p in (SYSTEMD / "dropins").iterdir())
    assert found == sorted(SERVICES)


def test_alert_template_unit():
    s = _ini(SYSTEMD / "xxl-alert@.service")
    assert "OnFailure" not in s.split("[Service]")[0].split("[Unit]")[1].replace("# This unit has NO OnFailure", "")
    assert "ExecStart=/home/dude/scrp/venv/bin/python3 -m scripts.ops_alert --unit %i" in s
    assert "SupplementaryGroups=systemd-journal" in s and "EnvironmentFile=/home/dude/scrp/.env" in s
    assert "User=dude" in s


def test_health_check_unit_and_timer():
    svc = _ini(SYSTEMD / "xxl-health-check.service")
    assert "OnFailure=xxl-alert@%n.service" in svc
    assert "ExecStart=/home/dude/scrp/venv/bin/python3 -m scripts.ops_health_check" in svc
    timer = _ini(SYSTEMD / "xxl-health-check.timer")
    assert "OnCalendar=*-*-* 08:15:00 Asia/Jerusalem" in timer
    assert "TimeZone=" not in timer.replace("`TimeZone=`", "")


def test_0815_is_outside_the_quiet_times():
    quiet = [((3, 30), (3, 45)), ((4, 0), (4, 30)), ((10, 0), (13, 0)), ((14, 25), (15, 0))]
    t = (8, 15)
    assert not any(a <= t <= b for a, b in quiet)


# =================================================================== nginx H4
def _zones():
    s = _ini(NGINX / "xxl-ratelimit-http.conf")
    found = re.findall(r"^limit_req_zone \$binary_remote_addr zone=(\w+):(\d+m)\s+rate=(\S+);", s, re.M)
    return {name: (size, rate) for name, size, rate in found}


def test_zone_rates():
    z = _zones()
    assert {k: v[1] for k, v in z.items()} == {
        "xxl_api": "30r/s", "xxl_heavy": "5r/s", "xxl_bulk": "6r/s",
        "xxl_suggest": "40r/s", "xxl_img": "60r/s", "xxl_serp": "10r/m"}
    assert all(v[0] == "10m" for v in z.values())        # same sizes: a reload, not a restart
    assert re.search(r"^limit_req_status 429;", _ini(NGINX / "xxl-ratelimit-http.conf"), re.M)


def _locations():
    s = _ini(NGINX / "xxl-ratelimit-api.conf")
    blocks = re.findall(r"^location\s+([^{]+)\{(.*?)^\}", s, re.M | re.S)
    return {k.strip(): re.findall(r"limit_req zone=(\w+) burst=(\d+) nodelay;", body) for k, body in blocks}, s


HEAVY = ["= /compare", "= /basket/compare", "= /promos/grouped", "= /promos/list", "= /promos/promoted",
         "= /promos/today", "= /admin/promos/search", r"~ ^/categories/[A-Za-z0-9.]+/items$"]


def test_heavy_locations_use_both_buckets():
    locs, _ = _locations()
    for loc in HEAVY:
        assert locs[loc] == [("xxl_heavy", "30"), ("xxl_api", "120")], loc


def test_promos_bulk_has_its_own_zone():
    locs, _ = _locations()
    assert locs["= /promos/bulk"] == [("xxl_bulk", "30"), ("xxl_api", "120")]
    assert sum(1 for v in locs.values() if ("xxl_heavy", "30") in v) == 8


def test_general_suggest_and_image_bursts():
    locs, s = _locations()
    assert re.search(r"^limit_req zone=xxl_api burst=120 nodelay;", s, re.M)
    assert locs["= /categories/browse-tree"] == [("xxl_api", "120")]
    assert locs["= /suggest"] == [("xxl_suggest", "120")]
    assert locs[r"~ ^/product/[0-9]+/image$"] == [("xxl_img", "300")]


def test_every_zone_used_is_defined():
    defined = set(_zones())
    used = set()
    for f in NGINX.glob("*.conf"):
        used |= set(re.findall(r"limit_req zone=(\w+)", _ini(f)))
    assert used <= defined, used - defined


# =================================================================== backup H3
BASH = shutil.which("bash")
needs_bash = pytest.mark.skipif(not BASH, reason="bash not available")


def _bash(script: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([BASH, "-c", script], capture_output=True, text=True, timeout=60,
                          env={**os.environ, **(env or {})})


def _bash_path(p: Path) -> str:
    """A directory as bash sees it in PATH (Git Bash on Windows: C:/x -> /c/x)."""
    q = p.as_posix()
    return f"/{q[0].lower()}{q[2:]}" if re.match(r"^[A-Za-z]:/", q) else q


def _keep(name: str, today: str) -> bool:
    path = BACKUP.as_posix()
    r = _bash(f'source "{path}"; keep_dump "{name}" "{today}" && echo KEEP || echo DROP')
    assert r.returncode == 0, r.stderr
    return r.stdout.strip() == "KEEP"


@needs_bash
@pytest.mark.parametrize("name, keep", [
    ("xxl_super-2026-11-13.dump", True),     # today
    ("xxl_super-2026-11-07.dump", True),     # 6 days
    ("xxl_super-2026-11-06.dump", False),    # 7 days, a Friday
    ("xxl_super-2026-10-18.dump", True),     # Sunday, 26 days
    ("xxl_super-2026-10-11.dump", False),    # Sunday, 33 days
    ("xxl_super-2026-06-01.dump", True),     # 1st of the month, 165 days
    ("xxl_super-2026-05-01.dump", False),    # 1st of the month, 196 days
    ("something-else.txt", True),            # unknown names are never deleted
])
def test_local_rotation(name, keep):
    assert _keep(name, "2026-11-13") is keep


@needs_bash
def test_refuses_a_non_crypt_remote(tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "rclone").write_text('#!/usr/bin/env bash\n[ "$1" = listremotes ] && echo "b2:          b2"\nexit 0\n',
                                 newline="\n")
    (fake / "rclone").chmod(0o755)
    conf = tmp_path / "backup.conf"
    conf.write_text('REMOTE="b2:"\n', newline="\n")
    log = tmp_path / "backup.log"
    r = _bash(f'export PATH="{_bash_path(fake)}:$PATH"; bash "{BACKUP.as_posix()}"',
              env={"XXL_BACKUP_CONF": conf.as_posix(), "XXL_BACKUP_LOG": log.as_posix()})
    assert r.returncode == 1
    assert "not crypt: refusing to upload an unencrypted dump" in r.stdout + r.stderr


@needs_bash
def test_refuses_an_empty_remote(tmp_path):
    conf = tmp_path / "backup.conf"
    conf.write_text("# nothing\n", newline="\n")
    r = _bash(f'bash "{BACKUP.as_posix()}"',
              env={"XXL_BACKUP_CONF": conf.as_posix(), "XXL_BACKUP_LOG": (tmp_path / "l").as_posix()})
    assert r.returncode == 1 and "REMOTE is not set" in r.stdout + r.stderr


def test_backup_script_has_no_secrets_and_lf_endings():
    raw = BACKUP.read_bytes()
    assert b"\r" not in raw
    s = raw.decode("utf-8")
    assert s.startswith("#!/usr/bin/env bash\n")
    code = "\n".join(line for line in s.splitlines() if not line.lstrip().startswith("#")).lower()
    for bad in ("config show", "password", "passwd", "obscure"):
        assert bad not in code, bad
    assert "rclone listremotes --long" in s          # names and types only
    assert 'ALLOW_PLAIN="0"' in s


def test_backup_config_example_names_a_crypt_remote():
    s = (ROOT / "deploy" / "backup" / "backup.conf.example").read_text(encoding="utf-8")
    assert 'REMOTE="b2crypt:"' in s and 'SUBDIR="daily"' in s and 'ALLOW_PLAIN="0"' in s


# ============================================ SU11A-82b: run_at is TEXT
# fetch_runs.run_at is TEXT in Postgres (db/schema_postgres.sql:50); the first
# version did now() - MAX(run_at) in SQL and Postgres rejected it.
@pytest.mark.parametrize("raw, expected", [
    ("2026-11-12T08:03:11.123456+00:00", datetime(2026, 11, 12, 8, 3, 11, 123456, tzinfo=timezone.utc)),  # what the loader writes
    ("2026-11-12T10:03:11+02:00", datetime(2026, 11, 12, 8, 3, 11, tzinfo=timezone.utc)),
    ("2026-11-12T08:03:11Z", datetime(2026, 11, 12, 8, 3, 11, tzinfo=timezone.utc)),
    ("2026-11-12 08:03:11z", datetime(2026, 11, 12, 8, 3, 11, tzinfo=timezone.utc)),
    ("2026-11-12T10:03:11", datetime(2026, 11, 12, 8, 3, 11, tzinfo=timezone.utc)),     # naive = Israel (UTC+2 in Nov)
    ("2026-07-12 10:03:11", datetime(2026, 7, 12, 7, 3, 11, tzinfo=timezone.utc)),      # naive in summer (UTC+3)
    (datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc), datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc)),
])
def test_parse_run_at(raw, expected):
    assert H.parse_run_at(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "garbage", "2026-13-40T00:00:00", "12/11/2026 10:00", "   "])
def test_parse_run_at_garbage_is_none(raw):
    assert H.parse_run_at(raw) is None


class _FakeResult:
    def __init__(self, rows=None, scalar=None):
        self._rows, self._scalar = rows or [], scalar

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _FakeConn:
    """Answers like Postgres: run_at comes back as TEXT."""
    def __init__(self, rows, size):
        self.rows, self.size, self.calls = rows, size, []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.calls.append((sql, params))
        if "pg_database_size" in sql:
            return _FakeResult(scalar=self.size)
        return _FakeResult(rows=self.rows)


def test_gather_db_computes_hours_in_python_from_text_timestamps():
    rows = [("7290027600007", "שופרסל", "2026-11-12T08:03:00+00:00"),     # 22.2 h before NOW
            ("7290058140886", "רמי לוי", "2026-11-11T08:00:00Z"),          # 46.25 h
            ("7290000000002", "ויקטורי", "2026-11-12T10:15:00"),           # naive Israel = 08:15 UTC, 22 h
            ("7290000000003", "חדשה", None),                               # never loaded
            ("7290000000004", "שבורה", "yesterday")]                       # unparsable
    active = {r[0] for r in rows} | {"7290000000099"}                       # one id not in chains
    conn = _FakeConn(rows, int(6.5 * GB))
    fresh, unparsable, size = H.gather_db(conn, active, NOW)
    by_id = {c: h for c, _, h in fresh}
    assert round(by_id["7290027600007"], 2) == 22.2
    assert round(by_id["7290058140886"], 2) == 46.25
    assert round(by_id["7290000000002"], 2) == 22.0
    assert by_id["7290000000003"] is None and by_id["7290000000099"] is None
    assert "7290000000004" not in by_id
    assert unparsable == ["prices: could not parse last run for שבורה (7290000000004)"]
    assert size == int(6.5 * GB)
    assert H.check_freshness(fresh, 26) == [
        "prices: חדשה (7290000000003) has no successful price load at all",
        "prices: not in chains (7290000000099) has no successful price load at all",
        "prices: רמי לוי (7290058140886) last loaded 46 h ago (limit 26 h)",
    ]
    sql, params = conn.calls[0]
    assert params == {"ids": sorted(active)}


def test_freshness_sql_runs_on_sqlite_with_text_run_at():
    from sqlalchemy import create_engine, text
    eng = create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE chains (chain_id TEXT PRIMARY KEY, name TEXT)"))
        c.execute(text("CREATE TABLE fetch_runs (id INTEGER PRIMARY KEY, chain_id TEXT NOT NULL, run_at TEXT NOT NULL, "
                       "files_loaded INTEGER DEFAULT 0)"))
        c.execute(text("INSERT INTO chains VALUES ('A', 'אלף'), ('B', 'בית'), ('C', 'גימל')"))
        c.execute(text("INSERT INTO fetch_runs (chain_id, run_at, files_loaded) VALUES "
                       "('A', '2026-11-11T08:00:00+00:00', 3), ('A', '2026-11-12T08:00:00+00:00', 5), "
                       "('A', '2026-11-12T09:00:00+00:00', 0), "     # a failed run (no files) is ignored
                       "('B', '2026-11-10T08:00:00+00:00', 0)"))
        rows = sorted(H.freshness_rows(c, {"A", "B"}))
    assert rows == [("A", "אלף", "2026-11-12T08:00:00+00:00"), ("B", "בית", None)]


def test_freshness_sql_runs_on_postgres_with_text_run_at():
    pg = pytest.importorskip("tests.test_promo_curation_su11a58_pg")
    if not pg.PG_URL:
        pytest.skip("SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")
    from sqlalchemy import create_engine, text
    with create_engine(pg.PG_URL).connect() as c:
        c.execute(text("CREATE TEMP TABLE chains (chain_id TEXT PRIMARY KEY, name TEXT)"))
        c.execute(text("CREATE TEMP TABLE fetch_runs (id SERIAL PRIMARY KEY, chain_id TEXT NOT NULL, run_at TEXT NOT NULL, "
                       "files_loaded INTEGER DEFAULT 0)"))
        c.execute(text("INSERT INTO chains VALUES ('A', 'a'), ('B', 'b')"))
        c.execute(text("INSERT INTO fetch_runs (chain_id, run_at, files_loaded) VALUES ('A', '2026-11-12T08:00:00+00:00', 5)"))
        fresh, unparsable, size = H.gather_db(c, {"A", "B"}, NOW)
    assert unparsable == [] and size > 0
    assert {cid: (None if h is None else round(h, 2)) for cid, _, h in fresh} == {"A": 22.25, "B": None}


def test_an_unparsable_run_is_a_problem_line_not_a_crash(healthy, monkeypatch):
    monkeypatch.setattr(H, "gather_db", lambda conn, active, now: (
        [("1", "a", 20.0)], ["prices: could not parse last run for b (2)"], int(6.5 * GB)))
    assert H.main([]) == 0
    (subject, body), = healthy
    assert "could not parse last run for b (2)" in body and "could not check" not in body
