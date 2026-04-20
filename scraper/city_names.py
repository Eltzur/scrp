"""Canonical Hebrew city names and variant normalization."""

# Maps canonical name → list of known variants (including the canonical itself)
CITY_VARIANTS: dict[str, list[str]] = {
    "ירושלים":   ["ירושלים", 'י"ם', "י-ם", "jerusalem", "ירושליים"],
    "תל אביב":   ["תל אביב", "תל-אביב", 'ת"א', "tel aviv", "תל אביב-יפו"],
    "חיפה":      ["חיפה", "haifa"],
    "באר שבע":   ["באר שבע", "באר-שבע", 'ב"ש', "beer sheva", "beer-sheva"],
    "ראשון לציון": ["ראשון לציון", "ראשון-לציון", 'ר"ל', "rishon lezion"],
    "פתח תקווה": ["פתח תקווה", "פתח-תקווה", 'פ"ת', "petah tikva"],
    "נתניה":     ["נתניה", "netanya"],
    "אשדוד":     ["אשדוד", "ashdod"],
    "אשקלון":    ["אשקלון", "ashkelon"],
    "הרצליה":    ["הרצליה", "herzliya"],
    "רמת גן":    ["רמת גן", "רמת-גן", "ramat gan"],
    "בני ברק":   ["בני ברק", "בני-ברק", "bnei brak"],
    "חולון":     ["חולון", "holon"],
    "בת ים":     ["בת ים", "בת-ים", "bat yam"],
    "כפר סבא":   ["כפר סבא", "כפר-סבא", "kfar saba"],
    "רחובות":    ["רחובות", "rehovot"],
    "הוד השרון": ["הוד השרון", "הוד-השרון", "hod hasharon"],
    "מודיעין":   ["מודיעין", "מודיעין-מכבים-רעות", "modiin"],
    "לוד":       ["לוד", "lod"],
    "רמלה":      ["רמלה", "ramla"],
}

# Inverted lookup: lowercase variant → canonical
_LOOKUP: dict[str, str] = {}
for _canonical, _variants in CITY_VARIANTS.items():
    _LOOKUP[_canonical.lower()] = _canonical
    for _v in _variants:
        _LOOKUP[_v.lower()] = _canonical


def normalize_city(raw: str | None) -> str | None:
    if not raw:
        return raw
    cleaned = raw.strip()
    return _LOOKUP.get(cleaned.lower(), cleaned)
