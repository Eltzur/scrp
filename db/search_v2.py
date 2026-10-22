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

SU11A-47: the page's prices come from search_item_prices (one precomputed row
per barcode and chain, filled by the same build from the live SQL) and go
through the same group_by_product, so the JSON is the live fetch's as of the
last build. The live fetch is used instead, per request, when the table is
missing or empty, when its built_at differs from search_items.built_at, when a
page item has no row there, or when a page item's winning promo has ended since
the build. suggest() answers GET /suggest from search_items + search_lexicon.

SU11A-50: the candidate step counts and orders the matches in SQL and ranks
only the rows up to the page in Python (Ranked, ranked_candidates): same rows,
same order, without shipping every match of a broad word to Python. The
filtered path (db/search_filtered.py: /compare, city / chain filters,
group_by=store) walks the same stream.

Pure functions (parse, aliases, tiers, ranking, correction, Eilat) take no
database and are unit-tested in tests/test_search_v2.py.
"""
from __future__ import annotations

import heapq
import logging
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterator
from datetime import datetime, timedelta, timezone

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from db.query import _digit_run_pattern, _like_escape, fetch_prices, group_by_product
from db.search_norm import normalize, tokenize

log = logging.getLogger(__name__)

MAX_AGE = timedelta(hours=48)
EILAT = "אילת"             # stores.city_canonical (CBS 2024 name; cerberus code 2600)
TYPO_MIN_SIMILARITY = 0.40    # SU11A-46: was 0.45; שוקלד -> שוקולד scores 0.444
_META_TTL_S = 60.0         # built_at check
_LEXICON_TTL_S = 600.0     # aliases and Eilat store ids
SUGGEST_MAX = 10
_SUGGEST_TERMS, _SUGGEST_BRANDS = 3, 2   # per answer; products fill the rest


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

# SU11A-50: the patterns are compiled once per alternative, not per candidate
# (same expressions; ranking a broad word's thousands of candidates spent most
# of its time rebuilding them).
@lru_cache(maxsize=1024)
def _whole_rx(alt: str) -> re.Pattern:
    if alt.isdigit():
        return re.compile(rf"(?<!\d){re.escape(alt)}(?!\d)")
    return re.compile(rf"(?<!\w){re.escape(alt)}(?!\w)")


@lru_cache(maxsize=1024)
def _starts_rx(alt: str) -> re.Pattern:
    if alt.isdigit():
        return re.compile(rf"{re.escape(alt)}(?!\d)")
    return re.compile(rf"{re.escape(alt)}(?!\w)")


def _whole(alt: str, s: str) -> bool:
    return _whole_rx(alt).search(s) is not None


def _starts(alt: str, s: str) -> bool:
    return _starts_rx(alt).match(s) is not None


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


# ---------------------------------------------------------------------------
# Ranked stream (SU11A-50)
# ---------------------------------------------------------------------------
# A broad word (חלב, שוקולד) matches thousands of search_items rows. Before,
# all of them came back to Python and were ranked there (assign_tier per row)
# before the page was cut: most of the 30-200 ms candidate step. Now Postgres
# counts the matches and sorts them by rank_key with a LOWER BOUND of the tier
# (coarse_tier_sql: plain LIKE tests, never above assign_tier), and Python takes
# rows in that order, computes the exact tier, and releases a row only once no
# later row can rank before it (every later row's key is at least its SQL key).
# Same rows, same order as rank(), but only the rows near the top are fetched
# and tiered. Tested against rank() in tests/test_search_filtered.py.
#
# item_code is sorted COLLATE "C" (code point order, like Python), so the SQL
# order and rank_key agree under any database collation.

_STREAM_FIRST = 300          # rows in the first fetch (a page needs ~30-60)


def coarse_tier_sql(groups: list[Group], q_norm: str) -> tuple[str, dict]:
    """SQL CASE giving 0 / 1 / 3, never above assign_tier's tier for the row.

    0: the name starts (LIKE prefix) with the phrase or a first-group
       alternative, or the manufacturer is the phrase (assign_tier's tier-0
       tests without the word-end check).
    1: a first-group alternative is a substring of the name (tiers 1 and 2
       both need that).
    3: anything else (tier 3).
    """
    first = groups[0]
    phrase_alts = sorted(p for p in {q_norm, " ".join(g.alts[-1] for g in groups)} if p)
    params: dict = {}
    zero, one = [], []
    for i, p in enumerate(phrase_alts):
        params[f"ctp{i}"] = _like_escape(p) + "%"
        params[f"ctm{i}"] = p
        zero.append(f"name_norm LIKE :ctp{i} ESCAPE '\\'")
        zero.append(f"manufacturer_norm = :ctm{i}")
    for i, a in enumerate(first.alts):
        params[f"cta{i}"] = _like_escape(a) + "%"
        params[f"ctn{i}"] = "%" + _like_escape(a) + "%"
        zero.append(f"name_norm LIKE :cta{i} ESCAPE '\\'")
        if len(groups) == 1:
            params[f"cte{i}"] = a
            zero.append(f"manufacturer_norm = :cte{i}")
        one.append(f"name_norm LIKE :ctn{i} ESCAPE '\\'")
    return (f"CASE WHEN {' OR '.join(zero)} THEN 0 WHEN {' OR '.join(one)} THEN 1 ELSE 3 END", params)


class Ranked:
    """Candidates of one query in rank order, produced lazily.

    total / comparable: all matches (non-pseudo) and those with 2+ live chains,
    as rank() + len() gave them. Iterating yields candidate dicts with "tier",
    in rank() order. fetch(limit, offset) returns SQL rows sorted by the coarse
    key (each with "ct"); a list source (barcodes, tests) is ranked in Python.
    """

    def __init__(self, total: int, comparable: int, fetch, groups: list[Group], q_norm: str,
                 first: list[dict] | None = None, first_limit: int = _STREAM_FIRST):
        self.total, self.comparable = total, comparable
        self._fetch, self._groups, self._q = fetch, groups, q_norm
        self._first, self._first_limit = first, first_limit
        self._list: list[dict] | None = None
        self._done: list[dict] = []        # released so far, in order
        self._it: Iterator[dict] | None = None
        self.fetched = 0      # SQL rows read so far
        self.queries = 0      # SQL statements run

    @classmethod
    def from_list(cls, cands: list[dict], groups: list[Group], q_norm: str) -> "Ranked":
        ranked = rank(cands, groups, q_norm) if groups else [dict(c, tier=0) for c in cands]
        r = cls(len(ranked), sum(1 for c in ranked if c["chains_live"] >= 2), None, groups, q_norm)
        r._list = ranked
        return r

    def _rows(self) -> Iterator[dict]:
        rows, limit, offset = self._first, self._first_limit, 0
        while True:
            if rows is None:
                rows = self._fetch(limit, offset)
                self.queries += 1
            self.fetched += len(rows)
            yield from rows
            offset += len(rows)
            if len(rows) < limit or offset >= self.total:
                return
            rows, limit = None, limit * 8

    def _merge(self) -> Iterator[dict]:
        if self._list is not None:
            yield from self._list
            return
        heap: list = []
        seq = 0
        for row in self._rows():
            bound = rank_key(row, row.pop("ct"))
            while heap and heap[0][0] < bound:
                yield heapq.heappop(heap)[2]
            row["tier"] = assign_tier(row["name_norm"], row["manufacturer_norm"], self._groups, self._q)
            heapq.heappush(heap, (rank_key(row, row["tier"]), seq, row))
            seq += 1
        while heap:
            yield heapq.heappop(heap)[2]

    def take(self, n: int) -> list[dict]:
        """The first n candidates in rank order (fewer when there are not n)."""
        if self._it is None:
            self._it = self._merge()
        while len(self._done) < n:
            nxt = next(self._it, None)
            if nxt is None:
                break
            self._done.append(nxt)
        return self._done[:n]


def choose_correction(candidates: list[tuple[str, float, int]]) -> str | None:
    """Closest lexicon term at similarity >= TYPO_MIN_SIMILARITY; the more frequent wins a tie."""
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
    prices_built_at: tuple[float, datetime | None] | None = None


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


def built_stamp(conn: Connection) -> datetime | None:
    """search_items.built_at (cached _META_TTL_S): the response cache's stamp."""
    return _built_at(conn)


