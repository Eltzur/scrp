"""SU11A-69 admin statistics: the nginx log parser, the platform split, the
visitor estimate, the privacy guarantee (nothing but counts reaches the
database or the output), idempotent re-runs, the credentialed sources
(GA4 / Play / App Store) with fake HTTP, and GET /admin/stats behind the
admin + 2FA gate.

SQLite stands in for Postgres here (tests/test_stats_su11a69_pg.py runs the
real migration).
    python -m pytest tests/test_stats_su11a69.py -q
"""
import datetime as dt
import gzip
import io
import json
import os
import sqlite3
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

import api.auth as auth
import api.routers.admin_stats as AS
from api.dependencies import get_db
from api.main import app
from db import stats as S
from scripts import stats_collect as C
from scripts import stats_logs as L
from scripts import stats_sources as X

sqlite3.register_adapter(date, lambda d: d.isoformat())
sqlite3.register_adapter(dt.datetime, lambda d: d.isoformat())

SCHEMA = [
    "CREATE TABLE stats_daily (source TEXT NOT NULL, metric TEXT NOT NULL, dimension TEXT NOT NULL DEFAULT '', "
    "day DATE NOT NULL, value INTEGER NOT NULL, updated_at TEXT, PRIMARY KEY (source, metric, dimension, day))",
    "CREATE TABLE stats_runs (source TEXT PRIMARY KEY, status TEXT NOT NULL, last_run_at TEXT, "
    "last_success_at TEXT, last_error_at TEXT, last_error TEXT, as_of DATE, note TEXT)",
]

# Personal / sensitive bits that must never leave the parser.
IPS = ["203.0.113.7", "198.51.100.23", "2001:db8::1", "192.0.2.44"]
UA_CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
UA_IPHONE_SAFARI = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
                    "(KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1")
UA_GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
UA_OKHTTP = "okhttp/4.12.0"
UA_IOS_APP = "SUPER%20XXL/2 CFNetwork/1568.200.51 Darwin/24.1.0"
UA_IOS_IMG = "SUPER XXL/1.2.2 (iPhone; iOS 18.1; Scale/3.00)"
SECRET_Q = "secretsearch"


def ts(d: date, h=12, m=0):
    return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=dt.timezone(dt.timedelta(hours=2))) \
        .strftime("%d/%b/%Y:%H:%M:%S %z")


def line(ip, when, req, status=200, ref="-", ua=UA_CHROME, host="super.xxl.co.il"):
    s = f'{ip} - - [{when}] "{req}" {status} 512 "{ref}" "{ua}"'
    return s + (f' "{host}"' if host is not None else "") + "\n"


D1, D2 = date(2026, 11, 4), date(2026, 11, 5)
TODAY = date(2026, 11, 6)


def web_lines():
    out = [
        # day 1: a person loads the home page with a search query + assets
        line(IPS[0], ts(D1, 9), f"GET /?q={SECRET_Q}&city=x HTTP/2.0", ref="https://www.google.com/search?q=x"),
        line(IPS[0], ts(D1, 9), "GET /assets/index-abc.js HTTP/2.0", ref="https://super.xxl.co.il/"),
        line(IPS[0], ts(D1, 9), "GET /favicon.ico HTTP/2.0"),
        line(IPS[0], ts(D1, 9, 5), "GET /categories/D02 HTTP/2.0", ref="https://super.xxl.co.il/"),
        line(IPS[0], ts(D1, 9, 6), "GET /categories/D02 HTTP/2.0", status=304, ref="https://super.xxl.co.il/"),
        # same IP, other browser = another visitor
        line(IPS[0], ts(D1, 10), "GET /promos HTTP/2.0", ua=UA_IPHONE_SAFARI, ref="https://l.facebook.com/x?fbclid=1"),
        line(IPS[1], ts(D1, 11), "GET /promos HTTP/2.0", ref="-"),
        # bot, admin, POST, 404 junk with extension, probe, other host
        line(IPS[2], ts(D1, 11), "GET /categories HTTP/1.1", ua=UA_GOOGLEBOT),
        line(IPS[3], ts(D1, 12), "GET / HTTP/2.0", host="admin.xxl.co.il"),
        line(IPS[3], ts(D1, 12), "POST /login HTTP/2.0"),
        line(IPS[3], ts(D1, 12), "GET /wp-login.php HTTP/1.1", status=404),
        line(IPS[3], ts(D1, 12), "GET /.env HTTP/1.1"),
        line(IPS[3], ts(D1, 12), "GET / HTTP/1.1", host="185.229.226.190"),
        line(IPS[1], ts(D1, 13), "GET / HTTP/2.0", host="xxl.co.il"),
        line(IPS[1], ts(D1, 13), "GET / HTTP/2.0", host="fly.xxl.co.il", ref="https://xxl.co.il/"),
        # day 2
        line(IPS[1], ts(D2, 8), f"GET /search/{SECRET_Q}?q={SECRET_Q} HTTP/2.0"),
        line(IPS[1], ts(D2, 8), "GET /product/7290004131074 HTTP/2.0"),
        "garbage line that is not nginx\n",
        # today: never counted
        line(IPS[0], ts(TODAY, 1), "GET / HTTP/2.0"),
    ]
    return out


