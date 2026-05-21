"""City resolution from store_name / address text.

Used as a *fallback* by chain scrapers when the numeric government
city-code lookup (CITY_CODES) yields nothing — which happens when a
chain's Stores XML omits the City field or reports a code we don't map.

Origin: extracted from the session-9j one-shot `normalize_cities.py`,
which backfilled 349 NULL-city stores. Porting the logic here means new
stores get a city at scrape time instead of accumulating as NULLs.

Public API:
    resolve_city(store_name, address, chain_id=None) -> (city|None, confidence)

`confidence` is 0.0–1.0. Callers should apply a threshold (recommend
≥0.80) before trusting an auto-match. Below that, leave city NULL and
let it surface in a periodic NULL-city audit.
"""
import re

# --------------------------------------------------------------------------
# City dictionary — canonical Hebrew names. Covers chains' supermarket
# footprint; not every Israeli town. Extend as new misses surface.
# --------------------------------------------------------------------------
CITIES: set[str] = {
    # Tier 1
    "ירושלים", "תל אביב", "תל אביב יפו", "חיפה", "באר שבע", "ראשון לציון",
    "פתח תקווה", "נתניה", "אשדוד", "אשקלון", "חולון", "בני ברק",
    "רמת גן", "רחובות", "בת ים", "כפר סבא", "הרצליה", "רעננה",
    "מודיעין", "מודיעין מכבים רעות", "לוד", "רמלה", "נצרת", "נצרת עילית",
    # Tier 2 (50K+)
    "ראש העין", "עפולה", "נהריה", "עכו", "טבריה", "אילת", "דימונה",
    "קרית גת", "קרית מוצקין", "קרית ביאליק", "קרית אתא", "קרית ים",
    "קרית אונו", "קרית שמונה", "קרית מלאכי", "קרית טבעון", "קרית חיים",
    "בית שמש", "ביתר עילית", "אריאל", "צפת", "טירה", "טייבה",
    "מעלה אדומים", "אור יהודה", "אור עקיבא", "יבנה", "גבעתיים",
    "גבעת שמואל", "הוד השרון", "יהוד", "נשר", "טירת כרמל", "טירת הכרמל",
    "פרדס חנה", "פרדס חנה כרכור", "בית שאן", "מגדל העמק", "שדרות",
    "מבשרת ציון", "נס ציונה", "גן יבנה", "אופקים", "נתיבות", "ערד",
    "כרמיאל", "מעלות", "מעלות תרשיחא", "ראש פינה", "חצור הגלילית",
    "יקנעם", "יוקנעם", "יקנעם עילית", "סחנין", "אלעד",
    "אום אל פחם", "באקה אל גרביה", "באקה ג'ת", "כפר קאסם", "קלנסווה",
    "טמרה", "כפר יונה", "תל מונד", "אבן יהודה", "פרדסיה", "קדימה",
    "קדימה צורן", "אבו גוש", "שוהם", "בנימינה", "כוכב יאיר",
    "בית דגן", "באר יעקב", "מזכרת בתיה", "גדרה", "קיסריה", "זכרון יעקב",
    "זכרון", "חדרה", "עתלית", "מטולה", "מצפה רמון",
    # Tier 3 / observed in 9j null data
    "חריש", "מיתר", "רכסים", "גוש עציון", "מישור אדומים", "שער בנימין",
    "באר טוביה", "תל חנן", "צור משה", "נוף הגליל", "גבעת רם",
    "כרכור", "בית וגן", "פולג", "אחד העם", "עקרון", "בילו",
    "חוצות המפרץ", "מבוא ביתר", "ביתן אהרן", "תל חי", "תל-חי",
    "דליית אל כרמל", "דלית אל כרמל", "צור יצחק", "נצר סירני",
    "עמק חפר", "בית חשמונאי", "יד אליהו", "איירפורט סיטי",
    "ראשלצ", "רעות", "כורדני", "אשדות יעקב",
    "דיזנגוף סנטר", "דיזנגוף", "סוקולוב",
    "צור יגאל", "ירוחם", "חצור", "כרמי גת", "כפר תבור",
    "קצרין", "כפר נטר", "גבעת עדה", "גבעת אולגה",
    "כפר ורדים", "אלקנה", "שילת", "בת חפר", "פתח תקוה",
    "שהם", "שפרעם", "ירכא", "כפר גנים", "אפרת", "סביונים",
    "אם המושבות", "רהט", "יפו", "כפר קרע", "צומת גבעת מרדכי",
    "בארות יצחק", "מידטאון", "כוכב הצפון", "אגמים", "דניה",
    "אבן גבירול", "גבעת אלונים", "אזורי חן", "תל ברוך", "אור ים",
    "סכנין", "ראש-פינה", "משמר השרון", "כנפי נשרים", "שירת הים",
    "נאות שמיר",
    # Sub-format favored neighborhoods (treated as city)
    "רמת השרון", "מטה בנימין", "רמת אביב", "רמת ישי",
    "גבעת אבני", "גבעת זאב", "ביר אל מכסור", "ביר זית",
}