def _prices_built_at(conn: Connection) -> datetime | None:
    """search_item_prices.built_at, None when the table is missing or empty (cached)."""
    now = time.monotonic()
    c = _cache.prices_built_at
    if c is not None and now - c[0] < _META_TTL_S:
        return c[1]
    val = None
    if conn.execute(text("SELECT to_regclass('public.search_item_prices') IS NOT NULL")).scalar():
        val = conn.execute(text("SELECT built_at FROM search_item_prices LIMIT 1")).scalar()
    _cache.prices_built_at = (now, val)
    return val


_PRE_COLS = ("item_code, chain_id, item_name, canonical_item_name, manufacturer_name, unit_of_measure, "
             "is_weighted, item_price, unit_of_measure_price, price_update_date, chain_name, store_id, "
             "store_name, city, store_fk, promo_unit_price, promo_min_qty, promo_description, promo_end")


def _precomputed_rows(conn: Connection, codes: list[str]) -> list[dict] | None:
    """The page's rows from search_item_prices, or None = use the live fetch.

    One row per (item, chain), already filtered (shelf > 0, live stores, Eilat
    rule) and in the live row order (ord), so group_by_product builds the same
    products from them. None when the table is not from this build, when an item
    has no row, or when a winning promo has ended since the build (the live
    fetch would pick another quote).
    """
    pre = _prices_built_at(conn)
    if pre is None or pre != _built_at(conn):
        return None
    rows = [dict(r) for r in conn.execute(text(f"""
        SELECT {_PRE_COLS},
               (promo_end IS NOT NULL AND CAST(promo_end AS timestamp) < NOW()) AS promo_ended
        FROM search_item_prices
        WHERE item_code IN :c
        ORDER BY item_code, ord
    """).bindparams(bindparam("c", expanding=True)), {"c": codes}).mappings()]
    if {r["item_code"] for r in rows} != set(codes) or any(r.pop("promo_ended") for r in rows):
        return None
    return rows


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
    """Every candidate, unranked (the SU11A-36 step). Kept as the reference that
    compare_search_v2 --filtered checks the Ranked stream against."""
    clause, params = where_clause(groups)
    if not clause:
        return []
    rows = conn.execute(text(
        f"SELECT {_COLS} FROM search_items WHERE NOT is_pseudo AND {clause}"), params).mappings().all()
    return [dict(r) for r in rows]


