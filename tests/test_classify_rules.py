"""SU11A-51 rule classifier prototype: precedence, negatives, GS1, priors, attributes.

Small hand-written taxonomies (tmp CSV) so each rule is tested in isolation, plus
integrity checks on the committed docs/catalog CSVs.
"""
import csv
from collections import Counter

import pytest

import scripts.catalog.classify_rules as C

COLS = ["id", "level", "parent_id", "name_he", "name_en", "keywords_he", "negative_keywords_he", "attributes", "notes"]


def _tax(tmp_path, rows):
    p = tmp_path / "tax.csv"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        for r in rows:
            w.writerow(list(r) + [""] * (len(COLS) - len(r)))
    return C.load_taxonomy(p)


@pytest.fixture
def tax(tmp_path):
    return _tax(tmp_path, [
        ("D01", "department", "", "פירות וירקות", "Produce", "", "קפוא*", "brand|size_value|size_unit|pack_count"),
        ("D01.C01", "category", "D01", "ירקות", "Vegetables", "עגבניות|פלפל|מלפפונים", "רוטב|חמוצים|שחור"),
        ("D02", "department", "", "חלב", "Dairy", "", "", "brand|size_value|size_unit|fat_pct|kosher_level"),
        ("D02.C01", "category", "D02", "חלב", "Milk", "חלב", "שוקולד"),
        ("D02.C01.S01", "subtype", "D02.C01", "שוקו", "Choc milk", "שוקו|משקה חלב"),
        ("D02.C02", "category", "D02", "גבינות", "Cheese", "גבינה|גבינת"),
        ("D02.C02.S01", "subtype", "D02.C02", "צהובות", "Yellow", "גאודה|צהובה"),
        ("D03", "department", "", "בשר", "Meat", "בשר", "", "brand|kosher_level|state"),
        ("D03.C01", "category", "D03", "עוף", "Chicken", "עוף|חזה עוף|שניצל+טרי"),
        ("D04", "department", "", "מזווה", "Pantry", "", ""),
        ("D04.C01", "category", "D04", "רטבים", "Sauces", "רוטב|רוטב עגבניות"),
        ("D04.C02", "category", "D04", "תבלינים", "Spices", "פלפל שחור|פפריקה"),
        ("D04.C03", "category", "D04", "חמוצים", "Pickles", "חמוצים|מלפפון,מלפפונים+בחומץ,כבוש*"),
        ("D05", "department", "", "קפואים", "Frozen", "", ""),
        ("D05.C01", "category", "D05", "ירקות קפואים", "Frozen veg", "אפונה,שעועית+קפוא*|מעושן*"),
        ("D06", "department", "", "אלכוהול", "Alcohol", "", "", "alcohol_pct"),
        ("D06.C01", "category", "D06", "בירה", "Beer", "בירה"),
        ("D07", "department", "", "ניקיון", "Cleaning", "", ""),
        ("D07.C01", "category", "D07", "ניקוי", "Cleaners", "סנו"),
        ("D07.C02", "category", "D07", "כביסה", "Laundry", "סנו"),
    ])


# ----------------------------------------------------------------- tokens / skip / glue
def test_tokens_split_hebrew_glued_to_numbers():
    assert C.tokens("מלפפונים בחומץ560ג") == ["מלפפונים", "בחומץ", "560", "ג"]


def test_tokens_normalise_quotes_and_dashes():
    assert C.tokens("קוקה-קולה 1.5 ל׳") == ["קוקה", "קולה", "1.5", "ל"]


def test_skip_words_and_numbers_do_not_count_as_position():
    eff, head = C.content_index(["מארז", "6", "חלב", "3%"])
    assert eff[2] == 0 and head == 4


def test_connector_ends_the_head_but_not_at_index_zero():
    _, head = C.content_index(["חלב", "בטעם", "וניל"])
    assert head == 1
    _, head0 = C.content_index(["על", "האש"])
    assert head0 == 2


# ----------------------------------------------------------------- precedence
def test_simple_match_is_high(tax):
    r = C.classify_rules(tax, "עגבניות שרי 500 גרם")
    assert (r.category_id, r.confidence, r.reason) == ("D01.C01", "high", "rule")


def test_negative_vetoes_the_node(tax):
    # "רוטב" vetoes vegetables; sauces win.
    r = C.classify_rules(tax, "רוטב עגבניות")
    assert r.category_id == "D04.C01"
    assert r.confidence == "high"   # the only remaining category in the head


def test_department_negative_vetoes_its_categories(tax):
    assert C.classify_rules(tax, "פלפל קפוא").category_id == ""


