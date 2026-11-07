"""SU11A-70 honest visitor counts: only a browser's GET / HEAD of a page with
status 200 / 304 is a page view; everything else on a web host is counted as
rejected_requests (no paths); the admin console is its own API platform and
is left out of the dashboard total; the "don't count this browser" flag field
skips page views into internal_page_views; all three log shapes parse; a re-run
REPLACES a day (metrics that disappear do not linger); and nothing but counts
ever reaches the database.
    python -m pytest tests/test_stats_su11a70.py -q
"""
import datetime as dt
import json
from datetime import date

import pytest
from sqlalchemy import text

from db import stats as S
from scripts import stats_collect as C
from scripts import stats_logs as L
from tests.test_stats_su11a69 import (  # noqa: F401  (fixtures)
    IPS, SECRET_Q, TODAY, UA_CHROME, UA_GOOGLEBOT, UA_IPHONE_SAFARI, UA_OKHTTP, engine, rows_of, ts, val,
)

D1, D2 = date(2026, 11, 4), date(2026, 11, 5)
H = "super.xxl.co.il"
UA_PY = "python-requests/2.33.1"
UA_CURL = "curl/8.5.0"
UA_DART = "Dart/3.5 (dart:io)"
COOKIE_VALUE = "1; xxl_session=SECRETCOOKIE"


def ln(ip, when, req, status=200, ref="-", ua=UA_CHROME, host=H, flag=None):
    s = f'{ip} - - [{when}] "{req}" {status} 512 "{ref}" "{ua}"'
    if host is not None:
        s += f' "{host}"'
        if flag is not None:
            s += f' "{flag}"'
    return s + "\n"


def agg(lines, days=(D1,)):
    a = L.Aggregator(list(days))
    for x in lines:
        a.feed_web(x)
    return a, {(m, dim, d): v for m, dim, d, v in a.web_rows()}


# ------------------------------------------------------------------ A1 page rule
@pytest.mark.parametrize("line_kw,kind", [
    (dict(req="GET / HTTP/2.0"), "page"),
    (dict(req="HEAD / HTTP/1.1"), "page"),
    (dict(req="GET /promos HTTP/2.0", status=304), "page"),
    (dict(req="GET /old HTTP/2.0", status=301), "rejected"),
    (dict(req="GET /x HTTP/2.0", status=302), "rejected"),
    (dict(req="GET /wp-admin HTTP/1.1", status=404), "rejected"),
    (dict(req="GET /wp-login.php HTTP/1.1", status=200), "rejected"),
    (dict(req="GET /.env HTTP/1.1", status=200), "rejected"),
    (dict(req="GET /.git/config HTTP/1.1", status=403), "rejected"),
    (dict(req="GET / HTTP/2.0", status=500), "rejected"),
    (dict(req="GET / HTTP/2.0", status=206), "rejected"),
    (dict(req="POST /login HTTP/2.0"), "rejected"),
    (dict(req="GET / HTTP/1.1", ua=UA_CURL), "bot"),
    (dict(req="GET / HTTP/1.1", ua=UA_PY), "bot"),
    (dict(req="GET / HTTP/1.1", ua="-"), "bot"),
    (dict(req="GET / HTTP/1.1", ua=""), "bot"),
    (dict(req="GET / HTTP/1.1", ua=UA_GOOGLEBOT), "bot"),
    (dict(req="GET / HTTP/1.1", ua=UA_DART), "rejected"),  # not a browser, not a known bot
    (dict(req="GET / HTTP/1.1", ua=UA_OKHTTP), "rejected"),
    (dict(req="GET /assets/index-abc.js HTTP/2.0"), "asset"),
    (dict(req="GET /favicon.ico HTTP/2.0", status=304), "asset"),
    (dict(req="GET /sitemap-super.xml HTTP/2.0"), "asset"),
    (dict(req="GET /assets/gone.js HTTP/2.0", status=404), "rejected"),
])
def test_page_rule(line_kw, kind):
    a, r = agg([ln(IPS[0], ts(D1), **line_kw)])
    got = {"page": r.get(("page_views", H, D1), 0), "bot": r.get(("bot_page_views", H, D1), 0),
           "rejected": r.get(("rejected_requests", H, D1), 0)}
    want = {k: (1 if k == kind else 0) for k in got}
    assert got == want, (line_kw, r)


