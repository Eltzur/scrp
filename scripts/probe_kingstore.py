"""Read-only probe of the King Store bina-projects portal.

Prints raw tables for stores, PriceFull file listing, and the resolved
download URL for the first file. No DB writes, no file downloads, no
edits to any scraper or yaml file.
"""
import json
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "https://kingstore.binaprojects.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ── STEP 1: Select_Store ──────────────────────────────────────────────────────
print("=== STEP 1: Select_Store ===")
try:
    r1 = SESSION.post(f"{BASE}/Select_Store.aspx", data={}, timeout=30)
    r1.raise_for_status()
    stores = r1.json()
    print(f"{'Kod':<10} Nm")
    print("-" * 60)
    for s in stores:
        kod = s.get("Kod", s.get("kod", "?"))
        nm  = s.get("Nm",  s.get("nm",  "?"))
        print(f"{str(kod):<10} {nm}")
    print(f"\nTotal stores: {len(stores)}")
except (ValueError, json.JSONDecodeError):
    print("JSON parse failed. Raw response:")
    print(r1.text[:3000])
except Exception as exc:
    print(f"STEP 1 ERROR: {exc}")
    sys.exit(1)

print()

# ── STEP 2: MainIO_Hok (PriceFull listing) ───────────────────────────────────
print("=== STEP 2: MainIO_Hok — PriceFull (FileType=4) ===")
try:
    r2 = SESSION.post(
        f"{BASE}/MainIO_Hok.aspx",
        data={"WStore": "", "WDate": "", "WFileType": "4"},
        timeout=30,
    )
    r2.raise_for_status()
    files = r2.json()
    print(f"{'Store':<8} {'DateFile':<14} FileNm")
    print("-" * 90)
    for f in files:
        store    = f.get("Store",    f.get("store",    "?"))
        filenm   = f.get("FileNm",   f.get("fileNm",   f.get("Filenm",   "?")))
        datefile = f.get("DateFile", f.get("dateFile", f.get("DateFile", "?")))
        print(f"{str(store):<8} {str(datefile):<14} {filenm}")
    print(f"\nTotal files: {len(files)}")

    # Parse distinct chain_ids from PriceFull filenames
    chain_ids = set()
    for f in files:
        filenm = f.get("FileNm", f.get("fileNm", f.get("Filenm", "")))
        m = re.search(r"PriceFull(\d{13})", str(filenm), re.IGNORECASE)
        if m:
            chain_ids.add(m.group(1))
    print(f"Distinct chain_id(s) in FileNm: {sorted(chain_ids) or '(none parsed)'}")

    first_file = None
    if files:
        first_file = files[0].get("FileNm", files[0].get("fileNm", files[0].get("Filenm")))

except (ValueError, json.JSONDecodeError):
    print("JSON parse failed. Raw response:")
    print(r2.text[:3000])
    first_file = None
except Exception as exc:
    print(f"STEP 2 ERROR: {exc}")
    first_file = None

print()

# ── STEP 3: Download.aspx — resolve .gz URL ──────────────────────────────────
print("=== STEP 3: Download.aspx — resolve URL for first file ===")
if not first_file:
    print("No file from Step 2 — skipping.")
else:
    print(f"Probing: {first_file}")
    try:
        r3 = SESSION.post(
            f"{BASE}/Download.aspx",
            params={"FileNm": first_file},
            data={},
            timeout=30,
        )
        r3.raise_for_status()
        result = r3.json()
        if isinstance(result, list) and result:
            row = result[0]
        elif isinstance(result, dict):
            row = result
        else:
            row = {}
        spath = row.get("SPath", row.get("spath", row.get("Spath", "?(key not found)")))
        print(f"SPath (direct .gz URL): {spath}")
        print(f"\nFull response: {json.dumps(result, ensure_ascii=False, indent=2)}")
    except (ValueError, json.JSONDecodeError):
        print("JSON parse failed. Raw response:")
        print(r3.text[:3000])
    except Exception as exc:
        print(f"STEP 3 ERROR: {exc}")
