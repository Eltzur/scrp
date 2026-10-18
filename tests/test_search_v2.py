"""Search v2 (SU11A-36): normalization, parsing, aliases, typo choice, ranking,
the Eilat rule, the engine with a fake database layer, and the SEARCH_V2 switch.
No database: the SQL-facing helpers are replaced with fakes.
    python -m pytest tests/test_search_v2.py -q
"""
from datetime import datetime, timedelta, timezone

import pytest

import api.routers.search as R
import db.search_v2 as V
from db.search_norm import coupon_pattern, is_pseudo, lexicon_words, normalize, tokenize


# --------------------------------------------------------------------------- normalize
@pytest.mark.parametrize("raw, want", [
    ("Milka", "milka"),
    ("COCA-COLA", "coca cola"),
    ("קוקה-קולה", "קוקה קולה"),
    ("קוקה־קולה", "קוקה קולה"),            # maqaf
    ("קוקה – קולה", "קוקה קולה"),               # en dash, spaces collapse
    ("ג׳בטה", "ג'בטה"),                          # geresh
    ("ג’בטה", "ג'בטה"),                          # right single quote
    ("ג`בטה", "ג'בטה"),
    ('ש״ח', 'ש"ח'),                              # gershayim
    ("ש“ח", 'ש"ח'),
    ("שָׁלוֹם", "שלום"),                          # niqqud
    ("  חלב   3%  ", "חלב 3%"),
    ("חלב 1.5% 1 ל'", "חלב 1.5% 1 ל'"),         # digits, %, '.' kept
    (None, ""),
    ("", ""),
])
def test_normalize(raw, want):
    assert normalize(raw) == want


def test_normalize_is_idempotent():
    for s in ["קוקה-קולה ZERO 1.5 ל׳", "שָׁלוֹם ״טרי״", "Milka  Oreo"]:
        assert normalize(normalize(s)) == normalize(s)


def test_tokenize_keeps_two_letter_words_and_drops_single_chars():
    assert tokenize("דג מלוח") == ["דג", "מלוח"]
    assert tokenize("ק") == []
    assert tokenize("חלב 3 %") == ["חלב"]
    assert tokenize("חלב 3%") == ["חלב", "3%"]


def test_lexicon_words_strip_edges_and_skip_numbers():
    assert lexicon_words('חלב, (טרי) 3% 500 ש"ח "תנובה"') == ["חלב", "טרי", 'ש"ח', "תנובה"]
    assert lexicon_words("חלב חלב") == ["חלב"]


# --------------------------------------------------------------------------- pseudo (D1)
@pytest.mark.parametrize("name, hit", [
    ("הנ.קופון מאגדת יוגורט תנובה", "discount_coupon_first_word"),
    ("קופון 15% שוקו תנובה", "coupon_first_word"),
    ("הנחת קופון שוקו", "discount_coupon_first_word"),
    ("קופסת שימורים", None),
    ("שוקולד עם קופון בפנים", None),     # only the first word counts
    ("קופה", None),
    # SU11A-46: a dot after the ה (7290000000435-style coupon names)
    ("ה.נ קופון מאגדת יוגורט", "discount_coupon_first_word"),
    ("ה.נ.קופון שוקו תנובה", "discount_coupon_first_word"),
    ("ה.נ. קופון קוטג'", "discount_coupon_first_word"),
    ("הנ קופון במבה", "discount_coupon_first_word"),
    # real products that merely contain קופ...
    ("שקופות 50 יח'", None),
    ("שקיות שקופות לאוכל", None),
    ("כוסות שקופות 200 מ\"ל", None),
    ("קופסה מרובעת", None),
    ("קופסאות אחסון 3 יח'", None),
    ("קופסת אוכל לילדים", None),
    ("ה.נ שקופות", None),
])
def test_coupon_pattern(name, hit):
    assert coupon_pattern(normalize(name)) == hit


def test_is_pseudo_price_rule():
    assert is_pseudo("שקית", 0.01) is True
    assert is_pseudo("שקית", 0.05) is False
    assert is_pseudo("שקית", None) is False
    assert is_pseudo("קופון 10%", 9.9) is True


# --------------------------------------------------------------------------- parsing
def test_barcode_variants():
    assert V.barcode_variants("7290004131074") == ["7290004131074"]
    assert V.barcode_variants("012345678905") == ["012345678905", "0012345678905"]
    assert V.barcode_variants("0012345678905") == ["0012345678905", "012345678905"]
    assert V.barcode_variants("1234567") is None          # too short
    assert V.barcode_variants("123456789012345") is None  # too long
    assert V.barcode_variants("חלב") is None
    assert V.barcode_variants("7290 004") is None


ALIASES = {"coca cola": "קוקה קולה", "cola": "קולה", "milka": "מילקה", "zero": "זירו"}


