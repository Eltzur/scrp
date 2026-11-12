"""SU11A-82 (SU11A-79 H2): the daily server health check. Mails ONLY when
something is wrong.

Run by xxl-health-check.timer at 08:15 Asia/Jerusalem (outside the quiet times).

    python3 -m scripts.ops_health_check             # check; mail if a problem
    python3 -m scripts.ops_health_check --dry-run   # check; print, never mail
    python3 -m scripts.ops_health_check --test-mail # send one test mail (SMTP path)

Checks (thresholds are env settings, lowercase; the defaults need no .env change):
  disk      / above ops_disk_max_pct (85) percent used
  certs     a TLS certificate expiring within ops_cert_min_days (14) days.
            /etc/letsencrypt/live/*/cert.pem when readable (root only on a
            default certbot install); otherwise the certificate each host in
            ops_tls_hosts actually serves on 127.0.0.1:443 (SNI), which is what
            visitors see.
  prices    an active chain (scraper/active_stores.yaml) with no successful
            price load (fetch_runs.files_loaded > 0, the /freshness source) in
            ops_fresh_max_hours (26) hours
  db        the database larger than ops_db_max_gb (10) GB
  backup    scrp-backup.service: last result not success, or its last run ended
            more than ops_backup_max_hours (26) hours ago

A check that cannot run is itself a problem ("could not check ..."), so a broken
check is never silent. Output and mail carry counts, names and dates only.
Exit 0 = healthy or mailed; 1 = problems found but the mail failed.
"""
from __future__ import annotations

import argparse
import glob
import shutil
import socket
import ssl
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.ops_common import env_number, host_label, send_alert

DEFAULT_TLS_HOSTS = ("xxl.co.il", "www.xxl.co.il", "super.xxl.co.il", "api-super.xxl.co.il",
                     "admin.xxl.co.il", "fly.xxl.co.il")
ACTIVE_STORES = Path(__file__).resolve().parent.parent / "scraper" / "active_stores.yaml"
BACKUP_UNIT = "scrp-backup.service"
GB = 1024 ** 3


@dataclass(frozen=True)
class Limits:
    disk_max_pct: float = 85.0
    cert_min_days: float = 14.0
    fresh_max_hours: float = 26.0
    db_max_gb: float = 10.0
    backup_max_hours: float = 26.0

    @classmethod
    def from_env(cls) -> "Limits":
        return cls(
            disk_max_pct=env_number("ops_disk_max_pct", cls.disk_max_pct),
            cert_min_days=env_number("ops_cert_min_days", cls.cert_min_days),
            fresh_max_hours=env_number("ops_fresh_max_hours", cls.fresh_max_hours),
            db_max_gb=env_number("ops_db_max_gb", cls.db_max_gb),
            backup_max_hours=env_number("ops_backup_max_hours", cls.backup_max_hours),
        )


# --------------------------------------------------------------- pure checks
def check_disk(used_bytes: int, total_bytes: int, max_pct: float) -> list[str]:
    if total_bytes <= 0:
        return ["disk: total size unknown"]
    pct = used_bytes / total_bytes * 100
    if pct > max_pct:
        free_gb = (total_bytes - used_bytes) / GB
        return [f"disk: / is {pct:.0f}% used ({free_gb:.1f} GB free), above {max_pct:.0f}%"]
    return []


def check_certs(certs: list[tuple[str, datetime | None]], now: datetime, min_days: float) -> list[str]:
    """certs: (name, notAfter in UTC, or None when it could not be read)."""
    out = []
    for name, not_after in sorted(certs):
        if not_after is None:
            out.append(f"tls: could not read the certificate of {name}")
            continue
        days = (not_after - now).total_seconds() / 86400
        if days < 0:
            out.append(f"tls: {name} certificate EXPIRED on {not_after:%Y-%m-%d}")
        elif days < min_days:
            out.append(f"tls: {name} certificate expires on {not_after:%Y-%m-%d} (in {days:.0f} days)")
    return out


def check_freshness(rows: list[tuple[str, str, float | None]], max_hours: float) -> list[str]:
    """rows: (chain_id, chain name, hours since the last successful load or None)."""
    out = []
    for chain_id, name, hours in sorted(rows, key=lambda r: r[0]):
        label = f"{name or '?'} ({chain_id})"
        if hours is None:
            out.append(f"prices: {label} has no successful price load at all")
        elif hours > max_hours:
            out.append(f"prices: {label} last loaded {hours:.0f} h ago (limit {max_hours:.0f} h)")
    return out


