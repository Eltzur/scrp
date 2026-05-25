# 9d-2 Scoping Report
*Generated May 25, 2026 (session 9n)*

---

## 1. CITIES — Remaining 100K+ cities

Current live cities (14 as of May 24 dropdown): Ashdod, Be'er Sheva, Hadera, Haifa, Jerusalem, Kfar Saba, Migdal HaEmek, Nahariya, Netanya, Akko, Kiryat Bialik, Rishon LeZion, Ramat Gan, Tel Aviv.

**Kfar Saba, Netanya, and Ramat Gan are already live** (added in 9d-1 or prior). Remaining 100K+ cities to add:

| City | Pop est. | Notes |
|---|---|---|
| Petah Tikva | ~250K | Major city, all chains present |
| Holon | ~200K | Adjacent to Tel Aviv, good chain coverage |
| Bnei Brak | ~200K | Shufersal Yesh/Yesh Hesed dominant; zero Carrefour confirmed |
| Ashkelon | ~145K | Southern coast, good Rami Levy / Shufersal presence |
| Rehovot | ~140K | Central, full chain presence expected |
| Bat Yam | ~130K | Adjacent to Tel Aviv, compact city |
| Beit Shemesh | ~120K | Religious mix; Shufersal Yesh likely |
| Herzliya | ~100K | Wealthy suburb, all chains present |
| Modi'in | ~100K | New city, Victory + Rami Levy strong |

9 new cities. Target: ~2 stores/chain/city × 7 chains × 9 cities = ~126 new stores → ~184 total.

**Bnei Brak:** `city_norm='בני ברק'` IS in the DB (stores exist). Gap is coverage: zero Carrefour (verified via store locator), Shufersal Yesh format doesn't publish individual PriceFull. Rami Levy is the best candidate — check whether any Rami Levy store has `city_norm='בני ברק'` and publishes PriceFull.

**PriceFull verification gate:** All candidate stores must pass `verify_publishes_pricefull()` before entering `active_stores.yaml`. Run verifications in the 10:00 IDT window (same as cron) for consistent results.

---

## 2. BRANCHES & COVERAGE

### a. Snapshot fallback — confirmed working

`scraper/base.py` `replace=True`: `DELETE FROM prices WHERE store_fk=:store_fk` runs only inside the loop over stores that have an entry in the PriceFull index. Stores absent from the index (portal not published yet, or not in `active_stores.yaml`) are skipped — existing price rows are untouched. **Stale-but-present beats absent.** No code change needed.

### b. Shufersal throughput

Currently configured: 1 store (073 only). Scheduled intent: 12 stores. At 10:00 IDT (business hours) the Shufersal portal runs slower than at 03:00 IDT — this is a regression risk for the page-scan bottleneck (was 40s/store at 03:00 IDT; may be 2–5× longer at 10:00 IDT). See Priority 4 below.

### c. Current coverage baseline (72h, as of May 25 catch-up run)

| Chain | Configured | Has prices | 24h | 72h | 72h% | Note |
|---|---|---|---|---|---|---|
| Rami Levy | 14 | 14 | 14 | 14 | **100%** | ✅ |
| Yochananof | 9 | 9 | 8 | 8 | **88%** | ⚠️ store 027 last=May 20 |
| Keshet | 8 | 8 | 3 | 4 | **50%** | ❌ stores 002/019/024/318 stale (May 17–20) |
| Carrefour | 9 | 9 | 2 | 2 | **22%\*** | ⚠️ \*metric artifact suspected — see below |
| Osher Ad | 8 | 8 | — | — | **unmeasurable** | `price_update_date` blank in XMLs |
| Victory | 9 | 9 | — | — | **unmeasurable** | `price_update_date` blank in XMLs |
| Shufersal | 1 | 1 | — | — | **unmeasurable** | `price_update_date` blank in XMLs |

**Carrefour 22% flag:** This may be a metric artifact. `price_update_date` in Carrefour XMLs reflects when the chain last updated that price — many items have months-old XML dates even in a fresh-today scrape. `fetch_runs` may show all 9 stores loaded successfully today. **Do not treat as a real 22% coverage gap until verified with the step-1 per-store metric.**

**Chains below 90% (confirmed real):**
- **Keshet 50%** — 4 of 8 stores not refreshed in 72h. Needs investigation.
- **Shufersal** — only 1 store configured; coverage% is meaningless until expanded.

**Metric gap:** Osher Ad, Victory, and Shufersal are **unmeasurable** via `price_update_date`. A `fetch_runs`-based per-store metric (Priority 1) is required before claiming their coverage is good or bad.

