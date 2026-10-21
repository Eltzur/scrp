-- SU11A-47 — search speed: precomputed per-chain prices for search v2.
--
-- NOT APPLIED IN SU11A-47. ADDITIVE AND IDEMPOTENT. ONE TRANSACTION.
-- APPLY BEFORE deploying the SU11A-47 API. (The API also works without it: it
-- checks for the table and keeps the live price fetch while it is missing, and
-- the build skips it with one warning. Applying first just means the first
-- build after the deploy already fills it.)
--
-- search_item_prices: for every live search_items barcode, ONE row per chain =
-- the quote search v2 shows for that chain today (its cheapest branch by
-- effective price, promo applied), written by scripts/build_search_items.py
-- from the SAME SQL the live path runs (db.query._PRICE_SQL / _PROMO_ONLY_SQL /
-- _PROMO_PICK_SQL) with the same filters (shelf price > 0, live stores, Eilat
-- rule D2). An unfiltered v2 /search reads its page from here and feeds the rows
-- to the same db.query.group_by_product, so the JSON is the one the live fetch
-- builds - as of the last build.
--
-- Columns are exactly the row fields group_by_product reads for a v2 page
-- (address is not here: the API response does not carry it):
--   item_code, chain_id     one row per (barcode, chain)
--   ord                     position of the chain's first quote in the live row
--                           order (shelf quotes by item_price then store_fk,
--                           then promo-only quotes by store_fk). It fixes the
--                           order of names_per_chain, of equal-price quotes,
--                           and which chain's row names the product.
--   item_name ... city, store_fk   the winning row, as _PRICE_SQL /
--                           _PROMO_ONLY_SQL return it (same types)
--   item_price              NULL for a promo-only quote (no shelf price)
--   promo_unit_price        the promo picked for that row, as float8 (what the
--                           Python side converts it to anyway)
--   promo_end               text, as the live SQL formats it; the API falls back
--                           to the live fetch for a page whose winning promo has
--                           ended since the build
--   built_at                = search_items.built_at of the same build; the API
--                           uses this table only while the two are equal
--
-- STAGING TWIN search_item_prices_next, swapped with search_items in the SAME
-- short transaction as the SU11A-36 tables. Renaming needs ownership, so both
-- are OWNED BY scrp_app (the role in DATABASE_URL).
--
-- The primary key (item_code, chain_id) is the item_code index the page read
-- uses (item_code IN (...) ORDER BY item_code, ord). No separate item_code index:
-- it would duplicate the key's leading column.
--
-- /suggest needs no new index: EXPLAIN on a 132,755-row synthetic search_items
-- used the SU11A-36 trigram GIN indexes (and the lexicon key) for every query,
-- with no sequential scan.
--
-- Apply (postgres cannot read files under ~dude, so pipe it rather than psql -f):
--     cat ~/scrp/db/migrations/su11a47_search_prices.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
--
-- Rollback (deploy the pre-SU11A-47 API first, or the API simply falls back to
-- the live fetch once the table is gone):
--     -- BEGIN;
--     -- DROP TABLE IF EXISTS search_item_prices, search_item_prices_next;
--     -- COMMIT;

BEGIN;

CREATE TABLE IF NOT EXISTS search_item_prices (
    item_code             TEXT             NOT NULL,
    chain_id              TEXT             NOT NULL,
    ord                   SMALLINT         NOT NULL,
    item_name             TEXT,
    canonical_item_name   TEXT,
    manufacturer_name     TEXT,
    unit_of_measure       TEXT,
    is_weighted           INTEGER,
    item_price            DOUBLE PRECISION,
    unit_of_measure_price DOUBLE PRECISION,
    price_update_date     TEXT,
    chain_name            TEXT,
    store_id              TEXT,
    store_name            TEXT,
    city                  TEXT,
    store_fk              INTEGER          NOT NULL,
    promo_unit_price      DOUBLE PRECISION,
    promo_min_qty         NUMERIC,
    promo_description     TEXT,
    promo_end             TEXT,
    built_at              TIMESTAMPTZ      NOT NULL,
    CONSTRAINT search_item_prices_pkey PRIMARY KEY (item_code, chain_id)
);
CREATE TABLE IF NOT EXISTS search_item_prices_next (
    item_code             TEXT             NOT NULL,
    chain_id              TEXT             NOT NULL,
    ord                   SMALLINT         NOT NULL,
    item_name             TEXT,
    canonical_item_name   TEXT,
    manufacturer_name     TEXT,
    unit_of_measure       TEXT,
    is_weighted           INTEGER,
    item_price            DOUBLE PRECISION,
    unit_of_measure_price DOUBLE PRECISION,
    price_update_date     TEXT,
    chain_name            TEXT,
    store_id              TEXT,
    store_name            TEXT,
    city                  TEXT,
    store_fk              INTEGER          NOT NULL,
    promo_unit_price      DOUBLE PRECISION,
    promo_min_qty         NUMERIC,
    promo_description     TEXT,
    promo_end             TEXT,
    built_at              TIMESTAMPTZ      NOT NULL,
    CONSTRAINT search_item_prices_next_pkey PRIMARY KEY (item_code, chain_id)
);

-- GRANTS / OWNERSHIP (lesson from 9d-2): migrations run as the postgres
-- superuser; the API and the build connect as scrp_app. Ownership covers SELECT
-- for the API and TRUNCATE / INSERT / ANALYZE / RENAME for the build.
ALTER TABLE search_item_prices      OWNER TO scrp_app;
ALTER TABLE search_item_prices_next OWNER TO scrp_app;

COMMIT;
