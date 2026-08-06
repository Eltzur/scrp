"""SU10A-7 recon (read-mostly): prevalence + per-chain encoding of the three
unparsed promo signals — club-only, max-qty, gift-count. Fetches one live promo
file per representative chain, raw-parses for the signal tags, counts + samples.
Only writes are benign store-metadata refreshes from load_stores(); no
promo/price/items rows touched. Throwaway-but-keepable: re-run to re-measure."""
import sys
from pathlib import Path
from collections import Counter
from lxml import etree
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)
import yaml
from db.db import connect
from scraper.registry import get_scraper
from scraper.base import RAW_DIR

CHAINS = {
    "7290058140886": "Rami Levy (Cerberus/std)",
    "7290873255550": "Tiv Taam (Cerberus/std)",
    "7290696200003": "Victory (REST)",
    "7290058108879": "King Store (Bina/flat)",
    "7290700100008": "Hazi Hinam (flat)",
}
TAGS = ["ClubID","ClubId","MaxQty","RedemptionLimit","AdditionalGiftCount",
        "GiftsItems","RewardType","IsGiftItem"]

def sig(p):
    d = {}
    for t in TAGS:
        el = p.find(f".//{t}")
        if el is not None:
            d[t] = el.get("count") if t == "GiftsItems" else (el.text or "").strip()
    return d

cfg = yaml.safe_load((ROOT / "scraper/active_stores.yaml").read_text(encoding="utf-8"))
by_chain = {c["chain_id"]: c.get("store_ids", []) for c in cfg["chains"]}
conn = connect()
for cid, label in CHAINS.items():
    print(f"\n===== {label} {cid} =====")
    try:
        sc = get_scraper(cid)
        sc.load_stores(conn)
        sids = [str(s) for s in by_chain.get(cid, [])][:10]
        idx = sc.build_promo_index(set(sids))
        entry = next((idx[s] for s in sids if s in idx), None)
        if entry is None and idx:
            entry = next(iter(idx.values()))
        if entry is None:
            print("  no promo file resolved for sampled stores"); continue
        gz = RAW_DIR / (entry["filename"] + ".gz")
        sc._download_gz(entry["url"], gz)
        data = sc._decompress(gz); gz.unlink(missing_ok=True)
        root = etree.fromstring(data if isinstance(data, (bytes, bytearray)) else data.encode())
        proms = root.findall(".//Promotion")
        n = len(proms); club_r = mq = gc = gi = 0
        cv, rv = Counter(), Counter()
        for p in proms:
            s = sig(p)
            club = s.get("ClubID") or s.get("ClubId")
            if club is not None:
                cv[club] += 1
                if (club.split() or ["0"])[0] not in ("0", ""): club_r += 1
            if s.get("MaxQty") and s["MaxQty"] not in ("0", "0.00", ""): mq += 1
            if s.get("AdditionalGiftCount") and s["AdditionalGiftCount"] not in ("0", ""): gc += 1
            if s.get("GiftsItems") and s["GiftsItems"] not in ("0", ""): gi += 1
            if s.get("RewardType"): rv[s["RewardType"]] += 1
        print(f"  {n} promotions in this store's file")
        print(f"  club-restricted:{club_r}  max_qty set:{mq}  AddGiftCount>0:{gc}  GiftsItems>0:{gi}")
        print(f"  club values:{dict(cv.most_common(6))}")
        print(f"  reward_type values:{dict(rv.most_common(8))}")
        for p in proms[:2]:
            print("   sample:", sig(p), "| desc:", (p.findtext(".//PromotionDescription") or "")[:35])
    except Exception as e:
        print("  ERROR:", repr(e))