### d. Bnei Brak gap

City_norm is populated in DB — not a normalization bug. Coverage gap: no Carrefour presence (verified, accepted); Shufersal Yesh/Yesh Hesed doesn't publish per-store PriceFull; Osher Ad store 011 not in `active_stores.yaml` (failed PriceFull verification in 9d-1). Best path: verify Rami Levy Bnei Brak stores.

---

## 3. CHAINS — Unscraped Israeli chains

| Chain | Portal type | Stores est. | Effort | Notes |
|---|---|---|---|---|
| AM:PM | Cerberus? | ~50 | LOW | Investigate portal; ~6-line subclass if confirmed Cerberus. Urban convenience tier. |
| Freshmarket | Cerberus? | ~30 | LOW-MED | Northern Israel focus. Worth investigating. |
| Co-op / מרקו | Cerberus? | ~40 | LOW-MED | Cooperative chain. Lower priority. |
| Hazi Hinam | HTML | ~150 | HIGH | **Skipped per architectural decision** — HTML fragility, no Cerberus endpoint. |
| Mega / Yenot Bitan | — | — | ZERO | Already scraped under Carrefour chain_id 7290055700007. |

Do not start new scraper development until existing 7 chains are at ≥90% coverage (Priority 3).

---

## 4. PERFORMANCE — 19.5 min run vs 13 min estimate

9g estimate was ~13 min for 216 stores (linear scale from 58 stores in 3m31s). The 9n catch-up run was ~19.5 min.

**Likely causes:**
- All 3 previously-failing chains (Victory, Osher Ad, Carrefour) loaded for the first time in days — higher data volume than a skip-heavy run
- Shufersal page-scan at 10:00 IDT (business hours) slower than at 03:00 IDT — confirmed risk

**Shufersal page-scan cache:** If expanding to 12 Shufersal stores, the scan phase alone could be 20–40 min at 10:00 IDT — consuming most of the cron window. A cache that remembers last successful start page per store would drop this significantly. **In-scope for 9d-2** if Shufersal expansion to 10+ stores is targeted; defer if staying at 1 store.

---

## 9d-2 Priority Order

### Priority 1 — Build fetch_runs-based per-store coverage metric

**Prerequisite for everything else.** `price_update_date` is unreliable for Osher Ad, Victory, and Shufersal (blank in their XMLs), making 3 of 7 chains unmeasurable. The current metric says "0% coverage" for chains that were actually loaded today.

**Implementation note:** `fetch_runs` is currently per-chain (one row per chain per cron run). To get per-store visibility, either:
- (a) Add per-store logging in `cron_main.py` / `base.py` — a new `store_runs` table or JSON payload in `fetch_runs.metadata`, or
- (b) Use `MAX(price_update_date)` only where reliable (Rami Levy, Yochananof, Keshet) and `fetch_runs.run_at` for the rest — a hybrid query

Option (b) is lighter but fragile. Option (a) is the right architecture for 9d-2 scale. Decide and scope before starting.

The per-chain FreshnessStrip API (`/freshness`) has the same blindspot: `MAX(run_at)` per chain means one fresh store makes the whole chain show "updated today," masking per-store staleness (Keshet 50%, Yochananof 88% on May 25 despite all chains showing green). A per-store freshness view is part of this deliverable.

### Priority 2 — City expansion (9 new 100K+ cities)

Add and verify store rows for all 9 cities against existing scrapers. Safe to do at this stage because Priority 1 makes the new stores' load status visible. Run PriceFull verifications in the 10:00 IDT window.

### Priority 3 — Coverage repair to ≥90% on 72h window

Once new cities are added, repair coverage across all chains including new stores. Current below-90% chains: Keshet (50%), Shufersal (1 store — needs expansion). Carrefour 22% — confirm or dismiss once Priority 1 metric is in place. Yochananof 88% (store 027) — minor, but include in this pass.

### Priority 4 — Cron / Shufersal page-scan optimization

Required once store count is up. The 12-store Shufersal phase risks blowing the 10:00 IDT cron window (estimated 20–40 min at business-hours portal speeds). Build page-scan cache if Shufersal expansion to 10+ stores is targeted.

### Priority 5 — New chains (AM:PM, Freshmarket, Co-op)

**Last.** New scraper code is the risky kind of expansion — do it only once the existing 7 chains are consistently healthy. Investigate AM:PM Cerberus portal first (lowest effort if confirmed). Do not start until Priority 3 is complete.