def test_aliases_longest_match_first_and_or_semantics():
    g = V.apply_aliases(["coca", "cola", "zero"], ALIASES)
    assert [x.alts for x in g] == [["coca cola", "קוקה קולה"], ["zero", "זירו"]]
    assert all(x.alias for x in g)
    g = V.apply_aliases(["משקה", "cola"], ALIASES)
    assert [x.alts for x in g] == [["משקה"], ["cola", "קולה"]]
    assert not g[0].alias


def test_aliases_no_match_and_empty_map():
    assert [x.alts for x in V.apply_aliases(["חלב", "3%"], ALIASES)] == [["חלב"], ["3%"]]
    assert [x.alts for x in V.apply_aliases(["חלב"], {})] == [["חלב"]]


def test_where_clause_digit_and_like():
    clause, params = V.where_clause(V.apply_aliases(["חלב", "80", "3%", "milka"], ALIASES))
    assert clause.count(" AND ") == 3
    assert params["g0a0"] == "%חלב%"
    assert params["g1a0"] == "(^|[^0-9])80([^0-9]|$)"
    assert params["g2a0"] == "%3\\%%"            # literal %, escaped
    assert params["g3a0"] == "%milka%" and params["g3a1"] == "%מילקה%"


# --------------------------------------------------------------------------- typo choice
def test_choose_correction_threshold_similarity_then_freq():
    assert V.choose_correction([("תנובה", 0.5, 900), ("תנובות", 0.3, 5)]) == "תנובה"
    assert V.choose_correction([("x", 0.39, 10_000)]) is None
    assert V.choose_correction([("x", 0.40, 1)]) == "x"
    assert V.choose_correction([("a", 0.6, 1), ("b", 0.5, 1000)]) == "a"
    assert V.choose_correction([("a", 0.5, 1), ("b", 0.5, 1000)]) == "b"
    assert V.choose_correction([]) is None


def test_typo_threshold_admits_shokolad_at_0_444():
    # pg_trgm similarity('שוקולד', 'שוקלד') = 4/9 = 0.444: below the old 0.45, eligible at 0.40.
    assert V.TYPO_MIN_SIMILARITY == 0.40
    assert V.choose_correction([("שוקולד", 0.444, 5000), ("שוק", 0.30, 9000)]) == "שוקולד"


# --------------------------------------------------------------------------- tiers + ranking
def _g(*tokens, aliases=None):
    return V.apply_aliases(list(tokens), aliases or {})


def test_tiers():
    g = _g("חלב")
    assert V.assign_tier("חלב 3% תנובה", "תנובה", g, "חלב") == 0
    assert V.assign_tier("משקה חלב סויה", "אלפרו", g, "חלב") == 1
    assert V.assign_tier("חלבה וניל", "אחווה", g, "חלב") == 2   # starts-with needs a word end
    assert V.assign_tier("שוקולד במילוי חלבה", "עלית", g, "חלב") == 2
    assert V.assign_tier("יוגורט", "חלב הארץ", g, "חלב") == 3


def test_tier_zero_when_query_is_the_manufacturer():
    assert V.assign_tier("קוטג' 5%", "תנובה", _g("תנובה"), "תנובה") == 0
    g = _g("tnuva", aliases={"tnuva": "תנובה"})
    assert V.assign_tier("קוטג' 5%", "תנובה", g, "tnuva") == 0


def test_tier_one_needs_every_word_whole():
    g = _g("חלב", "תנובה")
    assert V.assign_tier("משקה חלב", "תנובה", g, "חלב תנובה") == 1
    assert V.assign_tier("משקה חלב", "תנובות", g, "חלב תנובה") == 2


def _c(code, name, chains=1, pop=0, mfr=""):
    return {"item_code": code, "name_norm": name, "manufacturer_norm": mfr, "chains_live": chains,
            "popularity": pop, "promo_only": False, "is_pseudo": False}


def test_rank_order_is_price_neutral():
    cands = [
        _c("9", "חלבה", chains=9),                 # tier 2
        _c("5", "משקה חלב", chains=1),             # tier 1, single chain
        _c("4", "חלב טרי 3% בקרטון", chains=3),    # tier 0, 2+ chains, longer name
        _c("3", "חלב טרי", chains=3),              # tier 0, 2+ chains, shorter name
        _c("2", "חלב עמיד", chains=2, pop=50),     # tier 0, popular
        _c("1", "חלב עיזים", chains=1),            # tier 0, single chain
        _c("6", "יוגורט", chains=8, mfr="חלב"),   # tier 0 (query == manufacturer)
    ]
    order = [c["item_code"] for c in V.rank(cands, _g("חלב"), "חלב")]
    assert order == ["2", "6", "3", "4", "1", "5", "9"]