def _ranked(conn: Connection, groups: list[Group], q_norm: str, first_limit: int | None = None) -> Ranked:
    """The query's candidates as a Ranked stream (SU11A-50); total 0 = no match.

    first_limit: rows in the first fetch (default _STREAM_FIRST); each further
    fetch is 8x the previous one, so a walk to 3,000 (plus the look-ahead row) needs two statements at 600.
    """
    clause, params = where_clause(groups)
    if not clause:
        return Ranked.from_list([], groups, q_norm)
    ct, ct_params = coarse_tier_sql(groups, q_norm)
    sql = text(f"""
        SELECT {_COLS}, {ct} AS ct,
               count(*) OVER () AS n_total,
               count(*) FILTER (WHERE chains_live >= 2) OVER () AS n_comparable
        FROM search_items
        WHERE NOT is_pseudo AND {clause}
        ORDER BY ct, (chains_live < 2), popularity DESC, chains_live DESC, length(name_norm),
                 item_code COLLATE "C"
        LIMIT :lim OFFSET :off
    """)
    p = {**params, **ct_params}
    counts: list[int] = []

    def fetch(limit: int, offset: int) -> list[dict]:
        out = []
        for r in conn.execute(sql, {**p, "lim": limit, "off": offset}).mappings():
            d = dict(r)
            if not counts:
                counts.extend((int(d["n_total"]), int(d["n_comparable"])))
            del d["n_total"], d["n_comparable"]
            out.append(d)
        return out

    lim = first_limit or _STREAM_FIRST
    first = fetch(lim, 0)
    total, comparable = counts if counts else (0, 0)
    r = Ranked(total, comparable, fetch, groups, q_norm, first=first, first_limit=lim)
    r.queries = 1
    return r