def api_lines():
    return [
        line(IPS[0], ts(D1, 9), f"GET /search?q={SECRET_Q} HTTP/2.0", ua=UA_CHROME, ref="https://super.xxl.co.il/",
             host=None),
        line(IPS[0], ts(D1, 9), "OPTIONS /basket HTTP/2.0", ua=UA_CHROME, ref="https://super.xxl.co.il/", host=None),
        line(IPS[1], ts(D1, 9), f"GET /search?q={SECRET_Q} HTTP/1.1", ua=UA_OKHTTP, host=None),
        line(IPS[1], ts(D1, 9), "GET /product/7290004131074/image HTTP/1.1", ua=UA_OKHTTP, status=502, host=None),
        line(IPS[2], ts(D1, 9), "GET /cities HTTP/1.1", ua=UA_IOS_APP, host=None),
        line(IPS[2], ts(D1, 9), "GET /product/7290004131074/image HTTP/1.1", ua=UA_IOS_IMG, host=None),
        line(IPS[3], ts(D1, 9), "GET /admin/status HTTP/2.0", ua=UA_CHROME, ref="https://admin.xxl.co.il/", host=None),
        line(IPS[3], ts(D1, 9), "GET /categories/tree HTTP/2.0", ua=UA_CHROME, ref="https://admin.xxl.co.il/",
             host=None),
        line(IPS[3], ts(D1, 9), "GET /health HTTP/1.1", ua="curl/8.5.0", host=None),
        line(IPS[3], ts(D1, 9), "GET /search?q=a HTTP/1.1", ua="python-requests/2.33", host=None),
        line(IPS[3], ts(D1, 9), "GET /search?q=a HTTP/1.1", ua="Mozilla/5.0 something", host=None),
        line(IPS[0], ts(D2, 9), "GET /promos/today HTTP/1.1", ua=UA_OKHTTP, host=None),
    ]


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with eng.begin() as c:
        for ddl in SCHEMA:
            c.execute(text(ddl))
    eng.captured = []

    @event.listens_for(eng, "before_cursor_execute")
    def _capture(_c, _cur, statement, params, _ctx, _many):
        eng.captured.append((statement, params))
    return eng


@pytest.fixture
def logs(tmp_path, monkeypatch):
    """access.log (+ a rotated .1 and a .2.gz) and api-super.access.log."""
    wl = web_lines()
    (tmp_path / "access.log.1").write_text("".join(wl[:8]), encoding="utf-8")
    with gzip.open(tmp_path / "access.log.2.gz", "wt", encoding="utf-8") as f:
        f.write("".join(wl[8:15]))
    (tmp_path / "access.log").write_text("".join(wl[15:]), encoding="utf-8")
    (tmp_path / "api-super.access.log").write_text("".join(api_lines()), encoding="utf-8")
    # The oldest file reaches back before D1 starts: an older line in it.
    with open(tmp_path / "access.log.1", "a", encoding="utf-8") as f:
        f.write(line(IPS[0], ts(date(2026, 11, 3), 23), "GET / HTTP/2.0"))
    with open(tmp_path / "api-super.access.log", "a", encoding="utf-8") as f:
        f.write(line(IPS[0], ts(date(2026, 11, 3), 23), "GET /cities HTTP/2.0", ua=UA_OKHTTP, host=None))
    monkeypatch.setenv("stats_web_logs", str(tmp_path / "access.log*"))
    monkeypatch.setenv("stats_api_logs", str(tmp_path / "api-super.access.log*"))
    return tmp_path


