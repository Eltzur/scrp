"""Daily statistics collector for the admin console (SU11A-69).

    python3 -m scripts.stats_collect                  # all sources, the days still missing
    python3 -m scripts.stats_collect --sources web,api --days 7
    python3 -m scripts.stats_collect --dry-run        # count and print, write nothing
    python3 -m scripts.stats_collect --asc-request-analytics --admin-key-file F --admin-key-id ID

Run by scrp-stats.timer at 03:30 Israel time (deploy/systemd/scrp-stats.*) as
dude with SupplementaryGroups=adm, the least privilege that reads
/var/log/nginx (www-data:adm, 0640). Settings come from the unit's
EnvironmentFile (~/scrp/.env); this script never reads .env itself.

Which days:
  web / api (nginx logs)  the days after the last stored one, up to yesterday,
                          at most 7 (the first run backfills 7 from whatever the
                          14-day log rotation still holds). A day the logs do not
                          reach back to the start of is partial and is skipped,
                          never stored.
  ga4 / play / appstore   the last 7 days again on every run (their numbers move
                          for a few days); upserted.

Output and storage are COUNTS ONLY: no IP, user agent, URL, query string,
token or key is printed, logged or stored (CLAUDE.md; tests/test_stats_su11a69.py).
One transaction per source: one failing source never blocks the others. Exit 1
when a source errored (not_configured is not an error).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

from sqlalchemy import text

from db import stats as S
from scripts import stats_logs as L
from scripts import stats_sources as X

LOG_DEFAULTS = {
    "web": "/var/log/nginx/access.log*",
    "api": "/var/log/nginx/api-super.access.log*",
}
LOG_ENV = {"web": "stats_web_logs", "api": "stats_api_logs"}
MAX_LOG_DAYS = 7
API_DAYS = 7
ALL = ("web", "api", "ga4", "play", "appstore")


def today_il() -> date:
    return datetime.now(L.IL).date()


def _as_of(conn, source: str) -> date | None:
    v = conn.execute(text("SELECT as_of FROM stats_runs WHERE source = :s AND as_of IS NOT NULL"),
                     {"s": source}).scalar()
    if isinstance(v, str):
        v = date.fromisoformat(v[:10])
    return v


def log_days(conn, source: str, today: date, days: int | None) -> list[date]:
    if days:
        return L.days_back(today, days)
    last = _as_of(conn, source)
    yesterday = today - timedelta(days=1)
    if last is None:
        return L.days_back(today, MAX_LOG_DAYS)
    start = max(last + timedelta(days=1), today - timedelta(days=MAX_LOG_DAYS))
    return [start + timedelta(days=i) for i in range((yesterday - start).days + 1)]


def collect_logs(source: str, days: list[date], patterns: list[str]) -> tuple[list, list[date], dict]:
    """(rows, covered days, info) for web or api."""
    agg = L.Aggregator(days)
    info: dict = {}
    files = L.log_files(patterns)
    info["files"] = len(files)
    not_before = L.day_start(min(days)) if days else None
    feed = agg.feed_web if source == "web" else agg.feed_api
    for raw in L.read_lines(files, not_before=not_before, stats=info):
        feed(raw)
    skipped_old = info.get("files_skipped_old", 0) > 0
    covered = [d for d in days if agg.covered(d, skipped_old)]
    rows = agg.web_rows() if source == "web" else agg.api_rows()
    rows = [r for r in rows if r[2] in covered]
    info.update({k: v for k, v in agg.counts.items()})
    info["partial_days"] = [d.isoformat() for d in days if d not in covered]
    if source == "web" and agg.visitors_capped():
        info["visitors_capped"] = True
    return rows, covered, info


def _summary(source: str, rows: list) -> list[str]:
    """Counts per day for the run output (never a path or a referrer)."""
    out: dict[tuple[date, str], int] = {}
    for metric, dim, day, value in rows:
        if metric in ("top_path", "referrer"):
            continue
        key = (day, f"{metric}[{dim}]" if dim else metric)
        out[key] = out.get(key, 0) + value
    days = sorted({d for d, _ in out})
    return [f"  {d.isoformat()} " + " ".join(f"{k}={v}" for (dd, k), v in sorted(out.items()) if dd == d)
            for d in days]


def run_source(engine, source: str, *, today: date, days: int | None, dry_run: bool,
               http=None) -> str:
    """Collect one source in its own transaction. Returns ok | error | not_configured."""
    print(f"[{source}]")
    try:
        with engine.connect() as conn:
            if source in ("web", "api"):
                want = log_days(conn, source, today, days)
            else:
                want = L.days_back(today, days or API_DAYS)
            conn.rollback()
        if not want:
            print("  nothing to do (already up to date)")
            if not dry_run:
                with engine.begin() as conn:
                    S.record_run(conn, source, "ok", note="up to date")
            return "ok"

        note = None
        if source in ("web", "api"):
            pats = [p.strip() for p in (X.env(LOG_ENV[source]) or LOG_DEFAULTS[source]).split(",") if p.strip()]
            rows, covered, info = collect_logs(source, want, pats)
            if info["files"] == 0:
                raise X.SourceError("no log files found (check the path and the adm group)")
            print(f"  files={info['files']} read={info.get('files_read', 0)} lines={info.get('lines', 0)} "
                  f"unparsed={info.get('unparsed', 0)}"
                  + (f" no_host={info.get('no_host', 0)} admin={info.get('excluded_host', 0)} "
                     f"other_host={info.get('other_host', 0)}" if source == "web" else ""))
            if info["partial_days"]:
                print("  partial (not stored): " + ", ".join(info["partial_days"]))
                note = "partial days skipped: " + ", ".join(info["partial_days"])
            if source == "web" and info.get("no_host"):
                note = ((note + "; ") if note else "") + "lines without $host (see runbook step 5)"
            if info.get("visitors_capped"):
                note = ((note + "; ") if note else "") + f"visitors capped at {L.VISITOR_CAP}"
            write = lambda conn: S.replace_days(conn, source, covered, rows)  # noqa: E731
            as_of = max(covered) if covered else None
        else:
            fetch = {"ga4": X.ga4_fetch, "play": X.play_fetch, "appstore": X.asc_fetch}[source]
            try:
                {"ga4": X.ga4_configured, "play": X.play_configured, "appstore": X.asc_configured}[source]()
            except X.NotConfigured as exc:
                print(f"  not connected ({exc})")
                if not dry_run:
                    with engine.begin() as conn:
                        S.record_run(conn, source, "not_configured", note=str(exc))
                return "not_configured"
            got = fetch(want, http=http) if source != "appstore" else fetch(want, http=http, today=today)
            rows, as_of = got[0], got[1]
            if source == "appstore" and got[2]:
                note = got[2]
                print("  analytics report request missing (runbook: Connect later, App Store, step 5)")
            write = lambda conn: S.upsert(conn, source, rows)  # noqa: E731

        for line in _summary(source, rows):
            print(line)
        if dry_run:
            print(f"  dry run: {len(rows)} rows not written")
            return "ok"
        with engine.begin() as conn:
            n = write(conn)
            S.record_run(conn, source, "ok", as_of=as_of, note=note)
        print(f"  stored {n} rows, as of {as_of.isoformat() if as_of else '-'}")
        return "ok"
    except Exception as exc:  # one source never stops the others
        msg = X.safe_error(exc)
        print(f"  ERROR {msg}")
        if not dry_run:
            try:
                with engine.begin() as conn:
                    S.record_run(conn, source, "error", error=msg)
            except Exception as exc2:
                print(f"  (could not record the error: {type(exc2).__name__})")
        return "error"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sources", default=",".join(ALL))
    ap.add_argument("--days", type=int, default=None, help="days back from yesterday (1-14)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--asc-request-analytics", action="store_true",
                    help="one-time: create the App Store Analytics Reports request (needs an Admin key)")
    ap.add_argument("--admin-key-file")
    ap.add_argument("--admin-key-id")
    a = ap.parse_args(argv)

    if a.asc_request_analytics:
        if not (a.admin_key_file and a.admin_key_id):
            ap.error("--asc-request-analytics needs --admin-key-file and --admin-key-id")
        try:
            print("analytics report request: " + X.asc_request_analytics(a.admin_key_file, a.admin_key_id))
            return 0
        except Exception as exc:
            print("ERROR " + X.safe_error(exc))
            return 1

    if a.days is not None and not 1 <= a.days <= 14:
        ap.error("--days must be 1-14 (nginx keeps 14 days)")
    sources = [s.strip() for s in a.sources.split(",") if s.strip()]
    bad = [s for s in sources if s not in ALL]
    if bad:
        ap.error("unknown source: " + ", ".join(bad))

    from db.db import get_engine
    engine = get_engine()
    today = today_il()
    results = {s: run_source(engine, s, today=today, days=a.days, dry_run=a.dry_run) for s in sources}
    print("result: " + " ".join(f"{s}={r}" for s, r in results.items()))
    return 1 if "error" in results.values() else 0


if __name__ == "__main__":
    sys.exit(main())
