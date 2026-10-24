"""SU11A-52 catalog tables against a real Postgres: the migration (twice), the
precedence guard in the upsert SQL, import_categories dry run / apply, and the
build_search_items category hook.

Needs a throwaway Postgres server; SKIPPED unless SCRP_TEST_PG_URL is set, e.g.
    SCRP_TEST_PG_URL=postgresql://postgres:@127.0.0.1:5432/postgres
The test creates (and drops) its own database, su11a52_test, on that server and
never touches any other.
"""
import json
import os
from pathlib import Path

import pytest

PG_URL = os.environ.get("SCRP_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="SCRP_TEST_PG_URL not set (needs a throwaway Postgres)")

ROOT = Path(__file__).resolve().parent.parent
DB = "su11a52_test"
MIGRATION = ROOT / "db" / "migrations" / "su11a52_catalog.sql"

SCHEMA = """
CREATE TABLE items (item_code TEXT PRIMARY KEY, item_name TEXT, manufacturer_name TEXT, is_weighted INTEGER);
CREATE TABLE search_items (item_code TEXT PRIMARY KEY, name_norm TEXT NOT NULL DEFAULT '',
    manufacturer_norm TEXT NOT NULL DEFAULT '', is_pseudo BOOLEAN NOT NULL DEFAULT false,
    chains_live SMALLINT NOT NULL DEFAULT 0, stores_live INTEGER NOT NULL DEFAULT 0,
    promo_only BOOLEAN NOT NULL DEFAULT false, popularity INTEGER NOT NULL DEFAULT 0,
    built_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE SCHEMA gs1;
CREATE TABLE gs1.products (id SERIAL PRIMARY KEY, gtin TEXT, product_status TEXT, group_name TEXT,
    brandname TEXT, trade_item_description TEXT, full_content JSONB, modification_timestamp TIMESTAMPTZ);
"""
# item_code: (name_norm, is_pseudo, is_weighted)
ITEMS = {
    "7290000000011": ("פילה עוף טרי", False, 1),
    "7290000000022": ("קפה עלית טורקי 100 גרם", False, 0),
    "7290000000033": ("xyzzy", False, 0),            # rules: nothing; AI: D16.C04
    "7290000000044": ("פיקדון בקבוק", True, 0),       # pseudo: never classified
    "7290000000055": ("טחינה גולמית 500 גרם", False, 0),
    "7290000000066": ("שוקולד מריר 100 גרם", False, 0),
}


def _migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def engine():
    from sqlalchemy import create_engine, text
    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {DB}"))
        c.execute(text(f"CREATE DATABASE {DB}"))
        c.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scrp_app') "
                       "THEN CREATE ROLE scrp_app; END IF; END $$"))
    url = PG_URL.rsplit("/", 1)[0] + "/" + DB
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text(SCHEMA))
        for code, (name, pseudo, w) in ITEMS.items():
            c.execute(text("INSERT INTO items VALUES (:c, :n, NULL, :w)"), {"c": code, "n": name, "w": w})
            c.execute(text("INSERT INTO search_items (item_code, name_norm, is_pseudo, chains_live) "
                           "VALUES (:c, :n, :p, 3)"), {"c": code, "n": name, "p": pseudo})
        c.execute(text("INSERT INTO gs1.products (gtin, product_status, group_name, brandname) "
                       "VALUES ('7290000000022', 'פעיל', 'Coffee - Beans_Ground', 'עלית')"))
    eng.url_str = url
    yield eng
    eng.dispose()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {DB}"))
    admin.dispose()


def _apply_migration(eng):
    raw = eng.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute(_migration_sql())          # has its own BEGIN / COMMIT
        raw.commit()
    finally:
        raw.close()