def test_rank_ties_break_on_chains_then_length_then_code():
    cands = [_c("b", "חלב א", chains=2), _c("a", "חלב א", chains=2), _c("c", "חלב א", chains=5)]
    assert [c["item_code"] for c in V.rank(cands, _g("חלב"), "חלב")] == ["c", "a", "b"]


# --------------------------------------------------------------------------- Eilat (D2)
EILAT_FKS = frozenset({100, 101})


def _row(code, fk, price):
    return {"item_code": code, "store_fk": fk, "item_price": price}


def test_drop_eilat_keeps_other_stores_only():
    rows = [_row("a", 100, 5.0), _row("a", 1, 6.0), _row("a", 2, 6.5)]
    assert [r["store_fk"] for r in V.drop_eilat(rows, EILAT_FKS)] == [1, 2]


def test_drop_eilat_falls_back_when_only_eilat():
    rows = [_row("a", 100, 5.0), _row("a", 101, 5.5), _row("b", 100, 1.0), _row("b", 3, 2.0)]
    out = V.drop_eilat(rows, EILAT_FKS)
    assert sorted((r["item_code"], r["store_fk"]) for r in out) == [("a", 100), ("a", 101), ("b", 3)]


def test_drop_eilat_kept_when_city_filter_includes_eilat_or_no_eilat_stores():
    rows = [_row("a", 100, 5.0), _row("a", 1, 6.0)]
    assert V.drop_eilat(rows, EILAT_FKS, city=["אילת", "באר שבע"]) == rows
    assert V.drop_eilat(rows, frozenset()) == rows
    assert len(V.drop_eilat(rows, EILAT_FKS, city=["באר שבע"])) == 1


# --------------------------------------------------------------------------- engine (fake db layer)
CATALOG = [
    _c("7290000000001", "חלב טרי 3% תנובה", chains=5, mfr="תנובה"),
    _c("7290000000002", "משקה חלב סויה", chains=2, mfr="אלפרו"),
    _c("7290000000003", "חלבה וניל", chains=4, mfr="אחווה"),
    _c("7290000000004", "שוקולד מילקה אוראו", chains=6, mfr="מונדלז"),
    _c("0012345678905", "פריט יבוא", chains=1, mfr="יבואן"),
]
COUPON = _c("7290000000099", "הנ.קופון חלב תנובה", chains=3, mfr="תנובה")
COUPON["is_pseudo"] = True


def _matches(c, groups):
    hay = c["name_norm"] + " " + c["manufacturer_norm"]
    return all(any(a in hay for a in g.alts) for g in groups)


@pytest.fixture
def fake_db(monkeypatch):
    calls = {"prices": None}
    rows = CATALOG + [COUPON]
    V._cache.built_at = None
    V._cache.lexicon = None
    monkeypatch.setattr(V, "_built_at", lambda conn: datetime.now(timezone.utc) - timedelta(hours=2))
    monkeypatch.setattr(V, "_lexicon", lambda conn: ({"milka": "מילקה"}, frozenset({100})))
    monkeypatch.setattr(V, "_candidates", lambda conn, groups: [
        dict(c) for c in rows if not c["is_pseudo"] and _matches(c, groups)])
    monkeypatch.setattr(V, "_barcode", lambda conn, codes: [dict(c) for c in rows if c["item_code"] in codes])

    def correct(conn, groups):
        fixed = [V.Group(alts=["תנובה"], corrected_from=g.alts[0]) if g.alts[0] == "תנובא" else g for g in groups]
        return fixed if fixed != groups else None
    monkeypatch.setattr(V, "_correct", correct)

    def prices(conn, codes, **kw):
        calls["prices"] = list(codes)
        out = []
        for c in codes:
            out += [{"item_code": c, "store_fk": 100, "chain_id": "e", "price": 1.0},
                    {"item_code": c, "store_fk": 1, "chain_id": "x", "price": 2.0}]
        return out
    monkeypatch.setattr(V, "fetch_prices", prices)
    monkeypatch.setattr(V, "group_by_product", lambda rows: {
        r["item_code"]: {"item_code": r["item_code"], "fks": sorted({x["store_fk"] for x in rows
                                                                   if x["item_code"] == r["item_code"]})}
        for r in rows})
    return calls


def test_run_counts_ranks_and_prices_only_the_page(fake_db):
    r = V.run(None, "חלב", limit=2, offset=0)
    assert r.total_matches == 3                    # coupon pseudo-item excluded
    assert r.comparable_count == 3
    assert [p["item_code"] for p in r.products] == ["7290000000001", "7290000000002"]
    assert fake_db["prices"] == ["7290000000001", "7290000000002"]   # only the page
    assert r.has_more is True
    assert all(p["fks"] == [1] for p in r.products)                  # Eilat quote dropped
    r2 = V.run(None, "חלב", limit=2, offset=2)
    assert [p["item_code"] for p in r2.products] == ["7290000000003"] and r2.has_more is False


