import requests
import os
import xml.etree.ElementTree as ET
import sqlite3
from bs4 import BeautifulSoup

BASE_URL = "https://prices.shufersal.co.il/"

def get_available_shufersal_files():
    import re
    index_url = "https://prices.shufersal.co.il/?sort=Name&sortdir=ASC"
    print(f"Fetching directory listing from: {index_url}")
    resp = requests.get(index_url)
    resp.raise_for_status()
    print(resp.text[:2000])  # <--- Add this line
    file_names = re.findall(r'Price7290027600007-[\d-]+\.xml', resp.text)
    print(f"Found {len(file_names)} price files to process.")
    return file_names

def download_file(url, target_path):
    print(f"  Downloading {url} ...")
    response = requests.get(url, stream=True)
    if response.status_code == 404:
        print(f"  File not found: {url}")
        return False
    response.raise_for_status()
    with open(target_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"  Saved to {target_path}")
    return True

def parse_xml(xml_path):
    print(f"  Parsing {xml_path} ...")
    tree = ET.parse(xml_path)
    root = tree.getroot()
    items = []
    # try both Item and Product for possible XML formats
    for item in root.findall('.//Item'):
        code = item.findtext('ItemCode')
        name = item.findtext('ItemName')
        price = item.findtext('ItemPrice')
        if code and name and price:
            try:
                items.append({
                    'code': code,
                    'name': name,
                    'price': float(price)
                })
            except ValueError:
                continue
    return items

def upsert_items(db_path, items):
    print(f"  Updating database {db_path} ...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            code TEXT PRIMARY KEY,
            name TEXT,
            price REAL
        )
    ''')
    for item in items:
        c.execute('''
            INSERT OR REPLACE INTO products (code, name, price)
            VALUES (?, ?, ?)
        ''', (item['code'], item['name'], item['price']))
    conn.commit()
    conn.close()
    print("  Database updated.")

def process_shufersal_file(file_name):
    xml_url = f"{BASE_URL}{file_name}"
    local_xml_path = file_name
    db_path = "shufersal_prices.db"

    if not download_file(xml_url, local_xml_path):
        return

    items = parse_xml(local_xml_path)
    upsert_items(db_path, items)
    os.remove(local_xml_path)

if __name__ == "__main__":
    file_names = get_available_shufersal_files()
    for file_name in file_names:
        try:
            print(f"Processing {file_name}")
            process_shufersal_file(file_name)
        except Exception as e:
            print(f"Error processing {file_name}: {e}")