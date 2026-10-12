-- SU11A-36 — search v2: search_items (one row per live barcode) and search_lexicon.
--
-- NOT APPLIED IN SU11A-36. ADDITIVE AND IDEMPOTENT: new tables and indexes only;
-- nothing in items, prices, stores or promos is touched. Safe to apply before
-- the code is deployed (nothing reads these tables while SEARCH_V2 is off).
--
-- Filled by scripts/build_search_items.py --apply, never by hand.
--
-- STAGING TWINS (same columns, same indexes). The build fills search_items_next /
-- search_lexicon_next, then swaps names in ONE short transaction (tables, primary
-- keys and indexes; names stay attached to their role), so a
-- search never sees a half-built table. Renaming needs table ownership, so all
-- four tables are OWNED BY scrp_app (the role in DATABASE_URL that the API and
-- the build use). That also lets the build TRUNCATE and ANALYZE them. No CREATE
-- privilege on the schema is needed or granted.
--
-- NO FOREIGN KEY to items, deliberately (deviation from the SU11A-36 spec):
-- an FK would make every future DELETE on items check this table and fail while
-- a row still refers to the item, coupling the loader to a derived table. The
-- build only ever inserts item_codes it read from items in the same run.
--
-- pg_trgm 1.6 is already installed (SU11A-34 facts); IF NOT EXISTS is a no-op.
--
-- Apply (postgres cannot read files under ~dude, so pipe it rather than psql -f):
--     cat ~/scrp/db/migrations/su11a36_search_items.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
--
-- Rollback (only while SEARCH_V2 is off):
--     DROP TABLE search_items, search_items_next, search_lexicon, search_lexicon_next;

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- name_norm / manufacturer_norm: db/search_norm.normalize() of items.item_name /
--   items.manufacturer_name (the same columns the old search matches).
-- is_pseudo:   coupon pseudo-product (D1) - hidden from catalog search.
-- chains_live: distinct chains with a live quote, counted the way /search
--   counts chains_count (shelf price > 0 at a live store with an
--   item_chain_names row for that chain, or a promo-only quote at a live store).
-- stores_live: live stores with such a quote.
-- promo_only:  every live quote is promo-only (no shelf price anywhere).
-- popularity:  0 until SU11A-37 adds the counters (D3); carried over by rebuilds.
-- built_at:    one timestamp per build; the API falls back to the old search
--   when it is older than 48 hours.
CREATE TABLE IF NOT EXISTS search_items (
    item_code         TEXT        PRIMARY KEY,
    name_norm         TEXT        NOT NULL DEFAULT '',
    manufacturer_norm TEXT        NOT NULL DEFAULT '',
    is_pseudo         BOOLEAN     NOT NULL DEFAULT false,
    chains_live       SMALLINT    NOT NULL DEFAULT 0,
    stores_live       INTEGER     NOT NULL DEFAULT 0,
    promo_only        BOOLEAN     NOT NULL DEFAULT false,
    popularity        INTEGER     NOT NULL DEFAULT 0,
    built_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS search_items_next (
    item_code         TEXT        PRIMARY KEY,
    name_norm         TEXT        NOT NULL DEFAULT '',
    manufacturer_norm TEXT        NOT NULL DEFAULT '',
    is_pseudo         BOOLEAN     NOT NULL DEFAULT false,
    chains_live       SMALLINT    NOT NULL DEFAULT 0,
    stores_live       INTEGER     NOT NULL DEFAULT 0,
    promo_only        BOOLEAN     NOT NULL DEFAULT false,
    popularity        INTEGER     NOT NULL DEFAULT 0,
    built_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- kind: token (a word from item names / manufacturers, freq >= 3),
--       brand (a whole normalized manufacturer name, freq >= 3),
--       alias (data/brand_aliases.csv: term = normalized alias, canonical = the
--              catalog's Hebrew spelling, normalized).
-- freq: number of live items containing the term (aliases: of the canonical).
CREATE TABLE IF NOT EXISTS search_lexicon (
    term      TEXT    PRIMARY KEY,
    kind      TEXT    NOT NULL CHECK (kind IN ('token', 'brand', 'alias')),
    canonical TEXT    NOT NULL,
    freq      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS search_lexicon_next (
    term      TEXT    PRIMARY KEY,
    kind      TEXT    NOT NULL CHECK (kind IN ('token', 'brand', 'alias')),
    canonical TEXT    NOT NULL,
    freq      INTEGER NOT NULL DEFAULT 0
);

-- Trigram GIN: LIKE '%token%' and regex on names / manufacturers, similarity()
-- on lexicon terms. A btree for the ranking columns. The _next twins carry the
-- same indexes so a swap never leaves the live table without them.
CREATE INDEX IF NOT EXISTS idx_search_items_name_trgm      ON search_items      USING gin (name_norm gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_search_items_mfr_trgm       ON search_items      USING gin (manufacturer_norm gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_search_items_rank           ON search_items      (is_pseudo, popularity DESC, chains_live DESC, item_code);
CREATE INDEX IF NOT EXISTS idx_search_items_next_name_trgm ON search_items_next USING gin (name_norm gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_search_items_next_mfr_trgm  ON search_items_next USING gin (manufacturer_norm gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_search_items_next_rank      ON search_items_next (is_pseudo, popularity DESC, chains_live DESC, item_code);
CREATE INDEX IF NOT EXISTS idx_search_lexicon_term_trgm      ON search_lexicon      USING gin (term gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_search_lexicon_next_term_trgm ON search_lexicon_next USING gin (term gin_trgm_ops);

-- GRANTS / OWNERSHIP (lesson from 9d-2): migrations run as the postgres
-- superuser and the API connects as scrp_app. Ownership covers SELECT for the
-- API and TRUNCATE / INSERT / ANALYZE / RENAME for the build.
ALTER TABLE search_items        OWNER TO scrp_app;
ALTER TABLE search_items_next   OWNER TO scrp_app;
ALTER TABLE search_lexicon      OWNER TO scrp_app;
ALTER TABLE search_lexicon_next OWNER TO scrp_app;

COMMIT;