def test_longer_phrase_beats_shorter_at_same_position(tax):
    # פלפל (veg, 1 token, vetoed by שחור anyway) vs פלפל שחור (spices, 2 tokens)
    r = C.classify_rules(tax, "פלפל שחור גרוס")
    assert r.category_id == "D04.C02" and r.keyword == "פלפל שחור"


def test_earliest_position_wins_and_rival_lowers_confidence(tax):
    r = C.classify_rules(tax, "גבינה עם עגבניות")
    # עגבניות is after the connector "עם" -> not a head rival -> high
    assert (r.category_id, r.confidence) == ("D02.C02", "high")
    r2 = C.classify_rules(tax, "גבינה עגבניות")
    assert (r2.category_id, r2.confidence) == ("D02.C02", "medium")


def test_deepest_subtype_of_winning_category_is_reported(tax):
    r = C.classify_rules(tax, "גבינת גאודה 28%")
    assert r.category_id == "D02.C02.S01"


def test_subtype_inherits_parent_negative(tax):
    # שוקולד is a negative of D02.C01; the subtype keyword שוקו must not survive it.
    assert C.classify_rules(tax, "שוקו שוקולד").category_id == ""


def test_tie_between_categories_is_low(tax):
    r = C.classify_rules(tax, "סנו 1 ליטר")
    assert r.confidence == "low"
    assert set((C.Taxonomy.category_of(tax, r.category_id),) + r.tied) == {"D07.C01", "D07.C02"}


def test_match_only_after_connector_is_low(tax):
    r = C.classify_rules(tax, "משהו בטעם חלב")
    assert (r.category_id, r.confidence) == ("D02.C01", "low")


def test_conjunction_needs_every_part(tax):
    assert C.classify_rules(tax, "אפונה קפואה 800 גרם").category_id == "D05.C01"
    assert C.classify_rules(tax, "אפונה 800 גרם").category_id == ""
    assert C.classify_rules(tax, "מלפפונים קטנים בחומץ 560 ג").category_id == "D04.C03"


def test_prefix_keyword_matches_across_final_letters(tax):
    # מעושן* (final nun) must match מעושנת
    assert C.classify_rules(tax, "דג מעושנת").category_id == "D05.C01"
    assert C.classify_rules(tax, "חתיכה כבושים").category_id == ""   # conjunction still needs מלפפון


def test_department_keyword_is_capped_at_medium(tax):
    r = C.classify_rules(tax, "בשר ב- 50")
    assert (r.category_id, r.confidence) == ("D03", "medium")


def test_department_word_yields_to_a_category_of_the_same_department(tax):
    r = C.classify_rules(tax, "בשר חזה עוף")
    assert r.category_id == "D03.C01"


def test_conjunction_raw_schnitzel(tax):
    assert C.classify_rules(tax, "שניצל עוף טרי דק").category_id == "D03.C01"


def test_unmatched_name_is_unclassified(tax):
    r = C.classify_rules(tax, "מטריה כחולה")
    assert (r.category_id, r.confidence, r.reason) == ("", "", "")


# ----------------------------------------------------------------- GS1 and priors
def test_gs1_agreement_takes_the_deeper_id(tax):
    r = C.classify_rules(tax, "גבינה 200 גרם")
    out = C.combine_gs1(tax, r, ("D02.C02.S01", "high"))
    assert (out.category_id, out.confidence, out.reason) == ("D02.C02.S01", "high", "rule+gs1")


def test_gs1_fills_an_unclassified_item(tax):
    out = C.combine_gs1(tax, C.Result(), ("D06.C01", "medium"))
    assert (out.category_id, out.confidence, out.reason) == ("D06.C01", "medium", "gs1")


def test_gs1_high_overrides_a_disagreeing_rule_at_medium(tax):
    r = C.classify_rules(tax, "גבינה")
    out = C.combine_gs1(tax, r, ("D06.C01", "high"))
    assert (out.category_id, out.confidence, out.reason, out.rule_id) == ("D06.C01", "medium", "gs1", "D02.C02")


def test_gs1_medium_disagreement_keeps_the_rule_at_low(tax):
    r = C.classify_rules(tax, "גבינה")
    out = C.combine_gs1(tax, r, ("D06", "medium"))
    assert (out.category_id, out.confidence, out.reason) == ("D02.C02", "low", "rule")


def test_prior_breaks_a_tie_only(tax):
    tie = C.classify_rules(tax, "סנו 1 ליטר")
    prior = Counter({"D07.C02": 9, "D07.C01": 1})
    out = C.apply_prior(tax, tie, prior)
    assert (out.category_id, out.reason, out.confidence) == ("D07.C02", "prior", "medium")
    clear = C.classify_rules(tax, "עגבניות")
    assert C.apply_prior(tax, clear, Counter({"D07.C02": 50})) is clear


