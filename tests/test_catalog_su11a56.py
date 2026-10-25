"""SU11A-56 catalog v1.2: Dude's decisions on P1-P4 (still soft drinks, newspapers, the
shelf-stable pickles / olives storage split, no dragée sub-type), the GS1-only negative,
row feature tokens, and the Sonnet 5.5 request shape. No database, no API.
"""
import csv

import pytest

import scripts.catalog.classify_ai as A
import scripts.catalog.classify_rules as C
import scripts.catalog.combine as M

CAT = C.ROOT / "docs" / "catalog"
NEW = {"D09.C11": "D09", "D16.C08": "D16", "D07.C08.S01": "D07.C08"}


@pytest.fixture(scope="module")
def v12():
    return C.load_taxonomy(), C.load_gs1_map(), C.load_brand_hints()


def cls(v12, name, group="", code="", weighted=None):
    tax, gmap, hints = v12
    res = C.classify_rules(tax, name, hints, C.row_features(code, weighted))
    return C.combine_gs1(tax, res, gmap.get(group))


def under(got, want):
    return got == want or got.startswith(want + ".")


# ----------------------------------------------------------------- files
def test_v12_keeps_every_v11_id_and_adds_three(v12):
    tax = v12[0]
    v11 = C.load_taxonomy(CAT / "taxonomy_v1_1.csv")
    assert C.TAXONOMY_VERSION == "v1.2"
    assert set(tax.nodes) - set(v11.nodes) == set(NEW)
    assert set(v11.nodes) <= set(tax.nodes)
    for nid, n in v11.nodes.items():
        assert (tax.nodes[nid].parent, tax.nodes[nid].level, tax.nodes[nid].name_he) == (n.parent, n.level, n.name_he)
    for nid, parent in NEW.items():
        assert tax.nodes[nid].parent == parent
    assert tax.nodes["D09.C11"].name_he == "משקאות קלים לא מוגזים"
    assert tax.nodes["D16.C08"].name_he == "עיתונים ומגזינים"
    assert tax.nodes["D07.C08.S01"].name_he == "חמוצים וזיתים בשימורים"
    assert not [n for n in tax.nodes if "דרג" in tax.nodes[n].name_he]           # P4: no dragée node
    order = list(tax.nodes)
    for nid in tax.nodes:                                                       # parents before children
        assert not tax.nodes[nid].parent or order.index(tax.nodes[nid].parent) < order.index(nid)


def test_v12_gs1_map(v12):
    gmap = v12[1]
    assert gmap["Fruit Juice Drinks - Ready to Drink (Shelf Stable)"][0] == "D09.C11"
    assert gmap["Olives (Shelf Stable)"][0] == "D07.C08.S01"
    assert gmap["Fruit Juice - Ready to Drink (Shelf Stable)"][0] == "D09.C04"
    assert all(cid in v12[0].nodes for cid, _ in gmap.values())


def test_graded_review_rows_moved(v12):
    rows = {r["xlsx_row"]: r for r in csv.DictReader(open(CAT / "review_graded_v1.csv", encoding="utf-8"))}
    assert rows["39"]["correct_category_id"] == "D09.C11" and rows["113"]["correct_category_id"] == "D09.C11"
    assert rows["103"]["correct_category_id"] == "D16.C08"
    assert rows["54"]["correct_category_id"] == "D07.C08.S01"
    assert all(r["correct_category_id"] in v12[0].nodes for r in rows.values())


