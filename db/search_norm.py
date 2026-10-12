"""Text normalization shared by the search v2 build and engine (SU11A-36).

scripts/build_search_items.py writes search_items.name_norm / manufacturer_norm
with normalize(), and db/search_v2.py normalizes the query with the SAME
function, so both sides of every comparison went through identical rules.
Change it in one place only, and rebuild search_items after any change
(--apply), or stored names and queries stop agreeing.

Rules, in order:
  - Unicode NFC (composed forms; niqqud is stripped separately below)
  - Latin letters lowercased (Hebrew has no case)
  - quote marks unified: ״ “ ” „ and " -> "   ׳ ‘ ’ ` ´ and ' -> '
  - hyphen, maqaf and dashes -> space ("קוקה-קולה" == "קוקה קולה")
  - niqqud and cantillation marks removed
  - whitespace collapsed, ends trimmed
Everything else is kept as it is: digits, %, '.', ',' and the rest of the
punctuation, so "3%" and "1.5" still match the way the old search matches them.

Also: tokenize() (query tokens) and lexicon_words() (words for search_lexicon),
plus the coupon pseudo-item rule, all pure functions so they are unit-tested
without a database.
"""
from __future__ import annotations

import re
import unicodedata

_DOUBLE_QUOTES = "״“”„‟ʺ"   # ״ “ ” „ ‟ ʺ
_SINGLE_QUOTES = "׳‘’‚‛`´ʹʼ"  # ׳ ‘ ’ ‚ ‛ ` ´ ʹ ʼ
_DASHES = "-־‐‑‒–—―−"  # - ־ ‐ ‑ ‒ – — ― −

_TRANSLATE = {ord(c): '"' for c in _DOUBLE_QUOTES}
_TRANSLATE.update({ord(c): "'" for c in _SINGLE_QUOTES})
_TRANSLATE.update({ord(c): " " for c in _DASHES})

# Hebrew points and cantillation: U+0591-U+05BD, U+05BF, U+05C1-U+05C2,
# U+05C4-U+05C5, U+05C7. Maqaf (U+05BE) is handled above as a dash; sof pasuq
# (U+05C3) and paseq (U+05C0) are punctuation and stay.
_NIQQUD = re.compile("[֑-ׇֽֿׁׂׅׄ]")
_SPACES = re.compile(r"\s+")


def normalize(s: str | None) -> str:
    """The one normalization for names, manufacturers and queries. None -> ''."""
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s)
    s = _NIQQUD.sub("", s)
    s = s.translate(_TRANSLATE)
    s = s.lower()  # Latin (and other cased scripts); Hebrew is unaffected
    return _SPACES.sub(" ", s).strip()


def tokenize(q_norm: str) -> list[str]:
    """Query tokens: split on spaces, keep tokens of 2+ characters.

    Same rule as the old search's _is_meaningful: a 1-character token substring-
    matches most of the catalog and is dropped, while 2-letter Hebrew words
    (דג, תה) are real words and stay.
    """
    return [t for t in q_norm.split(" ") if len(t) >= 2]


# Punctuation stripped from the ends of a word for the lexicon. Quotes inside a
# word are kept (ש"ח, ג'בטה); a leading/trailing quote or bracket is noise.
_EDGE = "\"'.,;:!?()[]{}<>/\\|*+=#&@^~_"
_HAS_DIGIT = re.compile(r"\d")


def lexicon_words(text_norm: str) -> list[str]:
    """Distinct words of an already-normalized string, for search_lexicon.

    Words containing a digit are skipped: sizes and percentages are not
    vocabulary, and the typo fallback must never "correct" a number.
    """
    out = []
    seen = set()
    for raw in text_norm.split(" "):
        w = raw.strip(_EDGE)
        if len(w) < 2 or _HAS_DIGIT.search(w) or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


# ---------------------------------------------------------------------------
# Pseudo items (decision D1, SU11A-36)
# ---------------------------------------------------------------------------
# Coupon pseudo-products are chain promo mechanics published as items
# ("הנ.קופון מאגדת יוגורט תנובה", "קופון 15% שוקו תנובה", often priced 0.01).
# They are hidden from catalog search and stay in the promo layer.
#
# Conservative on purpose: only the FIRST word is checked, so a real product
# that merely mentions a coupon later in its name is not hidden. Patterns are
# matched against the normalized name.
COUPON_PATTERNS: dict[str, re.Pattern] = {
    # קופון..., קופונים...
    "coupon_first_word": re.compile(r"^קופו?ן"),
    # הנ.קופון / הנ קופון / הנ'קופון / הנחת קופון / הנחה קופון
    "discount_coupon_first_word": re.compile(r"^(הנ['\".]?|הנחת|הנחה)\s?קופו?ן"),
}
# Every live price of the item is below this (in NIS): 0.01-style placeholders.
PSEUDO_MAX_PRICE = 0.05


def coupon_pattern(name_norm: str) -> str | None:
    """Name of the coupon pattern the normalized name matches, or None."""
    for key, rx in COUPON_PATTERNS.items():
        if rx.search(name_norm):
            return key
    return None


def is_pseudo(name_norm: str, max_live_price: float | None) -> bool:
    """D1 rule: coupon-like first word, OR every live price below 0.05."""
    if coupon_pattern(name_norm):
        return True
    return max_live_price is not None and max_live_price < PSEUDO_MAX_PRICE