def test_prior_needs_enough_items(tax):
    tie = C.classify_rules(tax, "סנו 1 ליטר")
    assert C.apply_prior(tax, tie, Counter({"D07.C02": 3})).reason == "rule"


def test_classify_all_uses_manufacturer_prior(tax):
    rows = [{"item_code": str(i), "name": "סנו כביסה", "manufacturer": "סנו בע\"מ"} for i in range(6)]
    rows.append({"item_code": "x", "name": "סנו 1 ליטר", "manufacturer": "סנו בע\"מ"})
    # make the six confident: give the tie item's competitor a GS1 label
    gmap = {"L": ("D07.C02", "high")}
    for r in rows[:6]:
        r["gs1_group"] = "L"
    out = C.classify_all(tax, rows, gmap)
    assert out[-1].reason == "prior" and out[-1].category_id == "D07.C02"


# ----------------------------------------------------------------- attributes
@pytest.mark.parametrize("name,want", [
    ("חלב 3% 1 ליטר", (1000.0, "ml")),
    ("קולה 1.5 ל'", (1500.0, "ml")),
    ("אורז 1 ק\"ג", (1000.0, "g")),
    ("במבה 80 גרם", (80.0, "g")),
    ("שוקולד 100 גר'", (100.0, "g")),
    ("יין 750 מ\"ל", (750.0, "ml")),
    ("טונה 160ג'", (160.0, "g")),
])
def test_parse_size(name, want):
    assert C.parse_size(C.normalize(name)) == want


def test_parse_size_none():
    assert C.parse_size(C.normalize("גבינה צהובה")) is None


@pytest.mark.parametrize("name,want", [
    ("מים 6*1.5 ליטר", 6),
    ("שישיית קולה", 6),
    ("כוסות 50 יח'", 50),
    ("רביעיית יוגורט", 4),
    ("מגבת 50x85 ס\"מ", None),      # a size, not a pack
    ("פלייסמנט 33*33", None),
    ("גבינה 200 גרם", None),
])
def test_parse_pack(name, want):
    assert C.parse_pack(C.normalize(name)) == want


def test_fat_pct_only_where_the_node_offers_it(tax):
    assert C.extract_attributes(tax, "D02.C01", "חלב 3% 1 ליטר")["fat_pct"] == 3.0
    assert "fat_pct" not in C.extract_attributes(tax, "D01.C01", "עגבניות 3%")


def test_alcohol_pct_in_alcohol_department(tax):
    a = C.extract_attributes(tax, "D06.C01", "בירה 5.4% 330 מ\"ל")
    assert a["alcohol_pct"] == 5.4 and "fat_pct" not in a


def test_kosher_markers_and_glatt_only_for_meat(tax):
    assert C.extract_attributes(tax, "D02.C01", "חלב בד\"צ 1 ליטר")["kosher_level"] == "בד\"צ"
    assert C.extract_attributes(tax, "D03.C01", "חזה עוף טרי חלק")["kosher_level"] == "חלק"
    assert "kosher_level" not in C.extract_attributes(tax, "D02.C01", "חלב חלק")


def test_kosher_type_and_level_from_gs1(tax):
    a = C.extract_attributes(tax, "D02.C01", "חלב", {"gs1_kosher": "חלבי|הרבנות הראשית לישראל"})
    assert a["kosher_level"] == "רבנות"


def test_dietary_flags_whole_words_only():
    n = C.extract_attributes(None, "", "רדיאטור 9 צלעות")
    assert "sugar_free" not in n
    assert C.extract_attributes(None, "", "קולה זירו 1.5 ליטר")["sugar_free"] is True
    assert "vegan" not in C.extract_attributes(None, "", "נתחי טונה בשמן צמחי")
    assert C.extract_attributes(None, "", "גבינה על בסיס צמחי")["vegan"] is True
    assert "organic" not in C.extract_attributes(None, "", "סיביו חי שלם")
    assert C.extract_attributes(None, "", "קינואה אורגנית 1 קג")["organic"] is True
    assert C.extract_attributes(None, "", "לחם ללא גלוטן")["gluten_free"] is True
    assert "reduced" not in C.extract_attributes(None, "", "משקה קל בטעם מנגו")
    assert C.extract_attributes(None, "", "גבינה לייט")["reduced"] is True


