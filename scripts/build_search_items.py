"""Build search_items + search_lexicon for search v2 (SU11A-36).

    venv/bin/python3 -m scripts.build_search_items --report [--out /tmp/search_items_report.json]
    venv/bin/python3 -m scripts.build_search_items --apply
    venv/bin/python3 -m scripts.build_search_items --swap-back

--report  STRICTLY READ-ONLY (every connection default_transaction_read_only,
          plus SET TRANSACTION READ ONLY). Counts what --apply would write:
          live items, pseudo items per rule with 40 sample names each, Eilat
          stores, lexicon sizes, aliases whose Hebrew spelling matches nothing,
          and whether pg_trgm splits Hebrew into trigrams.
--apply   Fills search_items_next / search_lexicon_next (TRUNCATE + INSERT +
          ANALYZE, one transaction), checks the row count, then swaps the names
          with the live tables in a second, short transaction. A search reads
          either the old build or the new one, never a half-built table. The
          previous build stays in the *_next tables until the next run.
--swap-back  Swaps the names back: the previous build becomes live again
          (instant rollback of a bad build). Run it once only.

SU11A-47: the same --apply also fills search_item_prices_next (one row per
(barcode, chain): the quote search v2 shows for that chain) and swaps it in
the SAME swap transaction, so an unfiltered v2 /search reads its page prices
from there instead of the 7.9M-row prices table. The rows come from the live
path's own SQL (db.query._PRICE_SQL / _PROMO_ONLY_SQL with _PROMO_PICK_SQL),
aggregated in Postgres in --price-chunks statements (item_code ranges), never
pulled into Python. --swap-back swaps both. Without the su11a47 migration the
build makes search_items exactly as before and logs one warning; if the price
fill fails, search_items is still swapped in and the API keeps the live price
fetch (it uses search_item_prices only while its built_at equals
search_items.built_at).

statement_timeout 10 min on every connection; the swap waits at most 5 s for
its locks and is retried 3 times. Timings are printed. Needs the
su11a36_search_items.sql migration (tables owned by scrp_app, the role in
DATABASE_URL). Never writes to items, prices, stores or promos.

"Live" is exactly what /search shows today: a shelf price > 0 at a live store
(db.query liveness: last load within 3 days of its chain's latest) with an
item_chain_names row for that chain, or a promo-only quote at a live store
(the _PROMO_ONLY_SQL conditions). Pseudo items: db/search_norm.is_pseudo.
Output: counts, item names and codes only - no user data, no secrets.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = "10min"
TIMEOUT_MS = 600_000
SAMPLE = 40
LEXICON_MIN_FREQ = 3
INSERT_CHUNK = 5000
MIN_KEEP_RATIO = 0.5   # refuse to swap in a build with < 50% of the live row count
ALIASES = ROOT / "data" / "brand_aliases.csv"

PRICE_CHUNKS = 16      # SU11A-47: search_item_prices fill statements (item_code ranges)
MIN_PRICE_ITEMS = 0.98  # swap the prices in only when they cover >= 98% of the build's items

SWAP_PAIRS = [  # (live name, staging name): tables, primary keys, indexes
    ("TABLE", "search_items", "search_items_next"),
    ("INDEX", "search_items_pkey", "search_items_next_pkey"),
    ("INDEX", "idx_search_items_name_trgm", "idx_search_items_next_name_trgm"),
    ("INDEX", "idx_search_items_mfr_trgm", "idx_search_items_next_mfr_trgm"),
    ("INDEX", "idx_search_items_rank", "idx_search_items_next_rank"),
    ("TABLE", "search_lexicon", "search_lexicon_next"),
    ("INDEX", "search_lexicon_pkey", "search_lexicon_next_pkey"),
    ("INDEX", "idx_search_lexicon_term_trgm", "idx_search_lexicon_next_term_trgm"),
]
PRICE_TABLES = ("search_item_prices", "search_item_prices_next")
PRICE_SWAP_PAIRS = [  # SU11A-47; swapped together with SWAP_PAIRS
    ("TABLE", "search_item_prices", "search_item_prices_next"),
    ("INDEX", "search_item_prices_pkey", "search_item_prices_next_pkey"),
]

# Per (item, chain): shelf quotes and promo-only quotes from live stores, with
# the same joins and conditions as db.query._PRICE_SQL / _PROMO_ONLY_SQL, then
# one row per item. GROUP BY in the database; ~1 row per live item comes back.
AGG_SQL = """
WITH shelf AS (
    SELECT p.item_code, s.chain_id, count(*) AS n_stores, max(p.item_price) AS max_price
    FROM prices p
    JOIN stores s ON s.id = p.store_fk
    WHERE p.item_price > 0
      AND p.store_fk = ANY(:live)
    GROUP BY p.item_code, s.chain_id
), shelf_ok AS (
    SELECT sh.item_code, sh.chain_id, sh.n_stores, sh.max_price, true AS is_shelf
    FROM shelf sh
    JOIN chains c ON c.chain_id = sh.chain_id
    WHERE EXISTS (SELECT 1 FROM item_chain_names icn
                  WHERE icn.item_code = sh.item_code AND icn.chain_id = sh.chain_id)
), po AS (
    SELECT pm.item_code, s.chain_id, count(DISTINCT pm.store_fk) AS n_stores,
           max(pm.discount_price / pm.min_qty) AS max_price, false AS is_shelf
    FROM promos pm
    JOIN stores s ON s.id = pm.store_fk
    JOIN chains c ON c.chain_id = s.chain_id
    WHERE pm.store_fk = ANY(:live)
      AND (pm.promo_end >= NOW() OR pm.promo_end IS NULL)
      AND pm.item_code <> '0000000000000'
      AND pm.discount_price > 0
      AND pm.min_qty BETWEEN 1 AND 24
      AND c.name IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM prices pr
                      WHERE pr.store_fk = pm.store_fk AND pr.item_code = pm.item_code)
    GROUP BY pm.item_code, s.chain_id
), u AS (
    SELECT * FROM shelf_ok
    UNION ALL
    SELECT * FROM po
)
SELECT u.item_code,
       i.item_name,
       i.manufacturer_name,
       count(DISTINCT u.chain_id)::int  AS chains_live,
       sum(u.n_stores)::int             AS stores_live,
       NOT bool_or(u.is_shelf)          AS promo_only,
       max(u.max_price)::float          AS max_price
