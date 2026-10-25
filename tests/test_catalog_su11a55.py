"""SU11A-55 catalog v1.1: the rule fixes behind Dude's 20 review corrections, the new
grammar (head anchor "^", feature token §pct, hard negative "!"), brand pins, and the
graded review file. Every fix has the item it was made for plus guards against
collateral damage. No database.
"""
import csv

import pytest

import scripts.catalog.classify_rules as C
import scripts.catalog.combine as M

CAT = C.ROOT / "docs" / "catalog"


@pytest.fixture(scope="module")
def v11():
    return C.load_taxonomy(), C.load_gs1_map(), C.load_brand_hints()


def cls(v11, name, group=""):
    tax, gmap, hints = v11
    return C.combine_gs1(tax, C.classify_rules(tax, name, hints), gmap.get(group))


def under(got: str, want: str) -> bool:
    return got == want or got.startswith(want + ".")


# ----------------------------------------------------------------- files
def test_v11_has_exactly_the_v1_nodes(v11):
    tax = v11[0]
    v1 = C.load_taxonomy(CAT / "taxonomy_v1.csv")
    assert C.TAXONOMY_VERSION == "v1.1"
    assert list(v1.nodes) == list(tax.nodes)
    for nid, n in v1.nodes.items():
        m = tax.nodes[nid]
        assert (m.parent, m.level, m.name_he, m.name_en, m.attributes) == (n.parent, n.level, n.name_he,
                                                                           n.name_en, n.attributes)


def test_v11_hints_and_pin(v11):
    hints = v11[2]
    tivall = [h for hs in hints.values() for h in hs if h.brand == "טבעול"]
    assert len(tivall) == 1 and tivall[0].pin and tivall[0].category_id == "D06.C08"
    assert sum(h.pin for hs in hints.values() for h in hs) == 1


def test_review_graded_v1_file(v11):
    tax = v11[0]
    rows = list(csv.DictReader(open(CAT / "review_graded_v1.csv", encoding="utf-8", newline="")))
    src = list(csv.DictReader(open(CAT / "review_sample_v1.csv", encoding="utf-8", newline="")))
    assert len(rows) == len(src) == 150
    assert [r["item_code"] for r in rows] == [r["item_code"] for r in src]      # codes from the CSV, as text
    assert all(r["correct_category_id"] in tax.nodes for r in rows)
    assert sum(1 for r in rows if r["graded_text"]) == 20
    assert all(r["correct_category_id"] == r["predicted_category_id"] for r in rows if not r["graded_text"])
    assert [int(r["xlsx_row"]) for r in rows] == list(range(2, 152))


# ----------------------------------------------------------------- grammar
def test_head_anchor():
    r = C.parse_rule("^אפרסק", "X")
    assert r.parts[0][0].head
    assert C.match_rule(r, C.tokens("אפרסק צהוב"))
    assert C.match_rule(r, C.tokens("מארז אפרסק"))                   # pack words do not count
    assert not C.match_rule(r, C.tokens("פרוטאין אפרסק"))


def test_pct_feature():
    assert C.feature_tokens("פרוטאין אפרסק 1.6% 200 ג") == ["§pct"]
    assert C.feature_tokens("יופלה 3 % תות") == ["§pct"]
    assert C.feature_tokens("פרוטאין אפרסק 200 ג") == []
    assert "§pct" not in C.tokens("§pct x")                          # a real name cannot fake it
    r = C.parse_rule("פרוטאין+§pct", "D02.C03")
    toks = C.tokens("פרוטאין קוקוס 0% שומ") + C.feature_tokens("פרוטאין קוקוס 0% שומ")
    assert C.match_rule(r, toks) == (0, 2)
    assert not C.is_content("§pct")                                  # the feature token is never a content word


