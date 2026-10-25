"""SU11A-52 catalog v1: precedence, service pseudo rows, nameless fallback, brand
hints, v1 rule pins, AI output validation (mocked API), combine, build hook and
import planning. No database (the Postgres side is tests/test_catalog_su11a52_pg.py).
"""
import csv
import json
from datetime import datetime, timezone

import pytest

import scripts.catalog.classify_ai as A
import scripts.catalog.classify_rules as C
import scripts.catalog.combine as M
import scripts.catalog.import_categories as I
import scripts.catalog.store as S
from db.search_norm import is_pseudo, normalize, pseudo_pattern

CAT = C.ROOT / "docs" / "catalog"


@pytest.fixture(scope="module")
def v1():
    return C.load_taxonomy(), C.load_gs1_map(), C.load_brand_hints()


# ----------------------------------------------------------------- precedence
@pytest.mark.parametrize("existing,new,ok", [
    (None, "rule", True),
    ({"source": "rule", "reviewed": False}, "rule", True),     # same source: a re-run may update
    ({"source": "rule", "reviewed": False}, "gs1", True),
    ({"source": "gs1", "reviewed": False}, "rule", False),     # never downgrade
    ({"source": "ai", "reviewed": False}, "gs1", False),
    ({"source": "ai", "reviewed": False}, "ai", True),
    ({"source": "gs1", "reviewed": False}, "ai", True),
    ({"source": "manual", "reviewed": False}, "ai", False),    # automated never beats manual
    ({"source": "rule", "reviewed": True}, "ai", False),       # reviewed rows are never touched automatically
    ({"source": "manual", "reviewed": True}, "manual", True),  # an explicit human file may
    ({"source": "ai", "reviewed": True}, "manual", True),
])
def test_may_write(existing, new, ok):
    assert S.may_write(existing, new) is ok


def test_may_write_rejects_unknown_source():
    with pytest.raises(ValueError):
        S.may_write(None, "guess")


def test_upsert_sql_guards():
    auto, man = S.upsert_item_categories_sql(False), S.upsert_item_categories_sql(True)
    assert "NOT ic.reviewed" in auto and "ic.source <> 'manual'" in auto
    assert "NOT ic.reviewed" not in man
    assert "DO NOTHING" in S.INSERT_NEW_ITEM_CATEGORIES_SQL


def test_attribute_rows():
    rows = {r["attr_key"]: r for r in S.attribute_rows("1", {"size_value": 500.0, "size_unit": "g", "organic": True,
                                                             "fat_pct": 3.0, "brand": "תנובה"}, "rule")}
    assert "size_unit" not in rows
    assert rows["size_value"]["value_num"] == 500.0 and rows["size_value"]["unit"] == "g"
    assert rows["organic"]["value_text"] == "true"
    assert rows["fat_pct"]["unit"] == "%"
    assert rows["brand"]["value_text"] == "תנובה"


# ----------------------------------------------------------------- service pseudo rows
@pytest.mark.parametrize("name,hit", [
    ("פיקדון 30 אג", "deposit_first_word"),
    ("פקדון בקבוק בירה חוזר 500", "deposit_first_word"),
    ("החזר פיקדון מכונת בקבוקים", "deposit_first_word"),
    ("ארגז פקדון טובורג", "deposit_first_word"),
    ("משלוח", "delivery_first_word"),
    ("משלוח אינטרנט", "delivery_first_word"),
    ("משלוחים עכו", "delivery_first_word"),
    ("משלוח/הובלה בגין משט", "delivery_first_word"),
    ("הובלה מקרר מעל 300 ל' ניופאן", "delivery_first_word"),
    ("דמי טיפול", "fee_first_word"),
    ("מיחזור אריזה זכוכית", "fee_first_word"),
    ("עמלת משיכת מזמן", "fee_first_word"),
    ("תשלום על רבע שעה חניה", "fee_first_word"),
    # real products stay
    ("משלוח מנות פורים 26", None),
    ("משלוח מנות", None),
    ("דמי מייקאפ טבעי 35 מ\"ל", None),
    ("נביעות + תפוח 1.5 ליטר פיקדון", None),
    ("מחזור שלוש רגלים", None),
    ("שקית בד ללקוחות", None),
    ("הובלות", None),
])
def test_service_patterns(name, hit):
    assert pseudo_pattern(normalize(name)) == hit


