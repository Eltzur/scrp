"""Quick test: OpenFoodFacts lookup for Israeli barcodes."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests

BARCODES = [
    "7290000042015",
    "7290004131074",
    "7290000057149",
    "7290004129545",
    "72991008",
]

session = requests.Session()
session.headers["User-Agent"] = "IsraeliPriceComparison/1.0 (research)"

for barcode in BARCODES:
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    resp = session.get(url, timeout=15)
    data = resp.json()

    if data.get("status") != 1:
        print(f"{barcode}: NOT FOUND")
        continue

    p = data["product"]
    name_he = p.get("product_name_he") or p.get("product_name") or "(no name)"
    image   = p.get("image_front_url") or p.get("image_url") or "(no image)"
    print(f"{barcode}: {name_he}")
    print(f"  image: {image}")