# ----------------------------------------------------------------- P1 still soft drinks
@pytest.mark.parametrize("name,group,want", [
    ("שוופס מים בטעמים ענבים 1.5 ל'", "Drinks Flavoured - Ready to Drink", "D09.C11"),
    ("מים בטעם אפרסק 1.5 ל' נביעות", "", "D09.C11"),
    ("ספרינג תפוחים 1.5 ל'", "Fruit Juice - Ready to Drink (Shelf Stable)", "D09.C11"),  # GS1 juice group refused
    ("ספרינג מנגו 1 ל' קרטונית", "Fruit Juice Drinks - Ready to Drink (Shelf Stable)", "D09.C11"),
    ("תפוזינה משקה תפוזים 1.5 ל'", "", "D09.C11"),
    ("מוגו מוגו ליצ'י עם חתיכות ג'לי קוקוס 1ל", "", "D09.C11"),
    ("ספרינג נקטר מנגו 330 מ\"ל פחית", "", "D09.C04"),                                # nectar stays juice
    ("100% מיץ תפוזים מיוצר מרכז תפוזים טבעי", "Fruit Juice Drinks - Ready to Drink (Shelf Stable)", "D09.C04"),
    ("פריגת מיץ תפוזים 1 ליטר", "", "D09.C04"),
    ("שוופס פרוט ווטר אבטיח 1.5 ל'", "Drinks Flavoured - Ready to Drink", "D09.C03.S02"),
    ("קוקה קולה 1.5 ליטר", "", "D09.C03.S01"),
    ("נביעות מים מינרליים 1.5 ליטר", "", "D09.C01"),
    ("פיוז טי זירו אפרסק 1.5", "", "D09.C07"),
])
def test_p1_still_soft_drinks(v12, name, group, want):
    got = cls(v12, name, group).category_id
    assert under(got, want), got


def test_p1_flavoured_water_is_high(v12):
    assert cls(v12, "מים בטעם ענבים נביעות 500 מ\"ל").confidence == "high"


def test_gs1_only_negative_grammar():
    r = C.parse_rule("~ספרינג", "D09.C04", negative=True)
    assert r.hard and r.gs1_only
    r = C.parse_rule("!רסק", "D01.C04", negative=True)
    assert r.hard and not r.gs1_only


# ----------------------------------------------------------------- P2 newspapers
@pytest.mark.parametrize("name,want", [
    ("עיתון הארץ שישי", "D16.C08"), ("אכו שבועון", "D16.C08"), ("מגזין \"כדור\"", "D16.C08"),
    ("מחברת 40 דף", "D16.C07"), ("ספר ילדים רותי", "D16.C07"),
])
def test_p2_newspapers(v12, name, want):
    assert cls(v12, name).category_id == want


# ----------------------------------------------------------------- P3 storage split
@pytest.mark.parametrize("name,group,code,weighted,want", [
    ("זיתים ירוקים בלי גלעינים יכין 560 גרם", "", "7290018989807", "0", "D07.C08.S01"),   # size + shelf brand
    ("מלפפונים בחומץ 680 ג", "", "8936019610102", "0", "D07.C08.S01"),
    ("ויליפוד זיתים שחורים מזן קלמטה במי מלח בפח 454 גרם", "", "5201940010110", "0", "D07.C08.S01"),
    ("זיתים טבעיים קלמטה צנצנת זכוכית", "", "7290012212161", "", "D07.C08.S01"),          # jar word
    ("מלפפונים בחומץ עם עלה דובדבן", "", "5904603190906", "0", "D07.C08.S01"),            # imported GTIN
    ("זיתים ירוקים שלמים", "Olives (Shelf Stable)", "7290000000001", "0", "D07.C08.S01"),
    ("זית סורי שקיל", "", "9077575", "1", "D04.C05"),                                     # weighed
    ("זיתים במשקל", "", "7290003155965", "1", "D04.C05"),
    ("מלפפון במלח במשקל", "", "329316", "1", "D04.C05"),
    ("זית ממולא", "", "6441", "1", "D04.C05"),                                           # store code
    ("זיתים ירוקים 500 גרם", "", "6952", "", "D04.C05"),                                 # size but store code
    ("זיתים מעדנייה 400 גרם", "", "7290000000002", "0", "D04.C05"),                     # deli word wins
    ("מלפפון בחומץ 13-17 ב", "", "7290113192492", "0", "D04.C05"),                       # no evidence: deli
    ("רסק עגבניות 28% 580", "", "7290000355498", "0", "D07.C08"),                        # not a pickle: untouched
])
def test_p3_storage_split(v12, name, group, code, weighted, want):
    got = cls(v12, name, group, code, weighted).category_id
    assert got == want, got