FROM u
JOIN items i ON i.item_code = u.item_code
GROUP BY u.item_code, i.item_name, i.manufacturer_name
"""

# SU11A-47: search_item_prices columns = the row fields group_by_product reads
# for a v2 page (see db/migrations/su11a47_search_prices.sql).
PRICE_ROW_COLS = [
    "item_code", "chain_id", "item_name", "canonical_item_name", "manufacturer_name", "unit_of_measure",
    "is_weighted", "item_price", "unit_of_measure_price", "price_update_date", "chain_name", "store_id",
    "store_name", "city", "store_fk", "promo_unit_price", "promo_min_qty", "promo_description", "promo_end",
]
# One chunk = an item_code range. Bounds come from the database's own ordering
# (percentiles of items.item_code), so ranges neither overlap nor leave gaps
# under any collation, and the planner estimates them from its statistics
# (a hash-of-item_code filter was estimated at 0.5% and planned as per-row
# nested loops). NULL bound = open end; psycopg2 inlines the literal and the
# planner folds the NULL test away.
_PRICE_PART = "(CAST(:lo AS text) IS NULL OR {col} >= :lo) AND (CAST(:hi AS text) IS NULL OR {col} < :hi)"


def price_bounds(conn, chunks: int) -> list[tuple[str | None, str | None]]:
    """(lo, hi) item_code ranges covering every code exactly once."""
    from sqlalchemy import text
    if chunks <= 1:
        return [(None, None)]
    fr = [k / chunks for k in range(1, chunks)]
    cuts = conn.execute(text("SELECT percentile_disc(CAST(:f AS float8[])) WITHIN GROUP (ORDER BY item_code) "
                             "FROM items"), {"f": fr}).scalar() or []
    cuts = list(dict.fromkeys(c for c in cuts if c is not None))
    edges = [None, *cuts, None]
    return list(zip(edges[:-1], edges[1:]))


def price_fill_sql() -> str:
    """INSERT for one chunk of search_item_prices_next, built from the live SQL.

    Rows: db.query._PRICE_SQL (shelf + _PROMO_PICK_SQL) and _PROMO_ONLY_SQL with
    their item_code IN list swapped for an item_code range; nothing else in
    them changes. Then, in the database, the steps the API runs in Python on
    a page today:
      fetch_prices     shelf price > 0, live stores only
      drop_eilat       Eilat quotes out unless they are the item's only ones
      group_by_product per chain, the first row with the lowest effective price
                       (LEAST(shelf, promo)), in the live row order: shelf rows
                       by item_price then store_fk, then promo-only rows by
                       store_fk; ord = where the chain's first row sits in that
                       order
    """
    import db.query as Q
    shelf, po = Q._PRICE_SQL, Q._PROMO_ONLY_SQL.replace("/*EXTRA*/", "")
    w_shelf, w_po = "WHERE icn.item_code IN :codes", "WHERE p.item_code IN :codes"
    if shelf.count(w_shelf) != 1 or po.count(w_po) != 1:
        raise RuntimeError("db.query price SQL changed shape - update price_fill_sql")
    shelf = shelf.replace(w_shelf, "WHERE " + _PRICE_PART.format(col="icn.item_code")
                          + " AND " + _PRICE_PART.format(col="p.item_code"))
    po = po.replace(w_po, "WHERE " + _PRICE_PART.format(col="p.item_code"))
    rcols = ", ".join("promo_unit_price::double precision AS promo_unit_price" if c == "promo_unit_price" else c
                      for c in PRICE_ROW_COLS)
    out = ", ".join(f"w.{c}" for c in PRICE_ROW_COLS)
    return f"""
