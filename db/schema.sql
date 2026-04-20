CREATE TABLE IF NOT EXISTS chains (
    chain_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS stores (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id     TEXT NOT NULL REFERENCES chains(chain_id),
    sub_chain_id TEXT NOT NULL,
    store_id     TEXT NOT NULL,
    UNIQUE (chain_id, sub_chain_id, store_id)
);

CREATE TABLE IF NOT EXISTS items (
    item_code           TEXT PRIMARY KEY,
    item_type           INTEGER,
    item_name           TEXT,
    manufacturer_name   TEXT,
    manufacture_country TEXT,
    unit_qty            TEXT,
    quantity            REAL,
    is_weighted         INTEGER,
    unit_of_measure     TEXT,
    qty_in_package      INTEGER
);

CREATE TABLE IF NOT EXISTS prices (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    store_fk              INTEGER NOT NULL REFERENCES stores(id),
    item_code             TEXT NOT NULL,
    price_update_date     TEXT,
    item_price            REAL NOT NULL,
    unit_of_measure_price REAL,
    allow_discount        INTEGER,
    item_status           INTEGER,
    UNIQUE (store_fk, item_code)
);

CREATE INDEX IF NOT EXISTS idx_prices_item_code ON prices(item_code);
CREATE INDEX IF NOT EXISTS idx_items_name       ON items(item_name);
