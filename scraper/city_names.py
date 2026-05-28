"""Canonical Hebrew city names and variant normalization."""

# Manual store→city overrides: keyed (chain_id, store_id) → canonical city name.
# Used to permanently fix stores whose chain provides no reliable city data.
STORE_CITY_OVERRIDES: dict[tuple[str, str], str] = {
    ("7290696200003", "009"): "תל אביב",      # הארבעה ת"א
    ("7290696200003", "016"): "תל אביב",      # פלורנטין
    ("7290696200003", "022"): "חדרה",         # חדרה בפארק
    ("7290696200003", "023"): "ראשון לציון",  # ראשון פרס נובל
    ("7290696200003", "027"): "חיפה",         # שער העליה
    ("7290696200003", "037"): "אשדוד",        # קניון אשדוד
    ("7290803800003", "008"): "תל אביב",      # אחד העם
    ("7290803800003", "027"): "תל אביב",      # יד אליהו
    ("7290803800003", "054"): "תל אביב",      # ת"א - אחד העם
    ("7290058108879", "334"): "דיר חנא",
    ("7290058108879", "335"): "כפר ברא",
    ("7290058108879", "336"): "קלנסווה",
    ("7290058108879", "337"): "אעבלין",
    ("7290058108879", "339"): "תל אביב יפו",
    ("7290058108879", "340"): "סכנין",
}


def city_override(chain_id: str, store_id: str) -> str | None:
    """Return the manually-corrected city for a store, or None if no override.
    Keyed (chain_id, store_id); store_id normalized to 3-digit zero-padded."""
    return STORE_CITY_OVERRIDES.get((str(chain_id), str(store_id).zfill(3)))


# Maps canonical name → list of known variants (including the canonical itself)
CITY_VARIANTS: dict[str, list[str]] = {
    "ירושלים":   ["ירושלים", 'י"ם', "י-ם", "jerusalem", "ירושליים"],
    "תל אביב":   ["תל אביב", "תל-אביב", 'ת"א', "tel aviv", "תל אביב-יפו", "תל אביב יפו", "יפו"],
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
