-- PostgreSQL schema for the Israeli Price Comparison database.
-- Idempotent: safe to run multiple times (IF NOT EXISTS throughout).
-- Equivalent to db/schema.sql but with PG-native types.

CREATE TABLE IF NOT EXISTS chains (
    chain_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS stores (
    id           SERIAL PRIMARY KEY,
    chain_id     TEXT NOT NULL REFERENCES chains(chain_id),
    sub_chain_id TEXT NOT NULL,
    store_id     TEXT NOT NULL,
    store_name   TEXT,
    city         TEXT,
    city_norm    TEXT,
    address      TEXT,
    UNIQUE (chain_id, sub_chain_id, store_id)
);

CREATE TABLE IF NOT EXISTS items (
    item_code           TEXT PRIMARY KEY,
    item_type           INTEGER,
    item_name           TEXT,
    manufacturer_name   TEXT,
    manufacture_country TEXT,
    unit_qty            TEXT,
    quantity            DOUBLE PRECISION,
    is_weighted         INTEGER,
    unit_of_measure     TEXT,
    qty_in_package      INTEGER
);

CREATE TABLE IF NOT EXISTS prices (
    id                    SERIAL PRIMARY KEY,
    store_fk              INTEGER NOT NULL REFERENCES stores(id),
    item_code             TEXT NOT NULL,
    price_update_date     TEXT,
    item_price            DOUBLE PRECISION NOT NULL,
    unit_of_measure_price DOUBLE PRECISION,
    allow_discount        INTEGER,
    item_status           INTEGER,
    UNIQUE (store_fk, item_code)
);

CREATE TABLE IF NOT EXISTS fetch_runs (
    id              SERIAL PRIMARY KEY,
    chain_id        TEXT NOT NULL,
    run_at          TEXT NOT NULL,
    files_attempted INTEGER DEFAULT 0,
    files_loaded    INTEGER DEFAULT 0,
    items_inserted  INTEGER DEFAULT 0,
    status          TEXT
);

CREATE TABLE IF NOT EXISTS item_chain_names (
    item_code         TEXT NOT NULL,
    chain_id          TEXT NOT NULL,
    item_name         TEXT,
    manufacturer_name TEXT,
    PRIMARY KEY (item_code, chain_id),
    FOREIGN KEY (item_code) REFERENCES items(item_code),
    FOREIGN KEY (chain_id)  REFERENCES chains(chain_id)
);

CREATE INDEX IF NOT EXISTS idx_prices_item_code ON prices(item_code);
CREATE INDEX IF NOT EXISTS idx_items_name       ON items(item_name);
CREATE INDEX IF NOT EXISTS idx_stores_city_norm ON stores(city_norm);
CREATE INDEX IF NOT EXISTS idx_icn_item_name    ON item_chain_names(item_name);
CREATE INDEX IF NOT EXISTS idx_icn_mfr_name     ON item_chain_names(manufacturer_name);
