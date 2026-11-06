"""Credentialed statistics sources for SU11A-69: GA4, Google Play installs and
the App Store. Each one is OFF until Dude installs its credential files on the
server (docs/admin/su11a69_runbook.md, "Connect later"); until then
`configured()` says which setting is missing and the job records the source as
not_configured, so the admin screen shows "לא מחובר".

Settings (lowercase env names, CLAUDE.md convention; set in ~/scrp/.env, which
is the scrp-stats unit's EnvironmentFile). Credential FILES live outside the
repo, e.g. /etc/xxl/stats/, mode 600, owned by dude:
  stats_google_key_file      service-account JSON key (GA4 + Play bucket)
  stats_ga4_property_id      the NUMERIC GA4 property id (not G-YB4X4E5ZKM)
  stats_play_bucket          pubsite_prod_rev_<digits> (a gs:// URI is accepted)
  stats_play_package         default il.co.xxl.supermarket
  stats_asc_key_file         App Store Connect .p8 key, role Sales and Reports,
                             a SEPARATE key (never the EAS key B3NWA8C97L)
  stats_asc_key_id / stats_asc_issuer_id / stats_asc_vendor_number
  stats_asc_app_id           default 6829450422

Nothing here prints or logs a key, a token, a signed URL or a response body:
errors are reduced to the class / HTTP status / the API's error code
(safe_error). Only daily counts are returned.

All HTTP goes through the `http` object (a requests.Session by default), so the
tests replace it with a fake.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import os
import re
import time
from datetime import date, datetime, timedelta
from typing import Callable

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GA4_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
GCS_SCOPE = "https://www.googleapis.com/auth/devstorage.read_only"
ASC_API = "https://api.appstoreconnect.apple.com"
ASC_DISCOVERY_REPORT = "App Store Discovery and Engagement Standard"
DEFAULT_PACKAGE = "il.co.xxl.supermarket"
DEFAULT_ASC_APP = "6829450422"
FORBIDDEN_ASC_KEY_IDS = ("B3NWA8C97L",)  # the EAS "App Manager" key: never for stats
TIMEOUT = 30

Row = tuple[str, str, date, int]


class NotConfigured(Exception):
    """A setting is missing; the message names the setting, never a value."""


class SourceError(Exception):
    """A safe, short failure description (no secret, no URL, no body)."""


def env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, "").strip()
    return v or default


def _need(*names: str) -> dict[str, str]:
    missing = [n for n in names if not env(n)]
    if missing:
        raise NotConfigured("missing setting: " + ", ".join(missing))
    return {n: env(n) for n in names}


def _read_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        raise SourceError(f"key file not readable ({type(exc).__name__})") from None


_TOKENISH = re.compile(r"[A-Za-z0-9_\-./+=]{24,}")
_URL = re.compile(r"https?://\S+")


def safe_error(exc: BaseException) -> str:
    """Class + HTTP status + the API's error code; URLs and token-like strings removed."""
    if isinstance(exc, (SourceError, NotConfigured)):
        msg = str(exc)
    else:
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
        code = None
        if resp is not None:
            try:
                body = resp.json()
                code = ((body.get("error") or {}).get("status") if isinstance(body.get("error"), dict)
                        else body.get("error")) or ((body.get("errors") or [{}])[0].get("code"))
            except Exception:
                code = None
        msg = type(exc).__name__ + (f" HTTP {status}" if status else "") + (f" {code}" if code else "")
        if status is None:
            msg += ": " + str(exc)[:120]
    msg = _URL.sub("<url>", msg)
    msg = _TOKENISH.sub("<redacted>", msg)
    return msg[:300]


def _check(resp, what: str):
    if resp.status_code >= 400:
        code = None
        try:
            body = resp.json()
            err = body.get("error")
            code = (err.get("status") if isinstance(err, dict) else err) or (body.get("errors") or [{}])[0].get("code")
        except Exception:
            pass
        raise SourceError(f"{what}: HTTP {resp.status_code}" + (f" {code}" if code else ""))
    return resp


def default_http():
    import requests
    return requests.Session()


# ---------------------------------------------------------------------------
# Google: service-account token (RS256 JWT -> OAuth access token)
# ---------------------------------------------------------------------------

