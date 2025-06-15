import requests
import gzip
import os
import xml.etree.ElementTree as ET
import csv

# ---- SETTINGS ----

VICTORY_CHAIN = "7290696200003"
BASE_URL = f"https://laibcatalog.co.il/CompetitionRegulationsFiles/latest/{VICTORY_CHAIN}/"
DL_DIR = "victory_manual_files"
os.makedirs(DL_DIR, exist_ok=True)

# ---- YOUR FILES AND BRANCHES ----
branches = [
    {
        "branch": "91",
        "branch_name": "שוהם 91",
        "price_filename": "PriceFull7290696200003-091-202506140500-001",
        "promo_filename": "PromoFull7290696200003-091-202506140500-001",
    },
    {
        "branch": "45",
        "branch_name": "רעננה 45",
        "price_filename": "PriceFull7290696200003-045-202506140500-001",
        "promo_filename": "PromoFull7290696200003-045-202506140500-001",
    },
    {
        "branch": "47",
        "branch_name": "אופקים 47",
        "price_filename": "PriceFull7290696200003-047-202506140459-001",
        "promo_filename": "PromoFull7290696200003-047-202506140459-001",
    },
    {
        "branch": "44",
        "branch_name": "לינקולן תל אביב 44",
        "price_filename": "PriceFull7290696200003-044-202506140459-001",
        "promo_filename": "PromoFull7290696200003-044-202506140459-001",
    },
    {
        "branch": "41",
        "branch_name": "ברנע 41",
        "price_filename": "PriceFull7290696200003-041-202506140458-001",
        "promo_filename": "PromoFull7290696200003-041-202506140458-001",
    },
    # Add more as needed!
]

def download_file(filename, BASE_URL, DL_DIR):
    url = BASE_URL + filename + ".xml.gz"
    dest = os.path.join(DL_DIR, filename + ".xml.gz")
    if os.path.exists(dest):
        print(f"Already downloaded: {dest}")
        return dest
    print(f"Downloading {url} ...")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code == 200:
        with open(dest, "wb") as f:
            f.write(r.content)
        with open(dest, "rb") as f:
            if f.read(2) != b'\x1f\x8b':
                print("ERROR: Not a valid GZIP archive:", dest)
                os.remove(dest)
                return None
        return dest
    else:
        print(f"Download failed: {url} ({r.status_code})")
        return None

def extract_xml_from_gz(gz_filename):
    xml_filename = gz_filename[:-3]
    with gzip.open(gz_filename, 'rb') as fin, open(xml_filename, 'wb') as fout:
        fout.write(fin.read())
    print(f"Extracted: {xml_filename}")
    return xml_filename

def parse_prices(xml_filename, branch_name):
    tree = ET.parse(xml_filename)
    root = tree.getroot()
    results = {}
    for product in root.findall('.//Product'):
        code = product.findtext('ItemCode')
        name = product.findtext('ItemName')
        price_raw = product.findtext('ItemPrice')
        qty = product.findtext('QtyInPackage', '1')
        try:
            price_per_pack = float(price_raw) * float(qty)
        except:
            price_per_pack = None
        results[code] = {
            'name': name,
            f'price_{branch_name}': price_raw,
            f'price_per_pack_{branch_name}': price_per_pack,
        }
    print(f"Parsed {len(results)} items from {xml_filename}")
    return results

def parse_promos(xml_filename):
    tree = ET.parse(xml_filename)
    root = tree.getroot()
    promos = {}
    # Find all <Sale> nodes under <Sales>
    for sale in root.findall('.//Sale'):
        code = sale.findtext('ItemCode')
        promo_price = sale.findtext('DiscountedPrice')
        if code and promo_price is not None:
            promos[code] = promo_price
    print(f"Parsed {len(promos)} promo items from {xml_filename}")
    return promos

def merge_price_dicts(main_dict, new_dict, branch_name):
    for code, data in new_dict.items():
        if code not in main_dict:
            main_dict[code] = {'name': data['name']}
        for k, v in data.items():
            if k != "name":
                main_dict[code][k] = v

def merge_promos(main_dict, promo_dict, branch_name):
    for code, promo_price in promo_dict.items():
        if code not in main_dict:
            main_dict[code] = {'name': ''}
        main_dict[code][f'promo_price_{branch_name}'] = promo_price

# ---- MAIN LOGIC ----

all_prices = {}
branch_names = []

for b in branches:
    branch_name = b['branch_name']
    branch_names.append(branch_name)
    # --- PRICE ---
    price_gz_file = download_file(b['price_filename'], BASE_URL, DL_DIR)
    if price_gz_file:
        price_xml = extract_xml_from_gz(price_gz_file)
        if price_xml:
            data = parse_prices(price_xml, branch_name)
            merge_price_dicts(all_prices, data, branch_name)
    # --- PROMO ---
    promo_gz_file = download_file(b['promo_filename'], BASE_URL, DL_DIR)
    if promo_gz_file:
        promo_xml = extract_xml_from_gz(promo_gz_file)
        if promo_xml:
            promo_data = parse_promos(promo_xml)
            merge_promos(all_prices, promo_data, branch_name)

# ---- OUTPUT TO CSV ----

columns = ["code", "name"]
for b in branch_names:
    columns.append(f"price_{b}")
    columns.append(f"price_per_pack_{b}")
    columns.append(f"promo_price_{b}")

with open("victory_manual_prices.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=columns)
    w.writeheader()
    for code, row in all_prices.items():
        out = {"code": code, "name": row.get("name", "")}
        for col in columns:
            if col in row:
                out[col] = row[col]
        w.writerow(out)

print("\nDone! Results in victory_manual_prices.csv")