INSERT INTO search_item_prices_next ({", ".join(PRICE_ROW_COLS[:2])}, ord, {", ".join(PRICE_ROW_COLS[2:])}, built_at)
WITH shelf AS ({shelf}), po AS ({po}),
r AS (
    SELECT 0 AS src, {rcols} FROM shelf
    UNION ALL
    SELECT 1 AS src, {rcols} FROM po
), k AS (
    SELECT r.*, LEAST(r.item_price, r.promo_unit_price) AS eff,
           r.store_fk = ANY(:eilat) AS is_eilat
    FROM r
    WHERE (r.item_price IS NULL OR r.item_price > 0)
      AND r.store_fk = ANY(:live)
), e AS (
    SELECT k.*, bool_or(NOT k.is_eilat) OVER (PARTITION BY k.item_code) AS has_other
    FROM k
), w AS (
    -- win = 1: the chain's quote. f_*: the chain's FIRST row in the live order,
    -- carried on every row so ord needs no self-join (a join back to this set
    -- planned as a nested loop on a 1-row estimate: quadratic per chunk).
    SELECT e.*,
           row_number() OVER (PARTITION BY e.item_code, e.chain_id
                              ORDER BY e.eff, e.src, e.item_price, e.store_fk) AS win,
           min(e.src)         OVER c AS f_src,
           first_value(e.item_price) OVER (c ORDER BY e.src, e.item_price, e.store_fk) AS f_price,
           first_value(e.store_fk)   OVER (c ORDER BY e.src, e.item_price, e.store_fk) AS f_fk
    FROM e
    WHERE NOT e.is_eilat OR NOT e.has_other
    WINDOW c AS (PARTITION BY e.item_code, e.chain_id)
)
SELECT w.item_code, w.chain_id,
       row_number() OVER (PARTITION BY w.item_code ORDER BY w.f_src, w.f_price, w.f_fk) AS ord,
       {out.split(", ", 2)[2]}, CAST(:built_at AS timestamptz)