def rows_of(engine, source=None):
    with engine.connect() as c:
        q = "SELECT source, metric, dimension, day, value FROM stats_daily"
        rs = c.execute(text(q + (" WHERE source = :s" if source else "") + " ORDER BY 1,2,3,4"),
                       {"s": source} if source else {}).all()
    return [tuple(r) for r in rs]


def val(rows, metric, dim, day):
    m = [r[4] for r in rows if r[1] == metric and r[2] == dim and str(r[3]) == day.isoformat()]
    return m[0] if m else None


# ----------------------------------------------------------------- parser units
def test_page_asset_api_classification():
    assert L.is_page("GET", "/", 200) and L.is_page("GET", "/categories/D02", 304)
    assert not L.is_page("GET", "/assets/index.js", 200)
    for p in ("/favicon.ico", "/sitemap-super.xml", "/robots.txt", "/wp-login.php", "/manifest.webmanifest"):
        assert not L.is_page("GET", p, 200), p
    assert not L.is_page("POST", "/login", 200)
    assert not L.is_page("GET", "/x", 404)
    assert not L.is_page("GET", "/.env", 200) and not L.is_page("GET", "/.git/config", 200)
    assert L.clean_path(f"/search?q={SECRET_Q}") == "/search"
    assert L.clean_path("/a#frag") == "/a" and L.clean_path("/a;jsessionid=1") == "/a"
    assert L.clean_path("/u/0541234567") == "/u/{n}"
    assert L.clean_path("/x/a@b.com") == "(other)" and L.clean_path("/" + "a" * 130) == "(other)"
    assert L.route_path("/promos/") == "/promos" and L.route_path("/categories/D02.C02") == "/categories/D02.C02"
    assert L.route_path(f"/search/{SECRET_Q}") == L.OTHER_ROUTE == L.route_path("/categories/x y")


def test_bots_and_platforms():
    assert L.is_bot(UA_GOOGLEBOT) and L.is_bot("-") and L.is_bot("") and L.is_bot("curl/8.5.0")
    assert not L.is_bot(UA_CHROME) and not L.is_bot(UA_OKHTTP) and not L.is_bot(UA_IOS_APP)
    assert L.platform(UA_OKHTTP, "-") == "android"
    assert L.platform("Dalvik/2.1.0 (Linux; U; Android 14)", "-") == "android"
    assert L.platform(UA_IOS_APP, "-") == "ios"
    assert L.platform(UA_IOS_IMG, "-") == "ios"
    assert L.platform(UA_CHROME, "https://super.xxl.co.il/promos") == "web"
    assert L.platform(UA_IPHONE_SAFARI, "https://xxl.co.il/") == "web"  # mobile Safari is the web, not the app
    assert L.platform(UA_CHROME, "https://admin.xxl.co.il/") == "admin"  # SU11A-70 (was: not counted)
    assert L.platform(UA_CHROME, "-") == "other"
    assert L.platform("Mozilla/5.0", "https://evil.example/") == "other"
    assert L.platform(UA_GOOGLEBOT, "-") == "bot"


def test_referrer_domain():
    assert L.referrer_domain("-") == L.DIRECT
    assert L.referrer_domain("https://www.google.com/search?q=milk") == "google.com"
    assert L.referrer_domain("https://super.xxl.co.il/x") is None
    assert L.referrer_domain("http://203.0.113.9/x") == "(ip)"


def test_visitor_estimate_is_deterministic_within_a_run_and_salt_free_in_count():
    a = L.Aggregator([D1])
    k1 = a.visitor_key(D1, IPS[0], UA_CHROME)
    assert k1 == a.visitor_key(D1, IPS[0], UA_CHROME)  # same person, same run
    assert k1 != a.visitor_key(D1, IPS[0], UA_IPHONE_SAFARI)
    b = L.Aggregator([D1])
    assert b.visitor_key(D1, IPS[0], UA_CHROME) != k1  # a new random salt per run
    lines = web_lines()
    for agg in (a, b):
        for raw in lines:
            agg.feed_web(raw)
    # ... but the stored COUNT is the same for every run.
    assert a.web_rows() == b.web_rows()
    assert not hasattr(a, "salt_file")


