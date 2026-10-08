"""Unit tests for scripts/import_google_coordinates.py (SU11A-23). No database needed.
    python -m pytest tests/test_import_google_coordinates.py -q"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import scripts.import_google_coordinates as M

CENTROIDS = {"חיפה": (32.794, 34.990), "תל אביב-יפו": (32.080, 34.780)}


def store(**kw):
    base = dict(live=True, is_physical=True, chain="רשת", store_id="001", store_name="סניף",
                city_canonical="חיפה", lat=32.80, lon=34.99, geo_precision="street",
                geo_source="nominatim", coord_source=None)
    return {**base, **kw}


STORES = {1: store(), 2: store(store_id="002"), 3: store(geo_source="manual", coord_source="manual_pin"),
          4: store(live=False), 5: store(chain="אחרת")}


def cand(fk, lat=32.795, lon=34.991, source="google_exact", origin="A", precision="rooftop"):
    return {"store_fk": str(fk), "lat": str(lat), "lon": str(lon), "source": source,
            "origin": origin, "precision": precision, "label": "כתובת"}


def reasons(rep):
    return {int(c["store_fk"]): why for c, why in rep["rejected"]}


@pytest.mark.parametrize("src", ["google", "osm", "nominatim", "", None])
def test_source_outside_allow_list_rejected(src):
    rep = M.validate([cand(1, source=src)], STORES, CENTROIDS)
    assert "not in the allow-list" in reasons(rep)[1] and not rep["accepted"]


def test_allowed_but_not_loadable_source_rejected():
    rep = M.validate([cand(1, source="osm_house")], STORES, CENTROIDS)
    assert "not loaded by this importer" in reasons(rep)[1]


@pytest.mark.parametrize("lat", ["x", "", None])
def test_unparseable_coordinate_rejected(lat):
    rep = M.validate([cand(1, lat=lat)], STORES, CENTROIDS)
    assert reasons(rep)[1] == "unparseable coordinate"


@pytest.mark.parametrize("lat,lon", [(31.0, 32.0), (34.0, 35.0), (32.0, 36.5)])
def test_outside_israel_rejected(lat, lon):
    rep = M.validate([cand(1, lat=lat, lon=lon)], STORES, CENTROIDS)
    assert reasons(rep)[1] == "outside Israel bounds"


def test_manual_rows_skipped_without_override():
    rep = M.validate([cand(3)], STORES, CENTROIDS)
    assert [c["store_fk"] for c in rep["skipped_manual"]] == [3] and not rep["accepted"]
    assert [c["store_fk"] for c in rep["manual_pins"]] == [3]
    rep = M.validate([cand(3)], STORES, CENTROIDS, override_manual=True)
    assert [c["store_fk"] for c in rep["accepted"]] == [3]


def test_two_coordinates_for_one_store_rejected_and_overlap_reported():
    rep = M.validate([cand(1), cand(1, origin="B", source="google_reviewed")], STORES, CENTROIDS)
    assert rep["overlap_a_b"] == [1] and len(rep["rejected"]) == 2


def test_coverage_missing_and_extra():
    rep = M.validate([cand(1), cand(4), cand(99)], STORES, CENTROIDS)
    assert rep["missing"] == [2, 3, 5]
    assert rep["extra"] == [4, 99]
    assert reasons(rep)[4] == "not a live physical store" and reasons(rep)[99] == "unknown store_fk"


def test_reports_far_moves_far_centroid_precision_and_duplicates():
    rep = M.validate([cand(1, lat=32.08, lon=34.78, precision="places_shop"),   # Tel Aviv, store in Haifa
                      cand(2, lat=32.08001, lon=34.78001),                     # 1 m from store 1, same chain
                      cand(5, lat=32.08002, lon=34.78002)], STORES, CENTROIDS)  # different chain
    assert {c["store_fk"] for c in rep["far_moves"]} == {1, 2, 5}
    assert {c["store_fk"] for c in rep["far_centroid"]} == {1, 2, 5}
    assert [c["store_fk"] for c in rep["precision_review"]] == [1]
    assert len(rep["dups_same_chain"]) == 1 and len(rep["dups_diff_chain"]) == 2
    assert rep["move_hist"][">=5 km"] == 3


@pytest.mark.parametrize("text,want", [
    ("31.77561881546319, 34.704204499999996", (31.77561881546319, 34.704204499999996)),
    ("see map 32.03572,34.86519 ok", (32.03572, 34.86519)),
    ("34.8652, 32.0357", (32.0357, 34.8652)),            # swapped order is recognised
    ("סניף לא קיים", None), (None, None), ("12.5, 99.1", None),
])
def test_parse_pair(text, want):
    assert M.parse_pair(text) == want


def test_reviewed_rows_label_and_unparseable_listed():
    rows = [{"store_fk": "7", "Notes": "31.7756, 34.7042", "My decision": "הכישור 8 גן יבנה",
             "Google formatted address": "הכישור 8, רחובות, ישראל"},
            {"store_fk": "8", "Notes": None, "My decision": "סניף לא קיים", "Google formatted address": "x"},
            {"store_fk": "9", "Notes": "32.1, 34.9", "My decision": None, "Google formatted address": "גוגל 1"}]
    ok, bad = M.rows_from_reviewed(rows)
    assert [r["label"] for r in ok] == ["הכישור 8 גן יבנה", "גוגל 1"]
    assert all(r["source"] == "google_reviewed" for r in ok)
    assert [r["store_fk"] for r, _ in bad] == ["8"]


def test_exact_rows_only_true():
    rows = [{"store_fk": "1", "Exact": "TRUE", "Lat": "32.1", "Lon": "34.9", "Precision": "rooftop", "formatted_address": "a"},
            {"store_fk": "2", "Exact": "false", "Lat": "32.1", "Lon": "34.9", "Precision": "rooftop", "formatted_address": "b"},
            {"store_fk": "3", "Exact": "True", "Lat": "32.2", "Lon": "34.8", "Precision": "places_shop", "formatted_address": "c"}]
    out = M.rows_from_exact(rows)
    assert [r["store_fk"] for r in out] == ["1", "3"] and {r["source"] for r in out} == {"google_exact"}


def test_dry_run_performs_zero_writes(monkeypatch):
    conn = MagicMock()
    called = []
    monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: called.append(a))
    args = SimpleNamespace(apply=False, expect=None, session="SU11A-23", override_manual=False)
    M.run(args, conn, STORES, CENTROIDS, [cand(1), cand(2, origin="B", source="google_reviewed")], [])
    assert not conn.execute.called and not conn.commit.called
    assert conn.rollback.called and not called


def test_backup_table_name():
    assert M.backup_table("SU11A-23") == "stores_bak_su11a_23"


def test_apply_refuses_wrong_expect():
    args = SimpleNamespace(apply=True, expect=5, session="SU11A-23", override_manual=False)
    with pytest.raises(SystemExit):
        M.run(args, MagicMock(), STORES, CENTROIDS, [cand(1)], [])


# ---------------------------------------------------------------------------
# SU11A-23b: the importer's written values satisfy every CHECK constraint on `stores`.
# The allowed lists are read from the newest migration that (re)creates each constraint.
# ---------------------------------------------------------------------------
import re as _re
from pathlib import Path as _Path

_MIG = _Path(__file__).resolve().parent.parent / "db" / "migrations"


def _allowed(constraint: str, column: str) -> set[str]:
    files = sorted(f for f in _MIG.glob("*.sql") if f"ADD CONSTRAINT {constraint}" in f.read_text(encoding="utf-8"))
    assert files, f"no migration creates {constraint}"
    body = files[-1].read_text(encoding="utf-8")
    m = _re.search(rf"ADD CONSTRAINT {constraint}\s+CHECK \({column} IS NULL OR {column} IN \(([^)]*)\)\)", body)
    assert m, f"cannot parse {constraint} in {files[-1].name}"
    return set(_re.findall(r"'([^']+)'", m.group(1)))


def test_written_values_satisfy_every_check_constraint():
    assert M.WRITE_GEO_SOURCE in _allowed("stores_geo_source_chk", "geo_source")
    assert M.WRITE_GEO_PRECISION in _allowed("stores_geo_precision_chk", "geo_precision")
    assert set(M.LOADABLE_SOURCES) <= _allowed("stores_coord_source_check", "coord_source")
    assert set(M.ALLOWED_SOURCES) == _allowed("stores_coord_source_check", "coord_source")
    # the SQL literally writes the constants checked above
    assert f"geo_source = '{M.WRITE_GEO_SOURCE}'" in M.UPDATE_SQL
    assert f"geo_precision = '{M.WRITE_GEO_PRECISION}'" in M.UPDATE_SQL
    # retire / online only set is_physical (NOT NULL boolean) and last_loaded_at (nullable)
    assert "is_physical = false" in M.RETIRE_CLOSED_SQL and "last_loaded_at = NULL" in M.RETIRE_CLOSED_SQL
    assert M.MARK_ONLINE_SQL.count("=") == 2 and "is_physical = false" in M.MARK_ONLINE_SQL


def test_trial_writes_one_store_then_rolls_back():
    conn = MagicMock()
    conn.execute.return_value.rowcount = 1
    args = SimpleNamespace(apply=False, trial=True, expect=None, session="SU11A-23", override_manual=False,
                           retire_closed="18805,18812", mark_online="61543")
    M.run(args, conn, STORES, CENTROIDS, [cand(1), cand(2)], [])
    assert conn.execute.call_count == 1 + 2 + 1          # one coordinate UPDATE, two retire, one online
    assert conn.rollback.called and not conn.commit.called


@pytest.mark.parametrize("n,r,o", [(907, 2, 1), (908, 1, 1), (908, 2, 0)])
def test_check_counts_aborts_on_any_mismatch(n, r, o):
    with pytest.raises(SystemExit):
        M.check_counts(n, 908, r, 2, o, 1)


def test_check_counts_passes_exact():
    M.check_counts(908, 908, 2, 2, 1, 1)


# ---------------------------------------------------------------------------
# SU11A-23b: --extra (hand-confirmed coordinates)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("src", ["google", "manual", "osm", "", None])
def test_extra_row_with_source_outside_allow_list_rejected(src):
    rows = M.rows_from_extra([{"store_fk": "1", "lat": "32.795", "lon": "34.991", "source": src}])
    rep = M.validate(rows, STORES, CENTROIDS)
    assert not rep["accepted"] and "allow-list" in reasons(rep)[1]


def test_extra_row_values_pass_the_stores_constraints():
    rows = M.rows_from_extra([{"store_fk": "1", "lat": "32.795", "lon": "34.991", "source": "google_reviewed"}])
    rep = M.validate(rows, STORES, CENTROIDS)
    assert [c["store_fk"] for c in rep["accepted"]] == [1]
    assert rep["accepted"][0]["source"] in _allowed("stores_coord_source_check", "coord_source")
    assert M.WRITE_GEO_SOURCE in _allowed("stores_geo_source_chk", "geo_source")
    assert M.WRITE_GEO_PRECISION in _allowed("stores_geo_precision_chk", "geo_precision")


def test_extra_row_never_overwrites_a_manual_pin():
    rows = M.rows_from_extra([{"store_fk": "3", "lat": "32.795", "lon": "34.991", "source": "google_reviewed"}])
    rep = M.validate(rows, STORES, CENTROIDS)
    assert not rep["accepted"] and [c["store_fk"] for c in rep["skipped_manual"]] == [3]


def test_extra_row_may_replace_an_existing_google_coordinate():
    stores = {**STORES, 6: store(geo_source="google", coord_source="google_exact", geo_precision="address")}
    rows = M.rows_from_extra([{"store_fk": "6", "lat": "32.795", "lon": "34.991", "source": "google_reviewed"}])
    rep = M.validate(rows, stores, CENTROIDS)
    assert [c["store_fk"] for c in rep["accepted"]] == [6]
    assert "geo_source, '') <> 'manual'" in M.UPDATE_SQL         # the SQL guard keeps manual rows out too