FROM w
WHERE w.win = 1
"""


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- env + db
def _load_env(read_only: bool) -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    # libpq applies PGOPTIONS to every connection, including the one
    # db.query._load_liveness opens on its own.
    extra = f"-c statement_timeout={TIMEOUT_MS}"
    if read_only:
        extra = "-c default_transaction_read_only=on " + extra
    os.environ["PGOPTIONS"] = f"{os.environ.get('PGOPTIONS', '')} {extra}".strip()


def _connect(read_only: bool):
    from sqlalchemy import text
    from db.db import connect
    conn = connect()
    if read_only:
        conn.execute(text("SET TRANSACTION READ ONLY"))
    conn.execute(text(f"SET LOCAL statement_timeout = '{TIMEOUT}'"))
    return conn


# --------------------------------------------------------------------------- build (pure)
def load_aliases(path: Path) -> list[tuple[str, str]]:
    from db.search_norm import normalize
    out, seen = [], set()
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            a, c = normalize(row.get("alias")), normalize(row.get("canonical"))
            if a and c and a not in seen:
                seen.add(a)
                out.append((a, c))
    return out


def build_rows(agg: list[dict], popularity: dict[str, int], built_at: datetime) -> list[dict]:
    from db.search_norm import is_pseudo, normalize
    rows = []
    for r in agg:
        name = normalize(r["item_name"])
        mfr = normalize(r["manufacturer_name"])
        rows.append({
            "item_code": r["item_code"], "name_norm": name, "manufacturer_norm": mfr,
            "is_pseudo": is_pseudo(name, r["max_price"]),
            "chains_live": min(int(r["chains_live"]), 32767), "stores_live": int(r["stores_live"]),
            "promo_only": bool(r["promo_only"]), "popularity": popularity.get(r["item_code"], 0),
            "built_at": built_at,
        })
    return rows


def build_lexicon(rows: list[dict], aliases: list[tuple[str, str]]) -> dict[str, dict]:
    """term -> {kind, canonical, freq}. On a clash alias beats brand beats token."""
    from db.search_norm import lexicon_words
    real = [r for r in rows if not r["is_pseudo"]]
    tokens: Counter = Counter()
    brands: Counter = Counter()
    for r in real:
        tokens.update(set(lexicon_words(r["name_norm"])) | set(lexicon_words(r["manufacturer_norm"])))
        if len(r["manufacturer_norm"]) >= 2:
            brands[r["manufacturer_norm"]] += 1
    lex: dict[str, dict] = {}
    for t, n in tokens.items():
        if n >= LEXICON_MIN_FREQ:
            lex[t] = {"kind": "token", "canonical": t, "freq": n}
    for b, n in brands.items():
        if n >= LEXICON_MIN_FREQ:
            lex[b] = {"kind": "brand", "canonical": b, "freq": n}
    for a, c in aliases:
        n = sum(1 for r in real if c in r["name_norm"] or c in r["manufacturer_norm"])
        lex[a] = {"kind": "alias", "canonical": c, "freq": n}
    return lex


# --------------------------------------------------------------------------- read side
def read_inputs(conn) -> dict:
    from sqlalchemy import text
    import db.query as Q
    t0 = time.perf_counter()
    lv = Q._load_liveness()  # raises on failure: never build without the live filter
    live = sorted(lv.live_fks)
    if not live:
        raise SystemExit("no live stores - refusing to build")
    timings = {"liveness_ms": round((time.perf_counter() - t0) * 1000)}
    log(f"live stores: {len(live)}; aggregating live quotes per item (can take a few minutes)...")
    t0 = time.perf_counter()
    agg = [dict(r) for r in conn.execute(text(AGG_SQL), {"live": live}).mappings()]
    timings["aggregate_ms"] = round((time.perf_counter() - t0) * 1000)
    log(f"live items: {len(agg)} in {timings['aggregate_ms']} ms")
    return {"live_fks": live, "agg": agg, "timings": timings}


def _table_exists(conn, name: str) -> bool:
    from sqlalchemy import text
    return conn.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": f"public.{name}"}).scalar()


def read_popularity(conn) -> dict[str, int]:
    from sqlalchemy import text
    if not _table_exists(conn, "search_items"):
        return {}
    return {r[0]: r[1] for r in conn.execute(text(
        "SELECT item_code, popularity FROM search_items WHERE popularity <> 0"))}


# --------------------------------------------------------------------------- report
def report(conn, inputs: dict, aliases_path: Path) -> dict:
    from sqlalchemy import text
    from db.search_norm import COUPON_PATTERNS, PSEUDO_MAX_PRICE, coupon_pattern, normalize
    from db.search_v2 import EILAT

    agg = inputs["agg"]
    built_at = datetime.now(timezone.utc)
    rows = build_rows(agg, read_popularity(conn), built_at)
    raw = {r["item_code"]: r for r in agg}
    aliases = load_aliases(aliases_path)
    lex = build_lexicon(rows, aliases)

    def sample(codes: list[str]) -> list[str]:
        out = []
        for c in sorted(codes, key=_md5)[:SAMPLE]:
            a = raw[c]
            out.append(f"{c} | {a['item_name']} | {a['manufacturer_name']} | chains {a['chains_live']} | "
                       f"max price {a['max_price']}")
        return out

    by_pattern: dict[str, list[str]] = {k: [] for k in COUPON_PATTERNS}
    price_rule: list[str] = []
    mention_not_flagged: list[str] = []
    for r in rows:
        k = coupon_pattern(r["name_norm"])
        if k:
            by_pattern[k].append(r["item_code"])
        mp = raw[r["item_code"]]["max_price"]
        if mp is not None and mp < PSEUDO_MAX_PRICE:
            price_rule.append(r["item_code"])
        if not r["is_pseudo"] and "קופו" in r["name_norm"]:
            mention_not_flagged.append(r["item_code"])
    coupon_codes = {c for v in by_pattern.values() for c in v}
    pseudo = [r for r in rows if r["is_pseudo"]]

    eilat = conn.execute(text("""
        SELECT count(*) AS stores, count(*) FILTER (WHERE id = ANY(:live)) AS live,
               array_agg(DISTINCT city) AS raw_city_values
        FROM stores WHERE city_canonical = :c
    """), {"c": EILAT, "live": inputs["live_fks"]}).mappings().one()

    tables = {}
    for t in ("search_items", "search_items_next", "search_lexicon", "search_lexicon_next", *PRICE_TABLES):
        if _table_exists(conn, t):
            info = conn.execute(text(f"""
                SELECT (SELECT tableowner FROM pg_tables WHERE schemaname = 'public' AND tablename = :t) AS owner,
                       (SELECT count(*) FROM {t}) AS rows
            """), {"t": t}).mappings().one()
            tables[t] = dict(info)
        else:
            tables[t] = None
    built = conn.execute(text("SELECT max(built_at) FROM search_items")).scalar() if tables["search_items"] else None
    who = conn.execute(text("SELECT current_user")).scalar()

    trgm = {}
    try:
        with conn.begin_nested():
            trgm = dict(conn.execute(text("""
                SELECT array_length(show_trgm('חלב'), 1) AS trigrams_in_חלב,
                       similarity('תנובה', 'תנובא') AS sim_תנובה_תנובא,
                       similarity('שוקולד', 'שוקלד') AS sim_שוקולד_שוקלד
            """)).mappings().one())
    except Exception as exc:  # noqa: BLE001
        trgm = {"error": type(exc).__name__}

    changed = sum(1 for a in agg if normalize(a["item_name"]) != " ".join((a["item_name"] or "").lower().split()))
    kinds = Counter(v["kind"] for v in lex.values())
    out = {
        "session": "SU11A-36", "mode": "report", "current_user": who,
        "timings_ms": inputs["timings"],
        "live_stores": len(inputs["live_fks"]),
        "live_items": len(rows),
        "multi_chain_items": sum(1 for r in rows if r["chains_live"] >= 2),
        "promo_only_items": sum(1 for r in rows if r["promo_only"]),
        "names_changed_by_normalize_beyond_case_and_spaces": changed,
        "pseudo": {
            "total": len(pseudo),
            "coupon_rule_total": len(coupon_codes),
            "price_rule_total": len(price_rule),
            "both_rules": len(coupon_codes & set(price_rule)),
            "by_pattern": {k: len(v) for k, v in by_pattern.items()},
            "samples": {**{k: sample(v) for k, v in by_pattern.items()},
                        f"all_prices_below_{PSEUDO_MAX_PRICE}": sample(price_rule)},
            "mentions_coupon_NOT_flagged": {"count": len(mention_not_flagged),
                                            "samples": sample(mention_not_flagged)},
        },
        "eilat": {"column": "stores.city_canonical", "value": EILAT, **dict(eilat)},
        "expected_rows": {
            "search_items": len(rows),
            "search_items_searchable (not pseudo)": len(rows) - len(pseudo),
            "search_lexicon": len(lex),
            "search_lexicon_by_kind": dict(kinds),
            # One row per (item, live chain). An upper bound: a chain whose only
            # quotes for an item are in Eilat is dropped when other chains sell it.
            "search_item_prices (at most)": sum(r["chains_live"] for r in rows),
        },
        "aliases": {
            "file": aliases_path.relative_to(ROOT).as_posix(), "count": len(aliases),
            "canonical_matches_nothing": sorted(f"{a} -> {c}" for a, c in aliases if lex[a]["freq"] == 0),
        },
        "pg_trgm": trgm,
        "tables_now": tables,
        "search_items_built_at": built.isoformat() if built else None,
    }
    return out


def print_report(r: dict) -> None:
    p = print
    p("\n=== SU11A-36 build_search_items --report (read-only) ===")
    p(f"db role: {r['current_user']}; timings ms: {r['timings_ms']}")
    p(f"live stores {r['live_stores']} | live items {r['live_items']} | 2+ chains {r['multi_chain_items']} | "
      f"promo-only {r['promo_only_items']}")
    p(f"names changed by normalize (quotes / hyphens / niqqud): {r['names_changed_by_normalize_beyond_case_and_spaces']}")
    ps = r["pseudo"]
    p(f"\npseudo items: {ps['total']} (coupon rule {ps['coupon_rule_total']}, price rule {ps['price_rule_total']}, "
      f"both {ps['both_rules']}); by pattern: {ps['by_pattern']}")
    for k, lines in ps["samples"].items():
        p(f"\n[{k}] first {SAMPLE} by md5(item_code): code | name | manufacturer | chains | max live price")
        for ln in lines:
            p(f"  {ln}")
        if not lines:
            p("  (none)")
    m = ps["mentions_coupon_NOT_flagged"]
    p(f"\n[names containing קופו... that are NOT flagged] {m['count']}")
    for ln in m["samples"]:
        p(f"  {ln}")
    e = r["eilat"]
    p(f"\nEilat: {e['column']} = '{e['value']}': {e['stores']} stores, {e['live']} live; "
      f"raw stores.city values: {e['raw_city_values']}")
    x = r["expected_rows"]
    p(f"\nexpected rows: search_items {x['search_items']} (searchable {x['search_items_searchable (not pseudo)']}), "
      f"search_lexicon {x['search_lexicon']} {x['search_lexicon_by_kind']}, "
      f"search_item_prices at most {x['search_item_prices (at most)']} (one per item and live chain)")
    a = r["aliases"]
    p(f"aliases: {a['count']} from {a['file']}; Hebrew spelling matches no live item: "
      f"{len(a['canonical_matches_nothing'])}")
    for ln in a["canonical_matches_nothing"]:
        p(f"  {ln}")
    p(f"\npg_trgm: {r['pg_trgm']}  (trigrams_in_חלב should be 4-5; 0/NULL means Hebrew is not split "
      "into trigrams and the typo fallback cannot work)")
    p(f"tables now: {r['tables_now']}")
    p(f"search_items built_at now: {r['search_items_built_at']}")


# --------------------------------------------------------------------------- apply
def _insert(conn, table: str, cols: list[str], rows: list[dict]) -> None:
    from sqlalchemy import text
    sql = text(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})")
    for i in range(0, len(rows), INSERT_CHUNK):
        conn.execute(sql, rows[i:i + INSERT_CHUNK])


def _price_tables_exist(conn) -> bool:
    return all(_table_exists(conn, t) for t in PRICE_TABLES)


def swap(with_prices: bool | None = None) -> float:
    """Swap live <-> next names (tables, pkeys, indexes) in one transaction.

    with_prices None = also the search_item_prices pair when both of its tables
    exist (--swap-back); --apply passes False when the price fill did not succeed.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    for attempt in range(1, 4):
        conn = _connect(read_only=False)
        try:
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            pairs = list(SWAP_PAIRS)
            if with_prices or (with_prices is None and _price_tables_exist(conn)):
                pairs += PRICE_SWAP_PAIRS
            t0 = time.perf_counter()
            for kind, live, nxt in pairs:
                tmp = f"{live}__swap"
                conn.execute(text(f"ALTER {kind} {live} RENAME TO {tmp}"))
                conn.execute(text(f"ALTER {kind} {nxt} RENAME TO {live}"))
                conn.execute(text(f"ALTER {kind} {tmp} RENAME TO {nxt}"))
            conn.commit()
            return (time.perf_counter() - t0) * 1000
        except OperationalError as exc:
            conn.rollback()
            log(f"swap attempt {attempt}: could not get the locks ({type(exc.orig).__name__}); retrying")
            time.sleep(2)
        finally:
            conn.close()
    raise SystemExit("swap failed 3 times; the live tables are unchanged")