def test_hard_negative_refuses_gs1_plain_does_not(v11):
    tax = v11[0]
    assert C.parse_rule("!רסק", "D01.C04", negative=True).hard
    assert not C.parse_rule("רסק", "D01.C04", negative=True).hard
    # apple sauce in the GS1 group Apples: the hard negative of fresh fruit wins
    assert cls(v11, "רסק תפוחים ללא תוספת סוכר 710 גרם", "Apples").category_id == "D13.C04"
    # plain negatives keep stopping keywords only: GS1 still decides here (v1 behaviour)
    assert cls(v11, "קפה נמס עלית בטעם וניל 200 גרם", "Coffee - Instant").category_id == "D09.C08.S01"


# ----------------------------------------------------------------- the fixes (item it was made for + guards)
@pytest.mark.parametrize("name,group,want", [
    # F1 fresh fruit needs evidence
    ("פרוטאין אפרסק 1.6% 200 ג", "", "D02.C03"),                       # row 15 (with F2)
    ("פירות אקזוטיים", "", ""),                                          # row 113: no longer fresh fruit
    ("סקיטלס פירות יער 152 גרם", "", "!D01.C04"),
    ("תענוג פרי משמש 600 גרם", "", "!D01.C04"),
    ("ציזקייק פטל 400 גר", "", "!D09.C05"),
    ("בננה", "", "D01.C04"),
    ("תפוח עץ פינק ליידי במשקל", "", "D01.C04"),
    ("אבוקדו האס", "", "D01.C04"),
    ("פירות תוצרת חוץ שקיל", "", "D01.C04"),
    ("חצי אבטיח", "", "D01.C04"),
    ("גרגירי רימון 230 גר'", "", "D01.C04"),
    ("פטל ענבים 1.5 ליטר", "", "D09.C05"),
    # F2 protein + %
    ("פרוטאין קוקוס 0% שומ", "", "D02.C03"),
    ("טיםס -לחם שטוח 20% פרוטאין 270 גרם", "", "D05.C01"),
    # F3 flavoured water
    ("שוופס מים בטעמים ענבים 1.5 ל'", "Drinks Flavoured - Ready to Drink", "D09.C01"),   # row 39
    ("שוופס למון ליים 1.5 ל'", "Drinks Flavoured - Ready to Drink", "D09.C03"),
    ("שוופס פרוט ווטר אבטיח 1.5 ל'", "Drinks Flavoured - Ready to Drink", "D09.C03.S02"),  # confirmed row 70
    ("מים בטעם אפרסק 1.5 ל' נביעות", "", "D09.C01"),
    # F5 dragée
    ("דרגיה דובדובן לבן 500 גר PRISCO MAX", "", "D08.C01"),            # row 142
    # F6 nut mixes
    ("מעורב מובחר טבעי שקיל", "", "D08.C09"),                          # row 116
    ("מעורב טבעי תפזורת", "", "D08.C09"),
    ("מעורב ירושלמי טרי", "", "D03"),
    ("מעורב ישראלי מקוצב פרימיום טרי לצלייה בלבד", "", "D03"),
    # F7 רסק by context
    ("רסק תפוחים בטעם תות", "", "D13.C04"),                            # row 128
    ("רסק 22% רויאמיל 600 .", "", "D07.C08"),                          # row 143
    ("רסק עגבניות 28% 580", "", "D07.C08"),
    # F8 product lines
    ("סיני מיניס 500 גרם", "", "D07.C22"),                             # row 9
    ("דליפקאן 400 גר", "", "D07.C22"),                                 # row 81
    ("ויטמינצ'יק אננס 1 ליטר", "", "D09.C05"),                         # row 60
    ("ויטמינציק קרחון ענבי", "", "!D09.C05"),
    ("אכו שבועון", "", "D16.C07"),                                     # row 103
    ("מאנצ'ס תפזורת", "", "D08.C09"),                                  # row 124
    # F9 schnecken
    ("שנק קינמון בונז`ור", "", "D05.C06"),                             # row 106
    ("בונז'ור שנק פיצה", "", "D06.C04"),
    ("קינמון טחון 100 גרם", "", "D07.C14"),
    # F10 cabbage / mayo salads
    ("כרוב חמוציות 500 גר", "", "D04.C03"),                            # row 109
    ("כרוב אדום במיונז 250", "", "D04.C03"),
    ("כרוב לבן", "", "D01.C01"),
    ("חמוציות מיובשות 200 גרם", "", "D01.C05"),
    # F11 tapas
    ("טאפס פלפל אדום", "", "D02.C02"),                                 # row 111
    ("פלפל אדום", "", "D01.C01"),
    # F12 wok
    ("מנה חמה ווק נודלס ברוטב מוקפץ 70 גרם", "", "D07.C02"),           # row 13
    ("מחבת ווק 28 ס\"מ", "", "D15.C01"),
    # F13 Dubonim
    ("מארז דובונים 5*20 גר", "", "D08.C05"),                           # row 127
    ("הריבו דובונים 100 גרם", "", "D08.C02"),
    ("סוכריות גומי דובונים", "", "D08.C02"),
    # F14 cultured soy
    ("מעדן סויה ביו טבעי", "Dairy_Dairy Substitute Based Drinks - Ready to Drink (Perishable)", "D02.C03"),  # row 59
    ("מעדן שוקולד 4 יח'", "", "D02.C04"),
    ("רוטב סויה 500 מ\"ל", "", "D07.C10"),
])
def test_v11_fixes(v11, name, group, want):
    got = cls(v11, name, group).category_id
    if want.startswith("!"):
        assert not under(got, want[1:]), got
    elif not want:
        assert got == "", got
    else:
        assert under(got, want), got