def test_run_short_query_alias_typo_barcode(fake_db):
    assert V.run(None, "ק").total_matches == 0
    assert fake_db["prices"] is None
    r = V.run(None, "Milka")
    assert [p["item_code"] for p in r.products] == ["7290000000004"]
    r = V.run(None, "חלב תנובא")
    assert r.corrected_from == "חלב תנובא" and [p["item_code"] for p in r.products] == ["7290000000001"]
    assert V.run(None, "חלב").corrected_from is None
    r = V.run(None, "012345678905")                 # UPC-A -> EAN-13 with leading 0
    assert [p["item_code"] for p in r.products] == ["0012345678905"]


def test_run_refuses_stale_or_empty(monkeypatch, fake_db):
    monkeypatch.setattr(V, "_built_at", lambda conn: datetime.now(timezone.utc) - timedelta(hours=49))
    with pytest.raises(V.V2Unavailable):
        V.run(None, "חלב")
    monkeypatch.setattr(V, "_built_at", lambda conn: None)
    with pytest.raises(V.V2Unavailable):
        V.run(None, "חלב")


# --------------------------------------------------------------------------- SEARCH_V2 switch
@pytest.mark.parametrize("mode, engine, city, chain, group_by, want", [
    ("off", "v2", None, None, "chain", False),
    ("test", None, None, None, "chain", False),
    ("test", "v2", None, None, "chain", True),
    ("test", "v2", ["תל אביב"], None, "chain", False),
    ("test", "v2", None, ["7290027600007"], "chain", False),
    ("test", "v2", None, None, "store", False),
    ("on", None, None, None, "chain", True),
    ("on", "v1", None, None, "chain", False),
    ("on", None, ["אילת"], None, "chain", False),
])
def test_use_v2(mode, engine, city, chain, group_by, want):
    assert R._use_v2(mode, engine, city, chain, group_by) is want


@pytest.mark.parametrize("env, want", [(None, "off"), ("", "off"), ("ON", "on"), (" test ", "test"),
                                       ("yes", "off")])
def test_v2_mode(monkeypatch, env, want):
    if env is None:
        monkeypatch.delenv("SEARCH_V2", raising=False)
    else:
        monkeypatch.setenv("SEARCH_V2", env)
    assert R._v2_mode() == want


class _Conn:
    """Stands in for the request Connection: only begin_nested is used by the router."""
    def __init__(self):
        self.savepoints = 0

    def begin_nested(self):
        conn = self

        class _SP:
            def __enter__(self):
                conn.savepoints += 1

            def __exit__(self, *exc):
                return False
        return _SP()


def _search(**kw):
    args = dict(q="חלב", limit=30, offset=0, city=None, chain=None, group_by="chain", engine=None, conn=_Conn())
    args.update(kw)
    return R.search(**args)


@pytest.fixture
def old_path(monkeypatch):
    calls = []
    monkeypatch.setattr(R, "_build_result", lambda *a, **kw: calls.append(a) or "OLD")
    return calls


def test_flag_off_never_touches_v2(monkeypatch, old_path):
    monkeypatch.delenv("SEARCH_V2", raising=False)
    monkeypatch.setattr(V, "run", lambda *a, **kw: pytest.fail("v2 called with the flag off"))
    assert _search(engine="v2") == "OLD"


def test_v2_failure_falls_back_to_old_path(monkeypatch, old_path, caplog):
    monkeypatch.setenv("SEARCH_V2", "on")

    def boom(*a, **kw):
        raise RuntimeError("relation search_items does not exist")
    monkeypatch.setattr(V, "run", boom)
    assert _search() == "OLD"
    assert "search v2 failed" in caplog.text
    monkeypatch.setattr(V, "run", lambda *a, **kw: (_ for _ in ()).throw(V.V2Unavailable("stale")))
    assert _search() == "OLD"
    assert "unavailable" in caplog.text


def test_v2_answer_has_engine_and_corrected_from(monkeypatch, old_path):
    import json
    monkeypatch.setenv("SEARCH_V2", "test")
    monkeypatch.setattr(V, "run", lambda *a, **kw: V.V2Result(
        query="חלב תנובא", total_matches=0, comparable_count=0, has_more=False, products=[],
        corrected_from="חלב תנובא"))
    resp = _search(q="חלב תנובא", engine="v2")
    body = json.loads(resp.body)
    assert body["engine"] == "v2" and body["corrected_from"] == "חלב תנובא"
    assert set(body) == {"query", "total_matches", "comparable_count", "has_more", "items",
                         "engine", "corrected_from"}
    assert old_path == []
