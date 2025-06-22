import sqlite3
import csv
import os
import sys
from datetime import datetime

# === CONFIG ===
DB_FILE = "supermarket.db"
CSV_FILE = "victory_manual_prices.csv"  # or "price_comparison.csv"
CHAIN_NAME = "Victory"  # or "King"

# === LOAD CSV ===
def load_csv(filename):
    with open(filename, encoding="utf-8") as f:
        return list(csv.DictReader(f))

# === DB CONNECTION ===
def get_db():
    return sqlite3.connect(DB_FILE)

def ensure_chain_and_branch(conn, chain_name, branch_name, city=""):
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO chains (name) VALUES (?)", (chain_name,))
    conn.commit()
    cur.execute("SELECT id FROM chains WHERE name = ?", (chain_name,))
    chain_id = cur.fetchone()[0]

    cur.execute("INSERT OR IGNORE INTO branches (name, city, chain_id) VALUES (?, ?, ?)",
                (branch_name, city, chain_id))
    conn.commit()
    cur.execute("SELECT id FROM branches WHERE name = ?", (branch_name,))
    return cur.fetchone()[0]

def ensure_product(conn, code, name):
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO products (code, name) VALUES (?, ?)", (code, name))
    conn.commit()

def insert_price(conn, product_code, branch_id, price, promo, pack_price, is_lowest, lowest_type):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO prices (product_code, branch_id, date, price, promo_price, price_per_pack, is_lowest, lowest_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        product_code, branch_id,
        datetime.today().strftime("%Y-%m-%d"),
        price, promo, pack_price,
        is_lowest, lowest_type
    ))
    conn.commit()

# === MAIN LOADER ===
def load_data():
    data = load_csv(CSV_FILE)
    conn = get_db()
    cursor = conn.cursor()

    # Find all branch columns from CSV headers
    fieldnames = data[0].keys()
    branches = set()
    for name in fieldnames:
        if name.startswith("price_") and not name.startswith("price_per_pack_"):
            branch_name = name.replace("price_", "")
            branches.add(branch_name)

    print(f"Detected branches: {branches}")

    for row in data:
        code = row["code"]
        name = row["name"]
        ensure_product(conn, code, name)

        for branch in branches:
            branch_id = ensure_chain_and_branch(conn, CHAIN_NAME, branch)

            price = row.get(f"price_{branch}")
            promo = row.get(f"promo_price_{branch}")
            pack_price = row.get(f"price_per_pack_{branch}")
            is_lowest = row.get(f"LOWEST_{branch}", "") == "1"
            lowest_type = row.get(f"lowest_type_{branch}", "")

            # Convert empty strings to None
            price = float(price) if price and price != "None" else None
            promo = float(promo) if promo and promo != "None" else None
            pack_price = float(pack_price) if pack_price and pack_price != "None" else None

            insert_price(conn, code, branch_id, price, promo, pack_price, int(is_lowest), lowest_type)

    conn.close()
    print("✅ Data loaded into DB.")

if __name__ == "__main__":
    load_data()