def apply(conn, inputs: dict, aliases_path: Path, price_chunks: int = PRICE_CHUNKS) -> dict:
    from sqlalchemy import text
    timings = dict(inputs["timings"])
    for t in ("search_items", "search_items_next", "search_lexicon", "search_lexicon_next"):
        if not _table_exists(conn, t):
            raise SystemExit(f"table {t} is missing - apply db/migrations/su11a36_search_items.sql first")
    current = conn.execute(text("SELECT count(*) FROM search_items")).scalar()

    t0 = time.perf_counter()
    built_at = datetime.now(timezone.utc)
    rows = build_rows(inputs["agg"], read_popularity(conn), built_at)
    lex = build_lexicon(rows, load_aliases(aliases_path))
    timings["python_build_ms"] = round((time.perf_counter() - t0) * 1000)

    if current and len(rows) < current * MIN_KEEP_RATIO:
        raise SystemExit(f"new build has {len(rows)} rows, live table {current}: below "
                         f"{MIN_KEEP_RATIO:.0%} - refusing to swap; nothing changed")

    t0 = time.perf_counter()
    conn.execute(text("TRUNCATE search_items_next, search_lexicon_next"))
    _insert(conn, "search_items_next",
            ["item_code", "name_norm", "manufacturer_norm", "is_pseudo", "chains_live", "stores_live",
             "promo_only", "popularity", "built_at"], rows)
    _insert(conn, "search_lexicon_next", ["term", "kind", "canonical", "freq"],
            [{"term": k, **v} for k, v in lex.items()])
    conn.execute(text("ANALYZE search_items_next"))
    conn.execute(text("ANALYZE search_lexicon_next"))
    staged = conn.execute(text("SELECT count(*) FROM search_items_next")).scalar()
    conn.commit()
    timings["fill_ms"] = round((time.perf_counter() - t0) * 1000)
    if staged != len(rows):
        raise SystemExit(f"staged {staged} rows, expected {len(rows)} - not swapping")

    prices = fill_prices(conn, inputs, built_at, len(rows), price_chunks)
    timings.update(prices.pop("timings_ms", {}))
    timings["swap_ms"] = round(swap(with_prices=prices["swapped"]))
    pseudo = sum(1 for r in rows if r["is_pseudo"])
    return {"session": "SU11A-36/47", "mode": "apply", "built_at": built_at.isoformat(),
            "search_items": len(rows), "pseudo": pseudo, "searchable": len(rows) - pseudo,
            "search_lexicon": len(lex), "previous_live_rows": current,
            "search_item_prices": prices, "timings_ms": timings}


