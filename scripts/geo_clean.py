"""Clean a feed address into a Nominatim query (SU11A-15).

    clean_address(addr, cities, strip=("rehov",)) -> str

ONLY THE QUERY IS CLEANED. stores.address keeps exactly what the chain
published, address_override is never touched, and stores.geo_input is still
built from the raw address (scripts/geo_nominatim.build_geo_input), so the
geocoder's "did the input change?" test is unaffected by this module.

STREET-TYPE WORDS (Dude, SU11A-15). רחוב / רח' are always removed. שדרות / שד'
are removed only when the caller asks (strip=("rehov", "sderot")): OSM often
keeps "שדרות" inside the street name, so geo_nominatim queries a boulevard
with the word KEPT first and retries stripped only on NO_MATCH, logging both.
Rules for the removal:
  * only from the STREET part - the text before the house number (after a
    number-first address: after it), after any glued city suffix is gone;
  * never from the city: the city is a separate argument and is never edited;
  * whole tokens only (with ׳ ' ’ ` or a trailing dot), so רחובות, שדרות-the-
    city and any word merely containing these letters are untouched;
  * a street that is nothing but the type word ("שדרות", "שד' 5") is left as is.

The evaluator (geo_nominatim.normalize_street) already drops these words on
BOTH sides when it compares street names, so a stripped query is still
compared correctly.

Other rules, each from a real feed address (SU11A-13/15):
  "כישור 22, חולון, ישראל"      trailing ", ישראל"
  "כביש 4, … לפוריידיס 0"        placeholder house number 0
  'תרצה 19ר"ג'                   city (or its abbreviation) glued on
  "צה"ל 71, מרכ" / "… 124 מר"     truncated "מרכז" after the number
  "האורנים 1 מ.מסחרי"            "מ.מסחרי" / "מרכז מסחרי"
  "כביש מס' 4"                   -> "כביש 4"
  "בן יהודה 130 פינת בן גוריון"  corner: keep the first street
  "4-6 גרפית"                    range: keep the first number
  "הרב מסעוד אשר20א"             letters glued to the number
  'קק"ל 35'                      abbreviation -> "קרן קיימת לישראל 35"
  "נתןברניצקי 13"                common first name glued to the surname
"""
from __future__ import annotations

import re

_Q = "['׳’`.]"
TYPE_WORDS = {
    "rehov": re.compile(rf"^(?:רחוב|רח{_Q}?)$"),
    "sderot": re.compile(rf"^(?:שדרות|שד{_Q}?)$"),
}
# Glued abbreviation with a REQUIRED quote: "רח'הרצל", "שד'ירושלים".
_GLUED = {
    "rehov": re.compile(rf"^רח{_Q}(?=[א-ת])"),
    "sderot": re.compile(rf"^שד{_Q}(?=[א-ת])"),
}
# City abbreviations seen glued to house numbers or appended in feeds.
CITY_ABBR = {
    "רמת גן": ['ר"ג', "ר״ג", "ר'ג"],
    "תל אביב-יפו": ['ת"א', "ת״א", "תל אביב", "תל-אביב", "תל אביב יפו", "תלאביב"],
    "פתח תקווה": ['פ"ת', "פ״ת", "פתח תקוה", "פתח-תקווה"],
    "בני ברק": ['ב"ב', "ב״ב"],
    "ראשון לציון": ['ראשל"צ', "ראשל״צ", "ראשלצ"],
    "קריית אתא": ["ק.אתא", "קרית אתא"],
    "קריית ביאליק": ["ק.ביאליק", "קרית ביאליק"],
    "קריית מוצקין": ["ק.מוצקין", "קרית מוצקין"],
    "קריית ים": ["ק.ים", "קרית ים"],
    "קריית גת": ["ק.גת", "קרית גת"],
    "קריית שמונה": ["ק.שמונה", "קרית שמונה"],
    "באר שבע": ['ב"ש', "ב״ש", "באר-שבע"],
}
# Street-name abbreviations OSM spells out.
ABBREVIATIONS = {
    'קק"ל': "קרן קיימת לישראל",
    "קק״ל": "קרן קיימת לישראל",
    "ק.ק.ל": "קרן קיימת לישראל",
}
# First names that feeds glue to the surname ("נתןברניצקי"). Split only when at
# least 4 letters follow, so short real words starting with these are left alone.
_GLUED_FIRST_NAMES = ("אברהם", "יצחק", "יעקב", "משה", "דוד", "יוסף", "נתן", "חיים",
                      "שמואל", "אליהו", "מנחם", "זאב", "הרב")