def test_rejected_has_no_paths_and_other_bucket_is_real_pages():
    lines = [ln(IPS[1], ts(D1), f"GET /wp-admin/{SECRET_Q} HTTP/1.1", status=404),
             ln(IPS[1], ts(D1), "GET /.env HTTP/1.1"),
             ln(IPS[0], ts(D1), "GET /some-unlisted-page HTTP/2.0"),
             ln(IPS[0], ts(D1), "GET /categories/D02.C02.S01 HTTP/2.0"),
             ln(IPS[0], ts(D1), "GET /categories/X99 HTTP/2.0")]
    _, r = agg(lines)
    assert r[("rejected_requests", H, D1)] == 2
    assert r[("top_path", f"{H}/(other)", D1)] == 2      # an unlisted page and a bad category id
    assert r[("top_path", f"{H}/categories/D02.C02.S01", D1)] == 1
    assert not [k for k in r if "wp-admin" in k[1] or ".env" in k[1] or SECRET_Q in k[1]]


def test_routes_allowlist_matches_the_web_routes():
    """Every literal route in web/src/App.tsx is in ROUTES; the category family
    matches the web's CATEGORY_PATH."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "web" / "src"
    app = (root / "App.tsx").read_text(encoding="utf-8")
    routes = set(re.findall(r'path="(/[^"*:]*)"', app))
    assert routes and routes <= set(L.ROUTES), routes - set(L.ROUTES)
    seo = (root / "utils" / "seoMeta.ts").read_text(encoding="utf-8")
    assert r"CATEGORY_PATH = /^\/categories\/D\d{2}(\.C\d{2}(\.S\d{2})?)?$/" in seo
    for ok in ("/categories/D01", "/categories/D01.C02", "/categories/D01.C02.S03"):
        assert L.route_path(ok) == ok
    for bad in ("/categories/D1", "/categories/D01.X02", "/categories/D01.C02.S03.Z01", "/categories/d01"):
        assert L.route_path(bad) == L.OTHER_ROUTE


# ------------------------------------------------------------------- A2 admin platform
def test_admin_platform_before_web():
    assert L.platform(UA_CHROME, "https://admin.xxl.co.il/#stats") == "admin"
    assert L.platform(UA_CHROME, "https://super.xxl.co.il/") == "web"
    assert L.platform(UA_OKHTTP, "https://admin.xxl.co.il/") == "android"  # the apps never send that Referer
    a = L.Aggregator([D1])
    for x in (ln(IPS[0], ts(D1), "GET /admin/stats?days=30 HTTP/2.0", ref="https://admin.xxl.co.il/", host=None),
              ln(IPS[0], ts(D1), "GET /categories/tree HTTP/2.0", ref="https://admin.xxl.co.il/", host=None),
              ln(IPS[0], ts(D1), "GET /search?q=a HTTP/2.0", ref="https://super.xxl.co.il/", host=None)):
        a.feed_api(x)
    assert dict(((m, d), v) for m, d, _day, v in a.api_rows()) == {("calls", "admin"): 2, ("calls", "web"): 1}


def test_dashboard_total_leaves_admin_out(engine):
    with engine.begin() as c:
        S.replace_days(c, "api", [D2], [("calls", "android", D2, 40), ("calls", "web", D2, 60),
                                         ("calls", "admin", D2, 900)])
        S.replace_days(c, "web", [D2], [("page_views", H, D2, 7), ("visitors", H, D2, 3)])
    with engine.connect() as c:
        assert S.latest_summary(c)["api"] == {"day": "2026-11-05", "calls": 100}


# ------------------------------------------------------------------- A3 internal flag
def test_three_line_shapes_parse():
    old = L.parse_line(ln(IPS[0], ts(D1), "GET / HTTP/2.0", host=None))
    host = L.parse_line(ln(IPS[0], ts(D1), "GET / HTTP/2.0"))
    flag = L.parse_line(ln(IPS[0], ts(D1), "GET / HTTP/2.0", flag="1"))
    dash = L.parse_line(ln(IPS[0], ts(D1), "GET / HTTP/2.0", flag="-"))
    assert (old.host, old.internal) == (None, False)
    assert (host.host, host.internal) == (H, False)
    assert (flag.host, flag.internal) == (H, True)
    assert (dash.host, dash.internal) == (H, False)
    # Anything but exactly "1" is not the flag (nginx's map only writes "1" or "-").
    assert L.parse_line(ln(IPS[0], ts(D1), "GET / HTTP/2.0", flag="yes")).internal is False


def test_flagged_page_views_are_skipped_and_counted():
    lines = [
        ln(IPS[0], ts(D1, 9), "GET / HTTP/2.0", flag="1", ref="https://www.google.com/"),
        ln(IPS[0], ts(D1, 9), "GET /promos HTTP/2.0", flag="1"),
        ln(IPS[0], ts(D1, 9), "GET /assets/a.js HTTP/2.0", flag="1"),          # asset: nothing
        ln(IPS[0], ts(D1, 9), "GET /wp-admin HTTP/2.0", status=404, flag="1"),  # still rejected
        ln(IPS[1], ts(D1, 10), "GET /promos HTTP/2.0", flag="-"),
        ln(IPS[2], ts(D1, 10), "GET / HTTP/2.0"),                              # host-only line
        ln(IPS[2], ts(D1, 10), "GET / HTTP/2.0", ua=UA_GOOGLEBOT, flag="1"),   # a bot stays a bot
    ]
    _, r = agg(lines)
    assert r[("internal_page_views", H, D1)] == 2
    assert r[("page_views", H, D1)] == 2 and r[("visitors", H, D1)] == 2
    assert r[("bot_page_views", H, D1)] == 1 and r[("rejected_requests", H, D1)] == 1
    assert r[("top_path", f"{H}/promos", D1)] == 1 and r[("top_path", f"{H}/", D1)] == 1
    assert ("referrer", f"{H}|google.com", D1) not in r


# ------------------------------------------------------------- A4 replace per day
def test_rerun_replaces_the_day(engine, tmp_path, monkeypatch, capsys):
    log = tmp_path / "access.log"
    early = ln(IPS[0], ts(date(2026, 11, 3), 23), "GET / HTTP/2.0")
    log.write_text(early + ln(IPS[0], ts(D1), "GET / HTTP/2.0") + ln(IPS[0], ts(D1), "GET /.env HTTP/1.1")
                   + ln(IPS[1], ts(D1), "GET / HTTP/2.0", flag="1"), encoding="utf-8")
    monkeypatch.setenv("stats_web_logs", str(log))
    assert C.run_source(engine, "web", today=date(2026, 11, 5), days=1, dry_run=False) == "ok"
    first = {(m, d): v for _s, m, d, _day, v in rows_of(engine, "web")}
    assert first[("rejected_requests", H)] == 1 and first[("internal_page_views", H)] == 1
    # The same day again after the logs changed: metrics that are gone are gone.
    log.write_text(early + ln(IPS[0], ts(D1), "GET / HTTP/2.0") + ln(IPS[2], ts(D1), "GET /promos HTTP/2.0"),
                   encoding="utf-8")
    assert C.run_source(engine, "web", today=date(2026, 11, 5), days=1, dry_run=False) == "ok"
    second = {(m, d): v for _s, m, d, _day, v in rows_of(engine, "web")}
    assert ("rejected_requests", H) not in second and ("internal_page_views", H) not in second
    assert second[("page_views", H)] == 2
    out = capsys.readouterr().out
    assert "stored" in out


def test_days_flag_bounds():
    with pytest.raises(SystemExit):
        C.main(["--days", "15"])
    with pytest.raises(SystemExit):
        C.main(["--days", "0"])


# ------------------------------------------------------------------- A5 privacy guard
def test_new_field_never_reaches_the_db(engine, tmp_path, monkeypatch, capsys):
    log = tmp_path / "access.log"
    lines = [ln(IPS[0], ts(date(2026, 11, 3), 23), "GET / HTTP/2.0")]
    for i, ip in enumerate(IPS):
        lines += [ln(ip, ts(D1, 8 + i), f"GET /?q={SECRET_Q} HTTP/2.0", ua=UA_IPHONE_SAFARI, flag="1"),
                  ln(ip, ts(D1, 8 + i), f"GET /search/{SECRET_Q} HTTP/2.0", status=404, flag="-"),
                  ln(ip, ts(D1, 8 + i), "GET /promos HTTP/2.0", ua=UA_DART),
                  ln(ip, ts(D1, 8 + i), "GET /promos HTTP/2.0", flag=COOKIE_VALUE)]
    log.write_text("".join(lines), encoding="utf-8")
    monkeypatch.setenv("stats_web_logs", str(log))
    engine.captured.clear()
    assert C.run_source(engine, "web", today=date(2026, 11, 5), days=1, dry_run=False) == "ok"
    out = capsys.readouterr().out
    sent = json.dumps([[str(p) for p in (params.values() if isinstance(params, dict) else params or [])]
                       for _s, params in engine.captured], default=str)
    blob = sent + out + json.dumps(rows_of(engine), default=str)
    for bad in (*IPS, UA_IPHONE_SAFARI, UA_DART, "Mozilla", "Dart", SECRET_Q, "?q=", "SECRETCOOKIE", "xxl_session"):
        assert bad not in blob, bad
    r = {(m, d): v for _s, m, d, _day, v in rows_of(engine, "web")}
    assert r[("internal_page_views", H)] == 4 and r[("rejected_requests", H)] == 8
    # A malformed flag field is just "not internal": one page view per IP (the
    # early line is the day before).
    assert r[("page_views", H)] == 4
