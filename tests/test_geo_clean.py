"""Unit tests for scripts/geo_clean.py (SU11A-15). Run: python -m pytest tests/test_geo_clean.py -q"""
import pytest

from scripts.geo_clean import clean_address, has_sderot

BOTH = ("rehov", "sderot")

# (address, cities, strip, expected) - the 33 SU11A-15 phase-1 cases.
CASES = [
    ("רח' האורה 152", (), BOTH, "האורה 152"),
    ("רח׳ האורה 152", (), BOTH, "האורה 152"),
    ("רח’ האורה 152", (), BOTH, "האורה 152"),
    ("רח. האורה 152", (), BOTH, "האורה 152"),
    ("שדרות בן גוריון 5", (), BOTH, "בן גוריון 5"),
    ("שד' ירושלים 12", (), BOTH, "ירושלים 12"),
    ("רחוב הרצל 7", (), BOTH, "הרצל 7"),
    ("רחובות", (), BOTH, "רחובות"),                      # the city name, as an address
    ("שדרות", (), BOTH, "שדרות"),                        # Sderot / a bare type word
    ("הרצל 5", ("רחובות",), BOTH, "הרצל 5"),             # city Rehovot untouched
    ("הרצל 5", ("שדרות",), BOTH, "הרצל 5"),              # city Sderot untouched
    ("רחובות 12", (), BOTH, "רחובות 12"),
    ("שדרותיה 4", (), BOTH, "שדרותיה 4"),               # letters inside another word
    ("רחובי 3", (), BOTH, "רחובי 3"),
    ("רחוב", (), BOTH, "רחוב"),                          # never an empty street
    ("שד' 5", (), BOTH, "שד' 5"),
    ("שד' 26 באוקטובר 3", (), BOTH, "26 באוקטובר 3"),   # known limitation: parses fine
    ('תרצה 19ר"ג', ("רמת גן",), BOTH, "תרצה 19"),
    ("4-6 גרפית", (), BOTH, "4 גרפית"),
    ("האורנים 1 מ.מסחרי", (), BOTH, "האורנים 1"),
    ("כביש מס' 4", (), BOTH, "כביש 4"),
    ('רח\' הרוא"ה 152', ("רמת גן",), BOTH, 'הרוא"ה 152'),
    ("יפו 12", ("ירושלים",), BOTH, "יפו 12"),
    ("רח'הרצל 3", (), BOTH, "הרצל 3"),
    ("בן יהודה 130 פינת בן גוריון", (), BOTH, "בן יהודה 130"),
    ("הרצל פ.קיבוץ גלויות", (), BOTH, "הרצל"),
    ("ויצמן פינת יצחק רבין", (), BOTH, "ויצמן"),
    ("פינת חי 3", (), BOTH, "פינת חי 3"),
    ("כישור 22, חולון, ישראל", ("חולון",), BOTH, "כישור 22"),
    ('הלחי 16 ראשל"צ , ישראל', ("ראשון לציון",), BOTH, "הלחי 16"),
    ("דרך הים 1 , רחובות", ("רחובות",), BOTH, "דרך הים 1"),
    ("שרפה 22, כביש ראשי של העיר 0", ("אום אל פחם",), BOTH, "שרפה 22, כביש ראשי של העיר"),
    ("רח' התחייה 7, פרדס חנה", ("פרדס חנה",), BOTH, "התחייה 7"),
]

# SU11A-15 phase 2: default policy and the new rules.
CASES_PHASE2 = [
    # Default strips רחוב / רח' only; שדרות / שד' are kept for the first query.
    ("שדרות בן גוריון 5", (), ("rehov",), "שדרות בן גוריון 5"),
    ("שד' ירושלים 12", (), ("rehov",), "שד' ירושלים 12"),
    ("רח' האורה 152", (), ("rehov",), "האורה 152"),
    ("רחוב הרצל 7", (), ("rehov",), "הרצל 7"),
    # Letters glued to the house number.
    ("הרב מסעוד אשר20א", (), ("rehov",), "הרב מסעוד אשר 20א"),
    # Abbreviation spelled out.
    ('קק"ל 35', (), ("rehov",), "קרן קיימת לישראל 35"),
    # Common first name glued to the surname.
    ("נתןברניצקי 13", (), ("rehov",), "נתן ברניצקי 13"),
    ("דודאים 4", (), ("rehov",), "דודאים 4"),            # too short a remainder: untouched
    # Truncated "מרכז" after the number.
    ('צה"ל 71, מרכ', (), ("rehov",), 'צה"ל 71'),
    ("שד' הנשיא 124 מר", (), ("rehov",), "שד' הנשיא 124"),
]


@pytest.mark.parametrize("addr,cities,strip,want", CASES + CASES_PHASE2)
def test_clean_address(addr, cities, strip, want):
    assert clean_address(addr, cities, strip=strip) == want


def test_city_argument_is_never_edited():
    for city in ("רחובות", "שדרות"):
        cities = (city,)
        clean_address("רחוב הרצל 7", cities, strip=BOTH)
        assert cities == (city,)


def test_empty_and_none():
    assert clean_address(None) is None
    assert clean_address("") == ""


@pytest.mark.parametrize("addr,want", [
    ("שדרות בן גוריון 5", True), ("שד' ירושלים 12", True), ("שד׳ירושלים 3", True),
    ("רחוב הרצל 7", False), ("שדרותיה 4", False), ("הרצל 5", False), (None, False),
])
def test_has_sderot(addr, want):
    assert has_sderot(addr) is want
