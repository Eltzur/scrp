"""Unit tests for scripts/import_manual_pins.py guards (SU11A-19). Run on the server venv:
    python -m pytest tests/test_import_manual_pins.py -q
No database needed: validate_picks is pure."""
import pytest

from scripts.import_manual_pins import (check_expect, geo_input_for, move_report, validate_picks)

CENTROIDS = {"חיפה": (32.794, 34.990), "תל אביב-יפו": (32.080, 34.780)}


def store(**kw):
    base = dict(live=True, is_physical=True, city_canonical="חיפה", address="הנשיא 124",
                geo_source="nominatim", chain="רשת", store_id="001", lat=32.80, lon=34.99,
                geo_precision="street")
    return {**base, **kw}


STORES = {
    1: store(),
    2: store(address="הרצל 5", store_id="002"),
    3: store(live=False),
    4: store(is_physical=False),
    5: store(geo_source="manual"),
    6: store(city_canonical="עיר שאינה ידועה"),
    7: store(address="הנשיא 124", store_id="007"),        # same address as store 1
    8: store(city_canonical="תל אביב-יפו", address="דיזנגוף 1", lat=None, lon=None, geo_precision=None),
}


def row(fk, lat=32.795, lon=34.991, method="clicked", cid="", ts="2026-10-05T10:00:00Z"):
    return {"store_fk": str(fk), "lat": str(lat), "lon": str(lon), "method": method,
            "candidate_id": cid, "timestamp": ts}


def reasons(rej):
    return {int(r["store_fk"]) if str(r.get("store_fk", "")).isdigit() else r.get("store_fk"): why for r, why in rej}


def test_happy_path_and_geo_input():
    acc, rej, skip, _ = validate_picks([row(1, cid="osm:node/9", method="candidate_osm")], STORES, CENTROIDS)
    assert [r["store_fk"] for r in acc] == [1] and not rej and not skip
    assert acc[0]["geo_input"] == "manual candidate_osm osm:node/9 2026-10-05"


def test_unknown_and_non_numeric_store_fk():
    _, rej, _, _ = validate_picks([row(999), {**row(1), "store_fk": "abc"}], STORES, CENTROIDS)
    msgs = [w for _, w in rej]
    assert "unknown store_fk" in msgs and "store_fk is not a number" in msgs


@pytest.mark.parametrize("fk", [3, 4])
def test_not_live_or_not_physical(fk):
    _, rej, _, _ = validate_picks([row(fk)], STORES, CENTROIDS)
    assert reasons(rej)[fk] == "not a live physical store"


def test_bad_method_rejected():
    _, rej, _, _ = validate_picks([row(1, method="google")], STORES, CENTROIDS)
    assert reasons(rej)[1].startswith("bad method")


@pytest.mark.parametrize("lat,lon", [("x", 34.9), (float("nan"), 34.9)])
def test_bad_numbers(lat, lon):
    _, rej, _, _ = validate_picks([row(1, lat=lat, lon=lon)], STORES, CENTROIDS)
    assert 1 in reasons(rej)


def test_outside_israel_bbox():
    _, rej, _, _ = validate_picks([row(1, lat=31.0, lon=32.0)], STORES, CENTROIDS)
    assert reasons(rej)[1] == "outside Israel bounding box"


def test_more_than_15_km_from_centroid():
    _, rej, _, _ = validate_picks([row(1, lat=32.08, lon=34.78)], STORES, CENTROIDS)   # Tel Aviv, store is Haifa
    assert "km from the חיפה centroid" in reasons(rej)[1]


def test_no_centroid_rejected():
    _, rej, _, _ = validate_picks([row(6)], STORES, CENTROIDS)
    assert "no CBS centroid" in reasons(rej)[6]


def test_existing_manual_skipped_unless_overwrite():
    _, _, skip, _ = validate_picks([row(5)], STORES, CENTROIDS)
    assert [r["store_fk"] for r in skip] == [5]
    acc, _, skip, _ = validate_picks([row(5)], STORES, CENTROIDS, overwrite_manual=True)
    assert [r["store_fk"] for r in acc] == [5] and not skip


def test_duplicate_within_10m_different_address_rejects_both():
    acc, rej, _, _ = validate_picks([row(1), row(2, lat=32.79503)], STORES, CENTROIDS)   # ~3 m apart
    assert not acc and set(reasons(rej)) == {1, 2}


def test_duplicate_within_10m_same_address_allowed():
    acc, rej, _, _ = validate_picks([row(1), row(7, lat=32.79503)], STORES, CENTROIDS)
    assert {r["store_fk"] for r in acc} == {1, 7} and not rej


def test_same_store_twice_latest_timestamp_wins():
    acc, _, _, info = validate_picks(
        [row(1, lat=32.796, ts="2026-10-05T11:00:00Z"), row(1, lat=32.790, ts="2026-10-05T09:00:00Z")],
        STORES, CENTROIDS)
    assert len(acc) == 1 and acc[0]["lat"] == 32.796
    assert info["duplicate store_fk rows superseded"] == 1


def test_check_expect():
    check_expect(3, 3)
    with pytest.raises(SystemExit):
        check_expect(3, 2)
    with pytest.raises(SystemExit):
        check_expect(3, None)


def test_geo_input_defaults():
    assert geo_input_for({"method": "clicked", "candidate_id": "", "timestamp": "2026-10-05T10:00:00Z"}) \
        == "manual clicked - 2026-10-05"


def test_move_report_p90_never_exceeds_max():
    acc, _, _, _ = validate_picks([row(1), row(2, lat=32.80), row(7, lat=32.79)], STORES, CENTROIDS)
    line = next(l for l in move_report(acc) if l.startswith("moved"))
    p90 = int(line.split("p90 ")[1].split(" m")[0]); mx = int(line.split("max ")[1].split(" m")[0])
    assert p90 <= mx


def test_move_report_lists_moves_over_1km():
    acc, _, _, _ = validate_picks([row(1, lat=32.80, lon=34.99), row(8, lat=32.08, lon=34.78)], STORES, CENTROIDS)
    acc[0]["_store"] = {**acc[0]["_store"], "lat": 32.70, "lon": 34.99}       # previous pin ~11 km away
    lines = move_report(acc)
    assert any("moves over 1 km: 1" in l for l in lines)
    assert any("store_fk 1" in l for l in lines)
