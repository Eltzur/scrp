-- SU10A-5: formalize the `promos` table as a versioned migration.
--
-- The table has existed in production since 9d-9 but was only ever created
-- ad-hoc by db/db.py::init_db(), so there was no migration to review, no
-- documented GRANT, and nothing to reproduce it in a fresh environment. This
-- file records the schema that is ALREADY LIVE — it does not change it.
--
-- NON-DESTRUCTIVE BY CONSTRUCTION. Every statement is IF NOT EXISTS, so running
-- this against the production database is a no-op: the live table (currently
-- ~560K rows across all 14 chains) is left exactly as it is. There is
-- deliberately no DROP and no ALTER anywhere in this file. If the schema ever
-- needs to change, that belongs in a new migration, not in edits to this one.
--
-- GRANTS (lesson from 9d-2): migrations run as the postgres superuser, but the
-- scraper and API connect as scrp_app, so any object must be granted in the
-- same file or the app gets "permission denied for table ...". The sequence
-- grant matters as much as the table grant — INSERT fails without USAGE on the
-- SERIAL sequence. Verified in SU10A-5: scrp_app already holds all of these on
-- the live table, so these statements are a no-op there and exist for fresh
-- environments. GRANT is idempotent, hence no IF NOT EXISTS guard.

CREATE TABLE IF NOT EXISTS promos (
    id                       SERIAL PRIMARY KEY,
    -- References stores.id (the surrogate PK), NOT stores.store_id (the
    -- chain's own branch code). Same trap as the city_canonical CSV: the two
    -- are easy to confuse and a join on the wrong one silently returns nothing.
    store_fk                 INTEGER NOT NULL
                                 REFERENCES stores(id) ON DELETE CASCADE,
    item_code                TEXT NOT NULL,
    promo_id                 TEXT,
    promo_description        TEXT,
    -- Source DiscountType. NULL for every row written before SU10A-5: the
    -- original shared parser never emitted it. The flat-variant parser does.
    promo_type               INTEGER,
    allow_multiple_discounts BOOLEAN,
    -- Raw MinQty. NOT always a unit count — Rami Levy publishes a minimum
    -- SPEND here (5990 = 59.90 ILS), so dividing discount_price by it blindly
    -- manufactures ~100% discounts. The read path guards with a 1..24 window.
    min_qty                  NUMERIC,
    reward_type              INTEGER,
    -- Raw DiscountRate. Scale is portal-specific: Hazi Hinam publishes basis
    -- points (5000 = 50%), others a plain percent. Stored raw on purpose and
    -- normalized in db/query.py so the scale stays fixable without re-scraping.
    discount_rate            NUMERIC,
    -- Raw DiscountedPrice — a BUNDLE TOTAL for min_qty items, not a unit price.
    discount_price           NUMERIC,
    min_purchase_amount      NUMERIC,
    promo_start              TIMESTAMP,
    promo_end                TIMESTAMP,
    created_at               TIMESTAMP DEFAULT NOW(),
    -- One row per (store, item, promo). This is what makes the ingest an
    -- upsert and why duplicate rows are structurally impossible — the large
    -- row counts are legitimate per-store fan-out, not duplication.
    UNIQUE (store_fk, item_code, promo_id)
);

CREATE INDEX IF NOT EXISTS idx_promos_store_fk  ON promos(store_fk);
CREATE INDEX IF NOT EXISTS idx_promos_item_code ON promos(item_code);

GRANT SELECT, INSERT, UPDATE, DELETE ON promos TO scrp_app;
GRANT USAGE, SELECT ON SEQUENCE promos_id_seq TO scrp_app;
