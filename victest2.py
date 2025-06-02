import requests, os, gzip, xml.etree.ElementTree as ET, csv
from datetime import datetime

VICTORY_CHAIN = "7290696200003"
BASE_URL = f"https://laibcatalog.co.il/CompetitionRegulationsFiles/latest/{VICTORY_CHAIN}/"
DL_DIR = "victory_full_reports"
os.makedirs(DL_DIR, exist_ok=True)
TODAY = datetime.now().strftime("%Y%m%d")

branches = [
    {"branch_code":"001", "branch_name":"גן-יבנה ויקטורי 1"},
    {"branch_code":"002", "branch_name":"גדרה 2"},
    {"branch_code":"003", "branch_name":"שדרות 3"},
    {"branch_code":"005", "branch_name":"אורנית 5"},
    {"branch_code":"007", "branch_name":"(unknown)"},
    {"branch_code":"008", "branch_name":"אשדוד 8"},
    {"branch_code":"009", "branch_name":"הארבעה 9"},
    {"branch_code":"010", "branch_name":"לוד 10"},
    {"branch_code":"014", "branch_name":"בית שמש 14"},
    {"branch_code":"016", "branch_name":"פלורנטין 16"},
    {"branch_code":"021", "branch_name":"רמלה 21"},
    {"branch_code":"022", "branch_name":"חדרה 22"},
    {"branch_code":"023", "branch_name":"ראשל\"צ פרס נובל 23"},
    {"branch_code":"024", "branch_name":"קניון לב חדרה 24"},
    {"branch_code":"025", "branch_name":"עכו 25"},
    {"branch_code":"026", "branch_name":"ראש העין 26"},
    {"branch_code":"027", "branch_name":"שער עליה חיפה 27"},
    {"branch_code":"028", "branch_name":"גני תקווה 28"},
    {"branch_code":"029", "branch_name":"רמת גן 29"},
    {"branch_code":"030", "branch_name":"אלקנה 30"},
    {"branch_code":"031", "branch_name":"רוטשילד 31"},
    {"branch_code":"034", "branch_name":"מוצקין 34"},
    {"branch_code":"035", "branch_name":"אחד העם 35"},
    {"branch_code":"037", "branch_name":"קניון אשדוד 37"},
    {"branch_code":"038", "branch_name":"מבשרת 38"},
    {"branch_code":"039", "branch_name":"קוגל 39"},
    {"branch_code":"041", "branch_name":"ברנע 41"},
    {"branch_code":"044", "branch_name":"לינקולן תל אביב 44"},
    {"branch_code":"045", "branch_name":"רעננה 45"},
    {"branch_code":"046", "branch_name":"דימונה 46"},
    {"branch_code":"047", "branch_name":"אופקים 47"},
    {"branch_code":"048", "branch_name":"טירת הכרמל 48"},
    {"branch_code":"050", "branch_name":"תל מונד 50"},
    {"branch_code":"051", "branch_name":"מודעין 51"},
    {"branch_code":"052", "branch_name":"אשקלון 52"},
    {"branch_code":"053", "branch_name":"רמת ישי 53"},
    {"branch_code":"054", "branch_name":"קרית מלאכי 54"},
    {"branch_code":"055", "branch_name":"קרית גת 55"},
    {"branch_code":"056", "branch_name":"יבנה 56"},
    {"branch_code":"057", "branch_name":"מרגוזה 57"},
    {"branch_code":"058", "branch_name":"כפר יונה 58"},
    {"branch_code":"059", "branch_name":"עפולה 59"},
    {"branch_code":"060", "branch_name":"התנאים 60"},
    {"branch_code":"067", "branch_name":"יהודה הלוי 67"},
    {"branch_code":"068", "branch_name":"באר שבע 68"},
    {"branch_code":"069", "branch_name":"רעננה אחוזה 69"},
    {"branch_code":"070", "branch_name":"צור יצחק70"},
    {"branch_code":"071", "branch_name":"ראשון לציון מזרח 71"},
    {"branch_code":"073", "branch_name":"בית שאן 73"},
    {"branch_code":"074", "branch_name":"שבעת הכוכבים 74"},
    {"branch_code":"075", "branch_name":"וייצמן 75"},
    {"branch_code":"077", "branch_name":"לוד נתב\"ג 77"},
    {"branch_code":"079", "branch_name":"כ\"ס הירוקה 79"},
    {"branch_code":"080", "branch_name":"אלנבי 80"},
    {"branch_code":"081", "branch_name":"ראש העין פארק אפק 81"},
    {"branch_code":"082", "branch_name":"סיטי נס ציונה 82"},
    {"branch_code":"083", "branch_name":"רחובות 83"},
    {"branch_code":"084", "branch_name":"עמק חפר 84"},
    {"branch_code":"086", "branch_name":"טבעון 86"},
    {"branch_code":"087", "branch_name":"צמח 87"},
    {"branch_code":"088", "branch_name":"קניון איילון 88"},
    {"branch_code":"089", "branch_name":"ירושלים מלחה 89"},
    {"branch_code":"090", "branch_name":"נתניה 90"},
    {"branch_code":"091", "branch_name":"שוהם 91"},
    {"branch_code":"092", "branch_name":"נתיבות 92"},
    {"branch_code":"093", "branch_name":"חריש 93"},
    {"branch_code":"094", "branch_name":"שמוטקין 94"},
    {"branch_code":"095", "branch_name":"אשקלון בן גוריון 95"},
    {"branch_code":"096", "branch_name":"קריית אתא 96"},
    {"branch_code":"097", "branch_name":"אינטרנט 97"},
]