_COMMERCIAL = re.compile(r"(?:^|\s)(?:מ\.?\s?מסחרי|מרכז\s+מסחרי|מרכ\"מ)(?=\s|,|$)")
_KVISH = re.compile(r"כביש\s+(?:מס['׳’.]?|מספר)\s*(\d+)")
_CORNER = re.compile(r"(?<=\S)\s+(?:ו?פינת\s|פ\.\s?(?=[א-ת])).*$")
_RANGE = re.compile(r"(?<!\d)(\d{1,4})\s*-\s*\d{1,4}(?!\d)")
_TRUNC_MERKAZ = re.compile(r"(\d[א-ת]?)\s*,?\s*(?:מרכז|מרכ|מר)\.?\s*$")
_GLUED_DIGIT = re.compile(r"([א-ת]{2,})(\d)")
_NUMTOK = re.compile(r"^\d{1,4}[א-ת]?$")


def _city_variants(cities) -> list[str]:
    out: set[str] = set()
    for c in cities:
        if not c:
            continue
        c = re.sub(r"\s+", " ", c.strip())
        out |= {c, c.replace("-", " "), c.replace(" ", "-")}
        for k, v in CITY_ABBR.items():
            if c == k or c in v:
                out |= {k} | set(v)
    return sorted((v for v in out if v), key=len, reverse=True)


def strip_city(addr: str, cities) -> str:
    """Drop a city name/abbreviation at the end, glued to the number or not.
    Only when a house number survives - "יפו 12" in Jerusalem stays."""
    s = addr
    for v in _city_variants(cities):
        s2 = re.sub(rf"(?:\s*,\s*|\s+|(?<=\d)){re.escape(v)}\s*$", "", s)
        if s2 != s and re.search(r"\d", s2) and re.search(r"[א-תA-Za-z]{2}", s2):
            s = s2.strip(" ,")
    return s


def strip_type_words(street: str, strip=("rehov",)) -> str:
    """Remove street-type tokens from a STREET PART; never empty the street."""
    kept = []
    for t in street.split():
        if any(TYPE_WORDS[k].match(t) for k in strip):
            continue
        for k in strip:
            t = _GLUED[k].sub("", t)
        kept.append(t)
    if not any(re.search(r"[א-תA-Za-z]{2}", t) and not _NUMTOK.match(t) for t in kept):
        return street
    return " ".join(kept)


def has_sderot(addr: str | None) -> bool:
    """Does the address carry שדרות / שד' (whole token or glued with a quote)?"""
    for t in (addr or "").split():
        if TYPE_WORDS["sderot"].match(t) or _GLUED["sderot"].match(t):
            return True
    return False


def _split_glued_first_name(tok: str) -> str:
    for name in _GLUED_FIRST_NAMES:
        if tok.startswith(name) and len(tok) - len(name) >= 4 and re.fullmatch(r"[א-ת]+", tok):
            return f"{name} {tok[len(name):]}"
    return tok


def clean_address(addr: str | None, cities=(), strip=("rehov",)) -> str | None:
    if not addr:
        return addr
    s = re.sub(r"\s+", " ", addr).strip().strip(",")
    s = re.sub(r"\s*,?\s*ישראל\s*$", "", s)
    s = re.sub(r"(?<=\D)\s+0\s*$", "", s)
    s = strip_city(s, cities)
    s = _TRUNC_MERKAZ.sub(r"\1", s)
    s = _COMMERCIAL.sub(" ", s)
    s = _KVISH.sub(r"כביש \1", s)
    for k, v in ABBREVIATIONS.items():
        s = re.sub(rf"(?<![א-ת]){re.escape(k)}(?![א-ת])", v, s)
    s2 = _CORNER.sub("", s)
    if re.search(r"[א-ת]{2}", s2):
        s = s2
    s = _RANGE.sub(r"\1", s)
    s = _GLUED_DIGIT.sub(r"\1 \2", s)
    s = " ".join(_split_glued_first_name(t) for t in s.split())
    s = re.sub(r"\s+", " ", s).strip(" ,")
    out = []
    for part in s.split(","):
        toks = part.split()
        nums = [i for i, t in enumerate(toks) if _NUMTOK.match(t)]
        if nums:
            i = nums[-1]
            before, num, after = toks[:i], toks[i], toks[i + 1:]
            street = strip_type_words(" ".join(before if before else after), strip).split()
            p = " ".join(street + [num]) if before else " ".join([num] + street)
            if before and after:
                p += " " + " ".join(after)
        else:
            p = strip_type_words(part.strip(), strip)
        out.append(p.strip())
    return ", ".join(x for x in out if x)