def test_is_pseudo_service_and_coupon():
    assert is_pseudo(normalize("פיקדון בקבוק"), 0.3) is True
    assert is_pseudo(normalize("קופון 10%"), 9.9) is True
    assert is_pseudo(normalize("חלב 3%"), 6.0) is False


# ----------------------------------------------------------------- nameless fallback (build)
def test_build_rows_uses_fallback_name():
    import scripts.build_search_items as B
    agg = [{"item_code": "1", "item_name": "", "manufacturer_name": None, "chains_live": 1, "stores_live": 1,
            "promo_only": False, "max_price": 9.0},
           {"item_code": "2", "item_name": None, "manufacturer_name": None, "chains_live": 1, "stores_live": 1,
            "promo_only": False, "max_price": 9.0},
           {"item_code": "3", "item_name": "חלב 3%", "manufacturer_name": "תנובה", "chains_live": 2,
            "stores_live": 5, "promo_only": False, "max_price": 6.0},
           {"item_code": "4", "item_name": "  ", "manufacturer_name": None, "chains_live": 1, "stores_live": 1,
            "promo_only": False, "max_price": 50.0}]
    assert B.nameless_codes(agg) == ["1", "2", "4"]
    rows = {r["item_code"]: r for r in B.build_rows(agg, {}, datetime.now(timezone.utc),
                                                    {"1": "סלמון טרי טחון", "3": "IGNORED",
                                                     "4": "הובלה מקרר מעל 300 ל'"})}
    assert rows["1"]["name_norm"] == "סלמון טרי טחון"
    assert rows["2"]["name_norm"] == ""
    assert rows["3"]["name_norm"] == "חלב 3%"           # a real name is never replaced
    assert rows["4"]["is_pseudo"] is True                # service rule sees the fallback name


# ----------------------------------------------------------------- brand hints
COLS = ["id", "level", "parent_id", "name_he", "name_en", "keywords_he", "negative_keywords_he", "attributes", "notes"]


@pytest.fixture
def small(tmp_path):
    p = tmp_path / "tax.csv"
    rows = [("D01", "department", "", "ירקות", "Produce", "", ""),
            ("D01.C02", "category", "D01", "עשבי תיבול", "Herbs", "שמיר|כוסברה", ""),
            ("D04", "department", "", "מעדנייה", "Deli", "", ""),
            ("D04.C02", "category", "D04", "חומוס", "Hummus", "חומוס|מסבחה", ""),
            ("D11", "department", "", "ניקיון", "Cleaning", "", ""),
            ("D11.C01", "category", "D11", "כביסה", "Laundry", "לנור|מרכך כביסה", ""),
            ("D11.C07", "category", "D11", "אביזרים", "Tools", "דלי", ""),
            ("D12", "department", "", "טיפוח", "Care", "", ""),
            ("D12.C01", "category", "D12", "שמפו", "Shampoo", "מרכך|שמפו", ""),
            ("D06", "department", "", "קפואים", "Frozen", "", ""),
            ("D06.C08", "category", "D06", "תחליפים", "Substitutes", "בורגר מן הצומח", "")]
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        for r in rows:
            w.writerow(list(r) + [""] * (len(COLS) - len(r)))
    h = tmp_path / "hints.csv"
    h.write_text("brand,category_id,confidence,position,fallback,notes\n"
                 "שמיר,D04.C02,medium,first,no,\n"
                 "לנור,D11.C01,medium,any,yes,\n"
                 "טבע דלי,D06.C08,medium,any,yes,\n", encoding="utf-8")
    return C.load_taxonomy(p), C.load_brand_hints(h)


def test_brand_masks_word_that_is_a_keyword_elsewhere(small):
    tax, hints = small
    res = C.classify_rules(tax, "שמיר חומוס עם צנובר", hints)
    assert res.category_id == "D04.C02" and res.brand == "שמיר"


def test_brand_alone_keeps_rule(small):
    tax, hints = small
    assert C.classify_rules(tax, "שמיר במשקל", hints).category_id == "D01.C02"


def test_brand_without_fallback_keeps_rule(small):
    tax, hints = small
    assert C.classify_rules(tax, "שמיר ערוגות המשק", hints).category_id == "D01.C02"


def test_brand_position_first_only(small):
    tax, hints = small
    # שמיר later in the name is the herb (dill-flavoured cheese style)
    res = C.classify_rules(tax, "חומוס שמיר", hints)
    assert res.category_id == "D04.C02" and res.brand == ""