def fill_prices(conn, inputs: dict, built_at: datetime, n_items: int, chunks: int) -> dict:
    """SU11A-47: fill search_item_prices_next; never raises.

    {"swapped": False, ...} when the tables are missing (migration not applied)
    or the fill failed: search_items is swapped in on its own and the API keeps
    the live price fetch, because the stamps then differ.
    """
    from sqlalchemy import text
    from db.search_v2 import EILAT
    if not _price_tables_exist(conn):
        log("WARNING: search_item_prices is missing (db/migrations/su11a47_search_prices.sql not applied); "
            "building search_items only - the API keeps the live price fetch")
        return {"swapped": False, "reason": "tables missing"}
    timings: dict = {}
    t0 = time.perf_counter()
    try:
        eilat = [r[0] for r in conn.execute(text("SELECT id FROM stores WHERE city_canonical = :c"), {"c": EILAT})]
        sql = text(price_fill_sql())
        bounds = price_bounds(conn, chunks)
        conn.execute(text("TRUNCATE search_item_prices_next"))
        for k, (lo, hi) in enumerate(bounds):
            tc = time.perf_counter()
            conn.execute(sql, {"lo": lo, "hi": hi, "live": inputs["live_fks"], "eilat": eilat,
                               "built_at": built_at})
            log(f"search_item_prices chunk {k + 1}/{len(bounds)}: {round((time.perf_counter() - tc) * 1000)} ms")
        conn.execute(text("ANALYZE search_item_prices_next"))
        n_rows, n_codes = conn.execute(text(
            "SELECT count(*), count(DISTINCT item_code) FROM search_item_prices_next")).one()
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - search_items must still go live
        conn.rollback()
        log(f"WARNING: search_item_prices fill failed ({type(exc).__name__}: {str(exc)[:300]}); "
            "swapping search_items only - the API keeps the live price fetch")
        return {"swapped": False, "reason": f"fill failed: {type(exc).__name__}"}
    timings["prices_fill_ms"] = round((time.perf_counter() - t0) * 1000)
    out = {"rows": n_rows, "items": n_codes, "build_items": n_items, "chunks": len(bounds), "timings_ms": timings}
    if n_codes < n_items * MIN_PRICE_ITEMS:
        log(f"WARNING: search_item_prices covers {n_codes} of {n_items} items (< {MIN_PRICE_ITEMS:.0%}); "
            "not swapping it in - the API keeps the live price fetch")
        return {**out, "swapped": False, "reason": "too few items"}
    return {**out, "swapped": True}


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--report", action="store_true", help="read-only counts and samples")
    g.add_argument("--apply", action="store_true", help="build and swap in")
    g.add_argument("--swap-back", action="store_true", help="make the previous build live again")
    ap.add_argument("--aliases", default=str(ALIASES), help="alias,canonical CSV")
    ap.add_argument("--out", default=None, help="also write the result as JSON here")
    ap.add_argument("--price-chunks", type=int, default=PRICE_CHUNKS,
                    help="search_item_prices fill statements (SU11A-47)")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # Hebrew on any console
        stream.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(ROOT))

    _load_env(read_only=args.report)
    started = time.perf_counter()
    if args.swap_back:
        ms = swap()
        print(f"swapped back in {ms:.0f} ms: the previous build is live again")
        return 0

    conn = _connect(read_only=args.report)
    try:
        inputs = read_inputs(conn)
        if args.report:
            result = report(conn, inputs, Path(args.aliases))
            conn.rollback()
            print_report(result)
        else:
            result = apply(conn, inputs, Path(args.aliases), max(1, args.price_chunks))
            print(f"\n=== SU11A-36 build_search_items --apply ===\n{json.dumps(result, ensure_ascii=False, indent=1)}")
    finally:
        conn.close()
    print(f"\nelapsed {time.perf_counter() - started:.1f} s")
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"JSON: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