def test_migration_is_idempotent_and_owned(engine):
    from sqlalchemy import text
    _apply_migration(engine)
    _apply_migration(engine)
    with engine.connect() as c:
        owners = dict(c.execute(text("SELECT tablename, tableowner FROM pg_tables WHERE tablename IN "
                                     "('categories', 'item_categories', 'item_attributes')")).all())
        assert owners == {"categories": "scrp_app", "item_categories": "scrp_app", "item_attributes": "scrp_app"}
        idx = {r[0] for r in c.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'item_categories'"))}
        assert "idx_item_categories_category" in idx
        trig = c.execute(text("SELECT count(*) FROM pg_trigger t JOIN pg_class k ON k.oid = t.tgrelid "
                              "WHERE k.relname IN ('categories', 'item_categories', 'item_attributes') "
                              "AND NOT t.tgisinternal")).scalar()
        assert trig == 0


def _with_db(engine, monkeypatch):
    import db.db as D
    monkeypatch.setenv("DATABASE_URL", engine.url_str)
    monkeypatch.setattr(D, "_engine", None)


def _main(monkeypatch, args):
    """import_categories.main as a fresh server process would run it: PGOPTIONS
    (read-only for a dry run) is set per run, so reset it and the cached engine."""
    import db.db as D
    import scripts.catalog.import_categories as I
    monkeypatch.setenv("PGOPTIONS", "")
    if D._engine is not None:
        D._engine.dispose()
    monkeypatch.setattr(D, "_engine", None)
    try:
        return I.main(args)
    finally:
        if D._engine is not None:
            D._engine.dispose()


def test_import_dry_run_writes_nothing_then_apply(engine, monkeypatch, tmp_path, capsys):
    import scripts.catalog.import_categories as I
    from sqlalchemy import text
    _apply_migration(engine)
    _with_db(engine, monkeypatch)
    ai = tmp_path / "ai.csv"
    ai.write_text("item_code,category_id,confidence,reason,model\n"
                  "7290000000033,D16.C04,medium,toy,claude-haiku-5-5\n"
                  "7290000000099,D01,high,not live,claude-haiku-5-5\n", encoding="utf-8")
    assert _main(monkeypatch, ["--ai-labels", str(ai)]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["mode"] == "dry-run" and dry["live_items"] == 5 and dry["ai_labels_for_live_items"] == 1
    assert dry["item_categories_changes"] == {"insert": dry["item_categories_planned"]}
    assert dry["categories"]["insert"] == dry["categories"]["rows"]
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM categories")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM item_categories")).scalar() == 0

    assert _main(monkeypatch, ["--ai-labels", str(ai), "--apply"]) == 0
    res = json.loads(capsys.readouterr().out)
    with engine.connect() as c:
        rows = {r[0]: r[1:] for r in c.execute(text(
            "SELECT item_code, category_id, source, confidence, reviewed FROM item_categories"))}
        assert rows["7290000000011"][:2] == ("D03.C06", "rule")
        assert rows["7290000000022"][0].startswith("D09.C08") and rows["7290000000022"][1] == "gs1"
        assert rows["7290000000033"][:2] == ("D16.C04", "ai")
        assert rows["7290000000055"][0] == "D07.C20"
        assert "7290000000044" not in rows                     # pseudo
        assert c.execute(text("SELECT count(*) FROM categories")).scalar() == res["categories"]["rows"]
        brand = c.execute(text("SELECT value_text, source FROM item_attributes "
                               "WHERE item_code = '7290000000022' AND attr_key = 'brand'")).one()
        assert tuple(brand) == ("עלית", "gs1")

    # A second dry run sees no changes.
    assert _main(monkeypatch, ["--ai-labels", str(ai)]) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["item_categories_changes"] == {"unchanged": again["item_categories_planned"]}
    assert again["categories"]["unchanged"] == again["categories"]["rows"]