def test_brand_skips_placeholder_manufacturers():
    assert "brand" not in C.extract_attributes(None, "", "חלב", {"manufacturer": "לא ידוע"})
    assert C.extract_attributes(None, "", "חלב", {"manufacturer": "תנובה"})["brand"] == "תנובה"
    assert C.extract_attributes(None, "", "חלב", {"manufacturer": "לא ידוע", "gs1_brand": "יטבתה"})["brand"] == "יטבתה"


def test_flavour_and_state():
    a = C.extract_attributes(None, "", "יוגורט בטעם תות שדה 150 גרם")
    assert a["flavour"] == "תות שדה"
    assert C.extract_attributes(None, "", "פרגיות טרי")["state"] == "fresh"
    assert C.extract_attributes(None, "", "שריר קפוא")["state"] == "frozen"


# ----------------------------------------------------------------- run helpers
def test_review_sample_takes_top_chains_then_strata(tax):
    rows = [{"item_code": f"{i:04d}", "name": n, "chains_live": str(c)}
            for i, (n, c) in enumerate([("עגבניות", 14), ("גבינה", 3), ("סנו", 1), ("מטריה", 1), ("חלב", 9)])]
    res = [C.classify_rules(tax, r["name"]) for r in rows]
    s = C.review_sample(tax, rows, res, n_total=5, n_top=2)
    assert [x["item_code"] for x in s[:2]] == ["0000", "0004"]
    assert len(s) == 5 and all(x["correct_category_id"] == "" for x in s)
    assert {x["confidence"] for x in s} >= {"unclassified"}


def test_evaluate_reports_gs1_agreement(tax):
    rows = [{"item_code": "1", "name": "גבינה", "chains_live": "1", "gs1_group": "Cheese"},
            {"item_code": "2", "name": "עגבניות", "chains_live": "5", "gs1_group": "Cheese"},
            {"item_code": "3", "name": "מטריה", "chains_live": "1", "gs1_group": ""}]
    gmap = {"Cheese": ("D02.C02", "high")}
    ro = C.classify_all(tax, rows, None)
    fin = C.classify_all(tax, rows, gmap)
    rep = C.evaluate(tax, rows, fin, ro, gmap)
    g = rep["gs1_agreement"]
    assert (g["mapped_items"], g["rule_predicted"], g["accuracy_pct"]) == (2, 2, 50.0)
    assert rep["coverage_final"]["unclassified"]["items"] == 1
    assert rep["unclassified_leading_top50"] == [("מטריה", 1)]


# ----------------------------------------------------------------- committed CSVs
def test_committed_taxonomy_is_consistent():
    tax = C.load_taxonomy()
    levels = Counter(n.level for n in tax.nodes.values())
    assert levels["department"] >= 12 and 120 <= levels["category"] <= 160
    for n in tax.nodes.values():
        if n.parent:
            assert n.parent in tax.nodes and n.id.startswith(n.parent + ".")
    keys = {row["key"] for row in csv.DictReader(open(C.ROOT / "docs" / "catalog" / "attributes_v0.csv", encoding="utf-8"))}
    used = {a for n in tax.nodes.values() for a in n.attributes}
    assert used <= keys
    for r in tax.rules + tax.negatives:
        assert r.node in tax.nodes and r.parts


def test_committed_gs1_map_points_at_existing_nodes():
    tax = C.load_taxonomy()
    gmap = C.load_gs1_map()
    assert len(gmap) > 250
    assert all(cid in tax.nodes and conf in ("high", "medium") for cid, conf in gmap.values())


def test_committed_rules_on_known_names():
    tax = C.load_taxonomy()
    cases = {
        "חלב 3% 1 ליטר בקרטון": "D02.C01",
        "גבינה צהובה עמק 28% פרוסות": "D02.C02",
        "קוטג' 5% 250 גרם": "D02.C02",
        "במבה 80 גרם": "D08.C05",
        "קולה זירו 1.5 ליטר": "D09.C03",
        "נוזל כלים לימון 1 ליטר": "D11.C02",
        "אבקת כביסה אריאל 5 ק\"ג": "D11.C01",
        "שמפו לכלבים 500 מל": "D14.C03",
        "רוטב עגבניות 400 גרם": "D07.C10",
        "מלפפונים במלח 560 גרם": "D04.C05",
        "גלידת שמנת בטעם וניל": "D06.C03",
        "חזה עוף טרי": "D03.C06",
        "טונה בשמן 160 גרם": "D07.C07",
        "צלחות פלסטיק חד פעמיות 50 יח'": "D11.C10",
        "יין קברנה סוביניון 750 מל": "D10.C01",
    }
    for name, want in cases.items():
        got = C.classify_rules(tax, name).category_id
        assert tax.category_of(got) == want, (name, got)