def ranked_candidates(conn: Connection, q: str, aliases: dict,
                      first_limit: int | None = None) -> tuple[Ranked, str | None]:
    """(candidates, corrected_from): a barcode, the words, or one typo round.

    The candidate step shared by run() and the filtered path (db/search_filtered.py).
    """
    q_norm = normalize(q)
    variants = barcode_variants(q_norm)
    cands = _barcode(conn, variants) if variants else []
    if cands:
        return Ranked.from_list(cands, [], q_norm), None
    groups = apply_aliases(tokenize(q_norm), aliases)
    if not groups:
        return Ranked.from_list([], [], q_norm), None
    ranked = _ranked(conn, groups, q_norm, first_limit)
    if ranked.total:
        return ranked, None
    fixed = _correct(conn, groups)
    if fixed:
        again = _ranked(conn, fixed, q_norm, first_limit)
        if again.total:
            return again, q
    return ranked, None


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
    prices_source: str = "live"          # "precomputed" | "live" (SU11A-47)


def run(conn: Connection, q: str, limit: int = 30, offset: int = 0,
        city: list[str] | None = None, precomputed: bool = True) -> V2Result:
    """The v2 search. Raises V2Unavailable (or anything else) -> caller falls back.

    precomputed=False forces the live price fetch (compare_search_v2). A city
    filter always does: search_item_prices is national.
    """
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

    ranked, corrected_from = ranked_candidates(conn, q, aliases)
    lap("candidates")

    # SU11A-50: counted in SQL; only the rows up to the page are ranked here.
    total, comparable = ranked.total, ranked.comparable
    page = ranked.take(offset + limit)[offset:]
    lap("rank")

    products: list[dict] = []
    source = "live"
    if page:
        codes = [c["item_code"] for c in page]
        rows = _try_precomputed(conn, codes) if precomputed and not city else None
        if rows is not None:
            source = "precomputed"
        else:
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
        prices_source=source,
    )


def _try_precomputed(conn: Connection, codes: list[str]) -> list[dict] | None:
    """_precomputed_rows in its own SAVEPOINT; any error -> None (live fetch)."""
    try:
        with conn.begin_nested():
            return _precomputed_rows(conn, codes)
    except Exception as exc:  # noqa: BLE001 - the live fetch still answers
        log.warning("search_item_prices unreadable, using the live price fetch: %s", type(exc).__name__)
        return None


# ---------------------------------------------------------------------------
# /suggest (SU11A-47)
# ---------------------------------------------------------------------------

@dataclass
class Suggestions:
    query: str
    items: list[dict]
    corrected_from: str | None = None
    timings_ms: dict = field(default_factory=dict)


def _lexicon_prefix(conn: Connection, prefix: str, kinds: tuple[str, ...], n: int) -> list[dict]:
    rows = conn.execute(text("""
        SELECT term, kind, canonical, freq FROM search_lexicon
        WHERE term LIKE :p ESCAPE '\\' AND kind IN :k
        ORDER BY freq DESC, term
        LIMIT :n
    """).bindparams(bindparam("k", expanding=True)),
        {"p": _like_escape(prefix) + "%", "k": list(kinds), "n": n}).mappings().all()
    return [dict(r) for r in rows]


def _product_names(conn: Connection, codes: list[str]) -> dict[str, str]:
    if not codes:
        return {}
    return {r[0]: r[1] for r in conn.execute(text(
        "SELECT item_code, item_name FROM items WHERE item_code IN :c").bindparams(
        bindparam("c", expanding=True)), {"c": codes})}


def _suggest_products(conn: Connection, groups: list[Group], q_norm: str, n: int) -> list[dict]:
    """Best n live, non-pseudo items for the words typed so far.

    One word shorter than 3 letters: names starting with it (a 2-letter
    substring matches a large part of the catalog). Otherwise every word as a
    substring of the name or manufacturer, like /search. Order: name starts
    with the query, then search v2's price-neutral keys (2+ chains,
    popularity, chains, shorter name, item_code).
    """
    if len(groups) == 1 and not groups[0].alias and len(groups[0].alts[0]) < 3:
        clause, params = "name_norm LIKE :g0 ESCAPE '\\'", {"g0": _like_escape(groups[0].alts[0]) + "%"}
    else:
        clause, params = where_clause(groups)
    if not clause:
        return []
    params.update({"starts": _like_escape(q_norm) + "%", "n": n})
    rows = conn.execute(text(f"""
        SELECT item_code, name_norm, chains_live FROM search_items
        WHERE NOT is_pseudo AND {clause}
        ORDER BY (name_norm LIKE :starts ESCAPE '\\') DESC, (chains_live >= 2) DESC, popularity DESC,
                 chains_live DESC, length(name_norm), item_code
        LIMIT :n
    """), params).mappings().all()
    return [dict(r) for r in rows]


