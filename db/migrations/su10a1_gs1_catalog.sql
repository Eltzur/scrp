-- SU10A-1: GS1 Israel catalog — phase 1 (basic fields only)
--
-- Isolated in its own `gs1` schema: nothing here touches the supermarket scraper
-- tables (items/prices/stores/city_canonical). Dropping this schema would leave
-- the rest of the database untouched.
--
-- full_content / full_content_fetched_at are created now but stay NULL until
-- phase 2 wires up the per-product detail fetch. The phase-1 upsert deliberately
-- does NOT write those columns, so re-running the sweep can never clobber them.
--
-- GRANTS (lesson from 9d-2): migrations run as the postgres superuser, but the
-- scraper and API connect as scrp_app. Any new object MUST be granted in this
-- same file or the app gets "permission denied for table ...". Schema-level
-- USAGE is required on top of the table grants, and ALTER DEFAULT PRIVILEGES
-- covers whatever phase 2 adds.

CREATE SCHEMA IF NOT EXISTS gs1;

CREATE TABLE IF NOT EXISTS gs1.products (
    -- GS1's own record id. TEXT rather than BIGINT on purpose: this is an
    -- external system's identifier and we have not yet seen a live payload to
    -- confirm it is always numeric. Cheap to tighten later; expensive to have
    -- the first production run abort on a non-numeric id.
    id                      TEXT PRIMARY KEY,
    product_code            TEXT NOT NULL UNIQUE,
    gtin                    TEXT,
    supplier_gln            TEXT,
    retailer_gln            TEXT,
    group_id                TEXT,
    group_name              TEXT,
    brandname               TEXT,
    trade_item_description  TEXT,
    product_status          TEXT,
    effective_date_time     TIMESTAMPTZ,
    discontinued_date_time  TIMESTAMPTZ,
    modification_timestamp  TIMESTAMPTZ,
    full_content            JSONB,          -- phase 2
    fetched_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    full_content_fetched_at TIMESTAMPTZ     -- phase 2
);

-- modification_timestamp drives the incremental watermark; gtin and
-- supplier_gln are the two lookup paths we expect downstream.
CREATE INDEX IF NOT EXISTS idx_gs1_products_modification_ts ON gs1.products (modification_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_gs1_products_gtin            ON gs1.products (gtin);
CREATE INDEX IF NOT EXISTS idx_gs1_products_supplier_gln    ON gs1.products (supplier_gln);

-- Partial index so phase 2 can cheaply find rows still needing a detail fetch.
CREATE INDEX IF NOT EXISTS idx_gs1_products_needs_full_content
    ON gs1.products (id) WHERE full_content IS NULL;

CREATE TABLE IF NOT EXISTS gs1.sync_runs (
    id                          SERIAL PRIMARY KEY,
    started_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at                TIMESTAMPTZ,
    rows_fetched                INTEGER NOT NULL DEFAULT 0,
    -- Watermark: the highest modification_timestamp actually observed in this
    -- run, NOT now(). Using now() would silently skip any row modified while
    -- the sweep was in flight.
    last_modification_timestamp TIMESTAMPTZ,
    status                      TEXT NOT NULL DEFAULT 'running'
                                CHECK (status IN ('running', 'ok', 'error'))
);

-- The next run reads the watermark from the most recent successful run.
CREATE INDEX IF NOT EXISTS idx_gs1_sync_runs_ok_started
    ON gs1.sync_runs (started_at DESC) WHERE status = 'ok';

-- ---------------------------------------------------------------------------
-- GRANTS — required, see header note.
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA gs1 TO scrp_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA gs1 TO scrp_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA gs1 TO scrp_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA gs1
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO scrp_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA gs1
    GRANT USAGE, SELECT ON SEQUENCES TO scrp_app;
