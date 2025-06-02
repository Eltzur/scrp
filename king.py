import requests
import zipfile
import os
import xml.etree.ElementTree as ET
import csv
from datetime import datetime
from itertools import product

def download_file(url, filename):
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Could not download {url} (status {response.status_code})")
        return False
    with open(filename, "wb") as f:
        f.write(response.content)
    print(f"Downloaded: {filename}")
    return True

def extract_xml_from_zip(gz_filename):
    with zipfile.ZipFile(gz_filename, 'r') as zip_ref:
        for name in zip_ref.namelist():
            if name.endswith(".xml"):
                zip_ref.extract(name)
                return name
    return None

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
    return main_dict

def merge_promos(main_dict, promo_dict, branch_name):
    for code, promo_price in promo_dict.items():
        if code in main_dict:
            main_dict[code][f'promo_price_{branch_name}'] = promo_price
        else:
            main_dict[code] = {f'promo_price_{branch_name}': promo_price}
    return main_dict

def flag_lowest_prices(all_prices, branches):
    for code, row in all_prices.items():
        branch_prices = []
        price_type = {}  # branch -> 'promo' or 'regular'
        for branch, _ in branches:
            promo_price = row.get(f'promo_price_{branch}')
            reg_price = row.get(f'price_{branch}')
            val = None
            typ = None
            if promo_price is not None and promo_price not in ["", "None"]:
                try: 
                    val = float(promo_price)
                    typ = "promo"
                except: pass
            if (val is None or val == 0) and reg_price is not None and reg_price not in ["", "None"]:
                try: 
                    val = float(reg_price)
                    typ = "regular"
                except: pass
            if val is not None and val > 0:
                branch_prices.append((val, branch))
                price_type[branch] = typ
        if branch_prices:
            min_val = min(branch_prices, key=lambda t: t[0])[0]
            for val, branch in branch_prices:
                if val == min_val:
                    row[f'LOWEST_{branch}'] = "1"
                    row[f'lowest_type_{branch}'] = price_type.get(branch,"")
                else:
                    row[f'LOWEST_{branch}'] = ""
                    row[f'lowest_type_{branch}'] = ""

def find_latest_promo(branchcode, date_str, verbose=True):
    promo_minutes = [f"{h}{m:02d}" for h,m in product(['05','10'], range(30,40))]
    best_filedate, best_url = None, None
    for minute in promo_minutes:
        promo_filedate = f"{date_str}{minute}"
        url = f"https://kingstore.binaprojects.com/Download/PromoFull7290058108879-{branchcode}-{promo_filedate}.gz"
        resp = requests.head(url)
        if resp.status_code == 200:
            if verbose:
                print(f"  Found promo file for branch {branchcode} at {promo_filedate}")
            if best_filedate is None or promo_filedate > best_filedate:
                best_filedate, best_url = promo_filedate, url
    return best_filedate, best_url

if __name__ == "__main__":
    backup_dir = r'C:\scrp\kingDL'
    os.makedirs(backup_dir, exist_ok=True)

    dt = datetime.now()
    date_str = dt.strftime("%Y%m%d")
    times_to_try = ["0524", "1024"]

    branches = [
        ('Um-El-Fahem', '001'),
        ('Daburiya', '002'),
        ('Furidis', '003'),
        ('Kalanswa', '005'),
        ('Shefaraam', '006'),
        ('Sachnin', '007'),
        ('Beer Sheva', '008'),
        ('Tamra', '009'),
        ('Daliat El Carmel', '010'),
        ('Nazareth', '012'),
        ('Kassem', '013'),
        ('Haifa', '014'),
        ('Karmikel', '015'),
        ('Akko', '016'),
        ('Yafia', '017'),
        ('TLV-Yefet', '018'),
        ('Ramla', '019'),
        ('Basmat Tivon', '027'),
        ('Rahat', '028'),
        ('Nof Hagalil', '031'),
        ('Internet', '050'),
        ('Jerusalem', '200'),        
    ]
    
    feeds = []
    for name, branchcode in branches:
        found = False
        for t in times_to_try:
            filedate = f"{date_str}{t}"
            price_url = f"https://kingstore.binaprojects.com/Download/PriceFull7290058108879-{branchcode}-{filedate}.gz"
            resp = requests.head(price_url)
            if resp.status_code == 200:
                feeds.append((name, branchcode, filedate))
                print(f"Found price for {name} at {filedate}")
                found = True
                break
        if not found:
            print(f"WARNING: No price file found today for branch {name} ({branchcode})")
    
    all_prices = {}
    for branch_name, branchcode, filedate in feeds:
        gz_price = f"PriceFull7290058108879-{branchcode}-{filedate}.gz"
        url_price = f"https://kingstore.binaprojects.com/Download/PriceFull7290058108879-{branchcode}-{filedate}.gz"

        # Download and backup price file
        price_downloaded = download_file(url_price, gz_price)
        if price_downloaded:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            backup_path = os.path.join(backup_dir, f'{branch_name}_price_{timestamp}.gz')
            with open(gz_price, 'rb') as src, open(backup_path, 'wb') as dst:
                dst.write(src.read())
            print(f"Saved backup: {backup_path}")

            price_xml = extract_xml_from_zip(gz_price)
            if price_xml:
                data = parse_prices(price_xml, branch_name)
                merge_price_dicts(all_prices, data, branch_name)
                os.remove(price_xml)
            os.remove(gz_price)

        # Find and process the latest promo in time window
        promo_filedate, url_promo = find_latest_promo(branchcode, date_str)
        if promo_filedate and url_promo:
            gz_promo = f"PromoFull7290058108879-{branchcode}-{promo_filedate}.gz"
            promo_downloaded = download_file(url_promo, gz_promo)
            if promo_downloaded:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M")
                backup_path = os.path.join(backup_dir, f'{branch_name}_promo_{timestamp}.gz')
                with open(gz_promo, 'rb') as src, open(backup_path, 'wb') as dst:
                    dst.write(src.read())
                print(f"Saved backup: {backup_path}")
                promo_xml = extract_xml_from_zip(gz_promo)
                if promo_xml:
                    promos = parse_promos(promo_xml)
                    merge_promos(all_prices, promos, branch_name)
                    os.remove(promo_xml)
                os.remove(gz_promo)
        else:
            print(f"No promo file found for {branch_name} on {date_str}")

    # === FLAG LOWEST PRICES HERE ===
    flag_lowest_prices(all_prices, branches)

    # Build all columns for CSV
    columns = ['code', 'name']
    for branch, _ in branches:
        columns += [f'price_{branch}', f'price_per_pack_{branch}', f'promo_price_{branch}', f'LOWEST_{branch}', f'lowest_type_{branch}']

    with open('price_comparison.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for code, row in all_prices.items():
            row_out = {'code': code, 'name': row.get('name')}
            for col in columns:
                if col in row:
                    row_out[col] = row[col]
            writer.writerow(row_out)
    print("Saved to price_comparison.csv!")