def find_latest_file(branch_code, ftype):
    common_times = [
        "2350", "2300", "1700", "1200", "0700", "0500", "0000"
    ]
    for t in common_times:
        fn = f"{ftype}{VICTORY_CHAIN}-{branch_code}-{TODAY}{t}-001"
        url = BASE_URL + fn + ".xml.gz"
        resp = requests.head(url, headers={"User-Agent":"Mozilla/5.0"})
        if resp.status_code == 200:
            return fn
    return None

def download_file(filename):
    url = BASE_URL + filename + ".xml.gz"
    dest = os.path.join(DL_DIR, filename + ".xml.gz")
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if resp.status_code == 200:
        with open(dest, "wb") as f:
            f.write(resp.content)
        # Check gzipped magic
        with open(dest, "rb") as f:
            sig = f.read(2)
        if sig != b'\x1f\x8b':
            print(f"  Not a real gzip at {filename}, skipping.")
            os.remove(dest)
            return None
        return dest
    return None

# ... rest of your code unchanged ...

def extract_gz(gz_fname):
    xml_fname = gz_fname[:-3]
    with gzip.open(gz_fname, 'rb') as f_in, open(xml_fname, 'wb') as f_out:
        f_out.write(f_in.read())
    return xml_fname

def parse_prices(xml_filename, branch_name):
    root = ET.parse(xml_filename).getroot()
    results = {}
    for item in root.findall('.//Item'):
        code = item.findtext('ItemCode')
        name = item.findtext('ItemNm')
        price_raw = item.findtext('ItemPrice')
        qty = item.findtext('QtyInPackage', '1')
        try:
            price_per = float(price_raw) * float(qty)
        except: price_per = None
        results[code] = {'name': name, f'price_{branch_name}': price_raw, f'price_per_pack_{branch_name}': price_per}
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
        for k, v in data.items():
            if k != "name":
                main_dict[code][k] = v

def merge_promos(main_dict, promo_dict, branch_name):
    for code, promo_price in promo_dict.items():
        if code not in main_dict:
            main_dict[code] = {}
        main_dict[code][f'promo_price_{branch_name}'] = promo_price

all_prices = {}
all_branch_names = [b['branch_name'] for b in branches]

for b in branches:
    bcode = b['branch_code']
    bname = b['branch_name']
    print(f"\n--- Branch: {bname} ({bcode}) ---")
    for ftype in ['PriceFull', 'PromoFull']:
        fn = find_latest_file(bcode, ftype)
        if not fn:
            print(f"  No {ftype} file for {bname}")
            continue
        print(f"  Found {ftype} file: {fn}")
        gz = download_file(fn)
        if not gz:
            print(f"  Failed to download {fn}")
            continue
        try:
            xml = extract_gz(gz)
            if ftype == 'PriceFull':
                data = parse_prices(xml, bname)
                merge_price_dicts(all_prices, data, bname)
            else:
                promos = parse_promos(xml)
                merge_promos(all_prices, promos, bname)
            os.remove(xml)
        except Exception as e:
            print(f"  Error parsing {fn}: {e}")
        os.remove(gz)

columns = ["code", "name"] + \
    [f"price_{b}" for b in all_branch_names] + \
    [f"price_per_pack_{b}" for b in all_branch_names] + \
    [f"promo_price_{b}" for b in all_branch_names]

with open("victory_prices_full.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=columns)
    w.writeheader()
    for code, row in all_prices.items():
        out = {"code": code, "name": row.get("name")}
        for col in columns:
            if col in row:
                out[col] = row[col]
        w.writerow(out)

print("\nDone! Results in victory_prices_full.csv")