def test_precedence_in_the_database(engine, monkeypatch, tmp_path, capsys):
    """Manual, reviewed and higher-source rows survive an automated import; a
    manual review file replaces them."""
    import scripts.catalog.import_categories as I
    from sqlalchemy import text
    _apply_migration(engine)
    _with_db(engine, monkeypatch)
    ai = tmp_path / "ai.csv"
    ai.write_text("item_code,category_id,confidence,reason,model\n", encoding="utf-8")
    assert _main(monkeypatch, ["--ai-labels", str(ai), "--apply"]) == 0
    capsys.readouterr()
    with engine.begin() as c:
        c.execute(text("UPDATE item_categories SET category_id = 'D16.C07', source = 'manual', reviewed = true "
                       "WHERE item_code = '7290000000011'"))
        c.execute(text("UPDATE item_categories SET category_id = 'D08.C02', source = 'rule', reviewed = true "
                       "WHERE item_code = '7290000000066'"))
        c.execute(text("UPDATE item_categories SET category_id = 'D09', source = 'ai', model = 'm' "
                       "WHERE item_code = '7290000000022'"))
        c.execute(text("UPDATE item_categories SET category_id = 'D07', source = 'rule' "
                       "WHERE item_code = '7290000000055'"))
    assert _main(monkeypatch, ["--ai-labels", str(ai)]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["item_categories_changes"].get("protected") == 3          # manual, reviewed, ai > gs1
    assert _main(monkeypatch, ["--ai-labels", str(ai), "--apply"]) == 0
    capsys.readouterr()
    with engine.connect() as c:
        got = dict(c.execute(text("SELECT item_code, category_id FROM item_categories")).all())
    assert got["7290000000011"] == "D16.C07"     # manual kept
    assert got["7290000000066"] == "D08.C02"     # reviewed kept
    assert got["7290000000022"] == "D09"         # ai not downgraded by gs1
    assert got["7290000000055"] == "D07.C20"     # same source: updated
    review = tmp_path / "review.csv"
    review.write_text("item_code,correct_category_id\n7290000000022,D09.C08.S03\n", encoding="utf-8")
    assert _main(monkeypatch, ["--ai-labels", str(ai), "--manual", str(review), "--apply"]) == 0
    capsys.readouterr()
    with engine.connect() as c:
        r = c.execute(text("SELECT category_id, source, reviewed FROM item_categories "
                           "WHERE item_code = '7290000000022'")).one()
    assert tuple(r) == ("D09.C08.S03", "manual", True)


def test_import_refuses_without_migration(engine, monkeypatch, capsys):
    import scripts.catalog.import_categories as I
    from sqlalchemy import text
    _with_db(engine, monkeypatch)
    with engine.begin() as c:
        c.execute(text("ALTER TABLE item_attributes RENAME TO ia_hidden"))
    try:
        with pytest.raises(SystemExit, match="su11a52_catalog.sql"):
            _main(monkeypatch, [])
    finally:
        with engine.begin() as c:
            c.execute(text("ALTER TABLE ia_hidden RENAME TO item_attributes"))


def test_build_hook(engine, capsys):
    import scripts.build_search_items as B
    from sqlalchemy import text
    _apply_migration(engine)
    rows = [{"item_code": c, "name_norm": n, "is_pseudo": p} for c, (n, p, _) in ITEMS.items()]
    with engine.connect() as c:
        # categories empty -> skipped with one warning
        c.execute(text("DELETE FROM item_attributes"))
        c.execute(text("DELETE FROM item_categories"))
        c.execute(text("DELETE FROM categories"))
        c.commit()
        assert B.classify_new_items(c, rows) == {"skipped": "categories empty"}
        assert "categories is empty" in capsys.readouterr().err
    import scripts.catalog.classify_rules as C
    import scripts.catalog.import_categories as I
    with engine.begin() as c:
        c.execute(text("INSERT INTO categories (id, parent_id, level, name_he, name_en, sort_order, attributes, "
                       "active, taxonomy_version) VALUES (:id, :parent_id, :level, :name_he, :name_en, :sort_order, "
                       ":attributes, :active, :taxonomy_version)"), I.category_rows(C.load_taxonomy()))
        c.execute(text("INSERT INTO item_categories (item_code, category_id, confidence, source, model, "
                       "taxonomy_version) VALUES ('7290000000011', 'D16.C04', 'medium', 'ai', 'm', 'v1')"))
    with engine.connect() as c:
        res = B.classify_new_items(c, rows)
        got = dict(c.execute(text("SELECT item_code, source FROM item_categories")).all())
        cat = c.execute(text("SELECT category_id FROM item_categories WHERE item_code = '7290000000011'")).scalar()
    assert res["new_live_barcodes"] == 4 and res["inserted"] == res["classified"] == 3
    assert cat == "D16.C04" and got["7290000000011"] == "ai"            # existing row untouched
    assert got["7290000000022"] == "gs1" and "7290000000044" not in got and "7290000000033" not in got
    with engine.connect() as c:                                         # second run: nothing new
        assert B.classify_new_items(c, rows)["inserted"] == 0
    # tables missing -> skipped
    with engine.begin() as c:
        c.execute(text("ALTER TABLE item_categories RENAME TO ic_hidden"))
    try:
        with engine.connect() as c:
            assert B.classify_new_items(c, rows) == {"skipped": "tables missing"}
        assert "su11a52_catalog.sql not applied" in capsys.readouterr().err
    finally:
        with engine.begin() as c:
            c.execute(text("ALTER TABLE ic_hidden RENAME TO item_categories"))


def test_fallback_names_sql(engine):
    import scripts.build_search_items as B
    from sqlalchemy import text
    with engine.begin() as c:
        c.execute(text("CREATE TABLE IF NOT EXISTS item_chain_names (item_code TEXT, chain_id TEXT, item_name TEXT, "
                       "manufacturer_name TEXT, PRIMARY KEY (item_code, chain_id))"))
        c.execute(text("DELETE FROM item_chain_names"))
        for code, ch, name in [("A1", "1", "סלמון טרי"), ("A1", "2", "סלמון טרי"), ("A1", "3", "סלמון"),
                               ("A2", "1", "  "), ("A3", "1", None)]:
            c.execute(text("INSERT INTO item_chain_names VALUES (:c, :ch, :n, NULL)"), {"c": code, "ch": ch, "n": name})
        c.execute(text("INSERT INTO gs1.products (gtin, product_status, group_name, trade_item_description) "
                       "VALUES ('A2', 'פעיל', 'Fish', 'דג פורל'), ('A3', 'לא פעיל', 'Fish', 'ישן')"))
    with engine.connect() as c:
        names, stats = B.read_fallback_names(c, ["A1", "A2", "A3"])
    assert names == {"A1": "סלמון טרי", "A2": "דג פורל"}
    assert stats == {"nameless": 3, "from_item_chain_names": 1, "from_gs1": 1, "still_nameless": 1}