# Abbreviation → canonical expansion
ABBREV: dict[str, str] = {
    'כ"ס': "כפר סבא", 'כ״ס': "כפר סבא", "כס": "כפר סבא",
    'ראשל"צ': "ראשון לציון", 'ראשל״צ': "ראשון לציון", "ראשלצ": "ראשון לציון",
    'ת"א': "תל אביב", 'ת״א': "תל אביב",
    'ב"ש': "באר שבע", 'ב״ש': "באר שבע",
    'פ"ת': "פתח תקווה", 'פ״ת': "פתח תקווה",
    'בית"ר': "ביתר עילית", 'בית״ר': "ביתר עילית",
    'רמה"ש': "רמת השרון", 'רמה״ש': "רמת השרון",
    "ק.אתא": "קרית אתא", "ק. אתא": "קרית אתא",
    "ק.ביאליק": "קרית ביאליק", "ק. ביאליק": "קרית ביאליק",
    "ק.מוצקין": "קרית מוצקין", "ק. מוצקין": "קרית מוצקין",
    "ק.אונו": "קרית אונו", "ק. אונו": "קרית אונו",
    "ק.ים": "קרית ים", "ק. ים": "קרית ים",
    "ק.גת": "קרית גת", "ק. גת": "קרית גת",
    "ק.טבעון": "קרית טבעון", "ק. טבעון": "קרית טבעון",
    "ק.חיים": "קרית חיים", "ק. חיים": "קרית חיים",
    "מודיעין החדש": "מודיעין",
    "מידיעין": "מודיעין",
    "קריית": "קרית",
    "רמתהשרון": "רמת השרון",
    "Be": "BE",
}

# Sub-format prefixes — stripped before matching so "שלי רעננה" → "רעננה"
SHUFERSAL_PREFIXES = [
    "שלי", "דיל", "אקספרס", "BE", "יש חסד", "יש",
    "יוניברס", "מהדרין", "אקסטרא", "אקסטרה", "טוב מאוד",
]
CARREFOUR_PREFIXES = ["קרפור סיטי", "קרפור מרקט", "קרפור היפר", "קרפור", "יינות ביתן"]

# Chain IDs (canonical, post-9j corrections)
CHAIN_SHUFERSAL  = "7290027600007"
CHAIN_CARREFOUR  = "7290055700007"
CHAIN_RAMILEVY   = "7290058140886"
CHAIN_YOCHANANOF = "7290803800003"
CHAIN_KESHET     = "7290785400000"
CHAIN_OSHERAD    = "7290103152017"
CHAIN_VICTORY    = "7291059100008"

_SORTED_CITIES = sorted(CITIES, key=lambda x: -len(x))
_HEBREW = r"\u0590-\u05FF"

# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------
def _strip_leading_id(s: str) -> str:
    return re.sub(r"^\d{1,5}\s*-\s*", "", s).strip()

def _strip_trailing_parens(s: str) -> str:
    return re.sub(r"\s*\([^)]+\)\s*$", "", s).strip()

def _strip_chain_prefix(s: str, prefixes: list[str]) -> tuple[str, str | None]:
    for p in prefixes:
        if s.startswith(p + " ") or s.startswith(p + "-"):
            return s[len(p):].lstrip(" -"), p
        if s == p:
            return "", p
    return s, None

