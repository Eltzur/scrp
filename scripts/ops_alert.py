"""SU11A-82 (SU11A-79 H2): mail info@xxl.co.il when a systemd unit failed.

Run by the template unit xxl-alert@.service, which every scrp-* service names
in OnFailure= (drop-ins in deploy/systemd/dropins/). The instance name is the
failed unit, e.g. xxl-alert@scrp-backup.service.service -> --unit scrp-backup.service.

    python3 -m scripts.ops_alert --unit scrp-backup.service
    python3 -m scripts.ops_alert --unit scrp-backup.service --dry-run   # print, no mail

Subject "[XXL] <unit> failed on scrp-prod-il"; body: a hint for known cases,
the unit's state and the last 30 journal lines, all through ops_common.redact().
Exit 0 = mailed (or dry run), 1 = the mail could not be sent (the journal
keeps the lines; xxl-alert@ itself has no OnFailure, so there is no loop).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

from scripts.ops_common import host_label, redact, send_alert

JOURNAL_LINES = 30
_UNIT_RE = re.compile(r"^[A-Za-z0-9@_.:\\-]{1,200}$")

# Known failures that are not bugs (CLAUDE.md), named in the mail so nobody
# chases them at night.
HINTS = {
    "scrp-gs1-fetch.service": "A failure with 'media endpoint blocking' is the GS1 circuit breaker working, "
                              "not a bug; the next Sunday resumes.",
    "scrp-backup.service": "No new off-site backup today. Check the journal below, then run "
                           "`sudo systemctl start scrp-backup.service` once the cause is fixed.",
    "scrp-cron.service": "The daily price load failed or stopped early; prices may be stale until the next run.",
    "xxl-health-check.service": "The daily health check itself crashed; its problems were not mailed.",
}


def subject_for(unit: str, host: str) -> str:
    return f"[XXL] {unit} failed on {host}"


def run(cmd: list[str]) -> str:
    """Run a read-only command; its output, or a short note if it failed."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        return (r.stdout or "").strip() or (r.stderr or "").strip()[:300]
    except Exception as exc:  # noqa: BLE001 - an alert must still go out
        return f"({cmd[0]} not available: {type(exc).__name__})"


def unit_state(unit: str) -> str:
    return run(["systemctl", "show", unit, "--no-pager",
                "-p", "Result", "-p", "ExecMainStatus", "-p", "ActiveEnterTimestamp", "-p", "InactiveEnterTimestamp"])


def journal_tail(unit: str, lines: int = JOURNAL_LINES) -> str:
    return run(["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "short-iso"])


def build_body(unit: str, host: str, state: str, journal: str) -> str:
    parts = [f"{unit} failed on {host}.", ""]
    if unit in HINTS:
        parts += [HINTS[unit], ""]
    parts += ["State:", state or "(unknown)", "", f"Last {JOURNAL_LINES} journal lines:", journal or "(none)", "",
              "Sent by xxl-alert@.service (scripts/ops_alert.py, SU11A-82)."]
    return redact("\n".join(parts))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--unit", required=True)
    ap.add_argument("--dry-run", action="store_true", help="print the mail, send nothing")
    a = ap.parse_args(argv)
    if not _UNIT_RE.match(a.unit):
        print("refusing an odd unit name", file=sys.stderr)
        return 2
    host = host_label()
    subject = subject_for(a.unit, host)
    body = build_body(a.unit, host, unit_state(a.unit), journal_tail(a.unit))
    if a.dry_run:
        print(subject)
        print(body)
        return 0
    if send_alert(subject, body):
        print(f"alert mailed: {subject}")
        return 0
    print(f"alert NOT mailed (see the mailer warning above): {subject}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
