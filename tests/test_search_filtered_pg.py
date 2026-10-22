"""SU11A-50 filtered v2 path against a real Postgres, compared with the old path
(api.routers.search._build_result) on generated data: 5 chains, 4 cities (one
of them Eilat), dead stores, ₪0 shelf prices, missing item_chain_names rows,
every promo kind (direct, bundle, rate-only, 100% rate, ended, promo-only,
basket), coupon pseudo items.

Needs a throwaway Postgres server; SKIPPED unless SCRP_TEST_PG_URL is set, e.g.
    SCRP_TEST_PG_URL=postgresql://postgres:@127.0.0.1:5432/postgres
Creates (and drops) its own database, su11a50_test. No pg_trgm needed (no typo
correction here; that path is covered with fakes in test_search_filtered.py).
"""
import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PG_URL = os.environ.get("SCRP_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

ROOT = Path(__file__).resolve().parent.parent
DB = "su11a50_test"
EILAT = "אילת"
CITIES = ["רמת גן", "בני ברק", "ירושלים", EILAT]
CHAINS = "ABCDE"
FUTURE, PAST = "2099-01-01 00:00:00", "2001-01-01 00:00:00"
WORDS = ["חלב", "שוקולד", "לחם", "במבה", "ים", "קפה", "חלבה", "בחלב", "מריר", "לבן", "מלא", "אחיד"]
MFRS = ["תנובה", "עלית", "אסם", "שטראוס", "אנג'ל", None]
QUERIES = ["חלב", "שוקולד", "לחם", "במבה", "ים", "קפה", "תנובה", "חלב תנובה", "אסם"]


def _data(seed: int = 50):
    rnd = random.Random(seed)
    stores = {}   # id: (chain, city, live)
    sid = 0
    for ch in CHAINS:
        for city in CITIES:
            if city == EILAT and ch not in "AB":
                continue
            for _ in range(rnd.choice([1, 2])):
                sid += 1
                stores[sid] = (ch, city, True)
    for ch in "AC":   # dead branches: last load 30 days behind the chain
        sid += 1
        stores[sid] = (ch, CITIES[0], False)
    items = {}
    for n in range(90):
        words = rnd.sample(WORDS, rnd.choice([1, 2, 3]))
        name = " ".join(words) + f" {rnd.choice([1, 2, 5, 80, 500])} גרם"
        if n % 30 == 7:
            name = "הנ.קופון " + name          # coupon pseudo item
        items[f"72900000{n:05d}"] = (name, rnd.choice(MFRS))
    prices, icn, promos = [], set(), []
    ids = list(stores)
    for code in items:
        k = rnd.choice([0, 1, 2, 4, 6, 9])
        chosen = rnd.sample(ids, k)
        if code.endswith("3"):                  # Eilat only
            chosen = [i for i in ids if stores[i][1] == EILAT][:rnd.choice([1, 2])]
        for fk in chosen:
            price = rnd.choice([0.0, 4.9, 5.0, 5.0, 7.5, 9.9, 12.0])
            prices.append((fk, code, price))
            if rnd.random() < 0.92:             # some chains have no name row
                icn.add((code, stores[fk][0]))
        for fk in rnd.sample(ids, rnd.choice([0, 0, 1, 2])):
            kind = rnd.choice(["direct", "bundle", "rate", "rate100", "ended", "basket"])
            pid = f"p{len(promos)}"
            if kind == "direct":
                promos.append((fk, code, pid, "ב-4", 1, None, rnd.choice([3.5, 4.0, 4.9]), FUTURE))
            elif kind == "bundle":
                promos.append((fk, code, pid, "3 ב-10", 3, None, 10, FUTURE))
            elif kind == "rate":
                promos.append((fk, code, pid, "10%", 1, 10, None, FUTURE))
            elif kind == "rate100":
                promos.append((fk, code, pid, "1+1", 1, 100, None, FUTURE))
            elif kind == "ended":
                promos.append((fk, code, pid, "ב-1", 1, None, 1, PAST))
            else:
                promos.append((fk, code, pid, "קנה ב-100", 30, None, 50, FUTURE))
    return stores, items, prices, icn, promos


STORES, ITEMS, PRICES, ICN, PROMOS = _data()
LIVE = sorted(i for i, s in STORES.items() if s[2])
EILAT_FKS = frozenset(i for i, s in STORES.items() if s[1] == EILAT)


@pytest.fixture(scope="module")
def engine():
    from sqlalchemy import create_engine, text
    import tests.test_search_prices_pg as T
    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {DB}"))
        c.execute(text(f"CREATE DATABASE {DB}"))
    eng = create_engine(PG_URL.rsplit("/", 1)[0] + "/" + DB)
    mig = (ROOT / "db" / "migrations" / "su11a47_search_prices.sql").read_text(encoding="utf-8")
    mig = "\n".join(ln for ln in mig.splitlines()
                    if not ln.startswith(("BEGIN", "COMMIT", "ALTER TABLE")) and not ln.startswith("--"))
    now = datetime.now(timezone.utc)
    with eng.begin() as c:
        c.execute(text(T.SCHEMA))
        c.execute(text(mig))
        for ch in CHAINS:
            c.execute(text("INSERT INTO chains VALUES (:c, :n)"), {"c": ch, "n": f"רשת {ch}"})
        for sid, (ch, city, live) in STORES.items():
            c.execute(text("INSERT INTO stores (id, chain_id, store_id, store_name, city, city_canonical, address, "
                           "last_loaded_at) VALUES (:i, :c, :s, :n, :city, :city, :a, :t)"),
                      {"i": sid, "c": ch, "s": str(100 + sid), "n": f"סניף {sid}", "city": city, "a": f"רחוב {sid}",
                       "t": now if live else now - timedelta(days=30)})
        for code, (name, mfr) in ITEMS.items():
            c.execute(text("INSERT INTO items VALUES (:c, 1, :n, :m, '1', 1, 0, 'יחידה')"),
                      {"c": code, "n": name, "m": mfr})
        c.execute(text("INSERT INTO prices (store_fk, item_code, price_update_date, item_price, unit_of_measure_price) "
                       "VALUES (:f, :c, '2026-10-22 10:00', :p, :p)"),
                  [{"f": f, "c": code, "p": p} for f, code, p in PRICES])
        c.execute(text("INSERT INTO item_chain_names VALUES (:c, :ch, :n, :m)"),
                  [{"c": code, "ch": ch, "n": f"{ITEMS[code][0]} ({ch})", "m": ITEMS[code][1]}
                   for code, ch in sorted(ICN)])
        if PROMOS:
            c.execute(text("INSERT INTO promos (store_fk, item_code, promo_id, promo_description, min_qty, "
                           "discount_rate, discount_price, promo_end) VALUES (:f, :c, :i, :d, :q, :r, :p, :e)"),
                      [dict(zip("fcidqrpe", p)) for p in PROMOS])
    _build(eng)
    yield eng
    eng.dispose()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {DB}"))
    admin.dispose()


def _build(eng):
    """search_items (the build's own aggregate + rows) and search_item_prices, swapped in."""
    import scripts.build_search_items as B
    from sqlalchemy import text
    built = datetime.now(timezone.utc).replace(microsecond=0)
    with eng.connect() as conn:
        agg = [dict(r) for r in conn.execute(text(B.AGG_SQL), {"live": LIVE}).mappings()]
        rows = B.build_rows(agg, {}, built)
        conn.execute(text("DELETE FROM search_items"))
        B._insert(conn, "search_items", list(rows[0]), rows)
        res = B.fill_prices(conn, {"live_fks": LIVE}, built, len(rows), 3)
        assert res["swapped"], res
        conn.execute(text("ALTER TABLE search_item_prices RENAME TO search_item_prices__swap"))
        conn.execute(text("ALTER TABLE search_item_prices_next RENAME TO search_item_prices"))
        conn.execute(text("ALTER TABLE search_item_prices__swap RENAME TO search_item_prices_next"))
        conn.commit()


@pytest.fixture
def env(engine, monkeypatch):
    import db.query as Q
    import db.search_filtered as F
    import db.search_v2 as V
    lv = Q.Liveness(live_fks=frozenset(LIVE), dead_pairs=frozenset(), dead_names=frozenset(),
                    live_cities=frozenset(), live_chains=frozenset())
    monkeypatch.setattr(Q, "get_liveness", lambda: lv)
    V._cache.built_at = V._cache.prices_built_at = V._cache.lexicon = None
    # Small batches and first fetch, so the walk and the stream take many steps.
    monkeypatch.setattr(F, "BATCHES", (3, 5, 8, 400))
    monkeypatch.setattr(V, "_STREAM_FIRST", 4)
    monkeypatch.setattr(F, "STREAM_FIRST", 4)
    conn = engine.connect()
    yield conn
    conn.rollback()
    conn.close()


def _pseudo(conn) -> set[str]:
    from sqlalchemy import text
    return {r[0] for r in conn.execute(text("SELECT item_code FROM search_items WHERE is_pseudo"))}


def _j(p) -> dict:
    from api.routers.search import _to_model
    return json.loads(_to_model(p).model_dump_json())


def _all_pages(conn, q, limit=4, **kw):
    """Every page of the filtered path, in order; returns (items, first result)."""
    import db.search_filtered as F
    out, first, offset = [], None, 0
    for _ in range(200):
        r = F.run(conn, q, limit=limit, offset=offset, **kw)
        first = first or r
        out += r.products
        if not r.has_more:
            return out, first
        offset += limit
    raise AssertionError("no end of pages")


# --------------------------------------------------------------------------- the candidate stream

def test_ranked_stream_matches_full_rank(env):
    import db.search_v2 as V
    from db.search_norm import normalize, tokenize
    for q in QUERIES + ["חל", "80", "שוקולד מריר", "לחם 500"]:
        qn = normalize(q)
        groups = V.apply_aliases(tokenize(qn), {})
        want = V.rank(V._candidates(env, groups), groups, qn)
        r = V._ranked(env, groups, qn)
        got = r.take(10_000)
        assert [c["item_code"] for c in got] == [c["item_code"] for c in want], q
        assert [c["tier"] for c in got] == [c["tier"] for c in want], q
        assert r.total == len(want)
        assert r.comparable == sum(1 for c in want if c["chains_live"] >= 2)
        if len(want) > 4:
            assert r.queries >= 2        # several fetches, still the same order


def test_v2_run_unchanged_by_the_stream(env, monkeypatch):
    """run() pages from the stream; the result equals the old full ranking's page."""
    import db.search_v2 as V
    from db.search_norm import normalize, tokenize
    for q in QUERIES:
        qn = normalize(q)
        groups = V.apply_aliases(tokenize(qn), {})
        want = [c["item_code"] for c in V.rank(V._candidates(env, groups), groups, qn)]
        for offset in (0, 3, 7):
            r = V.run(env, q, limit=5, offset=offset)
            assert [c["item_code"] for c in r.ranked_page] == want[offset:offset + 5]
            assert r.total_matches == len(want)
            assert r.has_more == (offset + 5 < len(want))


# --------------------------------------------------------------------------- city / store set

@pytest.mark.parametrize("compare_only", [False, True])
def test_city_matches_old_path(env, compare_only):
    import api.routers.search as R
    import db.search_filtered as F
    pseudo = _pseudo(env)
    checked = 0
    for q in QUERIES:
        for city in CITIES:
            old = R._build_result(q, env, 1000, 0, [city], None, compare_only=compare_only)
            old_items = {it.product.item_code: json.loads(it.model_dump_json())
                         for it in old.items if it.product.item_code not in pseudo}
            new, first = _all_pages(env, q, city=[city], compare_only=compare_only)
            codes = [p["item_code"] for p in new]
            assert len(codes) == len(set(codes)), (q, city)
            assert set(codes) == set(old_items), (q, city, compare_only)
            for p in new:
                assert _j(p) == old_items[p["item_code"]], (q, city, p["item_code"])
                for qt in p["quotes"]:
                    assert qt["store_fk"] in {i for i, s in STORES.items() if s[1] == city}
            # Counts: exact once the walk covered every candidate. The old
            # /search lists every priced item, so it gives the expected numbers
            # for both endpoints (pseudo items left out, as v2 leaves them out).
            full = F.run(env, q, limit=100, offset=0, city=[city], compare_only=compare_only)
            every = [it for it in R._build_result(q, env, 1000, 0, [city], None, compare_only=False).items
                     if it.product.item_code not in pseudo]
            assert full.exact_counts
            assert full.total_matches == len(every)
            assert full.comparable_count == sum(1 for it in every if it.chains_count >= 2)
            checked += len(new)
    assert checked > 20


def test_city_and_chain(env):
    import api.routers.search as R
    pseudo = _pseudo(env)
    for q in ("חלב", "שוקולד", "תנובה"):
        for city, chain in (("רמת גן", ["A"]), ("בני ברק", ["B", "C"]), (EILAT, ["A"])):
            old = R._build_result(q, env, 1000, 0, [city], chain, compare_only=False)
            want = {it.product.item_code: json.loads(it.model_dump_json())
                    for it in old.items if it.product.item_code not in pseudo}
            new, _ = _all_pages(env, q, city=[city], chain=chain)
            assert {p["item_code"]: _j(p) for p in new} == want


def test_group_by_store_rows_match_old_path(env):
    import api.routers.search as R
    import db.search_filtered as F
    pseudo = _pseudo(env)
    for q in ("חלב", "לחם", "במבה"):
        for kw in ({"city": ["רמת גן"]}, {"chain": ["B"]}, {}):
            old = R._build_result(q, env, 10_000, 0, kw.get("city"), kw.get("chain"),
                                  compare_only=False, group_by="store")
            want = sorted(json.dumps(json.loads(it.model_dump_json()), sort_keys=True)
                          for it in old.items if it.product.item_code not in pseudo)
            new, _ = _all_pages(env, q, limit=3, group_by="store", **kw)
            got = sorted(json.dumps(_j(p), sort_keys=True) for p in new)
            assert got == want, (q, kw)
            full = F.run(env, q, limit=100, offset=0, group_by="store", **kw)
            assert full.exact_counts and full.total_matches == len(want)


def test_eilat_shown_in_eilat_and_dropped_nationwide(env):
    import db.search_filtered as F
    eilat_only_seen = shown_in_eilat = 0
    for q in QUERIES:
        r, _ = _all_pages(env, q, city=[EILAT])
        for p in r:
            assert all(qt["store_fk"] in EILAT_FKS for qt in p["quotes"])
            shown_in_eilat += 1
        nat, _ = _all_pages(env, q, compare_only=True)
        for p in nat:
            fks = {qt["store_fk"] for qt in p["quotes"]}
            if fks & EILAT_FKS:
                # D2: an Eilat quote only survives where the item has no other quote
                eilat_only_seen += 1
                assert fks <= EILAT_FKS
    assert shown_in_eilat > 0
    assert F.run(env, "חלב", limit=5, offset=0, city=[EILAT]).mode == "stores"


# --------------------------------------------------------------------------- nationwide modes

def _reference(conn, codes, chain=None):
    """search v2's nationwide view: live rows, Eilat rule over all chains, then the chain filter."""
    import db.query as Q
    import db.search_v2 as V
    rows = V.drop_eilat(Q.fetch_prices(conn, codes), EILAT_FKS, None)
    if chain:
        rows = [r for r in rows if r["chain_id"] in chain]
    return Q.group_by_product(rows)


def test_chain_filter_from_precomputed_equals_live_reference(env, monkeypatch):
    import db.search_filtered as F
    for q in ("חלב", "שוקולד", "לחם", "תנובה"):
        for chain in (["A"], ["B", "D"], ["E"]):
            new, first = _all_pages(env, q, chain=chain)
            assert first.mode == "chain-precomputed"
            assert all(qt["chain_id"] in chain for p in new for qt in p["quotes"])
            codes = [p["item_code"] for p in new]
            ref = _reference(env, codes, chain)
            assert [_j(p) for p in new] == [_j(ref[c]) for c in codes]
            # The live fallback (another build's prices) gives the same answer.
            orig = F.precomputed_ok
            F.precomputed_ok = lambda conn: False
            try:
                live, lf = _all_pages(env, q, chain=chain)
            finally:
                F.precomputed_ok = orig
            assert lf.mode == "chain-live"
            assert [_j(p) for p in live] == [_j(p) for p in new], (q, chain)


def test_national_compare_from_precomputed(env):
    import db.search_filtered as F
    import db.search_v2 as V
    from db.search_norm import normalize, tokenize
    for q in QUERIES:
        new, first = _all_pages(env, q, compare_only=True)
        assert first.mode == "national-precomputed"
        qn = normalize(q)
        groups = V.apply_aliases(tokenize(qn), {})
        ranked = [c["item_code"] for c in V.rank(V._candidates(env, groups), groups, qn)]
        ref = _reference(env, ranked)
        want = [c for c in ranked if c in ref and F.compare_ok(ref[c])]
        assert [p["item_code"] for p in new] == want, q
        assert [_j(p) for p in new] == [_j(ref[c]) for c in want]
        assert first.prices_source == "precomputed" or not new


def test_national_compare_without_precomputed_is_unsupported(env, monkeypatch):
    import db.search_filtered as F
    monkeypatch.setattr(F, "precomputed_ok", lambda conn: False)
    with pytest.raises(F.Unsupported):
        F.run(env, "חלב", limit=5, offset=0, compare_only=True)


def test_ceiling_stops_the_walk(env, monkeypatch):
    import db.search_filtered as F
    full, _ = _all_pages(env, "חלב", city=["רמת גן"])
    monkeypatch.setattr(F, "CEILING", 6)
    r = F.run(env, "חלב", limit=50, offset=0, city=["רמת גן"])
    assert r.walked == 6 and not r.exact_counts
    assert not r.has_more
    assert [p["item_code"] for p in r.products] == [p["item_code"] for p in full][:len(r.products)]
