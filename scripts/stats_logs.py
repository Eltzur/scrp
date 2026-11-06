"""nginx access-log aggregation for the admin statistics (SU11A-69).

Reads the logs line by line (plain and .gz, rotated .1 / .N.gz included) and
keeps ONLY counters in memory:

  web (super.xxl.co.il, xxl.co.il, www.xxl.co.il, fly.xxl.co.il; admin.xxl.co.il
  and unknown hosts are left out), per Israel-time day and host:
    page_views       GET HTML document requests, 2xx / 304, by a person
    bot_page_views   the same by a known crawler / tool (not in visitors)
    visitors         distinct sha256(salt + ip + user agent) of the people above.
                     The salt is random per day and per run, kept in memory only,
                     never written, so the digests cannot be recomputed or joined
                     later; only the COUNT leaves this module.
    top_path         the 20 most viewed paths per host: the site's own routes
                     only (route_path; anything else is "/(other)"), never a
                     query string
    referrer         the 10 most common external referrer DOMAINS per host
  api (api-super.xxl.co.il), per day and platform:
    calls / errors_5xx   web | android | ios | bot | other (admin calls and CORS
                         pre-flights are not counted)

What is NEVER kept or returned: an IP address, a user agent, a full URL, a
query string. The tests feed lines full of those and check the rows that would
reach the database (tests/test_stats_su11a69.py).

Log format. nginx's default `combined` has no host, so lines from the shared
access.log cannot be told apart by site. SU11A-69 adds `$host` at the end
(deploy/nginx/xxl-log-format.conf). Lines without it count under the host
"(unknown)" and are reported, never guessed.
"""
from __future__ import annotations

import glob
import gzip
import hashlib
import os
import re
import secrets
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, Iterator
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

IL = ZoneInfo("Asia/Jerusalem")

WEB_HOSTS = ("super.xxl.co.il", "xxl.co.il", "www.xxl.co.il", "fly.xxl.co.il")
EXCLUDED_HOSTS = ("admin.xxl.co.il",)
OWN_DOMAINS = ("xxl.co.il",)  # and every sub-domain: internal navigation, not a referrer
UNKNOWN_HOST = "(unknown)"
DIRECT = "(direct)"
TOP_PATHS = 20
TOP_REFERRERS = 10
# Bounded memory: past this many distinct visitors in one (host, day) the count
# stops growing and the run says so (far above today's traffic).
VISITOR_CAP = 100_000

# combined: $remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent
#           "$http_referer" "$http_user_agent"   (+ SU11A-69: "$host")
_LINE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<req>[^"]*)" (?P<status>\d{3}) \S+ '
    r'"(?P<ref>[^"]*)" "(?P<ua>[^"]*)"(?: "(?P<host>[^"]*)")?')

_ASSET_EXT = re.compile(
    r"\.(?:js|mjs|css|map|png|jpe?g|gif|svg|webp|avif|ico|woff2?|ttf|otf|eot|json|txt|xml|"
    r"webmanifest|mp4|webm|pdf|zip|gz|php|asp|aspx|env|ini|bak|sql|cgi|pl|yml|yaml|lock)$", re.I)

BOT_UA = re.compile(
    r"bot\b|bot/|crawl|spider|slurp|facebookexternalhit|bingpreview|headless|lighthouse|"
    r"python-|curl/|wget/|go-http-client|java/|httpclient|okhttp-bench|scrapy|ahrefs|semrush|"
    r"mj12|dotbot|petalbot|yandex|baidu|duckduck|applebot|gptbot|claude|ccbot|bytespider|"
    r"pingdom|uptime|monitor|preview|feedfetcher|google-inspectiontool|whatsapp|telegram|"
    r"discord|slack|skype|zgrab|masscan|nmap|nuclei|censys|expanse|l9explore|httpx", re.I)

_DIGITS = re.compile(r"\d{7,}")


def is_bot(ua: str) -> bool:
    return ua in ("", "-") or bool(BOT_UA.search(ua))


def platform(ua: str, referrer: str) -> str | None:
    """web | android | ios | bot | other for an api-super request; None = the
    admin console (not counted).

    The apps send no custom header today (xxl-super-mobile src/api/client.ts
    sets only Accept / Content-Type / Authorization), so the platform comes from
    the user agent their HTTP stacks add:
      android  React Native fetch and expo-image use OkHttp:   "okhttp/4.x"
               (Dalvik/ is Android's own HttpURLConnection)
      ios      NSURLSession:   "SUPER%20XXL/<build> CFNetwork/<v> Darwin/<v>";
               expo-image (SDWebImage):   "SUPER XXL/<version> (iPhone; iOS 18.1; Scale/3.00)"
      web      a browser ("Mozilla/") whose Referer is one of the shop sites
    """
    if is_bot(ua):
        return "bot"
    if ua.startswith(("okhttp/", "Dalvik/")):
        return "android"
    if "CFNetwork/" in ua or re.search(r"\((?:iPhone|iPad|iPod); iOS \d", ua):
        return "ios"
    host = _ref_host(referrer)
    if host in EXCLUDED_HOSTS:
        return None
    if ua.startswith("Mozilla/") and host is not None and _own(host):
        return "web"
    return "other"