def _expand_abbrev(s: str) -> str:
    """Expand abbreviations only at word boundaries — avoids corrupting
    words that merely contain an abbreviation (e.g. 'רכסים')."""
    for abbr, full in ABBREV.items():
        pattern = (r"(?:^|(?<=[^" + _HEBREW + r"A-Za-z]))"
                   + re.escape(abbr)
                   + r"(?=[^" + _HEBREW + r"A-Za-z]|$)")
        s = re.sub(pattern, full, s)
    return s

def _find_city(text: str, strict: bool = False) -> tuple[str | None, float]:
    """Find a known city in free text, Hebrew-safe word boundaries.
    strict=True requires the city to be ≥40% of the text (guards against
    street names that happen to contain a city name)."""
    if not text:
        return None, 0.0
    text = _expand_abbrev(text).strip()
    for city in _SORTED_CITIES:
        pattern = (r"(?:^|[^" + _HEBREW + r"A-Za-z])"
                   + re.escape(city)
                   + r"(?:[^" + _HEBREW + r"A-Za-z]|$)")
        m = re.search(pattern, text)
        if m:
            ratio = len(city) / max(len(text), 1)
            if strict and ratio < 0.4:
                continue
            at_edge = (m.start() <= 1) or (m.end() >= len(text) - 1)
            conf = 0.95 if ratio > 0.5 else (0.88 if at_edge else 0.75)
            return city, conf
    return None, 0.0

# --------------------------------------------------------------------------
# Per-chain matchers
# --------------------------------------------------------------------------
def _match_shufersal(store_name: str, address: str) -> tuple[str | None, float]:
    name = _strip_leading_id(store_name)
    name, _ = _strip_chain_prefix(name, SHUFERSAL_PREFIXES)
    head = _expand_abbrev(name.split("-")[0].strip())
    if head in CITIES:
        return head, 0.97
    for city in _SORTED_CITIES:
        if head == city or head.startswith(city + " ") or head.endswith(" " + city):
            return city, 0.95
    city, conf = _find_city(name)
    if city:
        return city, conf * 0.9
    return None, 0.0

def _match_carrefour(store_name: str, address: str) -> tuple[str | None, float]:
    if not store_name.strip() and not address.strip():
        return None, 0.0
    name = _strip_leading_id(_strip_trailing_parens(store_name))
    name, _ = _strip_chain_prefix(name, CARREFOUR_PREFIXES)
    name = _expand_abbrev(name)
    city, conf = _find_city(name)
    if city:
        return city, conf
    city, conf = _find_city(address, strict=True)
    if city:
        return city, conf * 0.85
    return None, 0.0

def _match_generic(store_name: str, address: str) -> tuple[str | None, float]:
    """Default matcher — store_name often IS the city, or contains it.
    Used for Yochananof, Keshet, Rami Levy, Osher Ad, Victory."""
    name = _strip_leading_id(store_name).strip()
    name = re.sub(r"^יוחננוף\s+", "", name).strip()  # drop chain-name prefix
    name = _expand_abbrev(name)
    if name in CITIES:
        return name, 0.98
    city, conf = _find_city(name)
    if city:
        return city, conf
    city, conf = _find_city(address, strict=True)
    if city:
        return city, conf * 0.85
    return None, 0.0

_CHAIN_MATCHERS = {
    CHAIN_SHUFERSAL: _match_shufersal,
    CHAIN_CARREFOUR: _match_carrefour,
}

# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def resolve_city(store_name: str | None,
                 address: str | None = None,
                 chain_id: str | None = None) -> tuple[str | None, float]:
    """Resolve a Hebrew city name from a store's name/address text.

    Returns (city, confidence). city is None when nothing matched.
    Pick a per-chain matcher when chain_id is known, else use the
    generic matcher. Callers should threshold confidence (≥0.80
    recommended) before writing the result.
    """
    store_name = (store_name or "").strip()
    address = (address or "").strip()
    if not store_name and not address:
        return None, 0.0
    matcher = _CHAIN_MATCHERS.get(chain_id, _match_generic)
    return matcher(store_name, address)