def test_aggregator_counts(logs):
    rows, covered, info = C.collect_logs("web", [D1, D2], [str(logs / "access.log*")])
    assert covered == [D1, D2] and info["files"] == 3 and info["unparsed"] == 1
    r = [("web", *x) for x in rows]
    assert val(r, "page_views", "super.xxl.co.il", D1) == 5     # /, /categories/D02 x2 (200 + 304), /promos x2
    assert val(r, "visitors", "super.xxl.co.il", D1) == 3       # ip0 chrome, ip0 safari, ip1
    assert val(r, "bot_page_views", "super.xxl.co.il", D1) == 1
    assert val(r, "page_views", "xxl.co.il", D1) == 1
    assert val(r, "page_views", "fly.xxl.co.il", D1) == 1
    assert val(r, "page_views", "super.xxl.co.il", D2) == 2
    assert not [x for x in r if "admin" in x[2] or "185.229" in x[2]]
    assert val(r, "top_path", "super.xxl.co.il/categories/D02", D1) == 2
    assert val(r, "top_path", "super.xxl.co.il/", D1) == 1
    assert val(r, "referrer", "super.xxl.co.il|google.com", D1) == 1
    assert val(r, "referrer", "super.xxl.co.il|l.facebook.com", D1) == 1
    assert val(r, "referrer", f"super.xxl.co.il|{L.DIRECT}", D1) == 1
    assert info["excluded_host"] == 1 and info["other_host"] == 1

    rows, _, _ = C.collect_logs("api", [D1, D2], [str(logs / "api-super.access.log*")])
    r = [("api", *x) for x in rows]
    assert val(r, "calls", "web", D1) == 1          # OPTIONS left out
    assert val(r, "calls", "admin", D1) == 2        # SU11A-70: the admin console has its own row
    assert val(r, "calls", "android", D1) == 2
    assert val(r, "errors_5xx", "android", D1) == 1
    assert val(r, "calls", "ios", D1) == 2
    assert val(r, "calls", "bot", D1) == 1          # python-requests (curl /health is skipped)
    assert val(r, "calls", "other", D1) == 1
    assert val(r, "calls", "android", D2) == 1


def test_lines_without_host_count_as_unknown():
    a = L.Aggregator([D1])
    a.feed_web(line(IPS[0], ts(D1), "GET / HTTP/2.0", host=None))
    a.feed_web(line(IPS[0], ts(D1), "GET /promos HTTP/2.0", host=None, ref="https://admin.xxl.co.il/"))
    assert ("page_views", L.UNKNOWN_HOST, D1, 1) in a.web_rows() and a.counts["no_host"] == 2


def test_partial_day_is_not_stored(tmp_path):
    # The logs start at 15:00 on D1: D1 is partial, D2 complete.
    p = tmp_path / "access.log"
    p.write_text(line(IPS[0], ts(D1, 15), "GET / HTTP/2.0") + line(IPS[0], ts(D2, 9), "GET / HTTP/2.0"))
    rows, covered, info = C.collect_logs("web", [D1, D2], [str(p)])
    assert covered == [D2] and info["partial_days"] == [D1.isoformat()]
    assert {r[2] for r in rows} == {D2}


def test_old_files_skipped_by_mtime(tmp_path):
    old = tmp_path / "access.log.9.gz"
    with gzip.open(old, "wt") as f:
        f.write(line(IPS[0], ts(date(2026, 10, 20)), "GET / HTTP/2.0"))
    t = time.mktime((2026, 10, 21, 0, 0, 0, 0, 0, -1))
    os.utime(old, (t, t))
    (tmp_path / "access.log").write_text(line(IPS[0], ts(D1, 15), "GET / HTTP/2.0"))
    rows, covered, info = C.collect_logs("web", [D1], [str(tmp_path / "access.log*")])
    assert info["files_skipped_old"] == 1 and covered == [D1]  # older files exist: the day is complete


def test_check_dimension_refuses_personal_data():
    for bad in ("203.0.113.7", "x 2001:db8::1 y", "/a?q=1", "https://x.y/", "a@b.c", "k=v", "a" * 201):
        with pytest.raises(S.UnsafeDimension):
            S.check_dimension(bad)
    for ok in ("super.xxl.co.il/categories/D02", "android", "super.xxl.co.il|google.com", "", "(direct)"):
        assert S.check_dimension(ok) == ok


# ------------------------------------------------------ the job end to end, privacy
def _run(engine, monkeypatch, capsys, sources=("web", "api"), days=None, **kw):
    for name in ("stats_google_key_file", "stats_ga4_property_id", "stats_play_bucket", *X.ASC_SETTINGS):
        monkeypatch.delenv(name, raising=False)
    res = {s: C.run_source(engine, s, today=TODAY, days=days, dry_run=False, **kw) for s in sources}
    return res, capsys.readouterr().out


