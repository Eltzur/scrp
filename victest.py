import requests
import os

# Folder to save files
download_dir = "victory_full_reports"
os.makedirs(download_dir, exist_ok=True)

# Base URL for Victory chain
victory_chain_id = "7290696200003"
base_url = f"https://laibcatalog.co.il/CompetitionRegulationsFiles/latest/{victory_chain_id}/"

# 5 samples from your printout (PriceFull or PromoFull for Victory branches)
rows = [
    ['PromoFull7290696200003-091-202506010501-001', 'ויקטורי', 'שוהם 91', 'מבצעים', 'gz', '77.70KB', '01/06/2025 05:01:29', 'לחץ כאן להורדה'],
    ['PriceFull7290696200003-091-202506010501-001', 'ויקטורי', 'שוהם 91', 'מחירים', 'gz', '212.82KB', '01/06/2025 05:01:14', 'לחץ כאן להורדה'],
    ['PromoFull7290696200003-045-202506010500-001', 'ויקטורי', 'רעננה 45', 'מבצעים', 'gz', '61.91KB', '01/06/2025 05:01:00', 'לחץ כאן להורדה'],
    ['PriceFull7290696200003-045-202506010500-001', 'ויקטורי', 'רעננה 45', 'מחירים', 'gz', '163.73KB', '01/06/2025 05:00:53', 'לחץ כאן להורדה'],
    ['PromoFull7290696200003-047-202506010500-001', 'ויקטורי', 'אופקים 47', 'מבצעים', 'gz', '106.74KB', '01/06/2025 05:00:42', 'לחץ כאן להורדה'],
]

for row in rows:
    filename = row[0]
    chain = row[1]
    # We use only PromoFull/PriceFull for Victory, but in this example they're all correct
    url = base_url + filename + ".xml.gz"
    dest = os.path.join(download_dir, filename + ".xml.gz")
    print(f"Downloading {url} ...")
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if resp.status_code == 200:
        with open(dest, "wb") as f:
            f.write(resp.content)
        print("Downloaded:", dest)
    else:
        print(f"Failed to download {url} -- status {resp.status_code}")