def test_fixed_rows_are_high_where_ai_would_otherwise_override(v11):
    # rule high -> the AI label is never consulted (combine_label)
    for name, group in (("מעדן סויה ביו טבעי", "Dairy_Dairy Substitute Based Drinks - Ready to Drink (Perishable)"),
                        ("מנה חמה ווק נודלס ברוטב מוקפץ 70 גרם", ""), ("דליפקאן 400 גר", ""),
                        ("כרוב חמוציות 500 גר", ""), ("מעורב מובחר טבעי שקיל", "")):
        assert cls(v11, name, group).confidence == "high", name


# ----------------------------------------------------------------- F4 brand pin
def test_tivall_pin(v11):
    tax, _, _ = v11
    r = cls(v11, "חטיפי תירס טבעול 657 גר")                            # row 86
    assert r.category_id.startswith("D06") and r.pinned == "D06"
    assert cls(v11, "טבעול שניצל תירס 750 גרם").category_id.startswith("D06")
    assert cls(v11, "נקניקיות וינר צמחוניות 680 גרם טבעול").category_id.startswith("D06")
    # a GS1 group outside the department cannot move it
    g = C.combine_gs1(tax, r, ("D08.C05", "high"))
    assert g.category_id == r.category_id
    # nor can an AI label outside it; one inside it still may
    rule = {"category_id": r.category_id, "confidence": "medium", "reason": r.reason, "keyword": r.keyword,
            "pinned": r.pinned}
    out = M.combine_label(rule, {"category_id": "D08.C05.S02", "confidence": "high", "reason": "corn puffs",
                                 "model": "m"}, set(tax.nodes))
    assert out["category_id"] == r.category_id and out["source"] == "rule"
    out = M.combine_label(rule, {"category_id": "D06.C05", "confidence": "high", "reason": "nuggets",
                                 "model": "m"}, set(tax.nodes))
    assert out["source"] == "ai" and out["category_id"] == "D06.C05"


def test_unpinned_brand_hint_unchanged(v11):
    # SU11A-52 hints keep their behaviour (שמיר = hummus brand, alone = the herb)
    assert cls(v11, "שמיר גורמה חומוס 200 גרם").category_id.startswith("D04.C02")
    assert cls(v11, "שמיר במשקל").category_id.startswith("D01.C02")
    assert cls(v11, "שמיר גורמה חומוס 200 גרם").pinned == ""