def check_db_size(size_bytes: int, max_gb: float) -> list[str]:
    gb = size_bytes / GB
    return [f"db: the database is {gb:.1f} GB, above {max_gb:.0f} GB"] if gb > max_gb else []


def check_backup(result: str | None, ended_at: datetime | None, now: datetime, max_hours: float) -> list[str]:
    if ended_at is None:
        return [f"backup: {BACKUP_UNIT} has no finished run on record"]
    out = []
    if result != "success":
        out.append(f"backup: the last {BACKUP_UNIT} run ended with result '{result or 'unknown'}'")
    hours = (now - ended_at).total_seconds() / 3600
    if hours > max_hours:
        out.append(f"backup: the last {BACKUP_UNIT} run ended {hours:.0f} h ago (limit {max_hours:.0f} h)")
    return out


def build_report(problems: list[str], host: str, now: datetime) -> tuple[str, str]:
    n = len(problems)
    subject = f"[XXL] health check: {n} problem{'s' if n != 1 else ''} on {host}"
    body = "\n".join([f"Daily health check on {host}, {now:%Y-%m-%d %H:%M} UTC.", ""]
                     + [f"- {p}" for p in problems]
                     + ["", "Sent by xxl-health-check.service (scripts/ops_health_check.py, SU11A-82). "
                            "Thresholds: env ops_* settings."])
    return subject, body


# -------------------------------------------------------------- the gathering
def parse_systemd_unix(value: str) -> datetime | None:
    """'@1731380592' (systemctl --timestamp=unix) -> aware UTC datetime; '' / 'n/a' -> None."""
    v = (value or "").strip()
    if not v.startswith("@"):
        return None
    try:
        return datetime.fromtimestamp(int(v[1:]), tz=timezone.utc)
    except ValueError:
        return None


def gather_backup() -> tuple[str | None, datetime | None]:
    r = subprocess.run(["systemctl", "show", BACKUP_UNIT, "--timestamp=unix", "--no-pager",
                        "-p", "Result", "-p", "ExecMainExitTimestamp"],
                       capture_output=True, text=True, timeout=30, check=True)
    props = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    return props.get("Result") or None, parse_systemd_unix(props.get("ExecMainExitTimestamp", ""))


def _pem_not_after(path: str) -> datetime:
    from cryptography import x509  # installed with python-jose[cryptography]
    cert = x509.load_pem_x509_certificate(Path(path).read_bytes())
    if hasattr(cert, "not_valid_after_utc"):          # cryptography >= 42
        return cert.not_valid_after_utc
    return cert.not_valid_after.replace(tzinfo=timezone.utc)


def _served_not_after(host: str) -> datetime | None:
    ctx = ssl.create_default_context()
    with socket.create_connection(("127.0.0.1", 443), timeout=10) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            cert = tls.getpeercert()
    raw = (cert or {}).get("notAfter")
    return datetime.fromtimestamp(ssl.cert_time_to_seconds(raw), tz=timezone.utc) if raw else None


def gather_certs(hosts: tuple[str, ...]) -> list[tuple[str, datetime | None]]:
    files = sorted(glob.glob("/etc/letsencrypt/live/*/cert.pem"))
    readable = [f for f in files if _readable(f)]
    if readable:
        return [(Path(f).parent.name, _pem_not_after(f)) for f in readable]
    out = []
    for h in hosts:
        try:
            out.append((h, _served_not_after(h)))
        except ssl.SSLCertVerificationError:
            out.append((h, None))   # expired / wrong name: reported as unreadable
    return out


def _readable(path: str) -> bool:
    try:
        with open(path, "rb"):
            return True
    except OSError:
        return False


def active_chain_ids(path: Path = ACTIVE_STORES) -> set[str]:
    import yaml
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(c["chain_id"]) for c in cfg.get("chains", []) if c.get("store_ids")}


# SU11A-82b: fetch_runs.run_at is TEXT (db/schema_postgres.sql:50), so the SQL
# only picks the newest loaded run per chain (the /freshness source, same text
# MAX as db/query.py fetch_freshness) and Python does the date arithmetic.
# Portable: an expanding IN bind, not Postgres-only ANY(:ids).
FRESHNESS_SQL = """
    SELECT c.chain_id, c.name, MAX(fr.run_at) AS last_run
    FROM chains c
    LEFT JOIN fetch_runs fr ON fr.chain_id = c.chain_id AND fr.files_loaded > 0
    WHERE c.chain_id IN :ids
    GROUP BY c.chain_id, c.name
"""