def test_job_privacy_nothing_but_counts(engine, logs, monkeypatch, capsys):
    res, out = _run(engine, monkeypatch, capsys, sources=C.ALL, days=2)
    assert res == {"web": "ok", "api": "ok", "ga4": "not_configured", "play": "not_configured",
                   "appstore": "not_configured"}
    # Every value the job sent to the database, and everything it printed:
    sent = json.dumps([[str(p) for p in (params.values() if isinstance(params, dict) else params or [])]
                       for _s, params in engine.captured], default=str)
    blob = sent + out + json.dumps(rows_of(engine), default=str)
    for ip in IPS:
        assert ip not in blob, ip
    for ua in (UA_CHROME, UA_IPHONE_SAFARI, UA_GOOGLEBOT, UA_OKHTTP, UA_IOS_APP, UA_IOS_IMG,
               "Mozilla", "Chrome", "okhttp", "CFNetwork", "Googlebot"):
        assert ua not in blob, ua
    assert SECRET_Q not in blob and "?" not in json.dumps(rows_of(engine)) and "fbclid" not in blob
    assert "q=" not in sent and "search?" not in blob
    # Only these columns are ever written.
    for statement, _ in engine.captured:
        if statement.lstrip().upper().startswith("INSERT INTO STATS_DAILY"):
            assert "(source, metric, dimension, day, value, updated_at)" in statement
    with engine.connect() as c:
        st = dict(c.execute(text("SELECT source, status FROM stats_runs")).all())
    assert st == res


def test_job_is_idempotent(engine, logs, monkeypatch, capsys):
    _run(engine, monkeypatch, capsys, days=2)
    first = rows_of(engine)
    _run(engine, monkeypatch, capsys, days=2)
    assert rows_of(engine) == first and len(first) > 20
    # The next normal run (no --days) has nothing left to do: as_of = D2 = yesterday.
    res, out = _run(engine, monkeypatch, capsys, sources=("web",), days=None)
    assert res == {"web": "ok"} and "already up to date" in out
    assert rows_of(engine) == first


def test_first_run_backfills_and_then_only_new_days(engine):
    with engine.connect() as c:
        assert C.log_days(c, "web", TODAY, None) == L.days_back(TODAY, 7)
    with engine.begin() as c:
        S.record_run(c, "web", "ok", as_of=date(2026, 11, 4))
    with engine.connect() as c:
        assert C.log_days(c, "web", TODAY, None) == [date(2026, 11, 5)]
    with engine.begin() as c:
        S.record_run(c, "web", "ok", as_of=date(2026, 11, 5))
    with engine.connect() as c:
        assert C.log_days(c, "web", TODAY, None) == []
    with engine.begin() as c:  # a failure keeps as_of
        S.record_run(c, "web", "error", error="X")
        assert c.execute(text("SELECT as_of, status, last_error FROM stats_runs")).one()[:3] == \
            ("2026-11-05", "error", "X")


def test_replace_days_drops_stale_top_entries(engine):
    with engine.begin() as c:
        S.replace_days(c, "web", [D1], [("top_path", "super.xxl.co.il/a", D1, 5),
                                         ("page_views", "super.xxl.co.il", D1, 5)])
        S.replace_days(c, "web", [D1], [("top_path", "super.xxl.co.il/b", D1, 4),
                                         ("page_views", "super.xxl.co.il", D1, 4)])
    assert [r[2] for r in rows_of(engine) if r[1] == "top_path"] == ["super.xxl.co.il/b"]
    with pytest.raises(ValueError), engine.begin() as c:
        S.replace_days(c, "web", [D1], [("page_views", "x", D2, 1)])