def test_brand_agreeing_department_keeps_full_result(small):
    tax, hints = small
    # לנור is itself a laundry keyword; masking it would leave "מרכך" (shampoo)
    assert C.classify_rules(tax, "לנור מרכך מרוכז", hints).category_id == "D11.C01"


def test_brand_fallback_and_mask(small):
    tax, hints = small
    assert C.classify_rules(tax, "טבע דלי בורגר מן הצומח", hints).category_id == "D06.C08"
    res = C.classify_rules(tax, "טבע דלי סייטן שווארמה", hints)        # rest matches nothing
    assert (res.category_id, res.reason, res.confidence) == ("D06.C08", "brand", "medium")
    assert C.classify_rules(tax, "דלי פלסטיק 10 ליטר", hints).category_id == "D11.C07"


def test_brand_attribute_fallback(v1):
    tax, _, hints = v1
    res = C.classify_rules(tax, "זוגלובק סלמי פיין", hints)
    attrs = C.extract_attributes(tax, res.category_id, "זוגלובק סלמי פיין", {}, res.brand)
    assert attrs.get("brand") == "זוגלובק"


# ----------------------------------------------------------------- committed v1 files
def test_v1_keeps_every_v0_id(v1):
    tax = v1[0]
    v0 = C.load_taxonomy(CAT / "taxonomy_v0.csv")
    assert set(v0.nodes) <= set(tax.nodes)
    for nid, n in v0.nodes.items():
        assert tax.nodes[nid].parent == n.parent and tax.nodes[nid].level == n.level


def test_v1_integrity(v1):
    tax, gmap, hints = v1
    assert len([n for n in tax.nodes.values() if n.level == "department"]) == 16
    for n in tax.nodes.values():
        assert not n.parent or n.parent in tax.nodes
    assert all(gid in tax.nodes for gid, _ in gmap.values())
    assert all(h.category_id in tax.nodes for hs in hints.values() for h in hs)
    keys = {r["key"] for r in csv.DictReader(open(CAT / "attributes_v1.csv", encoding="utf-8"))}
    assert all(set(n.attributes) <= keys for n in tax.nodes.values())
    # Dude's decisions (24 Oct 2026)
    assert tax.nodes["D06.C02"].parent == "D06"                        # frozen fruit in the freezer
    assert tax.nodes["D10.C05"].parent == "D10" and tax.nodes["D10.C04"].parent == "D10"
    assert "Fish - Prepared_Processed (Frozen)" not in gmap             # raw frozen fish stays D03


@pytest.mark.parametrize("name,want", [
    ("פילה עוף טרי ללא אנטיביוטיקה", "D03.C06"),
    ("פילה סלמון טרי", "D03.C08"),
    ("פילה בקר", "D03.C01"),
    ("טחינה גולמית 500 גרם סלה", "D07.C20"),
    ("טחינה הר כנען", "D07.C20"),
    ("סלט טחינה 500 גרם", "D04.C02"),
    ("טחינה ירוקה 250 גרם", "D04.C02"),
    ("חומוס צבר 850 גרם", "D04.C02"),
    ("שמיר גורמה חומוס 200 גרם", "D04.C02"),
    ("שמיר במשקל", "D01.C02"),
    ("עוגה בטעם דבש בית מ", "D05.C05"),
    ("רוגלך בטעם שוקולד בונז'ור", "D05.C06"),
    ("כתף כבש פרוס", "D03.C04"),
    ("עצמות מח פרוס קפוא", "D03.C05"),
    ("חזה הודו פרוס", "D04.C01.S01"),
    ("חטיף תפוא בטעם גבינה", "D08.C05.S01"),
    ("חטיפי גבינה מעושנת", "D02.C02"),
    ("חטיף נובילוס בטעם דג קוד וברווז 80 גרם", "D14"),
    ("כאמל כחול פקט", "D10.C05"),
    ("פרחי ברוקולי מוקפאים", "D06.C01"),
    ("תות שדה 300 ג' סנפרוסט", "D06.C02"),
    ("טבע דלי בורגר מן הצומח עם קינואה 400 גרם", "D06.C08"),
    ("סטייק מן הצומח צ'אנק", "D06.C08"),
    ("אינטואישן אדפ לגבר 100 מ\"ל", "D12.C14"),
    ("עדשות צבעוניות חודשיות", "D12.C15"),
    ("עדשים כתומות 1 ק\"ג", "D07.C05"),
    ("לנור מרכך מרוכז בניחוח יסמין 819 מל", "D11.C01.S02"),
    ("צנצנת זכוכית עם מכסה 1000 מ\"ל", "D15.C06"),
    ("צנצנת מסטיקים בטעם בזוקה", "D08.C03"),
    ("חרמון לבן 375 מ\"ל", ""),                                         # a wine name, not a cold cut
])
def test_v1_rule_pins(v1, name, want):
    tax, _, hints = v1
    got = C.classify_rules(tax, name, hints).category_id
    assert (got == want) if not want else (got == want or got.startswith(want + ".")), got