def google_token(http, key_file: str, scope: str) -> str:
    from jose import jwt
    try:
        key = json.loads(_read_file(key_file))
        email, pem = key["client_email"], key["private_key"]
    except (ValueError, KeyError):
        raise SourceError("key file is not a service-account JSON key") from None
    now = int(time.time())
    assertion = jwt.encode({"iss": email, "scope": scope, "aud": GOOGLE_TOKEN_URL,
                            "iat": now, "exp": now + 3600}, pem, algorithm="RS256")
    resp = _check(http.post(GOOGLE_TOKEN_URL, data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
        timeout=TIMEOUT), "google token")
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# B1. GA4 Data API: users, sessions, page views per day and hostname
# ---------------------------------------------------------------------------

def ga4_configured() -> None:
    _need("stats_google_key_file", "stats_ga4_property_id")


def ga4_fetch(days: list[date], http=None, token: Callable[..., str] | None = None) -> tuple[list[Row], date | None]:
    cfg = _need("stats_google_key_file", "stats_ga4_property_id")
    pid = cfg["stats_ga4_property_id"]
    if not pid.isdigit():
        raise SourceError("stats_ga4_property_id must be the numeric property id (GA4 Admin > Property details)")
    http = http or default_http()
    tok = (token or google_token)(http, cfg["stats_google_key_file"], GA4_SCOPE)
    body = {"dateRanges": [{"startDate": min(days).isoformat(), "endDate": max(days).isoformat()}],
            "dimensions": [{"name": "date"}, {"name": "hostName"}],
            "metrics": [{"name": "activeUsers"}, {"name": "sessions"}, {"name": "screenPageViews"}],
            "limit": 10000}
    resp = _check(http.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport",
                            json=body, headers={"Authorization": f"Bearer {tok}"}, timeout=TIMEOUT), "ga4 report")
    sums: dict[tuple[str, str, date], int] = {}
    for r in resp.json().get("rows") or []:
        d = datetime.strptime(r["dimensionValues"][0]["value"], "%Y%m%d").date()
        host = (r["dimensionValues"][1]["value"] or "").lower()
        host = host if re.fullmatch(r"(?:[a-z0-9-]+\.)*xxl\.co\.il", host) else "(other)"
        for metric, mv in zip(("users", "sessions", "page_views"), r["metricValues"]):
            k = (metric, host, d)
            sums[k] = sums.get(k, 0) + int(float(mv["value"]))
    rows = [(m, h, d, v) for (m, h, d), v in sorted(sums.items(), key=lambda kv: (kv[0][2], kv[0][0], kv[0][1]))]
    return rows, max((r[2] for r in rows), default=None)


# ---------------------------------------------------------------------------
# B2. Google Play: the Play Console statistics export in Cloud Storage
# ---------------------------------------------------------------------------

PLAY_COLUMNS = {
    "Daily Device Installs": "installs",
    "Daily Device Uninstalls": "uninstalls",
    "Active Device Installs": "active_devices",
    "Daily User Installs": "user_installs",
}


def play_bucket(raw: str) -> str:
    b = raw.strip()
    if b.startswith("gs://"):
        b = b[5:]
    b = b.split("/", 1)[0]
    if not re.fullmatch(r"pubsite_prod_rev_\d+|pubsite_prod_[a-z0-9_]+", b):
        raise SourceError("stats_play_bucket does not look like pubsite_prod_rev_<digits>")
    return b


def play_configured() -> None:
    _need("stats_google_key_file", "stats_play_bucket")
    play_bucket(env("stats_play_bucket") or "")


