"""Read-only catalog audit for category-based faceted filters (SU11A-35).

    venv/bin/python3 -m scripts.audit_catalog --out /tmp/catalog_audit.json | tee /tmp/catalog_audit.txt
    venv/bin/python3 -m scripts.audit_catalog --dry-run

Answers: how clean are the structured item fields, how well do product names
parse into attributes for ten pilot categories, and how big are the GS1,
duplicate and name-hygiene problems. Nothing here is used by the app.

"Live item" = the same definition search uses: at least one price row with
item_price > 0 at a store in db.query.get_liveness().live_fks (the chain's
latest load minus 3 days; db/query.py fetch_prices). Checked with an EXISTS
per item in chunks of 5,000 codes, so each probe is an index lookup on
prices(item_code, store_fk) INCLUDE (item_price) - never a join of the full
prices table.

Safety: every connection is READ ONLY with statement_timeout 60 s (PGOPTIONS,
which also covers get_liveness's own connection, plus SET TRANSACTION READ
ONLY). No DDL, no writes. Sampling is deterministic: rows are ordered by
md5(item_code) - computed in Python with hashlib, which gives the same order
as Postgres md5(item_code). The heuristic NOISE flags and attribute patterns
are rules for a human to check, not a classifier. Output holds catalog data
only - no user data, no secrets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

TIMEOUT_MS = 60_000
CHUNK = 5_000
SAMPLE = 40
EXAMPLES = 5
TOP_MFR = 40
GS1_GROUP_CAP = 300

HEB = "א-ת"            # א..ת including final forms
NB = rf"(?<![{HEB}A-Za-z])"      # no letter before
NA = rf"(?![{HEB}A-Za-z])"       # no letter after
NUM = r"(\d+(?:[.,]\d+)?)"

# Manufacturer values seen in production that do not name a manufacturer
# (xxl-super-mobile/src/lib/product-name.ts SENTINELS, observed in data).
SENTINELS = {"לא ידוע", "לא ידועה", "כללי", "כללית", "אחר", "הפריט בפיקוח"}

VOLUME = rf"{NUM}\s*(?:ליטר|ל{NA}|ל['׳]|מ[\"״]?ל{NA}|מ['׳]ל|ml{NA}|L{NA})"
WEIGHT = rf"{NUM}\s*(?:גרם|גר['׳]?{NA}|ג['׳]|ג{NA}|ק[\"״]?ג{NA}|קילו|kg{NA}|g{NA}|gr{NA})"
COUNT = rf"{NUM}\s*(?:יח['׳]?{NA}|יחידות|יחי{NA}|ביצים)"
SIZE_IN_NAME = re.compile(f"(?:{VOLUME})|(?:{WEIGHT})|(?:{COUNT})", re.I)
PERCENT = rf"{NUM}\s*%"


def w(x: str, prefix: bool = False) -> str:
    """Whole word; prefix=True also allows one attached ו/ה/ב/ל/מ/ש/כ."""
    return rf"{NB}{'[והבלמשכ]?' if prefix else ''}(?:{x}){NA}"


# --------------------------------------------------------------------------- pilots
# Each pilot: the search word, NOISE rules (regex, reason) that mark an item as
# clearly not the intended category, and attribute groups. "exclusive" groups
# should not overlap; the script measures how often they do. "ambiguous" is a
# note written up front; the overlap figure is the measured check.
P = lambda key, label, rx, amb=None: {"key": key, "label": label, "rx": rx, "ambiguous": amb}

PILOTS: dict[str, dict] = {
    "חלב": {
        "noise": [
            (r"שוקולד|שוקו(?!\s*לשתי)", "chocolate / choco drink"),
            (r"חלבה|חלבון|חלבי(?:ת|ים)?" + NA, "halva / protein / 'dairy' kosher label"),
            (r"גבינ|יוגורט|לבנה|שמנת|חמאה|אשל|גיל" + NA + r"|קוטג", "other dairy product"),
            (r"עוגי|עוגה|עוגת|ביסקוויט|וופל|ופל|חטיף|דגני|קורנפלקס|כריות", "baked goods / snack / cereal"),
            (r"גלידה|שלגון|ארטיק|פודינג|מעדן|קרם", "dessert / ice cream"),
            (r"תמ[\"״]?ל|מטרנה|סימילאק|נוטרילון|תחליף חלב אם", "infant formula"),
            (r"קפה|נס\s*קפה|קפוצ|לאטה|מלבין", "coffee drink / creamer"),
            (r"סבון|שמפו|תחליב|קרם גוף|רחצה", "cosmetics"),
        ],
        "word_only": True,  # חלב inside a longer word (חלבה, חלבון) is noise too
        "groups": [
            {"name": "fat", "label": "אחוז שומן", "exclusive": True, "values": PERCENT,
             "patterns": [P("fat_pct", "אחוז שומן (ערך)", PERCENT, "a % can also be cocoa or fruit content")]},
            {"name": "size", "label": "נפח", "exclusive": False,
             "patterns": [P("volume", "נפח בשם", VOLUME)]},
            {"name": "lactose", "label": "לקטוז", "exclusive": True, "patterns": [
                P("lactose_free", "ללא לקטוז", r"ללא\s*לקטוז|נטול\s*לקטוז|לקטוז\s*פרי"),
                P("lactose_low", "דל לקטוז", r"דל\s*לקטוז|מופחת\s*לקטוז"),
            ]},
            {"name": "plant", "label": "סוג צמחי", "exclusive": True, "patterns": [
                P("soy", "סויה", r"סויה"),
                P("almond", "שקדים", r"שקד"),
                P("oat", "שיבולת שועל", r"שיבולת|שבולת|שועל|אוטס|oat"),
                P("rice", "אורז", w("אורז", True), "rice may be a cereal or snack, not a rice drink"),
                P("coconut", "קוקוס", r"קוקוס"),
                P("hazelnut", "אגוזי לוז", r"לוז"),
            ]},
            {"name": "flavor", "label": "טעם", "exclusive": True, "patterns": [
                P("natural", "טבעי", r"טבעי"),
                P("vanilla", "וניל", r"וניל"),
                P("choco", "שוקו", r"שוקו|שוקולד", "also the noise rule for chocolate products"),
                P("banana", "בננה", r"בננה"),
                P("strawberry", "תות", w("תות", True)),
                P("coffee", "קפה", r"קפה|מוקה"),
            ]},
            {"name": "type", "label": "סוג", "exclusive": False, "patterns": [
                P("fresh", "טרי", w("טרי", True)),
                P("long_life", "עמיד / UHT", r"עמיד|UHT|חיי מדף|ארוך"),
                P("enriched", "מועשר", r"מועשר"),
                P("organic", "אורגני", r"אורגני"),
                P("goat", "עיזים", r"עיזים|עזים"),
                P("milk_drink", "משקה חלב", r"משקה"),
            ]},
            {"name": "pack", "label": "אריזה", "exclusive": True, "patterns": [
                P("carton", "קרטון", r"קרטון|קרט['׳]"),
                P("bag", "שקית", r"שקית|בשקית"),
                P("bottle", "בקבוק", r"בקבוק|בק['׳]"),
            ]},
        ],
    },
    "שוקולד": {
        "noise": [
            (r"ממרח", "spread (dept 5)"),
            (r"גלידה|שלגון|ארטיק|קרטיב|פרוזן", "ice cream (dept 6)"),
            (r"משקה|שוקו" + NA + r"|לשתיה|לשתייה", "chocolate drink"),
            (r"עוגה|עוגת|בראוני|מאפה|קרואסון|רוגלך|לחמני|בורקס", "cake / pastry"),
            (r"דגני|קורנפלקס|כריות|גרנולה", "cereal"),
            (r"פודינג|מעדן|יוגורט|מוס" + NA, "dairy dessert"),
            (r"אבקת|אבקה|קקאו להכנה|להכנת|סירופ|רוטב", "powder / syrup"),
            (r"בטעם\s*שוקולד|ציפוי\s*שוקולד|בציפוי", "only chocolate-flavoured or coated"),
            (r"שמפו|סבון|קרם גוף|שפתון|בושם", "cosmetics"),
        ],
        "groups": [
            {"name": "form", "label": "צורה", "exclusive": True, "patterns": [
                P("bar", "טבלה", r"טבל[הת]|טבלאות"),
                P("snack", "חטיף", r"חטיף"),
                P("praline", "פרלינים / בונבוניירה", r"פרלינ|פרלין|בונבוני"),
                P("cubes", "קוביות", r"קוביות|קוביה"),
                P("egg", "ביצה", r"ביצ[הת]|ביצי" + NA, "Kinder egg vs a real egg product"),
                P("box", "מארז", r"מארז|קופסת|קופסה"),
            ]},
            {"name": "type", "label": "סוג שוקולד", "exclusive": True, "patterns": [
                P("dark", "מריר", r"מריר"),
                P("milk", "חלב", w("חלב", True), "also 'במילוי חלב' and filling names"),
                P("white", "לבן", w("לבן", True)),
                P("cocoa_pct", "אחוז קקאו (ערך)", PERCENT, "a % can be fat or nut content"),
            ]},
            {"name": "inclusion", "label": "תוספות", "exclusive": False, "patterns": [
                P("nuts", "אגוזים", r"אגוז|לוז|נוגט|פיסטוק|קשיו"),
                P("almonds", "שקדים", r"שקד"),
                P("cream", "קרם / מילוי", r"קרם|ממולא|במילוי|מילוי"),
                P("crunch", "קראנץ'", r"קראנץ|קריספ|פריך|תפוח[יי]?\s*אורז"),
                P("wafer", "וופל", r"וופל|ופל" + NA),
                P("caramel", "קרמל", r"קרמל|טופי"),
                P("mint", "מנטה", r"מנטה|נענע"),
                P("biscuit", "עוגיות / ביסקוויט", r"עוגי|ביסקוויט|קרקר"),
                P("fruit", "פירות", r"תות|פטל|דובדבן|תפוז|צימוק"),
            ]},
            {"name": "diet", "label": "תזונה", "exclusive": False, "patterns": [
                P("no_sugar", "ללא סוכר", r"ללא\s*(?:תוספת\s*)?סוכר|דל\s*סוכר|מופחת\s*סוכר"),
                P("vegan", "טבעוני", r"טבעונ|vegan"),
                P("parve", "פרווה", r"פרווה|פרוה"),
            ]},
        ],
    },
    "פסטרמה": {
        "noise": [
            (r"כריך|סנדוויץ|פיצה|סלט|טורטיה|בורקס", "dish containing pastrami"),
            (r"תבלין|תערובת", "seasoning"),
        ],
        "groups": [
            {"name": "origin", "label": "מקור", "exclusive": True, "patterns": [
                P("chicken", "עוף", r"עוף|פרגית"),
                P("turkey", "הודו", r"הודו"),
                P("beef", "בקר", r"בקר|עגל|אנגוס|אסאדו"),
                P("lamb", "כבש", r"כבש|טלה"),
            ]},
            {"name": "flavor", "label": "טעם", "exclusive": False, "patterns": [
                P("bbq", "ברביקיו", r"ברביקיו|בארביקיו|BBQ|ברבקיו"),
                P("italian", "איטלקית", r"איטלק"),
                P("honey", "דבש", r"דבש"),
                P("paprika", "פפריקה", r"פפריק"),
                P("grill", "גריל / צלוי", r"גריל|צלוי|צלי" + NA),
                P("smoked", "מעושן", r"מעושנ|מעושן"),
                P("garlic", "שום", w("שום", True)),
                P("pepper", "פלפל", r"פלפל"),
                P("spicy", "חריף", r"חריף|צ['׳]?ילי"),
                P("herbs", "עשבי תיבול", r"עשבי|תבלינים|מתובל|ים\s*תיכוני"),
            ]},
            {"name": "form", "label": "מאפיינים", "exclusive": False, "patterns": [
                P("sliced", "פרוס", r"פרוס"),
                P("thin", "דק", r"דק" + NA + r"|דקיק"),
                P("low_fat", "דל שומן", r"דל\s*שומן|מופחת\s*שומן|\d\s*%\s*שומן"),
                P("gluten_free", "ללא גלוטן", r"ללא\s*גלוטן"),
                P("multipack", "מארז", r"מארז|זוגי|שלישי|\d+\s*\*"),
            ]},
        ],
    },
    "יוגורט": {
        "noise": [
            (r"גלידה|פרוזן|קפוא", "frozen yogurt (dept 6)"),
            (r"שמפו|סבון|תחליב|קרם גוף|מסכה|רחצה", "cosmetics"),
            (r"חטיף|דגני|כריות|ציפוי|בטעם\s*יוגורט|ממרח|רוטב|מטבל", "snack / coated / sauce"),
        ],
        "groups": [
            {"name": "fat", "label": "אחוז שומן", "exclusive": True,
             "patterns": [P("fat_pct", "אחוז שומן (ערך)", PERCENT, "% may be fruit or protein")]},
            {"name": "style", "label": "סגנון", "exclusive": False, "patterns": [
                P("greek", "יווני", r"יוונ"),
                P("bio", "ביו / פרוביוטי", r"ביו" + NA + r"|BIO|פרוביוט|אקטיביה"),
                P("drink", "לשתייה", r"לשתי|משקה"),
                P("protein", "חלבון", r"חלבון|PRO" + NA + r"|פרו" + NA),
                P("plant", "צמחי", r"סויה|שקד|קוקוס|צמחי|שיבולת"),
                P("goat_sheep", "עיזים / כבשים", r"עיזים|עזים|כבשים"),
                P("lactose_free", "ללא לקטוז", r"ללא\s*לקטוז"),
            ]},
            {"name": "flavor", "label": "טעם", "exclusive": True, "patterns": [
                P("natural", "טבעי", r"טבעי"),
                P("strawberry", "תות", w("תות", True)),
                P("peach", "אפרסק", r"אפרסק"),
                P("vanilla", "וניל", r"וניל"),
                P("banana", "בננה", r"בננה"),
                P("fruit", "פירות", r"פירות|פרי" + NA),
                P("honey", "דבש", r"דבש"),
            ]},
            {"name": "pack", "label": "אריזה", "exclusive": False, "patterns": [
                P("weight", "משקל בשם", WEIGHT),
                P("multipack", "מארז", r"מארז|רביעי|שישי|\d+\s*\*|\d+\s*יח"),
            ]},
        ],
    },
    "ביצים": {
        "noise": [
            (r"שוקולד|הפתעה|קינדר", "chocolate egg"),
            (r"אטריות|פסטה|לוקשן|פתיתים|נודלס", "egg noodles / pasta"),
            (r"סלט", "egg salad (dept 5)"),
            (r"שמפו|מסכה|קרם", "cosmetics"),
        ],
        "groups": [
            {"name": "size", "label": "גודל", "exclusive": True, "patterns": [
                P("xl", "XL", rf"(?<![A-Za-z])XL(?![A-Za-z])|אקסטרה\s*לארג"),
                P("l", "L", rf"(?<![A-Za-z])L(?![A-Za-z])|לארג|גדול", "L also stands for litre"),
                P("m", "M", rf"(?<![A-Za-z])M(?![A-Za-z])|מדיום|בינוני"),
                P("s", "S", rf"(?<![A-Za-z])S(?![A-Za-z])|קטנ"),
            ]},
            {"name": "count", "label": "כמות", "exclusive": False, "patterns": [
                P("count", "מספר ביצים (ערך)", rf"{NUM}\s*(?:יח['׳]?|יחידות|ביצים)|(?<!\d)(12|18|30)(?!\d)")]},
            {"name": "farming", "label": "גידול", "exclusive": False, "patterns": [
                P("free_range", "חופש", r"חופש|מרעה"),
                P("organic", "אורגני", r"אורגני"),
                P("omega", "אומגה", r"אומגה|omega"),
            ]},
            {"name": "type", "label": "סוג", "exclusive": False, "patterns": [
                P("brown", "חומות", r"חומ(?:ות|ה)" + NA),
                P("pasteurized", "מפוסטרות", r"פסטור"),
                P("liquid", "חלבון / נוזלי", r"חלבון|נוזלי|חלמון"),
            ]},
        ],
    },
    "שמן זית": {
        "noise": [
            (r"ב\s*שמן\s*זית|בשמן", "food packed in olive oil"),
            (r"טונה|סרדינ|שימורי|זיתים|ממרח|מטבל", "canned or preserved food"),
            (r"חטיף|צ['׳]?יפס|קרקר|לחם|פריכי|בייגלה", "snack / bread"),
            (r"סבון|קרם|שמפו|תחליב|מרכך", "cosmetics"),
            (r"רוטב|ויניגרט|מיונז|רטב", "sauce / dressing"),
        ],
        "groups": [
            {"name": "grade", "label": "סוג", "exclusive": True, "patterns": [
                P("extra_virgin", "כתית מעולה", r"כתית\s*מעול|אקסטרה\s*וירג|extra\s*virgin"),
                P("virgin", "כתית", r"כתית(?!\s*מעול)"),
                P("light", "עדין / מזוכך", r"מזוכך|לייט|light|עדין|רפיינד"),
            ]},
            {"name": "origin", "label": "ארץ מקור", "exclusive": True, "patterns": [
                P("israel", "ישראל", r"ישראל|גליל|מקומי"),
                P("spain", "ספרד", r"ספרד"),
                P("italy", "איטליה", r"איטל"),
                P("greece", "יוון", r"יוונ"),
                P("tunisia", "תוניסיה", r"תוניס"),
                P("portugal", "פורטוגל", r"פורטוג"),
            ]},
            {"name": "extra", "label": "מאפיינים", "exclusive": False, "patterns": [
                P("organic", "אורגני", r"אורגני"),
                P("spray", "ספריי", r"ספריי|תרסיס"),
                P("volume", "נפח בשם", VOLUME),
                P("tin", "פח", w("פח", True) + r"|פחית"),
                P("glass", "זכוכית", r"זכוכית"),
            ]},
        ],
    },
    "קפה": {
        "noise": [
            (r"יוגורט|מעדן|גלידה|שלגון|שוקולד|עוגה|עוגי|חטיף|סוכרי|ליקר|טופי", "coffee-flavoured food"),
            (r"כוס|מכונ|מקציף|פילטר|מסננת|מקינטה|פינג['׳]?אן", "equipment / filters"),
            (r"מלבין|קרמר|קרימר|קרם\s*לקפה", "creamer"),
            (r"שמפו|סבון|קרם|תחליב|סקראב", "cosmetics"),
            (r"בטעם\s*קפה", "only coffee-flavoured"),
        ],
        "groups": [
            {"name": "form", "label": "סוג קפה", "exclusive": True, "patterns": [
                P("instant", "נמס", r"נמס|מגורען|אינסטנט|נס\s*קפה|נסקפה"),
                P("ground", "טחון / טורקי", r"טחון|טורקי|שחור"),
                P("beans", "פולים", r"פולי|פולים"),
                P("capsules", "קפסולות", r"קפסול|נספרסו|תואם|דולצ|dolce|nespresso"),
                P("sticks", "סטיקים / מנות", r"סטיק|שקיק|מנות"),
                P("rtd", "מוכן לשתייה", r"מוכן\s*לשתי|אייס|ice|פחית|קר" + NA),
            ]},
            {"name": "type", "label": "מאפיינים", "exclusive": False, "patterns": [
                P("decaf", "נטול קפאין", r"נטול|דקאף|decaf"),
                P("espresso", "אספרסו", r"אספרסו|espresso"),
                P("milk_based", "קפוצ'ינו / לאטה / הפוך", r"קפוצ|לאטה|הפוך|מקיאטו|מוקה"),
                P("cardamom", "עם הל", w("הל", True) + r"|ערבי"),
                P("arabica", "ערביקה", r"ערביק|arabica"),
                P("weight", "משקל בשם", WEIGHT),
            ]},
        ],
    },
    "קולה": {
        "noise": [
            (r"סוכרי|גומי|ג['׳]?לי|ליקריץ|טופי|מסטיק|ארטיק|קרטיב", "candy / ice lolly"),
            (r"בטעם\s*קולה", "only cola-flavoured"),
        ],
        "word_only": True,
        "groups": [
            {"name": "sugar", "label": "סוכר", "exclusive": True, "patterns": [
                P("zero", "זירו", r"זירו|זרו|zero"),
                P("diet", "דיאט / לייט", r"דיאט|diet|לייט|light"),
                P("no_sugar", "ללא סוכר", r"ללא\s*סוכר"),
            ]},
            {"name": "brand_in_name", "label": "מותג", "exclusive": True, "patterns": [
                P("coca", "קוקה קולה", r"קוקה|coca"),
                P("pepsi", "פפסי", r"פפסי|pepsi"),
                P("rc", "RC", rf"(?<![A-Za-z])RC(?![A-Za-z])"),
            ]},
            {"name": "pack", "label": "אריזה", "exclusive": False, "patterns": [
                P("can", "פחית", r"פחית|פחיות|" + w("פח")),
                P("bottle", "בקבוק", r"בקבוק|בק['׳]"),
                P("multipack", "מארז", r"מארז|שישי|\d+\s*\*|\d+\s*יח"),
                P("volume", "נפח בשם", VOLUME),
            ]},
            {"name": "extra", "label": "מאפיינים", "exclusive": False, "patterns": [
                P("no_caffeine", "ללא קפאין", r"ללא\s*קפאין|נטול"),
                P("flavored", "בטעם", r"דובדבן|cherry|וניל|לימון|ליים"),
            ]},
        ],
    },
    "טחינה": {
        "noise": [
            (r"עוגי|עוגה|חטיף|מאפה|בורקס|לחמני|שוקולד|גלידה|חלבה", "sweet / baked with tahini"),
            (r"חציל|חומוס|סלט\s*(?!טחינה)", "salad with tahini (dept 5)"),
        ],
        "groups": [
            {"name": "type", "label": "סוג", "exclusive": True, "patterns": [
                P("raw", "גולמית", r"גולמי"),
                P("ready", "מוכנה / סלט טחינה", r"מוכנ|סלט\s*טחינה|ממרח"),
                P("whole", "מלאה / משולבת", r"מלא" + NA + r"|משולב|שומשום\s*מלא"),
            ]},
            {"name": "extra", "label": "מאפיינים", "exclusive": False, "patterns": [
                P("organic", "אורגני", r"אורגני"),
                P("origin_seed", "זן שומשום", r"אתיופ|הומרה|הומארה|ירושלמ|סודנ"),
                P("pct", "100%", r"100\s*%"),
                P("weight", "משקל בשם", WEIGHT),
                P("pack", "דלי / צנצנת / פח", r"דלי|צנצנת|" + w("פח") + r"|שקית"),
            ]},
        ],
    },
    "לחם": {
        "noise": [
            (r"פירורי|פרורי|קרוטונ", "breadcrumbs / croutons"),
            (r"שום|קפוא", "frozen garlic bread (dept 6)"),
            (r"מצה|מצות|פריכי|קרקר|קריספ", "matzah / crispbread (dept 9)"),
            (r"תבנית\s*ל|מכונת|סכין", "equipment"),
        ],
        "word_only": True,
        "groups": [
            {"name": "grain", "label": "סוג קמח", "exclusive": False, "patterns": [
                P("whole", "מלא / חיטה מלאה", r"חיטה\s*מלאה|קמח\s*מלא|" + w("מלא")),
                P("spelt", "כוסמין", r"כוסמין"),
                P("rye", "שיפון", r"שיפון"),
                P("multigrain", "דגנים", r"דגנ|רב\s*דגני|גרעינ|זרעים"),
                P("white", "לבן / אחיד", w("לבן") + "|" + w("אחיד")),
            ]},
            {"name": "diet", "label": "תזונה", "exclusive": False, "patterns": [
                P("light", "קל / דל קלוריות", w("קל") + r"|דל\s*קלורי|לייט"),
                P("gluten_free", "ללא גלוטן", r"ללא\s*גלוטן"),
                P("sourdough", "מחמצת", r"מחמצת|שאור"),
                P("no_salt_sugar", "ללא מלח / סוכר", r"ללא\s*(?:תוספת\s*)?(?:מלח|סוכר)"),
            ]},
            {"name": "form", "label": "צורה", "exclusive": False, "patterns": [
                P("sliced", "פרוס", r"פרוס"),
                P("baguette", "בגט", r"בגט|באגט"),
                P("weight", "משקל בשם", WEIGHT),
            ]},
        ],
    },
}

QUERY_LIST = [
    "live store set: db.query.get_liveness() (same function search uses)",
    "SELECT item_code, item_type, item_name, manufacturer_name, quantity, unit_qty, unit_of_measure, "
    "is_weighted, name_source FROM items",
    f"live items: EXISTS (prices.item_code = :c AND item_price > 0 AND store_fk = ANY(:live)) "
    f"in chunks of {CHUNK} codes",
    "SELECT count(*) FROM item_chain_names; item codes with count(DISTINCT item_name) > 1",
    "SELECT gtin, group_name, brandname FROM gs1.products WHERE gtin IS NOT NULL",
    "everything else (normalisation, patterns, duplicates, hygiene, samples) is computed in Python",
]


# --------------------------------------------------------------------------- normalisation
_QUOTES = "\"'״׳`”“’‘"
_CO_TOKENS = {"בעמ", "ltd", "inc", "llc", "co", "בע", "מ"}


def norm(s: str | None, company: bool = False) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(f"[{re.escape(_QUOTES)}]", "", s)
    s = re.sub(r"[^\w\s%.]", " ", s)
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)
    toks = s.split()
    if company:
        toks = [t for t in toks if t not in _CO_TOKENS]
    return " ".join(toks)


def is_placeholder_mfr(m: str | None) -> bool:
    if m is None or not m.strip():
        return True
    m = m.strip()
    return m in SENTINELS or not re.search(rf"[{HEB}A-Za-z]", m)


def md5key(code: str) -> str:
    return hashlib.md5(code.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- db
def _load_env() -> None:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    extra = f"-c default_transaction_read_only=on -c statement_timeout={TIMEOUT_MS}"
    os.environ["PGOPTIONS"] = f"{os.environ.get('PGOPTIONS', '')} {extra}".strip()


def _begin(conn) -> None:
    from sqlalchemy import text
    conn.execute(text("SET TRANSACTION READ ONLY"))
    conn.execute(text(f"SET LOCAL statement_timeout = {TIMEOUT_MS}"))


def load(conn, live_fks: list[int], log) -> dict:
    from sqlalchemy import text
    t = time.perf_counter()
    items = [dict(r._mapping) for r in conn.execute(text(
        "SELECT item_code, item_type, item_name, manufacturer_name, quantity, unit_qty, "
        "unit_of_measure, is_weighted, name_source FROM items"))]
    log(f"items: {len(items)} rows ({time.perf_counter() - t:.1f} s)")

    live: set[str] = set()
    codes = [i["item_code"] for i in items]
    probe = text("""
        SELECT c.code FROM unnest(CAST(:codes AS text[])) AS c(code)
        WHERE EXISTS (SELECT 1 FROM prices p
                      WHERE p.item_code = c.code AND p.item_price > 0
                        AND p.store_fk = ANY(:live))
    """)
    t = time.perf_counter()
    for i in range(0, len(codes), CHUNK):
        live.update(r[0] for r in conn.execute(probe, {"codes": codes[i:i + CHUNK], "live": live_fks}))
    log(f"live items: {len(live)} ({time.perf_counter() - t:.1f} s)")

    icn_rows = conn.execute(text("SELECT count(*) FROM item_chain_names")).scalar()
    multi_name = {r[0] for r in conn.execute(text(
        "SELECT item_code FROM item_chain_names GROUP BY item_code HAVING count(DISTINCT item_name) > 1"))}
    gs1 = [dict(r._mapping) for r in conn.execute(text(
        "SELECT gtin, group_name, brandname FROM gs1.products WHERE gtin IS NOT NULL"))]
    log(f"item_chain_names: {icn_rows}; gs1 rows: {len(gs1)}")
    return {"items": items, "live": live, "icn_rows": icn_rows, "multi_name": multi_name, "gs1": gs1}


# --------------------------------------------------------------------------- sections
def pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def s1_size(data: dict, live_items: list[dict]) -> dict:
    by_type = Counter((i["item_type"], i["is_weighted"]) for i in live_items)
    return {
        "items_rows": len(data["items"]),
        "live_items": len(live_items),
        "by_item_type_is_weighted": [{"item_type": k[0], "is_weighted": k[1], "items": v}
                                     for k, v in by_type.most_common()],
        "item_chain_names_rows": data["icn_rows"],
        "items_with_multiple_chain_names": len(data["multi_name"]),
        "live_items_with_multiple_chain_names": len(data["multi_name"] & data["live"]),
    }


def s2_fields(live_items: list[dict]) -> dict:
    n = len(live_items)
    mfr_raw = Counter((i["manufacturer_name"] or "").strip() for i in live_items)
    real = [i for i in live_items if not is_placeholder_mfr(i["manufacturer_name"])]
    mfr_norm = Counter(norm(i["manufacturer_name"], company=True) for i in real)
    has_qty = lambda i: i["quantity"] not in (None, 0)
    size_in_name_no_qty = [i for i in live_items if not has_qty(i) and SIZE_IN_NAME.search(i["item_name"] or "")]
    return {
        "coverage_pct": {
            "manufacturer_name (non-empty)": pct(sum(1 for i in live_items if (i["manufacturer_name"] or "").strip()), n),
            "manufacturer_name (real, not placeholder)": pct(len(real), n),
            "quantity (non-null, non-zero)": pct(sum(1 for i in live_items if has_qty(i)), n),
            "unit_qty (non-empty)": pct(sum(1 for i in live_items if (i["unit_qty"] or "").strip()), n),
            "unit_of_measure (non-empty)": pct(sum(1 for i in live_items if (i["unit_of_measure"] or "").strip()), n),
        },
        "placeholder_manufacturer_top": [{"value": k, "items": v} for k, v in mfr_raw.most_common(200)
                                         if is_placeholder_mfr(k)][:15],
        "manufacturer_distinct_raw": len(mfr_raw),
        "manufacturer_distinct_normalized": len(mfr_norm),
        "manufacturer_top40_normalized": [{"manufacturer": k, "items": v} for k, v in mfr_norm.most_common(TOP_MFR)],
        "unit_qty_distribution": [{"value": k, "items": v} for k, v in
                                  Counter((i["unit_qty"] or "").strip() for i in live_items).most_common(40)],
        "unit_of_measure_distribution": [{"value": k, "items": v} for k, v in
                                         Counter((i["unit_of_measure"] or "").strip() for i in live_items).most_common(40)],
        "size_in_name_but_no_quantity": len(size_in_name_no_qty),
        "size_in_name_but_no_quantity_examples": [i["item_name"] for i in
                                                  sorted(size_in_name_no_qty, key=lambda i: md5key(i["item_code"]))[:10]],
    }


def s3_gs1(data: dict, live: set[str]) -> dict:
    groups: dict[str, set] = defaultdict(set)
    with_row, with_group, with_brand = set(), set(), set()
    for r in data["gs1"]:
        code = r["gtin"]
        if code not in live:
            continue
        with_row.add(code)
        if (r["group_name"] or "").strip():
            with_group.add(code)
            groups[r["group_name"].strip()].add(code)
        if (r["brandname"] or "").strip():
            with_brand.add(code)
    ranked = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return {
        "live_items_with_gs1_row": len(with_row), "pct_of_live": pct(len(with_row), len(live)),
        "with_group_name": len(with_group), "with_brandname": len(with_brand),
        "distinct_group_names": len(groups),
        "group_names": [{"group_name": k, "items": len(v)} for k, v in ranked[:GS1_GROUP_CAP]],
        "group_names_not_shown": max(len(ranked) - GS1_GROUP_CAP, 0),
    }


def s4_pilot(word: str, spec: dict, live_items: list[dict]) -> dict:
    match = [i for i in live_items if word in (i["item_name"] or "")]
    match.sort(key=lambda i: md5key(i["item_code"]))
    word_rx = re.compile(w(word, True))
    noise_rx = [(re.compile(rx, re.I), why) for rx, why in spec["noise"]]

    def noise_reason(name: str) -> str | None:
        if spec.get("word_only") and not word_rx.search(name):
            return f"'{word}' only inside a longer word"
        for rx, why in noise_rx:
            if rx.search(name):
                return why
        return None

    clean = [i for i in match if noise_reason(i["item_name"] or "") is None]
    sample = match[:SAMPLE]
    out = {
        "matching_items": len(match),
        "matching_whole_word": sum(1 for i in match if word_rx.search(i["item_name"] or "")),
        "heuristic_clean_items": len(clean),
        "sample": [{"name": i["item_name"], "manufacturer": i["manufacturer_name"],
                    "quantity": i["quantity"], "unit_qty": i["unit_qty"],
                    "noise": noise_reason(i["item_name"] or "")} for i in sample],
        "groups": [],
    }
    out["sample_noise_count"] = sum(1 for s in out["sample"] if s["noise"])
    for g in spec["groups"]:
        hits_by_pat, entries = {}, []
        for p in g["patterns"]:
            rx = re.compile(p["rx"], re.I)
            hits = [i for i in match if rx.search(i["item_name"] or "")]
            hits_clean = [i for i in clean if rx.search(i["item_name"] or "")]
            entry = {"key": p["key"], "label": p["label"], "regex": p["rx"], "ambiguous_note": p["ambiguous"],
                     "hits": len(hits), "hit_pct_of_matching": pct(len(hits), len(match)),
                     "hit_pct_of_clean": pct(len(hits_clean), len(clean)),
                     "examples": [i["item_name"] for i in hits[:EXAMPLES]]}
            if "(ערך)" in p["label"]:  # value-extracting pattern: show the value spread
                vals = Counter()
                for i in hits_clean:
                    m = rx.search(i["item_name"] or "")
                    vals[next((x for x in m.groups() if x), m.group(0)).replace(",", ".")] += 1
                entry["values"] = vals.most_common(15)
            hits_by_pat[p["key"]] = {i["item_code"] for i in hits_clean}
            entries.append(entry)
        g_out = {"group": g["name"], "label": g["label"], "exclusive": g["exclusive"], "patterns": entries}
        any_hit = set().union(*hits_by_pat.values()) if hits_by_pat else set()
        g_out["coverage_pct_of_clean"] = pct(len(any_hit), len(clean))
        if g["exclusive"] and len(hits_by_pat) > 1:
            multi = [c for c in any_hit if sum(c in s for s in hits_by_pat.values()) > 1]
            g_out["overlap_pct"] = pct(len(multi), len(any_hit))
            if g_out["overlap_pct"] >= 5:
                g_out["flag"] = "AMBIGUOUS: exclusive patterns overlap on >= 5% of hits"
        out["groups"].append(g_out)
    return out


def s5_dups(live_items: list[dict]) -> dict:
    groups: dict[tuple, list] = defaultdict(list)
    for i in live_items:
        n = norm(i["item_name"])
        if not n:
            continue
        mfr = "" if is_placeholder_mfr(i["manufacturer_name"]) else norm(i["manufacturer_name"], company=True)
        q = round(float(i["quantity"]), 3) if i["quantity"] not in (None, 0) else None
        groups[(n, mfr, q)].append(i)
    dup = {k: v for k, v in groups.items() if len(v) > 1}
    top = sorted(dup.items(), key=lambda kv: (-len(kv[1]), kv[0][0]))[:15]
    return {
        "groups": len(dup), "rows_in_groups": sum(len(v) for v in dup.values()),
        "groups_with_no_manufacturer": sum(1 for k in dup if not k[1]),
        "top15": [{"name": v[0]["item_name"], "manufacturer": v[0]["manufacturer_name"], "quantity": k[2],
                   "codes": sorted(i["item_code"] for i in v)[:8], "count": len(v)} for k, v in top],
    }


def s6_hygiene(live_items: list[dict]) -> dict:
    names = [i["item_name"] or "" for i in live_items]
    n = len(names)
    mixed_tok = re.compile(rf"(?=\S*[{HEB}])(?=\S*[A-Za-z])\S+")
    both = re.compile(rf"[{HEB}].*[A-Za-z]|[A-Za-z].*[{HEB}]")
    quote_kinds = {
        '" (ascii)': lambda s: '"' in s,
        "״ (gershayim)": lambda s: "״" in s,
        "'' (two apostrophes)": lambda s: "''" in s,
        "' (single ascii apostrophe)": lambda s: "'" in s.replace("''", ""),
        "׳ (geresh)": lambda s: "׳" in s,
        "” “ (curly)": lambda s: "”" in s or "“" in s,
    }
    return {
        "leading_or_trailing_space_pct": pct(sum(1 for s in names if s != s.strip()), n),
        "double_space_pct": pct(sum(1 for s in names if "  " in s), n),
        "names_with_hebrew_and_latin_pct": pct(sum(1 for s in names if both.search(s)), n),
        "names_with_a_mixed_script_token_pct": pct(sum(1 for s in names if mixed_tok.search(s)), n),
        "mixed_token_examples": [s for s in sorted(names, key=lambda s: md5key(s)) if mixed_tok.search(s)][:8],
        "quote_variants_pct": {k: pct(sum(1 for s in names if f(s)), n) for k, f in quote_kinds.items()},
        "empty_name": sum(1 for s in names if not s.strip()),
        "name_source": [{"name_source": k, "items": v} for k, v in
                        Counter(i["name_source"] for i in live_items).most_common()],
    }


# --------------------------------------------------------------------------- output
def print_report(r: dict) -> None:
    p = print
    p("=== SU11A-35 catalog audit (read-only) ===")
    s = r["1_size"]
    p("\n## 1. Catalog size")
    p(f"items rows {s['items_rows']}; live items (price > 0 at a live store) {s['live_items']}")
    p(f"item_chain_names rows {s['item_chain_names_rows']}; items with >1 distinct chain name "
      f"{s['items_with_multiple_chain_names']} (live {s['live_items_with_multiple_chain_names']})")
    for x in s["by_item_type_is_weighted"][:12]:
        p(f"  item_type={x['item_type']} is_weighted={x['is_weighted']}: {x['items']}")

    f = r["2_fields"]
    p("\n## 2. Structured fields (live items)")
    for k, v in f["coverage_pct"].items():
        p(f"  {k}: {v}%")
    p("  placeholder manufacturer values: " + "; ".join(f"{x['value']!r} {x['items']}" for x in f["placeholder_manufacturer_top"]))
    p(f"  manufacturer distinct raw {f['manufacturer_distinct_raw']} -> normalized {f['manufacturer_distinct_normalized']}")
    p("  top 40 manufacturers (normalized): " + "; ".join(f"{x['manufacturer']} {x['items']}" for x in f["manufacturer_top40_normalized"]))
    p("  unit_qty: " + "; ".join(f"{x['value']!r} {x['items']}" for x in f["unit_qty_distribution"][:25]))
    p("  unit_of_measure: " + "; ".join(f"{x['value']!r} {x['items']}" for x in f["unit_of_measure_distribution"][:25]))
    p(f"  size written in the name but no quantity: {f['size_in_name_but_no_quantity']}")
    for e in f["size_in_name_but_no_quantity_examples"][:5]:
        p(f"    e.g. {e}")

    g = r["3_gs1"]
    p("\n## 3. GS1")
    p(f"live items with a gs1.products row {g['live_items_with_gs1_row']} ({g['pct_of_live']}%); "
      f"with group_name {g['with_group_name']}; with brandname {g['with_brandname']}; "
      f"distinct group_name {g['distinct_group_names']}")
    p("  " + "; ".join(f"{x['group_name']} {x['items']}" for x in g["group_names"]))
    if g["group_names_not_shown"]:
        p(f"  ... and {g['group_names_not_shown']} more group names (in the JSON)")

    p("\n## 4. Pilot categories")
    for word, pl in r["4_pilots"].items():
        p(f"\n### {word}: {pl['matching_items']} live items contain it "
          f"({pl['matching_whole_word']} as a whole word); heuristic clean {pl['heuristic_clean_items']}; "
          f"noise in the 40-item sample: {pl['sample_noise_count']}")
        for x in pl["sample"]:
            mark = f"  [NOISE: {x['noise']}]" if x["noise"] else ""
            p(f"  - {x['name']} | {x['manufacturer']}{mark}")
        for grp in pl["groups"]:
            extra = f", overlap {grp['overlap_pct']}%" if "overlap_pct" in grp else ""
            p(f"  [{grp['group']} / {grp['label']}] covers {grp['coverage_pct_of_clean']}% of clean items{extra}"
              f"{'  ' + grp['flag'] if 'flag' in grp else ''}")
            for e in grp["patterns"]:
                amb = f"  (note: {e['ambiguous_note']})" if e["ambiguous_note"] else ""
                p(f"    {e['key']} {e['label']}: {e['hit_pct_of_matching']}% of matching, "
                  f"{e['hit_pct_of_clean']}% of clean ({e['hits']}){amb}")
                if e.get("values"):
                    p("      values: " + ", ".join(f"{v} x{c}" for v, c in e["values"]))
                for ex in e["examples"]:
                    p(f"      e.g. {ex}")

    d = r["5_duplicates"]
    p("\n## 5. Duplicates (same normalized name + manufacturer + quantity, different barcodes)")
    p(f"groups {d['groups']}; rows {d['rows_in_groups']}; groups without a real manufacturer {d['groups_with_no_manufacturer']}")
    for x in d["top15"]:
        p(f"  {x['count']} x {x['name']} | {x['manufacturer']} | qty {x['quantity']} | {', '.join(x['codes'])}")

    h = r["6_hygiene"]
    p("\n## 6. Name hygiene (live items)")
    p(f"leading/trailing space {h['leading_or_trailing_space_pct']}%; double space {h['double_space_pct']}%; "
      f"Hebrew+Latin in one name {h['names_with_hebrew_and_latin_pct']}%; "
      f"mixed-script token {h['names_with_a_mixed_script_token_pct']}%; empty names {h['empty_name']}")
    p("quote marks: " + "; ".join(f"{k} {v}%" for k, v in h["quote_variants_pct"].items()))
    p("name_source: " + "; ".join(f"{x['name_source']} {x['items']}" for x in h["name_source"]))
    for e in h["mixed_token_examples"][:5]:
        p(f"  mixed e.g. {e}")
    p(f"\nelapsed {r['elapsed_s']} s; full JSON: {r['out']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="/tmp/catalog_audit.json")
    ap.add_argument("--dry-run", action="store_true", help="list what would be queried; no database")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    log = lambda m: print(m, file=sys.stderr, flush=True)

    if args.dry_run:
        print("database reads (READ ONLY, statement_timeout 60 s):")
        for q in QUERY_LIST:
            print(f"  - {q}")
        print(f"sections: 1 size, 2 structured fields, 3 GS1, 4 pilots, 5 duplicates, 6 name hygiene")
        print(f"pilots ({len(PILOTS)}): {', '.join(PILOTS)}")
        for word, spec in PILOTS.items():
            pats = sum(len(g["patterns"]) for g in spec["groups"])
            print(f"  {word}: {len(spec['noise'])} noise rules, {len(spec['groups'])} groups, {pats} patterns")
        print(f"samples: {SAMPLE} per pilot, ordered by md5(item_code); {EXAMPLES} examples per pattern")
        return 0

    _load_env()
    from db.db import connect
    from db.query import get_liveness

    started = time.perf_counter()
    lv = get_liveness()
    if lv is None:
        print("live-store set unavailable (get_liveness failed); stopping", file=sys.stderr)
        return 1
    conn = connect()
    try:
        _begin(conn)
        data = load(conn, sorted(lv.live_fks), log)
    finally:
        conn.rollback()
        conn.close()

    live_items = [i for i in data["items"] if i["item_code"] in data["live"]]
    report = {"session": "SU11A-35", "out": args.out, "live_stores": len(lv.live_fks)}
    report["1_size"] = s1_size(data, live_items)
    report["2_fields"] = s2_fields(live_items)
    report["3_gs1"] = s3_gs1(data, data["live"])
    report["4_pilots"] = {}
    for word, spec in PILOTS.items():
        log(f"pilot {word}")
        report["4_pilots"][word] = s4_pilot(word, spec, live_items)
    report["5_duplicates"] = s5_dups(live_items)
    report["6_hygiene"] = s6_hygiene(live_items)
    report["elapsed_s"] = round(time.perf_counter() - started, 1)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