def suggest(conn: Connection, q: str, limit: int = 8) -> Suggestions:
    """Type-ahead for GET /suggest: terms, brands and products; no prices.

    Same normalization, aliases and typo round as run(). Terms complete the
    last word typed (the words before it are kept in front); brands and aliases
    complete the whole query. A barcode (8-14 digits) answers that product
    only, when it is a live non-pseudo item.
    """
    t0 = time.perf_counter()
    limit = max(1, min(limit, SUGGEST_MAX))
    q_norm = normalize(q)
    out = Suggestions(query=q, items=[])
    if not q_norm:
        return out
    check_ready(conn)
    aliases, _eilat = _lexicon(conn)

    variants = barcode_variants(q_norm)
    if variants:
        hits = [c for c in _barcode(conn, variants) if not c["is_pseudo"]][:1]
        names = _product_names(conn, [c["item_code"] for c in hits])
        out.items = [{"kind": "product", "text": names.get(c["item_code"]) or c["name_norm"],
                      "item_code": c["item_code"]} for c in hits]
        out.timings_ms = {"total": round((time.perf_counter() - t0) * 1000, 1)}
        return out

    words = q_norm.split(" ")
    head, last = " ".join(words[:-1]), words[-1]
    # A lone 1-letter word is not a search token (tokenize), but it is a prefix.
    groups = apply_aliases(tokenize(q_norm), aliases) or ([Group(alts=[last])] if last else [])

    def collect(groups: list[Group], last: str) -> tuple[list[dict], list[dict], list[dict]]:
        terms = _lexicon_prefix(conn, last, ("token",), limit) if last else []
        brands = _lexicon_prefix(conn, q_norm, ("brand", "alias"), limit)
        products = _suggest_products(conn, groups, q_norm, limit) if groups else []
        return terms, brands, products

    terms, brands, products = collect(groups, last)
    if not (terms or brands or products) and len(q_norm) >= 3:
        fixed = _correct(conn, groups)
        if fixed:
            q_fixed = " ".join(g.alts[0] for g in fixed)
            words = q_fixed.split(" ")
            head, last = " ".join(words[:-1]), words[-1]
            terms, brands, products = collect(fixed, last)
            if terms or brands or products:
                out.corrected_from = q
                q_norm = q_fixed

    seen: set[str] = set()
    t_items, b_items = [], []
    for r in terms:
        text_ = f"{head} {r['term']}".strip()
        if text_ not in seen:
            seen.add(text_)
            t_items.append({"kind": "term", "text": text_, "count": int(r["freq"])})
    for r in brands:
        if r["term"] not in seen:
            seen.add(r["term"])
            b_items.append({"kind": "brand", "text": r["term"], "count": int(r["freq"])})
    names = _product_names(conn, [p["item_code"] for p in products])
    p_items = [{"kind": "product", "text": names.get(p["item_code"]) or p["name_norm"], "item_code": p["item_code"]}
               for p in products]

    # Up to 3 terms and 2 brands, products fill the rest; any short group's
    # slots go to the others (products, then terms, then brands).
    take_t = min(len(t_items), _SUGGEST_TERMS, limit)
    take_b = min(len(b_items), _SUGGEST_BRANDS, limit - take_t)
    take_p = min(len(p_items), limit - take_t - take_b)
    spare = limit - take_t - take_b - take_p
    extra_t = min(spare, len(t_items) - take_t)
    spare -= extra_t
    extra_b = min(spare, len(b_items) - take_b)
    out.items = t_items[:take_t + extra_t] + b_items[:take_b + extra_b] + p_items[:take_p]
    out.timings_ms = {"total": round((time.perf_counter() - t0) * 1000, 1)}
    return out
