"""Search v2 (SU11A-36): rank and count from search_items, price only the page.

The old /search (api/routers/search.py _build_result) fetches every live price
row of every matching barcode before it pages - 417K rows and ~15 s for חלב.
v2 matches, counts and ranks on search_items (one precomputed row per live
barcode, built nightly by scripts/build_search_items.py) and calls the existing
fetch_prices / group_by_product for the 30 barcodes on the page only.

Behind SEARCH_V2 (off | test | on, see the router). Anything unexpected here -
table missing, empty, older than 48 h, any exception - makes the router log a
warning and answer with the old path; v2 never causes a 500.

Differences from the old path, on purpose:
  - Ranking is price-neutral: relevance tier, then 2+ chains first, then
    popularity (0 until SU11A-37), chains, shorter name, item_code.
  - Coupon pseudo-items (D1) are not candidates, so they are neither listed nor
    counted in total_matches.
  - Matching is on normalized text (db/search_norm.py): case, quote marks,
    hyphens and niqqud no longer split a match.
  - Brand aliases (search_lexicon kind=alias) let "milka" also match מילקה.
  - A 0-result query gets one typo-correction round (corrected_from is set).
  - A barcode typed as the query (8-14 digits, incl. UPC-A <-> EAN-13) returns
    that item directly.
  - Eilat (VAT-free) quotes are dropped before cheapest / most expensive unless
    the city filter includes Eilat, keeping them only when an item has no
    other quote (D2).
  - total_matches / comparable_count come from search_items (as of the last
    build), not from a live price fetch.

Pure functions (parse, aliases, tiers, ranking, correction, Eilat) take no
database and are unit-tested in tests/test_search_v2.py.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from db.query import _digit_run_pattern, _like_escape, fetch_prices, group_by_product
from db.search_norm import normalize, tokenize

log = logging.getLogger(__name__)

MAX_AGE = timedelta(hours=48)
EILAT = "אילת"             # stores.city_canonical (CBS 2024 name; cerberus code 2600)
TYPO_MIN_SIMILARITY = 0.45
_META_TTL_S = 60.0         # built_at check
_LEXICON_TTL_S = 600.0     # aliases and Eilat store ids


class V2Unavailable(RuntimeError):
    """search_items cannot serve this request; the router uses the old path."""


# ---------------------------------------------------------------------------
# Query parsing (pure)
# ---------------------------------------------------------------------------

@dataclass
class Group:
    """One query word (or a matched multi-word alias): ANY alternative must match.

    alts[0] is what the user typed (normalized); an alias adds its canonical
    Hebrew spelling as a second alternative. OR, not replace: a Latin name that
    really is in the catalog still matches.
    """
    alts: list[str]
    alias: bool = False
    corrected_from: str | None = None

    @property
    def digit(self) -> bool:
        return self.alts[0].isdigit()


def barcode_variants(q: str) -> list[str] | None:
    """item_codes to try when the whole query is a barcode, else None.

    8-14 digits. A 12-digit UPC-A is the 13-digit EAN with a leading 0, so the
    other form is tried too.
    """
    s = q.strip()
    if not (s.isdigit() and 8 <= len(s) <= 14):
        return None
    out = [s]
    if len(s) == 12:
        out.append("0" + s)
    elif len(s) == 13 and s.startswith("0"):
        out.append(s[1:])
    return out


def apply_aliases(tokens: list[str], aliases: dict[str, str]) -> list[Group]:
    """Group tokens, matching the longest alias first ("coca cola" before "cola").

    aliases: normalized alias -> normalized canonical spelling.
    """
    max_words = max((a.count(" ") + 1 for a in aliases), default=1)
    groups: list[Group] = []
    i = 0
    while i < len(tokens):
        hit = None
        for n in range(min(max_words, len(tokens) - i), 0, -1):
            phrase = " ".join(tokens[i:i + n])
            if phrase in aliases:
                hit = (n, phrase)
                break
        if hit:
            n, phrase = hit
            canon = aliases[phrase]
            groups.append(Group(alts=[phrase] if canon == phrase else [phrase, canon], alias=True))
            i += n
        else:
            groups.append(Group(alts=[tokens[i]]))
            i += 1
    return groups


def where_clause(groups: list[Group]) -> tuple[str, dict]:
    """AND over groups; OR over each group's alternatives x (name, manufacturer).

    Same matching as the old build_word_clause: a bare number matches on a
    digit-run boundary (80 does not match 180), anything else is a substring.
    """
    clauses, params = [], {}
    for gi, g in enumerate(groups):
        ors = []
        for ai, alt in enumerate(g.alts):
            key = f"g{gi}a{ai}"
            if alt.isdigit():
                params[key] = _digit_run_pattern(alt)
                ors.append(f"name_norm ~ :{key} OR manufacturer_norm ~ :{key}")
            else:
                params[key] = f"%{_like_escape(alt)}%"
                ors.append(f"name_norm LIKE :{key} ESCAPE '\\' OR manufacturer_norm LIKE :{key} ESCAPE '\\'")
        clauses.append("(" + " OR ".join(ors) + ")")
    return " AND ".join(clauses), params


# ---------------------------------------------------------------------------
# Ranking (pure)
# ---------------------------------------------------------------------------

def _whole(alt: str, s: str) -> bool:
    if alt.isdigit():
        return re.search(rf"(?<!\d){re.escape(alt)}(?!\d)", s) is not None
    return re.search(rf"(?<!\w){re.escape(alt)}(?!\w)", s) is not None


def _starts(alt: str, s: str) -> bool:
    if alt.isdigit():
        return re.match(rf"{re.escape(alt)}(?!\d)", s) is not None
    return re.match(rf"{re.escape(alt)}(?!\w)", s) is not None


def assign_tier(name: str, mfr: str, groups: list[Group], q_norm: str) -> int:
    """Relevance tier of one candidate (lower is better).

    0  the name starts with the query phrase or its first word (whole word),
       or the query IS the manufacturer ("תנובה" -> every Tnuva product)
    1  every query word is a whole word in the name or manufacturer, and the
       first one is in the name
    2  the first word is in the name, as a substring ("חלבה" for "חלב")
    3  the first word is only in the manufacturer
    """
    if not groups:
        return 3
    first = groups[0]
    phrase_alts = {q_norm, " ".join(g.alts[-1] for g in groups)}
    if mfr and (mfr in phrase_alts or (len(groups) == 1 and mfr in first.alts)):
        return 0
    if any(_starts(p, name) for p in phrase_alts if p) or any(_starts(a, name) for a in first.alts):
        return 0
    in_name = [a for a in first.alts if a in name]
    if in_name and any(_whole(a, name) for a in in_name) and \
            all(any(_whole(a, name) or _whole(a, mfr) for a in g.alts) for g in groups):
        return 1
    if in_name:
        return 2
    return 3


def rank_key(c: dict, tier: int) -> tuple:
    """Price-neutral order: tier, 2+ chains first, popularity, chains, short name, code."""
    return (tier, 0 if c["chains_live"] >= 2 else 1, -c["popularity"], -c["chains_live"],
            len(c["name_norm"]), c["item_code"])


def rank(cands: list[dict], groups: list[Group], q_norm: str) -> list[dict]:
    for c in cands:
        c["tier"] = assign_tier(c["name_norm"], c["manufacturer_norm"], groups, q_norm)
    return sorted(cands, key=lambda c: rank_key(c, c["tier"]))


def choose_correction(candidates: list[tuple[str, float, int]]) -> str | None:
    """Closest lexicon term at similarity >= 0.45; the more frequent wins a tie."""
    ok = [c for c in candidates if c[1] >= TYPO_MIN_SIMILARITY]
    if not ok:
        return None
    ok.sort(key=lambda c: (-round(c[1], 6), -c[2], c[0]))
    return ok[0][0]


# ---------------------------------------------------------------------------
# Eilat (D2, pure)
# ---------------------------------------------------------------------------

def drop_eilat(rows: list[dict], eilat_fks: frozenset, city: list[str] | None = None) -> list[dict]:
    """Drop Eilat quotes before cheapest / most expensive are chosen.

    Eilat is VAT-free, so its prices beat the rest of the country and made the
    national "cheapest" an Eilat branch. Kept when the city filter includes
    Eilat, and for an item whose ONLY quotes are in Eilat (it stays visible).
    """
    if not eilat_fks or (city and EILAT in city):
        return rows
    has_other = {r["item_code"] for r in rows if r.get("store_fk") not in eilat_fks}
    return [r for r in rows if r.get("store_fk") not in eilat_fks or r["item_code"] not in has_other]


# ---------------------------------------------------------------------------
# Database side
# ---------------------------------------------------------------------------

@dataclass
class _Cache:
    built_at: tuple[float, datetime | None] | None = None
    lexicon: tuple[float, dict, frozenset] | None = None


_cache = _Cache()


def _built_at(conn: Connection) -> datetime | None:
    now = time.monotonic()
    c = _cache.built_at
    if c is not None and now - c[0] < _META_TTL_S:
        return c[1]
    val = conn.execute(text("SELECT built_at FROM search_items LIMIT 1")).scalar()
    _cache.built_at = (now, val)
    return val


def _lexicon(conn: Connection) -> tuple[dict, frozenset]:
    now = time.monotonic()
    c = _cache.lexicon
    if c is not None and now - c[0] < _LEXICON_TTL_S:
        return c[1], c[2]
    aliases = {r[0]: r[1] for r in conn.execute(text(
        "SELECT term, canonical FROM search_lexicon WHERE kind = 'alias'"))}
    eilat = frozenset(r[0] for r in conn.execute(text(
        "SELECT id FROM stores WHERE city_canonical = :c"), {"c": EILAT}))
    _cache.lexicon = (now, aliases, eilat)
    return aliases, eilat


def check_ready(conn: Connection) -> None:
    built = _built_at(conn)
    if built is None:
        raise V2Unavailable("search_items is empty")
    if built.tzinfo is None:
        built = built.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - built > MAX_AGE:
        raise V2Unavailable(f"search_items is stale (built {built.isoformat()})")


_COLS = "item_code, name_norm, manufacturer_norm, chains_live, popularity, promo_only, is_pseudo"


def _candidates(conn: Connection, groups: list[Group]) -> list[dict]:
    clause, params = where_clause(groups)
    if not clause:
        return []
    rows = conn.execute(text(
        f"SELECT {_COLS} FROM search_items WHERE NOT is_pseudo AND {clause}"), params).mappings().all()
    return [dict(r) for r in rows]


def _barcode(conn: Connection, codes: list[str]) -> list[dict]:
    rows = conn.execute(text(f"SELECT {_COLS} FROM search_items WHERE item_code IN :c")
                        .bindparams(bindparam("c", expanding=True)), {"c": codes}).mappings().all()
    return [dict(r) for r in rows]


def _correct(conn: Connection, groups: list[Group]) -> list[Group] | None:
    """One correction round: unknown plain words -> closest lexicon term. None = nothing changed."""
    plain = [g for g in groups if not g.alias and not g.digit and len(g.alts[0]) >= 3]
    if not plain:
        return None
    known = {r[0] for r in conn.execute(text(
        "SELECT term FROM search_lexicon WHERE term IN :t").bindparams(bindparam("t", expanding=True)),
        {"t": [g.alts[0] for g in plain]})}
    changed = False
    out: list[Group] = []
    for g in groups:
        if g in plain and g.alts[0] not in known:
            cands = [(r[0], float(r[1]), int(r[2])) for r in conn.execute(text("""
                SELECT term, similarity(term, :t) AS sim, freq
                FROM search_lexicon
                WHERE kind IN ('token', 'brand') AND term % :t
                ORDER BY sim DESC, freq DESC
                LIMIT 10
            """), {"t": g.alts[0]})]
            best = choose_correction(cands)
            if best and best != g.alts[0]:
                out.append(Group(alts=[best], corrected_from=g.alts[0]))
                changed = True
                continue
        out.append(g)
    return out if changed else None


@dataclass
class V2Result:
    query: str
    total_matches: int
    comparable_count: int
    has_more: bool
    products: list[dict]                 # group_by_product dicts, in rank order
    corrected_from: str | None = None
    ranked_page: list[dict] = field(default_factory=list)  # debug: the page's candidates with tier
    timings_ms: dict = field(default_factory=dict)


def run(conn: Connection, q: str, limit: int = 30, offset: int = 0,
        city: list[str] | None = None) -> V2Result:
    """The v2 search. Raises V2Unavailable (or anything else) -> caller falls back."""
    t = {"start": time.perf_counter()}

    def lap(name: str) -> None:
        now = time.perf_counter()
        t[name] = round((now - t.pop("_last", t["start"])) * 1000, 1)
        t["_last"] = now

    check_ready(conn)
    aliases, eilat_fks = _lexicon(conn)
    q_norm = normalize(q)
    empty = V2Result(query=q, total_matches=0, comparable_count=0, has_more=False, products=[])
    if len(q_norm.replace(" ", "")) < 2:
        return empty

    corrected_from = None
    variants = barcode_variants(q_norm)
    cands = _barcode(conn, variants) if variants else []
    groups: list[Group] = []
    if not cands:
        groups = apply_aliases(tokenize(q_norm), aliases)
        if not groups:
            return empty
        cands = _candidates(conn, groups)
        if not cands:
            fixed = _correct(conn, groups)
            if fixed:
                cands = _candidates(conn, fixed)
                if cands:
                    groups, corrected_from = fixed, q
    lap("candidates")

    ranked = rank(cands, groups, q_norm) if groups else [dict(c, tier=0) for c in cands]
    total = len(ranked)
    comparable = sum(1 for c in ranked if c["chains_live"] >= 2)
    page = ranked[offset:offset + limit]
    lap("rank")

    products: list[dict] = []
    if page:
        codes = [c["item_code"] for c in page]
        rows = drop_eilat(fetch_prices(conn, codes), eilat_fks, city)
        by_item = group_by_product(rows)
        # An item whose quotes all disappeared since the build is skipped.
        products = [by_item[c] for c in codes if c in by_item]
    lap("prices")
    t.pop("_last", None)
    t["total"] = round((time.perf_counter() - t.pop("start")) * 1000, 1)

    return V2Result(
        query=q,
        total_matches=total,
        comparable_count=comparable,
        # Paged on search_items, so the next offset is valid even when an item
        # on this page was skipped for having no live quote any more.
        has_more=(offset + len(page)) < total,
        products=products,
        corrected_from=corrected_from,
        ranked_page=page,
        timings_ms=t,
    )
