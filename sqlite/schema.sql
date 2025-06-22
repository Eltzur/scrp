-- Supermarket Chains
CREATE TABLE IF NOT EXISTS chains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
);

-- Store Branches
CREATE TABLE IF NOT EXISTS branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    city TEXT,
    chain_id INTEGER,
    FOREIGN KEY (chain_id) REFERENCES chains(id)
);

-- Products
CREATE TABLE IF NOT EXISTS products (
    code TEXT PRIMARY KEY,
    name TEXT
);

-- Prices per branch per day
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code TEXT,
    branch_id INTEGER,
    date TEXT,
    price REAL,
    promo_price REAL,
    price_per_pack REAL,
    is_lowest INTEGER DEFAULT 0,
    lowest_type TEXT,
    FOREIGN KEY (product_code) REFERENCES products(code),
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);
