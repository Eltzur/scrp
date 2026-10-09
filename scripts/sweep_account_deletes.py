"""Retry pending Supabase auth deletes and purge completed rows (SU11A-28).

    python3 -m scripts.sweep_account_deletes --dry-run
    python3 -m scripts.sweep_account_deletes

(a) Every deleted_accounts row with auth_deleted_at IS NULL: one call to the
    Supabase admin API (api.supabase_admin.delete_auth_user), recording
    auth_deleted_at on success or attempts + 1 / last_error on failure.
(b) Rows whose auth_deleted_at is older than PURGE_AFTER_DAYS are deleted.
--dry-run prints what it would do and calls nothing.

NOT scheduled in SU11A-28 — no systemd timer or cron wiring yet.
Output carries user ids, counts and short error codes only; never the admin key.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

from sqlalchemy import text

PURGE_AFTER_DAYS = 7

PENDING_SQL = text(
    "SELECT CAST(user_id AS TEXT) AS user_id, attempts FROM deleted_accounts "
    "WHERE auth_deleted_at IS NULL ORDER BY requested_at"
)
PURGE_COUNT_SQL = text(
    "SELECT count(*) FROM deleted_accounts "
    "WHERE auth_deleted_at IS NOT NULL AND auth_deleted_at < :cutoff"
)
PURGE_SQL = text(
    "DELETE FROM deleted_accounts "
    "WHERE auth_deleted_at IS NOT NULL AND auth_deleted_at < :cutoff"
)


def purge_cutoff(now: dt.datetime | None = None) -> dt.datetime:
    now = now or dt.datetime.now(dt.timezone.utc)
    return now - dt.timedelta(days=PURGE_AFTER_DAYS)


def sweep(conn, dry_run: bool = False, now: dt.datetime | None = None, out=print) -> dict:
    from api.routers.account import finish_auth_delete

    pending = [(r.user_id, r.attempts) for r in conn.execute(PENDING_SQL)]
    cutoff = purge_cutoff(now)
    stale = conn.execute(PURGE_COUNT_SQL, {"cutoff": cutoff}).scalar() or 0

    report = {"pending": len(pending), "retried_ok": 0, "retried_failed": 0, "purged": 0}
    if dry_run:
        for uid, attempts in pending:
            out(f"would retry auth delete user_id={uid} (attempts so far {attempts})")
        out(f"would purge {stale} completed row(s) older than {PURGE_AFTER_DAYS} days")
        conn.rollback()
        return report

    for uid, _ in pending:
        ok, err = finish_auth_delete(conn, uid)
        if ok:
            report["retried_ok"] += 1
            out(f"auth delete done user_id={uid}")
        else:
            report["retried_failed"] += 1
            out(f"auth delete still pending user_id={uid} error={err}")

    report["purged"] = conn.execute(PURGE_SQL, {"cutoff": cutoff}).rowcount or 0
    conn.commit()
    out(f"purged {report['purged']} completed row(s)")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="print what would happen; change nothing")
    args = ap.parse_args(argv)

    from db.db import connect

    with connect() as conn:
        report = sweep(conn, dry_run=args.dry_run)
    print(report)
    return 1 if report["retried_failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
