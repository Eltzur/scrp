-- SU11A-52 — catalog categories v1: categories, item_categories, item_attributes.
--
-- NOT APPLIED IN SU11A-52. ADDITIVE AND IDEMPOTENT. ONE TRANSACTION.
-- Nothing reads these tables yet: no API, web or mobile code uses them, so the
-- file can be applied at any time. Filled by scripts/catalog/import_categories.py
-- (taxonomy + labels, dry run by default) and, for NEW live barcodes only, by
-- scripts/build_search_items.py --apply (rule / gs1 rows; it skips with one
-- warning while these tables are missing).
--
-- Contents:
--   categories        the taxonomy (docs/catalog/taxonomy_v1.csv): one row per
--                     department / category / sub-type. attributes = the filter
--                     attributes the node offers, INHERITED from its ancestors
--                     (what a facet list for that node shows).
--   item_categories   one primary category per barcode, with confidence, source
--                     and provenance (detail = rule keyword / GS1 group / AI reason;
--                     model = AI model id, NULL otherwise).
--   item_attributes   parsed attributes per barcode (size, pack count, fat %, kosher
--                     level, brand, ...): value_text or value_num (+ unit).
--
-- PRECEDENCE (enforced in scripts/catalog/store.py, in Python and in the upsert's
-- ON CONFLICT ... WHERE): manual > ai > gs1 > rule. An automated run never
-- overwrites a manual row, never downgrades a row to a lower source, and never
-- touches a row with reviewed = true. No triggers: the writers enforce it.
--
-- NO FOREIGN KEY from item_categories / item_attributes to items (as in
-- su11a36_search_items.sql): an FK would couple the price loader's deletes to a
-- derived table. item_categories.category_id DOES reference categories(id):
-- a label must name a node of the taxonomy. Retired nodes stay with
-- active = false (ids are never reused or renumbered).
--
-- OWNER scrp_app (the role in DATABASE_URL): the import and the build write
-- with it; ownership also lets them ANALYZE.
--
-- Apply (postgres cannot read files under ~dude, so pipe it rather than psql -f):
--     cat ~/scrp/db/migrations/su11a52_catalog.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1

BEGIN;

CREATE TABLE IF NOT EXISTS categories (
    id               TEXT        PRIMARY KEY,                 -- D07, D07.C20, D02.C01.S01
    parent_id        TEXT        NULL REFERENCES categories(id),
    level            SMALLINT    NOT NULL CHECK (level IN (1, 2, 3)),  -- department / category / sub-type
    name_he          TEXT        NOT NULL,
    name_en          TEXT        NOT NULL DEFAULT '',
    sort_order       INTEGER     NOT NULL DEFAULT 0,
    attributes       TEXT[]      NOT NULL DEFAULT '{}',
    active           BOOLEAN     NOT NULL DEFAULT true,
    taxonomy_version TEXT        NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories (parent_id);

CREATE TABLE IF NOT EXISTS item_categories (
    item_code        TEXT        PRIMARY KEY,
    category_id      TEXT        NOT NULL REFERENCES categories(id),
    confidence       TEXT        NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
    source           TEXT        NOT NULL CHECK (source IN ('rule', 'gs1', 'ai', 'manual')),
    detail           TEXT        NULL,
    model            TEXT        NULL,
    taxonomy_version TEXT        NOT NULL,
    decided_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed         BOOLEAN     NOT NULL DEFAULT false
);
-- Facet counts and "items in category X": by category, then confidence.
CREATE INDEX IF NOT EXISTS idx_item_categories_category ON item_categories (category_id, confidence);

CREATE TABLE IF NOT EXISTS item_attributes (
    item_code        TEXT        NOT NULL,
    attr_key         TEXT        NOT NULL,
    value_text       TEXT        NULL,
    value_num        NUMERIC     NULL,
    unit             TEXT        NULL,
    source           TEXT        NOT NULL CHECK (source IN ('rule', 'gs1', 'ai', 'manual')),
    PRIMARY KEY (item_code, attr_key)
);
-- Facet values per attribute ("all kosher levels", "sizes between ...").
CREATE INDEX IF NOT EXISTS idx_item_attributes_key ON item_attributes (attr_key, value_text, value_num);

ALTER TABLE categories      OWNER TO scrp_app;
ALTER TABLE item_categories OWNER TO scrp_app;
ALTER TABLE item_attributes OWNER TO scrp_app;

COMMIT;

-- ---------------------------------------------------------------------------
-- ROLLBACK (manual; NOT part of the migration). Nothing in the API reads these
-- tables, so they can be dropped at any time; build_search_items then skips its
-- category step with one warning.
-- ---------------------------------------------------------------------------
-- BEGIN;
-- DROP TABLE IF EXISTS item_attributes;
-- DROP TABLE IF EXISTS item_categories;
-- DROP TABLE IF EXISTS categories;
-- COMMIT;