def test_missing_logs_is_an_error_without_paths_leaking(engine, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("stats_web_logs", str(tmp_path / "none*"))
    res, out = _run(engine, monkeypatch, capsys, sources=("web",), days=1)
    assert res == {"web": "error"} and "no log files found" in out


# ------------------------------------------------------------ credentialed sources
class Resp:
    def __init__(self, status=200, body=None, content=b""):
        self.status_code, self._body, self.content = status, body, content

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeHttp:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def _hit(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for key, resp in self.routes:
            if key in url:
                return resp(url, kw) if callable(resp) else resp
        return Resp(404, {"errors": [{"code": "NOT_FOUND"}]})

    def get(self, url, **kw):
        return self._hit("GET", url, **kw)

    def post(self, url, **kw):
        return self._hit("POST", url, **kw)


def fake_token(*_a, **_k):
    return "tok-SECRET-0123456789abcdefghijklmnop"


def test_ga4(monkeypatch):
    monkeypatch.setenv("stats_google_key_file", "/etc/xxl/stats/google.json")
    monkeypatch.setenv("stats_ga4_property_id", "123456789")
    body = {"rows": [
        {"dimensionValues": [{"value": "20261104"}, {"value": "super.xxl.co.il"}],
         "metricValues": [{"value": "40"}, {"value": "50"}, {"value": "120"}]},
        {"dimensionValues": [{"value": "20261104"}, {"value": "evil.example"}],
         "metricValues": [{"value": "1"}, {"value": "1"}, {"value": "1"}]}]}
    http = FakeHttp([("runReport", Resp(200, body))])
    rows, as_of = X.ga4_fetch([D1, D2], http=http, token=fake_token)
    assert ("page_views", "super.xxl.co.il", D1, 120) in rows and ("users", "(other)", D1, 1) in rows
    assert as_of == D1
    sent = http.calls[0][2]["json"]
    assert sent["dateRanges"] == [{"startDate": "2026-11-04", "endDate": "2026-11-05"}]
    monkeypatch.setenv("stats_ga4_property_id", "G-YB4X4E5ZKM")
    with pytest.raises(X.SourceError, match="numeric"):
        X.ga4_fetch([D1], http=http, token=fake_token)


def test_play(monkeypatch):
    monkeypatch.setenv("stats_google_key_file", "/k.json")
    monkeypatch.setenv("stats_play_bucket", "gs://pubsite_prod_rev_01234567890987654321/stats/installs/")
    csv_txt = ("Date,Package Name,Daily Device Installs,Daily Device Uninstalls,Daily Device Upgrades,"
               "Total User Installs,Daily User Installs,Daily User Uninstalls,Active Device Installs\n"
               "2026-11-04,il.co.xxl.supermarket,12,3,40,900,11,2,610\n"
               "2026-11-05,il.co.xxl.supermarket,9,1,5,909,9,1,\n")
    raw = b"\xff\xfe" + csv_txt.encode("utf-16-le")
    http = FakeHttp([("installs_il.co.xxl.supermarket_202611_overview.csv", Resp(200, None, raw))])
    rows, as_of = X.play_fetch([D1, D2], http=http, token=fake_token)
    assert ("installs", "", D1, 12) in rows and ("uninstalls", "", D1, 3) in rows
    assert ("active_devices", "", D1, 610) in rows and not [r for r in rows if r[0] == "active_devices" and r[2] == D2]
    assert as_of == D2
    assert "pubsite_prod_rev_01234567890987654321" in http.calls[0][1]
    with pytest.raises(X.SourceError, match="no installs export"):
        X.play_fetch([date(2026, 9, 1)], http=FakeHttp([]), token=fake_token)
    monkeypatch.setenv("stats_play_bucket", "my-bucket")
    with pytest.raises(X.SourceError):
        X.play_configured()


def _gz_tsv(rows):
    return gzip.compress(("\n".join("\t".join(r) for r in rows) + "\n").encode())


def test_appstore(monkeypatch):
    for k, v in {"stats_asc_key_file": "/k.p8", "stats_asc_key_id": "ABCDEF1234",
                 "stats_asc_issuer_id": "11111111-2222-3333-4444-555555555555",
                 "stats_asc_vendor_number": "87654321"}.items():
        monkeypatch.setenv(k, v)
    hdr = ["Provider", "SKU", "Product Type Identifier", "Units", "Apple Identifier"]
    sales = _gz_tsv([hdr, ["APPLE", "superxxl-ios-001", "1", "7", "6829450422"],
                     ["APPLE", "superxxl-ios-001", "3F", "2", "6829450422"],
                     ["APPLE", "superxxl-ios-001", "7", "30", "6829450422"],
                     ["APPLE", "other", "1", "99", "111"]])
    disc = _gz_tsv([["Date", "App Apple Identifier", "Event", "Counts", "Unique Counts"],
                    ["2026-11-04", "6829450422", "Impression", "300", "200"],
                    ["2026-11-04", "6829450422", "Page view", "40", "30"],
                    ["2026-11-04", "6829450422", "Tap", "5", "5"]])

    def sales_route(url, kw):
        d = kw["params"]["filter[reportDate]"]
        return Resp(200, None, sales) if d == "2026-11-04" else Resp(404, {"errors": [{"code": "NOT_FOUND"}]})

    http = FakeHttp([
        ("/v1/salesReports", sales_route),
        ("/analyticsReportRequests/R1/reports", Resp(200, {"data": [{"id": "REP"}]})),
        ("/analyticsReportRequests", Resp(200, {"data": [{"id": "R1"}]})),
        ("/analyticsReports/REP/instances", Resp(200, {"data": [
            {"id": "I1", "attributes": {"processingDate": "2026-11-05"}},
            {"id": "I0", "attributes": {"processingDate": "2026-10-01"}}]})),
        ("/analyticsReportInstances/I1/segments", Resp(200, {"data": [{"attributes": {"url": "https://signed.example/seg?sig=AAA"}}]})),
        ("signed.example", Resp(200, None, disc)),
    ])
    rows, as_of, note = X.asc_fetch([date(2026, 11, 1), D1, D2], http=http, today=TODAY, token=fake_token)
    assert ("downloads", "", D1, 7) in rows and ("redownloads", "", D1, 2) in rows and ("updates", "", D1, 30) in rows
    assert ("downloads", "", date(2026, 11, 1), 0) in rows       # 404, 5 days old: no sales
    assert not [r for r in rows if r[2] == D2 and r[0] == "downloads"]  # 404, 1 day old: not published yet
    assert ("impressions", "", D1, 300) in rows and ("page_views", "", D1, 40) in rows
    assert as_of == D1 and note is None
    seg_call = [c for c in http.calls if "signed.example" in c[1]][0]
    assert "headers" not in seg_call[2]  # the pre-signed URL gets no Authorization header
    assert not [c for c in http.calls if "I0" in c[1]]  # old instance not downloaded

    http2 = FakeHttp([("/v1/salesReports", Resp(404, {})), ("/analyticsReportRequests", Resp(200, {"data": []}))])
    _, _, note = X.asc_fetch([D1], http=http2, today=TODAY, token=fake_token)
    assert note == "analytics_request_missing"

    monkeypatch.setenv("stats_asc_key_id", "B3NWA8C97L")
    with pytest.raises(X.SourceError, match="EAS"):
        X.asc_configured()


def test_tokens_are_signed_correctly(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    from jose import jwt
    ec_key = ec.generate_private_key(ec.SECP256R1())
    p8 = tmp_path / "AuthKey.p8"
    p8.write_bytes(ec_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()))
    t = X.asc_token(str(p8), "ABCDEF1234", "issuer-1")
    assert jwt.get_unverified_header(t)["kid"] == "ABCDEF1234"
    assert jwt.get_unverified_claims(t)["aud"] == "appstoreconnect-v1"
    with pytest.raises(X.SourceError):
        X.asc_token(str(p8), "B3NWA8C97L", "issuer-1")

    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = rsa_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    kf = tmp_path / "google.json"
    kf.write_text(json.dumps({"client_email": "stats@scrp.iam.gserviceaccount.com", "private_key": pem}))
    http = FakeHttp([("oauth2.googleapis.com/token", Resp(200, {"access_token": "AT"}))])
    assert X.google_token(http, str(kf), X.GA4_SCOPE) == "AT"
    claims = jwt.get_unverified_claims(http.calls[0][2]["data"]["assertion"])
    assert claims["scope"] == X.GA4_SCOPE and claims["iss"].startswith("stats@")
    with pytest.raises(X.SourceError, match="not readable"):
        X.google_token(http, str(tmp_path / "missing.json"), X.GA4_SCOPE)


def test_not_configured_and_errors_are_safe(engine, monkeypatch, capsys):
    res, out = _run(engine, monkeypatch, capsys, sources=("ga4", "play", "appstore"), days=1)
    assert set(res.values()) == {"not_configured"}
    with engine.connect() as c:
        notes = dict(c.execute(text("SELECT source, note FROM stats_runs")).all())
    assert notes["ga4"] == "missing setting: stats_google_key_file, stats_ga4_property_id"

    # A failing API: the stored / printed error has the status and the API's code, no token or URL.
    monkeypatch.setenv("stats_google_key_file", "/k.json")
    monkeypatch.setenv("stats_ga4_property_id", "123")
    http = FakeHttp([("runReport", Resp(403, {"error": {"status": "PERMISSION_DENIED",
                                                         "message": "token tok-SECRET-0123456789abcdefghijklmnop"}}))])
    monkeypatch.setattr(X, "google_token", fake_token)
    r = C.run_source(engine, "ga4", today=TODAY, days=1, dry_run=False, http=http)
    out = capsys.readouterr().out
    with engine.connect() as c:
        err = c.execute(text("SELECT last_error FROM stats_runs WHERE source = 'ga4'")).scalar()
    assert r == "error" and err == "ga4 report: HTTP 403 PERMISSION_DENIED"
    assert "SECRET" not in out + err and "googleapis" not in out + err

    class Boom(Exception):
        pass
    assert X.safe_error(Boom("see https://x.example/a?sig=1 key eyJhbGciOiJFUzI1NiIsImtpZCI6IkFCQyJ9")) == \
        "Boom: see <url> key <redacted>"


# --------------------------------------------------------------- GET /admin/stats
@pytest.fixture
def client(engine, monkeypatch):
    def _get_db():
        with engine.connect() as conn:
            yield conn
    tokens = {"admin2": {"sub": "a", "email": "admin@example.test", "aal": "aal2"},
              "admin1": {"sub": "a", "email": "admin@example.test", "aal": "aal1"},
              "user": {"sub": "b", "email": "user@example.test", "aal": "aal2"}}
    monkeypatch.setattr(auth, "_decode", lambda tok: tokens.get(tok))
    monkeypatch.setenv("ADMIN_USER_EMAILS", "admin@example.test")
    monkeypatch.setattr(AS, "_today_il", lambda: TODAY)
    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_admin_stats_gate(client):
    for headers, code in (({}, "admin_required"), ({"Authorization": "Bearer user"}, "admin_required"),
                          ({"Authorization": "Bearer admin1"}, "mfa_required")):
        r = client.get("/admin/stats", headers=headers)
        assert (r.status_code, r.json()) == (403, {"code": code})


def test_admin_stats_body(client, engine, logs, monkeypatch, capsys):
    _run(engine, monkeypatch, capsys, sources=C.ALL, days=2)
    r = client.get("/admin/stats?days=7", headers={"Authorization": "Bearer admin2"})
    assert r.status_code == 200
    b = r.json()
    assert (b["from"], b["to"], b["days"]) == ("2026-10-30", "2026-11-05", 7)
    assert b["sources"]["web"]["status"] == "ok" and b["sources"]["web"]["as_of"] == "2026-11-05"
    assert b["sources"]["ga4"]["status"] == "not_configured"
    s = {(x["source"], x["metric"], x["dimension"]): x["points"] for x in b["series"]}
    assert s[("web", "page_views", "super.xxl.co.il")] == [["2026-11-04", 5], ["2026-11-05", 2]]
    assert s[("api", "calls", "android")] == [["2026-11-04", 2], ["2026-11-05", 1]]
    assert not [k for k in s if k[1] in ("top_path", "referrer")]
    assert {"dimension": "super.xxl.co.il/categories/D02", "value": 2} in b["top_paths"]
    # /search/<text> and /product/<code> are not routes of the site: one "(other)" bucket.
    assert {"dimension": "super.xxl.co.il/(other)", "value": 2} in b["top_paths"]
    assert {"dimension": "super.xxl.co.il|google.com", "value": 1} in b["top_referrers"]
    blob = r.text
    assert not [ip for ip in IPS if ip in blob] and SECRET_Q not in blob and "Mozilla" not in blob
    assert client.get("/admin/stats?days=0", headers={"Authorization": "Bearer admin2"}).status_code == 422
    assert client.get("/admin/stats?days=401", headers={"Authorization": "Bearer admin2"}).status_code == 422


def test_admin_stats_before_migration(monkeypatch):
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    def _get_db():
        with eng.connect() as conn:
            yield conn
    monkeypatch.setattr(auth, "_decode", lambda tok: {"sub": "a", "email": "admin@example.test", "aal": "aal2"})
    monkeypatch.setenv("ADMIN_USER_EMAILS", "admin@example.test")
    app.dependency_overrides[get_db] = _get_db
    try:
        b = TestClient(app).get("/admin/stats", headers={"Authorization": "Bearer x"}).json()
    finally:
        app.dependency_overrides.clear()
    assert b["unavailable"] is True and b["series"] == [] and b["sources"]["web"]["status"] == "never_run"
