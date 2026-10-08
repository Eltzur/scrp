"""The geocoders never touch manual or Google-loaded coordinates (SU11A-23).
    python -m pytest tests/test_geo_guard.py -q"""
import pytest

from scripts.geo_guard import is_protected, protected_sql
import scripts.geo_centroids as C
import scripts.geo_nominatim as N


@pytest.mark.parametrize("row,protected", [
    ({"geo_source": "manual", "coord_source": None}, True),
    ({"geo_source": "google", "coord_source": None}, True),
    ({"geo_source": "nominatim", "coord_source": "google_exact"}, True),
    ({"geo_source": "nominatim", "coord_source": "google_reviewed"}, True),
    ({"geo_source": None, "coord_source": "manual_pin"}, True),
    ({"geo_source": "nominatim", "coord_source": "osm_house"}, False),
    ({"geo_source": "cbs_centroid", "coord_source": None}, False),
    ({"geo_source": None}, False),
])
def test_is_protected(row, protected):
    assert is_protected(row) is protected


def _row(**kw):
    base = dict(geo_source="nominatim", coord_source=None, geo_precision="street",
                geo_input="x", address="הרצל 5", city_canonical="חיפה", has_override=False)
    return {**base, **kw}


@pytest.mark.parametrize("kw", [dict(geo_source="manual"), dict(geo_source="google"),
                                dict(coord_source="google_exact"), dict(coord_source="google_reviewed"),
                                dict(coord_source="manual_pin")])
def test_geo_nominatim_needs_geocode_skips_protected(kw):
    assert N.needs_geocode(_row(**kw), include_overrides=True) is False


def test_geo_nominatim_still_targets_ordinary_rows():
    assert N.needs_geocode(_row()) is True


@pytest.mark.parametrize("hc", [False, True])
def test_geo_nominatim_target_sql_has_guard(hc):
    sql = N._TARGETS_SQL.format(coord_col="NULL::text AS coord_source", protected=protected_sql("s", hc))
    assert "NOT IN ('manual', 'google')" in sql
    assert ("coord_source NOT IN ('google_exact', 'google_reviewed', 'manual_pin')" in sql) is hc


@pytest.mark.parametrize("hc", [False, True])
def test_geo_centroids_target_sql_has_guard(hc):
    sql = C.target_sql(hc)
    assert "lat IS NULL" in sql and "NOT IN ('manual', 'google')" in sql
    assert ("coord_source NOT IN ('google_exact', 'google_reviewed', 'manual_pin')" in sql) is hc
