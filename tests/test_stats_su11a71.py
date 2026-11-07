"""SU11A-71: the site is an SPA, so nginx answers 200 (index.html) for ANY path.
A page view therefore also needs the path to be one of the site's own routes
(stats_logs.ROUTES + the category family, checked against App.tsx in
test_stats_su11a70.py); every other 200 is a rejected request.
    python -m pytest tests/test_stats_su11a71.py -q
"""
import pytest

from scripts import stats_logs as L
from tests.test_stats_su11a69 import IPS, SECRET_Q, UA_GOOGLEBOT, ts
from tests.test_stats_su11a70 import D1, H, agg, ln


@pytest.mark.parametrize("path", [
    "/wp-admin", "/wp-admin/", "/wp-login", "/.env", "/xmlrpc.php", "/admin", "/phpmyadmin",
    "/cgi-bin/luci", "/search/" + SECRET_Q, "/product/7290004131074", "/categories/X99",
    "/categories/D01.C02.S03.Z04", "/promos/today",
])
def test_spa_200_for_a_non_route_is_rejected(path):
    _, r = agg([ln(IPS[0], ts(D1), f"GET {path} HTTP/1.1", status=200)])
    assert r.get(("page_views", H, D1), 0) == 0
    assert r.get(("visitors", H, D1), 0) == 0
    assert r[("rejected_requests", H, D1)] == 1
    assert not [k for k in r if k[0] == "top_path"]


@pytest.mark.parametrize("path", [
    "/", "/promos", "/promos/", "/categories", "/categories/D02", "/categories/D02.C01",
    "/categories/D02.C01.S03", "/privacy", "/account/delete", "/login", "/fashion",
])
def test_real_routes_are_page_views(path):
    _, r = agg([ln(IPS[0], ts(D1), f"GET {path}?city=x HTTP/2.0", status=200)])
    assert r[("page_views", H, D1)] == 1
    assert r.get(("rejected_requests", H, D1), 0) == 0
    assert r[("top_path", f"{H}{path.rstrip('/') or '/'}", D1)] == 1


def test_bot_probe_is_rejected_not_a_bot_page_view():
    _, r = agg([ln(IPS[2], ts(D1), "GET /xmlrpc.php HTTP/1.1", ua=UA_GOOGLEBOT),
                ln(IPS[2], ts(D1), "GET /promos HTTP/1.1", ua=UA_GOOGLEBOT)])
    assert r[("bot_page_views", H, D1)] == 1
    assert r[("rejected_requests", H, D1)] == 1


def test_internal_flag_only_on_routes():
    _, r = agg([ln(IPS[0], ts(D1), "GET /promos HTTP/2.0", flag="1"),
                ln(IPS[0], ts(D1), "GET /wp-admin HTTP/2.0", flag="1")])
    assert r[("internal_page_views", H, D1)] == 1
    assert r[("rejected_requests", H, D1)] == 1


def test_is_route():
    assert L.is_route("/") and L.is_route("/categories/D10.C05") and L.is_route("/baskets/")
    assert not L.is_route("/(other)") and not L.is_route("/wp-admin") and not L.is_route("(other)")