def _ref_host(referrer: str) -> str | None:
    if not referrer or referrer == "-":
        return None
    try:
        h = urlsplit(referrer).hostname
    except ValueError:
        return None
    return h.lower() if h else None


def _own(host: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in OWN_DOMAINS)


def referrer_domain(referrer: str) -> str | None:
    """External referrer domain (no path, no query, no "www."), DIRECT, or None
    for internal navigation."""
    host = _ref_host(referrer)
    if host is None:
        return DIRECT
    if _own(host):
        return None
    host = host[4:] if host.startswith("www.") else host
    if re.fullmatch(r"[\d.]+|\[?[0-9a-f:]+\]?", host):
        return "(ip)"
    return host[:100]


def clean_path(target: str) -> str:
    """The request target without query string / fragment / params, with long
    digit runs masked, at most 120 characters."""
    p = target.split("?", 1)[0].split("#", 1)[0].split(";", 1)[0]
    if not p.startswith("/"):
        p = "/" + p if not p.startswith("http") else (urlsplit(p).path or "/")
    p = _DIGITS.sub("{n}", p)
    if "@" in p or "=" in p or "://" in p or len(p) > 120:
        return "(other)"
    return p


# Top paths keep ONLY the site's own routes (web/src/App.tsx; fly.xxl.co.il is
# one page). Any other path - a typo, a scanner probe, a link someone made with
# text in it - counts as "(other)": a path segment can carry free text, and
# free text is never stored.
OTHER_ROUTE = "/(other)"
ROUTES = frozenset((
    "/", "/accessibility", "/account/delete", "/baskets", "/categories", "/disclaimer", "/fashion",
    "/favorites", "/login", "/my-ratings", "/partnerships", "/portal-preview", "/privacy", "/promos",
    "/reset-password", "/signup",
))
_CATEGORY_ROUTE = re.compile(r"/categories/[A-Z]\d{2}(?:\.[A-Z]\d{2}){0,2}")


def route_path(path: str) -> str:
    """A known route (trailing slash dropped), else OTHER_ROUTE."""
    p = path.rstrip("/") or "/"
    if p in ROUTES or _CATEGORY_ROUTE.fullmatch(p):
        return p
    return OTHER_ROUTE


def is_page(method: str, path: str, status: int) -> bool:
    """An HTML document request: GET, 2xx or 304, not an asset, not a probe."""
    if method != "GET" or not (200 <= status < 300 or status == 304):
        return False
    if path.startswith(("/assets/", "/.", "/api/")) or path == "(other)":
        return False
    return not _ASSET_EXT.search(path)


def parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.strptime(ts, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None


@dataclass
class Line:
    ip: str
    when: datetime
    method: str
    target: str
    status: int
    referrer: str
    ua: str
    host: str | None


def parse_line(raw: str) -> Line | None:
    m = _LINE.match(raw)
    if not m:
        return None
    when = parse_ts(m["ts"])
    if when is None:
        return None
    parts = m["req"].split(" ")
    if len(parts) < 2:
        return None
    host = m["host"]
    return Line(ip=m["ip"], when=when, method=parts[0], target=parts[1], status=int(m["status"]),
                referrer=m["ref"], ua=m["ua"], host=host.lower().split(":", 1)[0] if host else None)


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def log_files(patterns: Iterable[str]) -> list[str]:
    out: set[str] = set()
    for pat in patterns:
        out.update(p for p in glob.glob(pat) if os.path.isfile(p))
    return sorted(out)


def read_lines(paths: Iterable[str], not_before: datetime | None = None,
               stats: dict | None = None) -> Iterator[str]:
    """Stream every line of every file (gzip by name). A file last written
    before `not_before` cannot hold a line of the wanted days and is skipped;
    `stats` counts files read / skipped."""
    for p in paths:
        if not_before is not None and os.path.getmtime(p) < not_before.timestamp():
            if stats is not None:
                stats["files_skipped_old"] = stats.get("files_skipped_old", 0) + 1
            continue
        if stats is not None:
            stats["files_read"] = stats.get("files_read", 0) + 1
        opener = gzip.open if p.endswith(".gz") else open
        with opener(p, "rt", encoding="utf-8", errors="replace") as f:
            yield from f


def day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=IL)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