# A run_at without an offset is read as the server's local time. Every current
# writer (scraper/base.py, scraper/shufersal.py, scripts/seed_hazihinam.py)
# stores datetime.now(timezone.utc).isoformat(), i.e. UTC with "+00:00", so a
# naive value can only be a legacy row.
LOCAL_TZ = "Asia/Jerusalem"


def parse_run_at(raw) -> datetime | None:
    """fetch_runs.run_at -> aware UTC datetime, or None when it cannot be parsed.
    Accepts ISO 8601 with "+02:00", "+00:00" or "Z", a space instead of "T",
    and naive values (taken as Asia/Jerusalem). A datetime passes through."""
    if isinstance(raw, datetime):
        dt = raw
    else:
        text_value = str(raw or "").strip()
        if not text_value:
            return None
        if text_value.endswith(("Z", "z")):
            text_value = text_value[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text_value)
        except ValueError:
            return None
    if dt.tzinfo is None:
        from zoneinfo import ZoneInfo
        dt = dt.replace(tzinfo=ZoneInfo(LOCAL_TZ))
    return dt.astimezone(timezone.utc)


def freshness_rows(conn, ids: set[str]) -> list[tuple[str, str, object]]:
    """(chain_id, name, newest loaded run_at as stored) for the given chains."""
    from sqlalchemy import bindparam, text
    if not ids:
        return []
    stmt = text(FRESHNESS_SQL).bindparams(bindparam("ids", expanding=True))
    return [(str(r[0]), r[1], r[2]) for r in conn.execute(stmt, {"ids": sorted(ids)}).all()]


def gather_db(conn, active: set[str], now: datetime) -> tuple[list[tuple[str, str, float | None]], list[str], int]:
    """Freshness rows (hours since the last successful load, None = never),
    problem lines for run_at values that cannot be parsed, and the DB size."""
    from sqlalchemy import text
    fresh: list[tuple[str, str, float | None]] = []
    unparsable: list[str] = []
    rows = freshness_rows(conn, active)
    for chain_id, name, raw in rows:
        if raw is None:
            fresh.append((chain_id, name, None))
            continue
        at = parse_run_at(raw)
        if at is None:
            unparsable.append(f"prices: could not parse last run for {name or '?'} ({chain_id})")
            continue
        fresh.append((chain_id, name, (now - at).total_seconds() / 3600))
    found = {r[0] for r in rows}
    fresh += [(cid, "not in chains", None) for cid in sorted(active - found)]
    size = conn.execute(text("SELECT pg_database_size(current_database())")).scalar()
    return fresh, unparsable, int(size or 0)


def collect(limits: Limits, now: datetime) -> list[str]:
    problems: list[str] = []

    def attempt(what: str, fn) -> None:
        try:
            problems.extend(fn())
        except Exception as exc:  # noqa: BLE001 - a broken check is a problem, never silence
            problems.append(f"{what}: could not check ({type(exc).__name__})")

    def disk():
        u = shutil.disk_usage("/")
        return check_disk(u.used, u.total, limits.disk_max_pct)

    def certs():
        hosts = tuple(h.strip() for h in (_env("ops_tls_hosts") or ",".join(DEFAULT_TLS_HOSTS)).split(",") if h.strip())
        return check_certs(gather_certs(hosts), now, limits.cert_min_days)

    def database():
        from db.db import get_engine
        with get_engine().connect() as conn:
            fresh, unparsable, size = gather_db(conn, active_chain_ids(), now)
        return (check_freshness(fresh, limits.fresh_max_hours) + unparsable
                + check_db_size(size, limits.db_max_gb))

    def backup():
        result, ended = gather_backup()
        return check_backup(result, ended, now, limits.backup_max_hours)

    attempt("disk", disk)
    attempt("tls", certs)
    attempt("prices / db", database)
    attempt("backup", backup)
    return problems


def _env(name: str) -> str:
    import os
    return (os.environ.get(name) or "").strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="print the result, never mail")
    ap.add_argument("--test-mail", action="store_true", help="send one test mail and exit")
    a = ap.parse_args(argv)
    host, now = host_label(), datetime.now(timezone.utc)
    if a.test_mail:
        ok = send_alert(f"[XXL] test alert from {host}", "A test of the SU11A-82 alert mail path. No action needed.")
        print("test mail sent" if ok else "test mail NOT sent (see the mailer warning above)")
        return 0 if ok else 1
    problems = collect(Limits.from_env(), now)
    if not problems:
        print("health check OK: no problems")
        return 0
    subject, body = build_report(problems, host, now)
    print(subject)
    print(body)
    if a.dry_run:
        return 0
    return 0 if send_alert(subject, body) else 1


if __name__ == "__main__":
    sys.exit(main())