# ----------------------------------------------------------------- AI (mocked API)
@pytest.fixture
def ai_rows():
    return [{"item_code": f"72900000{i:05d}", "name": f"מוצר {i}", "manufacturer": "לא ידוע",
             "gs1_group": "Beer" if i == 0 else ""} for i in range(7)]


def test_item_payload_hides_placeholders_and_optional_gs1():
    r = {"name": "חלב 3% תנובה", "manufacturer": "לא ידוע", "gs1_group": "Milk"}
    assert A.item_payload(r) == {"n": "חלב 3% תנובה", "g": "Milk"}
    assert A.item_payload(r, hide_gs1=True) == {"n": "חלב 3% תנובה"}
    assert A.item_payload({"name": "x", "manufacturer": "שטראוס"})["m"] == "שטראוס"


def test_select_items_skips_high_nameless_and_pseudo():
    pred = [{"item_code": "1", "confidence": "high"}, {"item_code": "2", "confidence": "medium"},
            {"item_code": "3", "confidence": ""}, {"item_code": "4", "confidence": "low"},
            {"item_code": "5", "confidence": ""}]
    export = {"1": {"item_code": "1", "name": "חלב"}, "2": {"item_code": "2", "name": "גבינה"},
              "3": {"item_code": "3", "name": "", "icn_name": "סלמון טרי"},
              "4": {"item_code": "4", "name": "פיקדון בקבוק"}, "5": {"item_code": "5", "name": ""}}
    assert [r["item_code"] for r in A.select_items(pred, export)] == ["2", "3"]


def test_system_prompt_and_schema(v1):
    tax = v1[0]
    sp = A.system_prompt(tax)
    assert "D07.C20 | " in sp and "D10.C05 | " in sp
    enum = A.output_schema(tax)["properties"]["items"]["items"]["properties"]["category_id"]["enum"]
    assert set(enum) == set(tax.nodes) | {"unknown"}


def test_parse_response_validates(ai_rows):
    batch = ai_rows[:4]
    text = json.dumps({"items": [
        {"i": 0, "category_id": "D10.C02", "confidence": "high", "reason": "beer"},
        {"i": 0, "category_id": "D01", "confidence": "high", "reason": "duplicate index"},
        {"i": 1, "category_id": "D99.C99", "confidence": "high", "reason": "invented id"},
        {"i": 2, "category_id": "unknown", "confidence": "low", "reason": "bare brand"},
        {"i": 3, "category_id": "D01", "confidence": "sure", "reason": "bad confidence"},
        {"i": 9, "category_id": "D01", "confidence": "high", "reason": "out of range"},
    ]})
    labels, missing = A.parse_response(text, batch, {"D10.C02", "D01"}, "m")
    assert [(x["item_code"], x["category_id"]) for x in labels] == [(batch[0]["item_code"], "D10.C02"),
                                                                    (batch[2]["item_code"], "unknown")]
    assert missing == [batch[1]["item_code"], batch[3]["item_code"]]


def _fake_call(answers):
    calls = []

    def call(client, model, system, schema, payload, max_tokens, effort=""):
        calls.append(payload)
        a = answers(len(calls), payload)
        if isinstance(a, Exception):
            raise a
        return json.dumps({"items": a}), {"input_tokens": 100, "output_tokens": 50,
                                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 900}, "end_turn"
    return call, calls


