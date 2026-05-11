# Session 9d-1 — PriceFull Verification Report

**Date:** 2026-05-11  
**Scope:** All stores in `scheduled_stores.yaml` after Phase B city expansion  
**Tool:** `build_pricefull_index()` per scraper, Shufersal 100-page listing scan  
**Result:** 58/72 verified · 14 excluded · active_stores.yaml generated

---

## Summary table

| Chain | Scheduled | Verified | Excluded |
|---|---|---|---|
| Shufersal | 12 | 1 | 11 |
| Rami Levy | 15 | 14 | 1 |
| Osher Ad | 10 | 8 | 2 |
| Victory | 9 | 9 | 0 |
| Yochananof | 9 | 9 | 0 |
| Keshet | 8 | 8 | 0 |
| Carrefour | 9 | 9 | 0 |
| **Total** | **72** | **58** | **14** |

---

## Category 1 — Warehouse / internal nodes (permanent ignore)

These stores have no city data, never appeared in any PriceFull listing,
and have no user impact. Do NOT replace in 9d-2.

| Chain | Store ID | Store name |
|---|---|---|
| Rami Levy | 004 | (no store name — likely a routing/warehouse node) |
| Osher Ad | 002 | (no store name — internal) |
| Osher Ad | 004 | (no store name — internal) |

---

## Category 2 — Shufersal sub-chain landscape (needs 9d-2 systematic work)

**Important caveat:** שלי stores are marked as unverified due to scan-depth
limits, NOT because they provably lack PriceFull. Store 002 ("שלי ירושלים")
has 5,551 prices loaded in session 8a, confirming שלי stores DO publish
PriceFull. Their listing position is beyond our 100-page scan (pages 36–135)
at the time verification ran (evening). In 9d-2, a deeper or timed scan is
needed to confirm שלי availability.

### Sheli (שלי) stores — scan-depth false negatives (8 stores)

| Store ID | Store name | City target |
|---|---|---|
| 001 | 1 - שלי ת"א- בן יהודה | Tel Aviv |
| 002 | 2 - שלי ירושלים- אגרון | Jerusalem (HAS 5,551 prices — confirmed real store) |
| 003 | 3 - שלי גבעתיים- סירקין | Givatayim |
| 004 | 4 - שלי חיפה- כרמל | Haifa |
| 007 | 7 - שלי ת"א- ארלוזורוב | Tel Aviv |
| 017 | 17 - שלי חיפה- חורב | Haifa |
| 024 | 24 - שלי אשדוד- הנביאים | Ashdod |
| 040 | 40 - שלי ב"ש- עומר | Be'er Sheva |

### Universe (יוניברס) stores — needs manual check (1 store)

| Store ID | Store name | City target |
|---|---|---|
| 035 | 35 - יוניברס באר שבע וולפסון | Be'er Sheva |

### BE format stores — needs manual check (1 store)

| Store ID | Store name | City target |
|---|---|---|
| 618 | 618 - BE ראשון לציון | Rishon LeZion |

---

## Category 3 — Missing from local DB or scan inconclusive

| Chain | Store ID | Issue |
|---|---|---|
| Shufersal | 010 | Not in local SQLite stores table — possibly a store added after session 8a load_stores |

---

## 9d-2 Work Queue

Stores needing replacement, grouped by city, for real user impact.
Warehouse nodes (Category 1) are excluded from this queue.

### Shufersal — high priority (10 stores need verification or replacement)

The root issue: Phase B selected "lowest 2 store_ids per city" which
biases toward old Sheli stores. Shufersal's PriceFull-verified formats
(from pages 36–100 scan) are: **יש / יש חסד**, **אקספרס**, **יוניברס**.
The "lowest store_id" heuristic doesn't capture these.

| City | Scheduled (excluded) | Replacement direction |
|---|---|---|
| Tel Aviv | 001 (שלי), 007 (שלי) | Find יש/אקספרס stores in TA with PriceFull |
| Haifa | 004 (שלי), 017 (שלי) | Find אקספרס/יש stores in Haifa |
| Be'er Sheva | 035 (Universe — check), 040 (שלי) | 035 may work — verify; find יש/אקספרס for 040 |
| Rishon LeZion | 618 (BE — check) | 618 may work — verify at 3 AM; find alternative |
| Ashdod | 024 (שלי) | 073 already verified; add 2nd Ashdod if available |
| Jerusalem | 002 (שלי — HAS prices!) | Re-verify 002 at 3 AM; likely works |

### Rami Levy — low priority
Store 004 is a warehouse node. Jerusalem coverage adequate with 001–003, 005.

### Osher Ad — low priority
Stores 002, 004 are warehouse nodes. Existing coverage adequate.

---

## 9d-2 Design Notes

### Shufersal sub-chain selection rethink
The "lowest store_id per city" heuristic is wrong for Shufersal because:
- Low store IDs (1–40) are predominantly old Sheli format stores
- Sheli stores publish PriceFull but at deep listing positions (timing-sensitive)
- יש, יש חסד, and אקספרס stores have higher IDs but appear reliably in pages 36–100
- **Recommendation:** Select Shufersal stores by scanning the PriceFull listing
  at 3 AM, then matching to cities by store_name, rather than using "lowest store_id"

### Yesh as a Shufersal sub-brand in the UI
- Jerusalem and Bnei Brak Shufersal coverage is dominated by יש and יש חסד stores
- These display as "שופרסל" in our UI but users may know them as "יש"
- Decision on display name deferred to 9d-2

### Shufersal store catalog source
- Eltzur is investigating a StoreNext-published canonical store list (476 stores
  with format prefixes in names) and whether equivalent lists exist for other chains
- This could feed a future `chain_stores_registry` table enabling format-aware
  selection (e.g., "pick 2 non-Sheli stores per city for Shufersal")
- Recommended schema: `chain_id, store_id, format, city, active` — maintained
  independently of scraper runs

### Carrefour PriceFull publishing pattern
- Stores with IDs 63–999 (many Carrefour City) do NOT publish PriceFull
- Stores with IDs 1–92 (Hyper/Market format) and 1200+ (migrated City stores) do
- Selection must be verified against live listing, not just Stores XML membership

### Verification scan depth
- 100-page Shufersal scan at 9 PM is insufficient — PriceFull files from 3 AM
  may be at pages 135+ by evening
- Future verification should run at 3–4 AM immediately after daily PriceFull publication
- For other chains (Cerberus/Victory/PublishPrice): single-call listing is accurate
  regardless of time of day