def decode_play_csv(raw: bytes) -> list[dict]:
    """The export is UTF-16 (with BOM); older files are UTF-8."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        txt = raw.decode("utf-16")
    else:
        txt = raw.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(txt)))


def play_rows(records: list[dict], package: str) -> list[Row]:
    rows: list[Row] = []
    for rec in records:
        if (rec.get("Package Name") or package) != package:
            continue
        try:
            d = date.fromisoformat((rec.get("Date") or "").strip())
        except ValueError:
            continue
        for col, metric in PLAY_COLUMNS.items():
            v = (rec.get(col) or "").strip()
            if v.lstrip("-").isdigit():
                rows.append((metric, "", d, max(0, int(v))))
    return rows


def play_fetch(days: list[date], http=None, token: Callable[..., str] | None = None) -> tuple[list[Row], date | None]:
    cfg = _need("stats_google_key_file", "stats_play_bucket")
    bucket = play_bucket(cfg["stats_play_bucket"])
    package = env("stats_play_package", DEFAULT_PACKAGE)
    http = http or default_http()
    tok = (token or google_token)(http, cfg["stats_google_key_file"], GCS_SCOPE)
    auth = {"Authorization": f"Bearer {tok}"}
    months = sorted({d.strftime("%Y%m") for d in days})
    rows: list[Row] = []
    found = 0
    for ym in months:
        name = f"stats/installs/installs_{package}_{ym}_overview.csv"
        from urllib.parse import quote
        resp = http.get(f"https://storage.googleapis.com/storage/v1/b/{bucket}/o/{quote(name, safe='')}",
                        params={"alt": "media"}, headers=auth, timeout=TIMEOUT)
        if resp.status_code == 404:
            continue  # no file for that month yet
        _check(resp, "play export")
        found += 1
        rows += play_rows(decode_play_csv(resp.content), package)
    if not found:
        raise SourceError("no installs export for these months yet (Play writes it within a few days; "
                          "check the bucket id and the service account's Play Console access)")
    return rows, max((r[2] for r in rows), default=None)


# ---------------------------------------------------------------------------
# B3. App Store Connect: Sales Reports (units) + Analytics Reports (impressions)
# ---------------------------------------------------------------------------

ASC_SETTINGS = ("stats_asc_key_file", "stats_asc_key_id", "stats_asc_issuer_id", "stats_asc_vendor_number")


def asc_configured() -> None:
    cfg = _need(*ASC_SETTINGS)
    if cfg["stats_asc_key_id"] in FORBIDDEN_ASC_KEY_IDS:
        raise SourceError("stats_asc_key_id is the EAS App Manager key; create a separate Sales and Reports key")


def asc_token(key_file: str, key_id: str, issuer: str) -> str:
    from jose import jwt
    if key_id in FORBIDDEN_ASC_KEY_IDS:
        raise SourceError("the EAS App Manager key must not be used for statistics")
    now = int(time.time())
    return jwt.encode({"iss": issuer, "iat": now, "exp": now + 1200, "aud": "appstoreconnect-v1"},
                      _read_file(key_file), algorithm="ES256", headers={"kid": key_id, "typ": "JWT"})


def _tsv(raw: bytes) -> list[dict]:
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    txt = raw.decode("utf-8-sig")
    first = txt.split("\n", 1)[0]
    return list(csv.DictReader(io.StringIO(txt), delimiter="\t" if "\t" in first else ","))


def sales_rows(records: list[dict], app_id: str, d: date) -> list[Row]:
    """Product Type Identifier: 1* = first download, 3* = re-download, 7* = update
    (iOS / universal / iPad variants)."""
    sums = {"downloads": 0, "redownloads": 0, "updates": 0}
    for rec in records:
        if (rec.get("Apple Identifier") or "").strip() != app_id:
            continue
        pt = (rec.get("Product Type Identifier") or "").strip()
        try:
            units = int(float(rec.get("Units") or 0))
        except ValueError:
            continue
        metric = {"1": "downloads", "3": "redownloads", "7": "updates"}.get(pt[:1])
        if metric:
            sums[metric] += max(0, units)
    return [(m, "", d, v) for m, v in sums.items()]


def discovery_rows(records: list[dict], app_id: str) -> dict[date, dict[str, int]]:
    out: dict[date, dict[str, int]] = {}
    for rec in records:
        if (rec.get("App Apple Identifier") or app_id).strip() != app_id:
            continue
        metric = {"impression": "impressions", "page view": "page_views"}.get((rec.get("Event") or "").strip().lower())
        if not metric:
            continue
        try:
            d = date.fromisoformat((rec.get("Date") or "").strip()[:10])
            n = int(float(rec.get("Counts") or 0))
        except ValueError:
            continue
        day = out.setdefault(d, {"impressions": 0, "page_views": 0})
        day[metric] += max(0, n)
    return out


def asc_fetch(days: list[date], http=None, today: date | None = None,
              token: Callable[..., str] | None = None) -> tuple[list[Row], date | None, str | None]:
    """(rows, as_of, note). A 404 on a sales day means "no sales" once the day is
    3+ days old; a newer day is simply not published yet (Apple publishes the
    daily report the next day, sometimes later) and is retried on the next run."""
    asc_configured()
    cfg = _need(*ASC_SETTINGS)
    app_id = env("stats_asc_app_id", DEFAULT_ASC_APP)
    http = http or default_http()
    today = today or date.today()
    tok = (token or asc_token)(cfg["stats_asc_key_file"], cfg["stats_asc_key_id"], cfg["stats_asc_issuer_id"])
    auth = {"Authorization": f"Bearer {tok}"}
    rows: list[Row] = []
    for d in days:
        resp = http.get(f"{ASC_API}/v1/salesReports", headers=auth, timeout=TIMEOUT, params={
            "filter[frequency]": "DAILY", "filter[reportType]": "SALES", "filter[reportSubType]": "SUMMARY",
            "filter[vendorNumber]": cfg["stats_asc_vendor_number"], "filter[reportDate]": d.isoformat(),
            "filter[version]": "1_1"})
        if resp.status_code == 404:
            if (today - d).days >= 3:
                rows += [(m, "", d, 0) for m in ("downloads", "redownloads", "updates")]
            continue
        _check(resp, "sales report")
        rows += sales_rows(_tsv(resp.content), app_id, d)

    note = None
    try:
        disc = _discovery(http, auth, app_id, days)
        for d in sorted(disc):
            rows += [(m, "", d, v) for m, v in disc[d].items()]
    except _NoAnalyticsRequest:
        note = "analytics_request_missing"
    as_of = max((r[2] for r in rows if r[0] == "downloads"), default=None)
    return rows, as_of, note


class _NoAnalyticsRequest(Exception):
    pass


def _get_all(http, url: str, auth: dict, params: dict | None = None, pages: int = 5) -> list[dict]:
    out: list[dict] = []
    for _ in range(pages):
        resp = _check(http.get(url, headers=auth, params=params, timeout=TIMEOUT), "analytics list")
        body = resp.json()
        out += body.get("data") or []
        url = (body.get("links") or {}).get("next")
        params = None
        if not url:
            break
    return out


def _discovery(http, auth: dict, app_id: str, days: list[date]) -> dict[date, dict[str, int]]:
    reqs = _get_all(http, f"{ASC_API}/v1/apps/{app_id}/analyticsReportRequests", auth,
                    {"filter[accessType]": "ONGOING"})
    if not reqs:
        raise _NoAnalyticsRequest()
    reports = _get_all(http, f"{ASC_API}/v1/analyticsReportRequests/{reqs[0]['id']}/reports", auth,
                       {"filter[name]": ASC_DISCOVERY_REPORT})
    if not reports:
        return {}
    lo = min(days) - timedelta(days=1)
    instances = [i for i in _get_all(http, f"{ASC_API}/v1/analyticsReports/{reports[0]['id']}/instances", auth,
                                     {"filter[granularity]": "DAILY", "limit": 200})
                 if (i.get("attributes") or {}).get("processingDate", "") >= lo.isoformat()]
    out: dict[date, dict[str, int]] = {}
    # Later processing dates restate earlier ones: the newest instance wins per day.
    for inst in sorted(instances, key=lambda i: i["attributes"]["processingDate"]):
        per_instance: dict[date, dict[str, int]] = {}
        for seg in _get_all(http, f"{ASC_API}/v1/analyticsReportInstances/{inst['id']}/segments", auth):
            url = (seg.get("attributes") or {}).get("url")
            if not url:
                continue
            resp = _check(http.get(url, timeout=TIMEOUT), "analytics segment")  # pre-signed: no auth header
            for d, vals in discovery_rows(_tsv(resp.content), app_id).items():
                acc = per_instance.setdefault(d, {"impressions": 0, "page_views": 0})
                for k, v in vals.items():
                    acc[k] += v
        out.update(per_instance)
    return {d: v for d, v in out.items() if d in set(days)}


def asc_request_analytics(key_file: str, key_id: str, http=None) -> str:
    """One-time: create the ONGOING Analytics Reports request. Apple allows that
    only with an ADMIN key (a temporary one, revoked afterwards); the daily key
    then reads the reports. Returns 'created' or 'exists'."""
    issuer = env("stats_asc_issuer_id")
    if not issuer:
        raise NotConfigured("missing setting: stats_asc_issuer_id")
    app_id = env("stats_asc_app_id", DEFAULT_ASC_APP)
    http = http or default_http()
    auth = {"Authorization": f"Bearer {asc_token(key_file, key_id, issuer)}"}
    if _get_all(http, f"{ASC_API}/v1/apps/{app_id}/analyticsReportRequests", auth, {"filter[accessType]": "ONGOING"}):
        return "exists"
    _check(http.post(f"{ASC_API}/v1/analyticsReportRequests", headers=auth, timeout=TIMEOUT, json={
        "data": {"type": "analyticsReportRequests", "attributes": {"accessType": "ONGOING"},
                 "relationships": {"app": {"data": {"type": "apps", "id": app_id}}}}}), "analytics request")
    return "created"