@dataclass
class _WebDay:
    page_views: int = 0
    bot_page_views: int = 0
    visitors: set = field(default_factory=set)
    visitors_capped: bool = False
    paths: Counter = field(default_factory=Counter)
    referrers: Counter = field(default_factory=Counter)


class Aggregator:
    """Counters for a set of Israel-time days. Feed it lines; read rows()."""

    def __init__(self, days: Iterable[date]):
        self.days = set(days)
        self._salts = {d: secrets.token_bytes(32) for d in self.days}  # memory only
        self.web: dict[tuple[str, date], _WebDay] = defaultdict(_WebDay)
        self.api_calls: Counter = Counter()
        self.api_5xx: Counter = Counter()
        self.min_seen: datetime | None = None
        self.counts = Counter()  # lines, unparsed, no_host, excluded_host, other_host, outside_days

    def _day(self, line: Line) -> date | None:
        if self.min_seen is None or line.when < self.min_seen:
            self.min_seen = line.when
        d = line.when.astimezone(IL).date()
        if d not in self.days:
            self.counts["outside_days"] += 1
            return None
        return d

    def visitor_key(self, d: date, ip: str, ua: str) -> bytes:
        return hashlib.sha256(self._salts[d] + ip.encode() + b"\x00" + ua.encode()).digest()[:16]

    def feed_web(self, raw: str) -> None:
        self.counts["lines"] += 1
        line = parse_line(raw)
        if line is None:
            self.counts["unparsed"] += 1
            return
        d = self._day(line)
        if d is None:
            return
        host = line.host
        if host is None:
            self.counts["no_host"] += 1
            host = UNKNOWN_HOST
        elif host in EXCLUDED_HOSTS:
            self.counts["excluded_host"] += 1
            return
        elif host not in WEB_HOSTS:
            self.counts["other_host"] += 1
            return
        path = clean_path(line.target)
        if not is_page(line.method, path, line.status):
            return
        if host == UNKNOWN_HOST and _ref_host(line.referrer) in EXCLUDED_HOSTS:
            return  # best effort before the $host format: admin navigation
        w = self.web[(host, d)]
        if is_bot(line.ua):
            w.bot_page_views += 1
            return
        w.page_views += 1
        if len(w.visitors) < VISITOR_CAP:
            w.visitors.add(self.visitor_key(d, line.ip, line.ua))
        else:
            w.visitors_capped = True
        w.paths[route_path(path)] += 1
        ref = referrer_domain(line.referrer)
        if ref is not None:
            w.referrers[ref] += 1

    def feed_api(self, raw: str) -> None:
        self.counts["lines"] += 1
        line = parse_line(raw)
        if line is None:
            self.counts["unparsed"] += 1
            return
        d = self._day(line)
        if d is None:
            return
        path = clean_path(line.target)
        if line.method == "OPTIONS" or path.startswith("/admin/") or path in ("/health", "/robots.txt"):
            return
        p = platform(line.ua, line.referrer)
        if p is None:
            return
        self.api_calls[(p, d)] += 1
        if line.status >= 500:
            self.api_5xx[(p, d)] += 1

    def covered(self, d: date, skipped_old_files: bool) -> bool:
        """The logs reach back to the start of day d (else the day is partial
        and must not replace what is stored)."""
        if skipped_old_files:
            return True
        return self.min_seen is not None and self.min_seen <= day_start(d)

    def web_rows(self) -> list[tuple[str, str, date, int]]:
        rows = []
        for (host, d), w in sorted(self.web.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            rows += [("page_views", host, d, w.page_views), ("bot_page_views", host, d, w.bot_page_views),
                     ("visitors", host, d, len(w.visitors))]
            for path, n in sorted(w.paths.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_PATHS]:
                rows.append(("top_path", f"{host}{path}", d, n))
            for ref, n in sorted(w.referrers.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_REFERRERS]:
                rows.append(("referrer", f"{host}|{ref}", d, n))
        return rows

    def api_rows(self) -> list[tuple[str, str, date, int]]:
        rows = [("calls", p, d, n) for (p, d), n in sorted(self.api_calls.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
        rows += [("errors_5xx", p, d, n) for (p, d), n in sorted(self.api_5xx.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
        return rows

    def visitors_capped(self) -> bool:
        return any(w.visitors_capped for w in self.web.values())


def days_back(today: date, n: int) -> list[date]:
    """The n completed days before today, oldest first."""
    return [today - timedelta(days=i) for i in range(n, 0, -1)]