def test_run_budget_checkpoint_and_resume(tmp_path, v1, ai_rows, monkeypatch):
    tax = v1[0]
    monkeypatch.setenv(A.KEY_ENV, "sk-SENTINEL-not-a-real-key")
    ok = lambda n, p: [{"i": x["i"], "category_id": "D09", "confidence": "medium", "reason": "drink"} for x in p]
    call, calls = _fake_call(ok)
    s1 = A.run(ai_rows, tmp_path, None, "claude-haiku-5-5", tax, 2, 4, 2, 5, call=call)
    assert s1["requests"] == 2 and s1["labels"] == 4 and s1["stopped"] == "max-requests reached"
    assert len(calls) == 2
    call2, calls2 = _fake_call(ok)
    s2 = A.run(ai_rows, tmp_path, None, "claude-haiku-5-5", tax, 2, 4, 10, 5, call=call2)
    assert s2["already_done"] == 4 and s2["todo"] == 3 and s2["labels"] == 3 and s2["stopped"] == ""
    assert {x["n"] for p in calls2 for x in p} == {f"מוצר {i}" for i in range(4, 7)}
    assert s1["estimated_cost_usd"] > 0
    out = tmp_path / "labels.csv"
    assert A.write_labels(tmp_path, out) == 7
    for f in tmp_path.iterdir():
        assert "SENTINEL" not in f.read_text(encoding="utf-8")        # the key never reaches a file