def test_row_features_and_storage():
    assert C.row_features("6952") == ["§weighed"]
    assert C.row_features("7290018989807", "1") == ["§weighed"]
    assert C.row_features("7290018989807", "0") == []
    assert C.row_features("5904603190906") == ["§import"]
    assert C.storage_of(C.tokens("זיתים שקיל") + ["§size"]) == "deli"
    assert C.storage_of(C.tokens("זיתים") + ["§size"]) == "shelf"
    assert C.storage_of(C.tokens("זיתים")) == ""
    assert C.split_storage("D04.C05", "shelf", {"D07.C08.S01"}) == "D07.C08.S01"
    assert C.split_storage("D04.C05", "shelf", {"D04.C05"}) == "D04.C05"        # older taxonomy: no split
    assert C.split_storage("D07.C08", "shelf", {"D07.C08.S01"}) == "D07.C08"


def test_combine_reads_ai_pickles_by_storage(v12):
    valid = set(v12[0].nodes)
    rule = {"category_id": "D07.C08.S01", "confidence": "medium", "reason": "rule", "keyword": "זיתים",
            "storage": "shelf"}
    out = M.combine_label(rule, {"category_id": "D04.C05", "confidence": "high", "reason": "olives", "model": "m"},
                          valid)
    assert out["category_id"] == "D07.C08.S01" and not out["disagreement"]
    rule = {"category_id": "", "confidence": "", "reason": "", "keyword": "", "storage": "shelf"}
    out = M.combine_label(rule, {"category_id": "D04.C05", "confidence": "high", "reason": "olives", "model": "m"},
                          valid)
    assert out["category_id"] == "D07.C08.S01" and out["source"] == "ai"
    rule["storage"] = "deli"
    out = M.combine_label(rule, {"category_id": "D04.C05", "confidence": "high", "reason": "olives", "model": "m"},
                          valid)
    assert out["category_id"] == "D04.C05"


# ----------------------------------------------------------------- P4
@pytest.mark.parametrize("name,want", [
    ("דרגיה דובדובן לבן 500 גר PRISCO MAX", "D08.C01"),
    ("דרגיה שקד מריר 500 גר PRISCO MAX", "D08.C01"),
    ("פטל קפוא מצופה בשוקו", "D06.C02"),          # frozen chocolate-coated fruit stays frozen (decision open)
])
def test_p4_dragee(v12, name, want):
    assert under(cls(v12, name).category_id, want)


# ----------------------------------------------------------------- AI request shape (no API)
class _Resp:
    def __init__(self):
        self.content = [type("B", (), {"type": "text", "text": '{"items": []}'})()]
        self.usage = {"input_tokens": 1, "output_tokens": 1}
        self.stop_reason = "end_turn"


class _Client:
    def __init__(self):
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return _Resp()


@pytest.mark.parametrize("model,thinking", [
    ("claude-sonnet-5-5", {"type": "between_tools"}),      # Sonnet 5.5 rejects "disabled"
    ("claude-haiku-5-5", {"type": "disabled"}),
])
def test_thinking_off_per_model(model, thinking):
    c = _Client()
    A.call_batch(c, model, "sys", {"type": "object"}, [{"i": 0, "n": "x"}], 100)
    assert c.calls[0]["thinking"] == thinking


def test_prompt_knows_v12(v12):
    sp = A.system_prompt(v12[0])
    for nid in NEW:
        assert f"\n{nid} | " in sp
    assert "D07.C08.S01" in A.INSTRUCTIONS and "D09.C11" in A.INSTRUCTIONS and "D16.C08" in A.INSTRUCTIONS
    assert "Pickles and olives are deli (D04.C05)" not in A.INSTRUCTIONS
