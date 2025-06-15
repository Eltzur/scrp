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
price_files = [
    {"branch": "91", "branch_name": "שוהם 91", "filename": "PriceFull7290696200003-091-202506140500-001"},
    {"branch": "45", "branch_name": "רעננה 45", "filename": "PriceFull7290696200003-045-202506140500-001"},
    {"branch": "47", "branch_name": "אופקים 47", "filename": "PriceFull7290696200003-047-202506140459-001"},
    {"branch": "44", "branch_name": "לינקולן תל אביב 44", "filename": "PriceFull7290696200003-044-202506140459-001"},
    {"branch": "41", "branch_name": "ברנע 41", "filename": "PriceFull7290696200003-041-202506140458-001"},
    # Add more as needed!
]

def download_file(filename, BASE_URL, DL_DIR):
    url = BASE_URL + filename + ".xml.gz"
    dest = os.path.join(DL_DIR, filename + ".xml.gz")
    if os.path.exists(dest):
        print(f"Already downloaded: {dest}")
        return dest
    print(f"Downloading {url} ...")
    r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"})
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

def merge_price_dicts(main_dict, new_dict, branch_name):
    for code, data in new_dict.items():
        if code not in main_dict:
            main_dict[code] = {'name': data['name']}
        for k, v in data.items():
            if k != "name":
                main_dict[code][k] = v

# ---- MAIN LOGIC ----

all_prices = {}
branch_names = []

for b in price_files:
    fname = b['filename']
    branch_name = b['branch_name']
    branch_names.append(branch_name)
    gz_file = download_file(fname, BASE_URL, DL_DIR)
    if gz_file:
        xml_file = extract_xml_from_gz(gz_file)
        if xml_file:
            data = parse_prices(xml_file, branch_name)
            merge_price_dicts(all_prices, data, branch_name)
            # Optionally uncomment the next line to clean up extracted XMLs after successful parse:
            # os.remove(xml_file)
        else:
            print(f"Could not extract XML from {gz_file}")
    else:
        print(f"Could not download file for {fname}")

# ---- OUTPUT TO CSV ----

columns = ["code", "name"]
for b in branch_names:
    columns.append(f"price_{b}")
    columns.append(f"price_per_pack_{b}")

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