def test_run_stops_on_consecutive_errors(tmp_path, v1, ai_rows):
    call, calls = _fake_call(lambda n, p: RuntimeError("boom"))
    s = A.run(ai_rows, tmp_path, None, "claude-haiku-5-5", v1[0], 1, 1, 100, 3, call=call)
    assert s["failed"] == 3 and s["labels"] == 0 and s["stopped"] == "3 consecutive errors"
    log = [json.loads(x) for x in (tmp_path / "run_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {x["error"] for x in log} == {"RuntimeError"}


def test_missing_items_are_retried(tmp_path, v1, ai_rows):
    first = lambda n, p: [{"i": p[0]["i"], "category_id": "D09", "confidence": "high", "reason": "x"}]
    call, _ = _fake_call(first)
    s = A.run(ai_rows[:3], tmp_path, None, "claude-haiku-5-5", v1[0], 3, 1, 1, 5, call=call)
    assert s["labels"] == 1 and s["missing"] == 2
    assert len(A.load_checkpoint(tmp_path / "checkpoint.jsonl")) == 1


def test_make_client_requires_key(monkeypatch):
    monkeypatch.delenv(A.KEY_ENV, raising=False)
    with pytest.raises(SystemExit):
        A.make_client()


def test_cost_estimate():
    u = {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000,
         "cache_read_input_tokens": 1_000_000}
    assert A.cost_usd("claude-haiku-5-5", u) == pytest.approx(0.10 + 0.50 + 0.125 + 0.01)


# ----------------------------------------------------------------- combine
R_HIGH = {"category_id": "D02.C02", "confidence": "high", "reason": "rule", "keyword": "גבינה"}
R_MED = {"category_id": "D08.C01", "confidence": "medium", "reason": "rule", "keyword": "שוקולד"}
R_LOW = {"category_id": "D07", "confidence": "low", "reason": "rule", "keyword": "תערובת"}
R_GS1 = {"category_id": "D09.C04", "confidence": "medium", "reason": "gs1", "keyword": "", "gs1_group": "Juice"}
R_NONE = {"category_id": "", "confidence": "", "reason": "", "keyword": ""}


def ai(cid, conf):
    return {"category_id": cid, "confidence": conf, "reason": "r", "model": "claude-haiku-5-5"}


@pytest.mark.parametrize("rule,a,want", [
    (R_HIGH, ai("D08.C01", "high"), ("D02.C02", "high", "rule", False)),     # high rule stands
    (R_NONE, ai("D08.C01", "medium"), ("D08.C01", "medium", "ai", False)),
    (R_NONE, ai("D08.C01", "low"), ("D08.C01", "low", "ai", False)),
    (R_NONE, ai("unknown", "high"), None),
    (R_NONE, None, None),
    (R_LOW, ai("D07.C14", "high"), ("D07.C14", "high", "ai", False)),
    (R_LOW, ai("D07.C14", "low"), ("D07", "low", "rule", False)),
    (R_MED, ai("D08.C01.S01", "medium"), ("D08.C01.S01", "high", "ai", False)),  # agree, AI deeper
    (R_MED, ai("D08", "high"), ("D08.C01", "high", "rule", False)),               # agree, rule deeper
    (R_MED, ai("D05.C05", "high"), ("D05.C05", "low", "ai", True)),               # disagree, AI high
    (R_MED, ai("D05.C05", "medium"), ("D08.C01", "low", "rule", True)),           # disagree, AI medium
    (R_GS1, ai("D09.C04", "high"), ("D09.C04", "high", "gs1", False)),
    ({**R_MED, "category_id": "D08.C01.S02"}, ai("D08.C01.S01", "high"),
     ("D08.C01", "high", "rule", False)),                                       # sibling sub-types: the category
    (R_MED, ai("D99.C01", "high"), ("D08.C01", "medium", "rule", False)),         # invalid AI id ignored
])
def test_combine_label(v1, rule, a, want):
    f = M.combine_label(rule, a, set(v1[0].nodes))
    got = (f["category_id"], f["confidence"], f["source"], f["disagreement"]) if f else None
    assert got == want


# ----------------------------------------------------------------- build hook (pure part)
def test_category_rows_for_new_barcodes(v1):
    import scripts.build_search_items as B
    tax = v1[0]
    rows = [{"item_code": "1", "name_norm": "פילה עוף טרי", "is_pseudo": False},
            {"item_code": "2", "name_norm": "פיקדון בקבוק", "is_pseudo": True},
            {"item_code": "3", "name_norm": "", "is_pseudo": False},
            {"item_code": "4", "name_norm": "xyzzy", "is_pseudo": False},
            {"item_code": "5", "name_norm": "קפה עלית טורקי 100 גרם", "is_pseudo": False}]
    out = {r["item_code"]: r for r in B.category_rows(rows, {"5": "Coffee - Beans_Ground"}, set(tax.nodes))}
    assert set(out) == {"1", "5"}
    assert out["1"]["category_id"] == "D03.C06" and out["1"]["source"] == "rule"
    assert out["5"]["source"] == "gs1" and out["5"]["category_id"].startswith("D09.C08")
    assert all(r["reviewed"] is False and r["taxonomy_version"] == C.TAXONOMY_VERSION for r in out.values())
    # ids missing from the stored taxonomy are left out (FK safety)
    assert B.category_rows(rows, {}, {"D09"}) == []


# ----------------------------------------------------------------- import planning (pure part)
def test_category_rows_inherit_attributes(v1):
    rows = {r["id"]: r for r in I.category_rows(v1[0])}
    assert rows["D02.C01.S01"]["level"] == 3 and rows["D02.C01.S01"]["parent_id"] == "D02.C01"
    assert "fat_pct" in rows["D02.C01.S01"]["attributes"] and "brand" in rows["D02.C01.S01"]["attributes"]
    assert rows["D01"]["parent_id"] is None and rows["D01"]["level"] == 1


def test_plan_labels_and_manual(v1, tmp_path):
    tax, gmap, hints = v1
    items = [{"item_code": "1", "name_norm": "פילה עוף טרי 1 ק\"ג", "is_weighted": 1},
             {"item_code": "2", "name_norm": "xyzzy", "is_weighted": 0},
             {"item_code": "3", "name_norm": "xyzzy qq", "is_weighted": 0}]
    cats, attrs = I.plan_labels(items, {"1": ("", "עוף טוב")}, {"3": ai("D16.C04", "medium")}, tax, gmap, hints)
    by = {c["item_code"]: c for c in cats}
    assert by["1"]["category_id"] == "D03.C06" and by["3"]["source"] == "ai" and "2" not in by
    a1 = {(r["attr_key"], r["source"]) for r in attrs if r["item_code"] == "1"}
    assert ("brand", "gs1") in a1 and ("weighted", "rule") in a1 and ("size_value", "rule") in a1
    p = tmp_path / "review.csv"
    p.write_text("item_code,correct_category_id\n1,D03.C07\n2,\n3,D99\n", encoding="utf-8")
    man, bad = I.manual_rows(p, set(tax.nodes))
    assert [(m["item_code"], m["source"], m["reviewed"]) for m in man] == [("1", "manual", True)]
    assert bad == ["3: D99"]
    existing = {"1": {"category_id": "D03.C06", "confidence": "high", "source": "manual", "reviewed": True},
                "3": {"category_id": "D16.C04", "confidence": "medium", "source": "ai", "detail": "ai: r",
                      "model": "claude-haiku-5-5", "taxonomy_version": C.TAXONOMY_VERSION, "reviewed": False}}
    d = I.diff_counts(cats, existing, tuple(S.ITEM_CATEGORY_COLS[1:]))
    assert d == {"protected": 1, "unchanged": 1}
