import gzip
import os
import xml.etree.ElementTree as ET
import csv
from datetime import datetime
import re
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from collections import defaultdict

VICTORY_CHAIN = "7290696200003"
VICTORY_URL = f"https://laibcatalog.co.il/CompetitionRegulationsFiles/latest/{VICTORY_CHAIN}/"
VICTORY_DL_DIR = "victoryfiles"
os.makedirs(VICTORY_DL_DIR, exist_ok=True)

def fetch_file_list():
    print("Launching browser to fetch file list from", VICTORY_URL)
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    driver.get(VICTORY_URL)
    import time
    time.sleep(10)  # Wait for JS/AJAX if any
    html = driver.page_source
    with open("scraped_source.html", "w", encoding="utf-8") as f:
        f.write(html)
    driver.quit()
    soup = BeautifulSoup(html, "html.parser")
    # Find the actual table of downloads
    rows = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) >= 8:
            # Build a row as a list (adjust indices per layout if needed)
            row = [td.get_text(strip=True) for td in tds[:-1]]
            # Filename extraction from download link/button
            href = tr.find("a")
            if href and "href" in href.attrs:
                # Remove .xml.gz if present
                fname_base = href["href"].replace(".xml.gz", "").replace(".gz", "")
                # Add filename prefix (this matches site)
                row.insert(0, fname_base)
                rows.append(row)
    return rows

def extract_fileinfo(row):
    """
    Parse filename type, branch_code, date, time from filename.
    """
    # Example: 'PromoFull7290696200003-091-202506010501-001'
    fname = row[0]
    m = re.match(r'(PriceFull|PromoFull)7290696200003-(\d{3})-(\d{8})(\d{4})-001', fname)
    if not m:
        return None
    typ, branch_code, date, time = m.group(1), m.group(2), m.group(3), m.group(4)
    return {'type': typ, 'branch_code': branch_code, 'date': date, 'time': time, 'file': fname}

def is_valid_gzip(path):
    try:
        with open(path, "rb") as f:
            return f.read(2) == b'\x1f\x8b'
    except:
        return False

def download_file(filename):
    url = VICTORY_URL + filename + ".xml.gz"
    dest_path = os.path.join(VICTORY_DL_DIR, filename + ".xml.gz")
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if resp.status_code == 200:
        with open(dest_path, "wb") as f:
            f.write(resp.content)
        if is_valid_gzip(dest_path):
            print(f"Downloaded: {filename} (valid gzip)")
            return dest_path
        else:
            print(f"Downloaded but NOT valid gzip: {filename} (removing!)")
            os.remove(dest_path)
            return None
    print(f"FAILED: {url}")
    return None

def extract_gz(gz_fname):
    xml_fname = gz_fname[:-3]
    with gzip.open(gz_fname, 'rb') as f_in, open(xml_fname, 'wb') as f_out:
        f_out.write(f_in.read())
    return xml_fname

def parse_prices(xml_filename, branch_name):
    tree = ET.parse(xml_filename)
    root = tree.getroot()
    results = {}
    for item in root.findall('.//Item'):
        code = item.findtext('ItemCode')
        name = item.findtext('ItemNm')
        price_raw = item.findtext('ItemPrice')
        qty_in_package = item.findtext('QtyInPackage', '1')
        try:
            price_per_pack = float(price_raw) * float(qty_in_package)
        except:
            price_per_pack = None
        results[code] = {
            'name': name,
            f'price_{branch_name}': price_raw,
            f'price_per_pack_{branch_name}': price_per_pack
        }
    return results

def parse_promos(xml_filename):
    promos = {}
    tree = ET.parse(xml_filename)
    root = tree.getroot()
    for promo in root.findall('.//Promotion'):
        promo_price = promo.findtext('DiscountedPrice')
        items = promo.find('PromotionItems')
        if items is not None:
            for item in items.findall('Item'):
                code = item.findtext('ItemCode')
                if code and promo_price:
                    promos[code] = promo_price
    return promos

def merge_price_dicts(main_dict, new_dict, branch_name):
    for code, data in new_dict.items():
        if code not in main_dict:
            main_dict[code] = {'name': data['name']}
        main_dict[code][f'price_{branch_name}'] = data[f'price_{branch_name}']
        main_dict[code][f'price_per_pack_{branch_name}'] = data[f'price_per_pack_{branch_name}']

def merge_promos(main_dict, promo_dict, branch_name):
    for code, promo_price in promo_dict.items():
        if code in main_dict:
            main_dict[code][f'promo_price_{branch_name}'] = promo_price
        else:
            main_dict[code] = {f'promo_price_{branch_name}': promo_price}

if __name__ == "__main__":
    target_date = datetime.now().strftime("%Y%m%d")
    rows = fetch_file_list()  # Each row: [filename, ...]
    # Build a dict: latest_per_branch[branch_code]['price'|'promo'] = (datetime: YYYYMMDDHHMM, filename)
    latest_per_branch = defaultdict(dict)
    branch_code_to_name = {}  # optional map

    for row in rows:
        info = extract_fileinfo(row)
        if not info:
            continue
        if info['date'] != target_date:
            continue
        key = info['branch_code']
        branch_code_to_name[key] = row[2]  # Store branch name (from scraped table)
        typ = 'price' if info['type'] == 'PriceFull' else 'promo'
        dtstr = info['date'] + info['time']
        if typ not in latest_per_branch[key] or dtstr > latest_per_branch[key][typ][0]:
            latest_per_branch[key][typ] = (dtstr, info['file'])

    all_prices = {}

    # Download, extract, parse latest PriceFull and PromoFull for each branch
    for branch_code in latest_per_branch:
        branch_name = branch_code_to_name.get(branch_code, branch_code)
        for typ in ['price', 'promo']:
            if typ in latest_per_branch[branch_code]:
                dtstr, filebase = latest_per_branch[branch_code][typ]
                print(f"Processing: {typ} file {filebase} for branch {branch_code} ({branch_name})")
                gz_file = download_file(filebase)
                if gz_file:
                    try:
                        xml_file = extract_gz(gz_file)
                        if typ == 'price':
                            data = parse_prices(xml_file, branch_name)
                            merge_price_dicts(all_prices, data, branch_name)
                        else:
                            promos = parse_promos(xml_file)
                            merge_promos(all_prices, promos, branch_name)
                        os.remove(xml_file)
                    except Exception as e:
                        print(f"Extraction/parsing error {filebase}: {e}")
                    os.remove(gz_file)
    print("Parsing complete.")

    # Save to CSV
    # Build all columns (gather all branch names we saw)
    all_branch_names = set()
    for bname in branch_code_to_name.values():
        all_branch_names.add(bname)
    columns = ['code', 'name']
    for b in sorted(all_branch_names):
        columns += [
            f'price_{b}',
            f'price_per_pack_{b}',
            f'promo_price_{b}'
        ]

    with open('victory_price_comparison.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for code, row in all_prices.items():
            row_out = {'code': code, 'name': row.get('name')}
            for col in columns:
                if col in row:
                    row_out[col] = row[col]
            writer.writerow(row_out)
    print("Saved to victory_price_comparison.csv!")
