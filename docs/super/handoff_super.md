# SCRP — Project Handoff

> A living document. Update at the end of each session. Paste at the start of each new chat.
> Last updated: September 24, 2026 (mobile /search latency investigation, read-only, parked; also Sept 23: GS1 catalog-value measurement + "What's Good for Europe" reform assessment)

---

## 🎯 Vision

xxl.co.il is an Israeli multi-vertical savings platform. The supermarket vertical (super.xxl.co.il) is the anchor product — a clean, fast, accurate price comparison tool for Israeli grocery shoppers, powered by government-mandated transparency XML feeds.

**Near-term (6 months):** Match and exceed Cheapersal.co.il on data coverage, UX clarity, and location relevance. Every search result shows the branch name, address, and last update time. Promo prices highlighted where discount ≥10% or 2-for-1. Mobile-first responsive design.

**Medium-term (6-12 months):** Native mobile experience with barcode scanner — user scans a product in-store and instantly sees prices at nearby supermarkets within 500m radius, powered by store GPS coordinates from StoresFull XMLs. GS1 Israel integration for canonical product names, images, and nutritional data.

**Long-term:** AI-powered natural language search ("where's the cheapest cottage cheese near me?"), basket optimization across chains, and expansion to additional verticals (flights, hotels, fashion) under the xxl.co.il umbrella.

**Core principles:** data accuracy over coverage, location relevance over volume, mobile experience over desktop, free tier as the honeypot.

---

## 🏗️ Architecture

| Layer | Tech | Where | Status |
|---|---|---|---|
| Frontend | React + Vite + TypeScript + Tailwind | Kamatera nginx (PRIMARY for ALL xxl.co.il surfaces) — serves portal (xxl.co.il + www), super.xxl.co.il, and flights (fly.xxl.co.il). Portal & super share ONE build (web/dist). Hostinger (`82.198.227.247`) is COLD FALLBACK / DR only — older static copy, no live traffic. | ✅ Live |
| Backend | FastAPI + gunicorn + uvicorn | Kamatera `scrp-prod-il` via systemd `scrp-api.service`, behind nginx + Let's Encrypt | ✅ Live since May 18, 2026 |
| Database | Postgres 18.4 | Kamatera `scrp-prod-il` (`185.229.226.190`), localhost-only (5432 closed at UFW) | ✅ Live |
| Scraper cron | Python (`scraper.cron_main`) | Kamatera `scrp-prod-il` via systemd timer | ✅ Daily 10:00 IDT, DST-aware (changed from 03:00 in session 9n — portals publish 02:00–05:00 UTC; 10:00 IDT = 07:00 UTC clears the window) |
| Backups | pg_dump → rclone → Backblaze B2 | Kamatera systemd timer `scrp-backup.timer` (daily 04:00 IDT) + B2 bucket `xxl-scrp-backups` | ✅ Live since May 19, 2026 |
| DNS | box.co.il (ns1/2/3.box.co.il) | — | ✅ |
| Auth | Supabase | Supabase project (auth only — no Data API usage from client) | ✅ Live |

**Local dev:** `C:\scrp` on Windows 10/11. PowerShell + VS Code + Claude Code in VS Code terminal.

**Repo:** github.com/Eltzur/scrp (main branch is production)

**Production URLs:**
- Portal: https://xxl.co.il (and https://www.xxl.co.il)
- Supermarket app: https://super.xxl.co.il
- Backend: https://api-super.xxl.co.il
- Scraper/DB server (SSH only): `ssh dude@185.229.226.190` (Kamatera Tel Aviv, scrp-prod-il)

**Portal + domain hosting (Kamatera cutover, July 5 2026):**
- **Kamatera (`185.229.226.190`) is PRIMARY for ALL xxl.co.il surfaces**, including the portal. Hostinger (`82.198.227.247`) is COLD FALLBACK / DR only — it holds an older static copy and receives no live traffic.
- `xxl.co.il` + `www.xxl.co.il` are served by a Kamatera nginx block: `/etc/nginx/sites-available/xxl.co.il`, root `/var/www/super.xxl.co.il` (shared with super.xxl.co.il), SSL via certbot (cert expires 2026-10-03).
- DNS: A records at box.co.il for `xxl.co.il` and `www.xxl.co.il` → `185.229.226.190` (Kamatera). Cut over from Hostinger (`82.198.227.247`) on July 5, 2026.
- **Portal and super SHARE ONE React build (web/dist).** Because the xxl.co.il nginx block shares root `/var/www/super.xxl.co.il`, deploying web/ updates BOTH super.xxl.co.il and the portal (xxl.co.il / www) in one deploy.
- **Routing logic lives in React, NOT nginx/.htaccess.** `isPortalHostname()` in `web/src/utils/hostname.ts` checks `window.location.hostname` and renders `PortalPage` at `/` when on xxl.co.il, else renders `AppShell` (supermarket app).
- **DR revert path:** repoint the `xxl.co.il` + `www` A records at box.co.il back to `82.198.227.247` (Hostinger cold copy).

**Key infrastructure commands:**

*Kamatera (all production infra):*
- SSH: `ssh dude@185.229.226.190` (or `ssh root@...` via key for admin)
- API service: `systemctl status scrp-api.service` (gunicorn on 127.0.0.1:8000, nginx proxy on 443)
- Reload API: `systemctl restart scrp-api.service`
- nginx config: `/etc/nginx/sites-available/api-super.xxl.co.il` (managed by certbot)
- Manual scrape: `cd ~/scrp && venv/bin/python -m scraper.cron_main`
- Scheduled scrape: `systemctl start scrp-cron.service` (daily 03:00 IDT timer)
- Scrape logs: `journalctl -u scrp-cron.service --since "yesterday" | tail -50`
- API logs: `journalctl -u scrp-api.service -f`
- Postgres console: `sudo -u postgres psql xxl_super`
- Cert renewal: auto via `certbot.timer` (next ~02:30 IDT daily), expires 2026-08-16
- UFW open ports: 22, 80, 443
- Manual backup: `systemctl start scrp-backup.service`
- Backup logs: `journalctl -u scrp-backup.service --since "yesterday"`
- List B2 backups: `rclone ls b2:xxl-scrp-backups/daily/`
- Restore (scratch DB): `sudo -u postgres createdb test_restore && sudo -u postgres pg_restore -d test_restore /var/backups/scrp/xxl_super-YYYY-MM-DD.dump`

**Folder layout (matters because some folders are misleadingly named):**
- `web/` — React frontend (NOT the backend, despite the name)
- `api/` — FastAPI backend
- `scraper/` — scraper code + cron entrypoint
- `db/` — schema, migrations, helper scripts
- `frontend/` — empty stub, leftover from skeleton commit, ignore

**Frontend deployment (Kamatera):**
- Deploy via `scripts/deploy_frontend.ps1`: build `web/` → scp `dist/` to `/var/www/super.xxl.co.il` on Kamatera. This updates BOTH super.xxl.co.il AND the portal (xxl.co.il / www) because the xxl.co.il nginx block shares that root.
- SPA routing (React Router fallback) is handled by the nginx `try_files` fallback in each server block; hostname routing is handled in React (`isPortalHostname()`).
- **Legacy (dead):** the old Hostinger path (build → zip `dist/*` → upload+extract in `public_html/`) is retired. Hostinger holds only a cold DR copy and receives no live traffic.

---

## 📊 Current Production State

**Last updated: August 10, 2026 (end of session SU10A-8)**

- **14 chains** in registry: Shufersal, Rami Levy, Osher Ad, Victory, Yochananof, Keshet, Carrefour, Tiv Taam, King Store, Shefa Birkat Hashem, Shuk Hayir, Fresh Market, Super Yuda, חצי חינם / Hazi Hinam (added 9d-9)
- **~1,200 stores** in active_stores.yaml (post 9d-9 additions: Rami Levy +72→98, Yochananof +35→50, Keshet +12→22, Osher Ad +11→23, Hazi Hinam +1→12; Paz + Dor Alon removed in 9d-8)
- **city_canonical** is the source of truth for all city data (rebuilt from CBS 2024 in 9d-8, 0 NULLs). city_norm is legacy/broken — do not use.
- **Delta mode active for ALL 14 chains** (SU10A-6 added the last 6: Tiv Taam, Carrefour, Victory, then King Store, Shefa, Shuk Hayir). Controlled by `DELTA_CHAINS` in `registry.py` + `uses_delta()`. **Delta mode has no periodic PriceFull resync** — the base class only falls back per-store when a delta file is missing, so a missed cron day silently loses that day's changes until someone runs `run_one <chain> --full`.
- **Per-store parallelism**: `STORE_WORKERS=4` in `base.py` and `shufersal.py`. Each worker opens its own DB connection. Shufersal: 4436s → 544s (8×). Tiv Taam: 6913s → 93s (74×).
- **Chain-level parallelism**: `cron_main.py` ThreadPoolExecutor(max_workers=6). Full cron target: <30 min (to be confirmed by next 10:00 IDT run).
- **City dropdown**: 0.13s response (was 3.7s — prices JOIN removed in 9d-8).
- **Verification gate**: `active_stores.yaml` (verified to publish PriceFull/Price) is what cron uses; `scheduled_stores.yaml` is the wish-list. See `db/verification_report_9d1.md` for excluded stores.
- **GS1 Israel catalog**: ✅ LIVE (SU10A-1/2, July 2026). Own `gs1` schema on the same Postgres. **22,559 products across 77 suppliers**; **11,496 carry full per-product detail** (`gs1.products.full_content` JSONB — kosher/Kashrut certification 100%, media assets 100%, ingredients 97%, nutrition panel 67%); **11,450 product images** fetched and resized (800px/JPEG-80, 0.62 GB). Incremental sweep is wired into the nightly cron, exception-wrapped so a GS1 failure never fails the supermarket scrape. Counts drift upward nightly — re-query rather than trusting this line.
- **✅ GS1 phase-2 data is now customer-facing (SU10A-4).** Images and the kashrut / nutrition / ingredients / allergens blocks all reach users through the product detail modal, alongside the product name. Two endpoints serve it: `GET /product/{item_code}/details` (200 with `has_gs1_data: false` and null sections for the ~91% of items with no GTIN match — a normal case, not an error) and `GET /product/{item_code}/image`.
  - *Historical context for why the image path looks the way it does:* the images still sit in `~/gs1_images` on the VPS as loose `dude`-owned files, with no nginx route, no web root, no URL scheme and no `product_image_url` column populated — `www-data` cannot read `~dude`. Rather than relocating ~11.5K files, the API serves them directly: the filename is the GTIN and the GTIN is the item_code, so it resolves with a `stat()` and no DB hit. That permission gap is worked around, not closed, so a future move to nginx/CDN serving is still an open option.
- **Canonical names**: ✅ RESOLVED (was "blocked on GS1 IL access" — that access is live and the pipeline has run). Weighted token voting (session 8b) plus GS1 enrichment both write `items.item_name`; **10,585 items are stamped `name_source='gs1'`**. SU10A-3 also fixed the display bug that made this invisible: the API was showing one chain's arbitrary raw scrape instead of the computed canonical name, so **87% of the GS1 enrichment was landing in the DB and never reaching a user**. Both ranking and display now read `items.item_name`.
- **Search** ranks by relevance tier (item_name prefix → whole word → substring → manufacturer-only), then multi-chain, then cheapest, then `item_code` as a deterministic tie-break. **Numeric and percentage tokens are NOT filtered** — they are product attributes and were previously discarded, silently widening every sized query (SU10A-3 reversed this; the old "tokens filtered" behaviour from session 8b is gone). `חלב 3%` narrows to 3% milk; `במבה 80` narrows to 80 g. Bare numbers match on a digit-run boundary so `80` does not match inside `180`. **Length < 2 is the only remaining token filter.**
- **Promos**: ✅ REBUILT AND RESOLVED (SU10A-5) — previously flagged "CRITICALLY BROKEN" on a premise that did not survive audit. A UNIQUE (store_fk, item_code, promo_id) constraint makes duplicate rows structurally impossible; the large per-chain counts are legitimate per-store fan-out. **All 14 chains are now populated** (~560K rows, up from 274K) after onboarding the 4 that produced none. Discounts are computed at READ TIME in `db/query.py` — never stored — so unit semantics stay fixable without re-scraping. Served by `GET /promos/grouped` (chain → city → branch, no dedup, no cap). **Never key promo logic on `reward_type` / `DiscountType` / rate or `min_qty` units without per-chain verification** — all three vary by chain.
- **Known coverage gap**: Bnei Brak has no Carrefour/Yenot Bitan/Mega presence (verified via carrefour.co.il store locator) — accepted, not a bug.
- **Live site status**: ✅ super.xxl.co.il + xxl.co.il fully operational, all API calls served from Kamatera over HTTPS.

---

## ✅ Sessions Completed

> **Older sessions (8L through SU10S-20) are archived verbatim, oldest first, in [handoff_super_archive.md](handoff_super_archive.md)** (moved in SU10S-26).

---

## Potential Data Sources

External data sources we're evaluating for catalog enrichment. Each entry tracks status, key questions, and decision gates. **Single source of truth — do not split into separate files.**

### GS1 Israel — Digital Catalog of Items (added May 14, 2026)

**What it is:** GS1 IL's digital catalog — barcode-keyed (GTIN) product master data. GS1 is the global NGO that owns the barcode standard. The Israeli chapter operates the local catalog at https://www.gs1il.org/what-is-the-digital-catalog-of-items/

**Fields offered (per their marketing page):**
- Barcode (GTIN) — canonical product ID
- Full product name + description (canonical, brand-owner authored)
- Images — including 360° and marketing imagery
- Nutritional info
- Kashrut certifications
- Logistics data (pack sizes, weights)
- Brand / marketing metadata

**Why high-priority:** Closes the three gaps the OS scraper research (May 14) flagged — canonical names, brands, images — from a single authoritative source. Bonus fields (kashrut, nutrition, 360° images) unlock future verticals like dietary filtering, allergen flagging, and richer product detail pages.

**Architecture fit:** Enrichment layer joined to existing scraper output via barcode (GTIN). NOT a replacement for the gov.il scraper — gov.il still needed for prices. Clean add-on, not a rewrite.

**Status:** Eltzur registered via gs1il.org website on May 14, 2026. Awaiting contact from GS1 IL with details.

**Open questions for GS1 IL (in priority order, ask in first reply):**
1. Is a price-comparison / consumer-info platform eligible as a data consumer, or is read access restricted to retailers/manufacturers?
2. Pricing structure for read-only API or data feed access for our use case?
3. API specification — REST / bulk file download / GraphQL? Rate limits? Update frequency?
4. Coverage — what % of Israeli grocery SKUs are currently in the catalog?
5. Image licensing — can we display catalog images on a consumer-facing site at no extra cost, or is there a per-display / per-API-call fee?
6. Data freshness SLA — how often do brand owners update their listings?

**Decision gates:**
- 🟢 GREEN: Platform-eligible access, ≤₪3k/month, REST API or bulk feed, ≥70% SKU coverage → prioritize integration immediately after 9g
- 🟡 YELLOW: Eligible but pricier (₪3-10k/month) → defer until pre-revenue funding lands or revenue covers it
- 🔴 RED: Retailer-only access OR ≥₪10k/month → file under "revisit at scale"

**Important caveats (don't assume too much from marketing page):**
- GS1 is non-profit but NOT free. Pricing varies wildly by country and tier — could be hundreds or tens of thousands of shekels annually. Unknown until they reply.
- Catalog only covers products whose brand owners have opted in. Israeli participation rate unknown.
- Doesn't replace gov.il for prices — GS1 carries product master data, not commercial pricing.

**Follow-up cadence:** If no reply from GS1 IL within 5 business days (target: May 21, 2026), Eltzur sends a polite follow-up via their contact form or phone (03-5198714).

**Relationship to other sources:** GS1 and StoreNext are PARALLEL candidates, not mutually exclusive. GS1 is brand-owner-sourced (manufacturer-uploaded); StoreNext is retailer-sourced. They may complement each other — GS1 fills the canonical-name + image gap, StoreNext could fill chain-specific pricing/promo metadata. Pursue both threads in parallel.

---

### StoreNext (status: REJECTED — pricing prohibitive, May 17, 2026)

**Status:** Outreach completed May 2026. StoreNext quoted **NIS 30,000 (~$8,000 USD) for a one-time Excel export** of their catalog data. Pricing is approximately 4 years of scrp's total infrastructure budget for a static, single delivery (not even an ongoing API or feed). Hard pass at current stage.

**What we'd have gotten:** Branch lists for all 7 chains with sub-format classification, potentially product catalog data. Free CSV branch lists at `storenext.co.il/תמיכה-ושירות/` remain accessible — those are still useful for the 9e Registry idea if we revisit it (see decision below).

**Why rejected:**
- Price is one-time, not subscription — no obvious "grow into it" tier
- Single Excel export means data goes stale; not an ongoing relationship
- ROI doesn't work pre-revenue. Even if StoreNext data unlocked premium tier conversions, NIS 30K is years of recouping at hobby pricing
- GS1 IL (pending reply) is the better-shaped data source — barcode-keyed canonical product master data with images, kashrut, nutrition. Different layer than StoreNext's chain-store-registry focus
- The actual gaps we wanted to close (images, brands, canonical names) are addressed by GS1, not StoreNext

**Future:** Revisit only if (a) GS1 path doesn't pan out AND (b) scrp has revenue or funding to absorb the cost. Re-engage StoreNext at scale (5K+ MAU, paying premium tier exists) when the value calculation flips.

**Free StoreNext data still usable:** Branch CSVs at `storenext.co.il/תמיכה-ושירות/` are free and can power the 9e Registry concept independently of the paid catalog. Re-scoped 9e (see Pending Sessions) reflects this.

---

### OpenFoodFacts (status: abandoned)

Tried during earlier catalog enrichment exploration. Abandoned due to poor Israeli barcode coverage (most IL grocery SKUs absent from the global OFF database). **Do not revisit.**

---

## 🧭 Pending Sessions

→ See [docs/roadmap.md](../roadmap.md) for the current prioritized list.

| Session | What | Notes |
|---|---|---|
| **9m** | Cron hardening + post-holiday cleanup | ✅ Carrefour retry/backoff (9m partial, prior). This session: Shufersal parse_filename store_id padding bug FOUND & FIXED (commit 63ec27e — both return paths now .zfill(3); was returning unpadded '2'/'5'/'21' so PriceFull index never matched padded DB targets). City dropdowns sorted alphabetically (Hebrew localeCompare) instead of by chain count. Stale Railway DATABASE_URL removed from local .env. .gitattributes added (*.py eol=lf) + shufersal.py renormalized (kills phantom 261-line CRLF diffs). Carrefour store 1167 split-pair resolved. Shufersal page-cache verification DEFERRED to next session (holiday — no fresh PriceFull files, inconclusive). |
| **9m-followup** | Shufersal verification + Carrefour padding fix | ✅ Shufersal padding fix (63ec27e) verified — metadata returns 3-digit store IDs. Carrefour PriceFull lookup padding bug found & fixed: base.py now normalizes target store_id via _pad_store_id before index lookup (commit 0812bdc) — stores 60/81 were silently skipped because active_stores.yaml has unpadded IDs ("60") while the index keys are zero-padded ("060"). Store 6 confirmed a genuine upstream Carrefour publishing gap, not a code bug. Hostinger frontend deploy: alphabetical city sort live (85ee335). |
| **9n** | 3-chain diagnostic + cron timing fix + FreshnessStrip deploy | ✅ Root cause of Victory/Osher Ad/Carrefour daily zero-loads identified: timing race — cron at 03:00 IDT (midnight UTC) fires before portals publish. Portals confirmed to publish 02:09–05:00 UTC consistently over 6+ days. Cron timer moved to 10:00 IDT (07:00 UTC) via `sed` on Kamatera `/etc/systemd/system/scrp-cron.timer`. Catch-up run succeeded all 7 chains. FreshnessStrip downward-expand code confirmed correct in web/ source (was never deployed). web/deploy.zip rebuilt — awaiting Hostinger upload. Column-misalignment report in 9n table was RTL terminal rendering artifact; DB data confirmed correct. |
| **9f-followup** | ~~Portal polish~~ | ✅ Done May 14, 2026. See session detail below. |
| **9h** | **Claude Haiku integration for portal search** | Replace `web/src/utils/portalSearchRouter.ts` mock classifier with real Claude Haiku API call. Function signature already designed for one-line swap. Budget: ~$5/mo at 1K daily queries. |
| **9i** | Contact form on xxl.co.il | Real form with Supabase backend + spam protection + email notifications. Currently footer has mailto link only. |
| **Server hardening** | sudo NOPASSWD for dude, disable root SSH, HSTS header, compress OG images (~5.6MB each) | Small cleanups, batch into one ~30 min session. |
| **9g-2** (deferred) | **Parallel chain execution** | Skipped after 9g-1 results. Sequential cron now 3m31s; parallelism would save ~2.8 min. Low ROI until something specific unblocks it. Revisit when full cron pressure returns. |
| 9e (rescoped) | StoreNext FREE branch CSV ingestion | Original 9e premise (paid product catalog) dead — StoreNext paid tier rejected (NIS 30K one-time, May 2026). Free CSV branch lists at `storenext.co.il/תמיכה-ושירות/` remain usable. Rescoped to: ingest free branch CSVs only into `chain_stores_registry` table with sub-format classification (Sheli/Deal/Express/Yesh/Universe/BE for Shufersal; similar for others). Refactor Phase B selection to be format-aware. Solves Shufersal sub-chain heterogeneity systematically. No longer urgent since verification gate (9d-1) already prevents silent failures — quality-of-life, not blocker. |
| 9d-2 | City expansion Phase 2 | Remaining 12 cities >100K pop (Petah Tikva, Netanya, Holon, Ramat Gan, Ashkelon, Rehovot, Bat Yam, Beit Shemesh, Kfar Saba, Herzliya, Modi'in). Target ~216 stores total. **Requires 9g first** — running 216-store cron at current 1.5min/store = 5+ hours. |
| 9d-4 | City expansion Phase 3 | 50K+ cities (~25-30 more). Target ~540 stores. |
| **stores table data hygiene** | **Add format guard to `sub_chain_id` / `store_id`** | Rami Levy split (was `sub='1'` vs `'001'`) resolved in 9k; Carrefour `store_id` padding resolved in 9j-followup. base.py lookup now routes through `_pad_store_id` (9m-followup, commit 0812bdc) — a drifted yaml store_id resolves correctly instead of silently failing. A CHECK constraint on the stores table is now optional/nice-to-have, no longer urgent. |
| Promotions + price history | Parse Promo XML files, build history charts | Sample Promo XML files captured in 9d-1 for future analysis. Requires sufficient daily snapshots first. |
| **Price history (product-detail tab)** | "מחירי היסטוריה" — per-product price-over-time chart (monthly/yearly), web + mobile | **Requested Sept 26, 2026. NOT BUILDABLE TODAY — blocked on data, not on UI.** `upsert_price` writes `ON CONFLICT (store_fk, item_code) DO UPDATE`: the key carries no date, so every cron run overwrites the previous price in place and nothing dated survives. This is the **Snapshot pricing only** decision under Key Architectural Decisions, and it is the same dependency as the **Promotions + price history** row above — scope the two together, don't duplicate them. Prerequisites: **(a) schema decision** — a dedicated `price_history` table, *not* making `prices` append-only; append-only changes the row shape every read-path query assumes (compare, basket, `_PRICE_SQL`), which is a far wider blast radius than a new table. **(b) No backfill is possible** — history accrues only from the day it is switched on, so the chart stays empty/thin for months afterward; that is a product decision to accept up front, not a bug to fix later. **(c) Storage plan first** — `prices` is already 7,686,194 rows / 3,749 MB at snapshot-only (measured Sept 24, 2026; see the mobile /search latency section), and a dated table grows by roughly a snapshot per retained day, so retention/rollup must be settled before switching it on. **Decided this session: do NOT ship a placeholder 4th tab ahead of the data** — a tab that stays empty for months reads as broken, not as "coming soon." **Low priority, long-term roadmap — not scheduled.** |
| Google OAuth | Wire up deferred-from-9b option | Requires Google Cloud Console OAuth client setup |
| Investigate disappearing tables | Risk hygiene | Deferred pending future AWS/GCP migration (decided in 9c planning) |
| **Search Quality** | Hebrew search precision fixes | Word-boundary matching, kosher-marker filtering ("חלבי"/"פרווה"/"בשרי" leaking into "חלב"/"בשר" searches — example: jelly appearing under "חלב" because it's labeled "חלבי"). Stretch: Hebrew stemming. Defer until after StoreNext data is in hand (may solve upstream via better categorization). |
| **OS scraper research** | ~~Review OpenIsraeliSupermarkets repos + Kaggle dataset~~ | ✅ Done May 14, 2026. Writeup at docs/research/os_scraper_2026_05_14.md. Key findings: MIT-licensed (not GPL/AGPL as feared), geo-block is industry-wide (confirms 9g VPS plan), Kaggle dataset NOT a Carrefour/Victory stopgap, no new sources for images/categories/brands (StoreNext still the path). |

---

## 📌 Open Items — Next Session (9d-10)

- **Confirm full cron run** — check 10:00 IDT tomorrow. Expected <30 min with per-store parallelism (STORE_WORKERS=4) + chain-level parallelism (max_workers=6). First run with delta for 8 chains.
- **Supabase keep-alive** — timer files deployed to `deploy/systemd/`, still needs enabling on server:
  ```bash
  sudo systemctl daemon-reload && sudo systemctl enable supabase-keepalive.timer && sudo systemctl start supabase-keepalive.timer
  ```
- **Seed Hazi Hinam** — run `python3 -m scripts.seed_hazihinam` on server before next cron (seeds physical stores 201-217 from store 103 PriceFull so delta can apply incremental updates).
- **Missing stores — Victory + Carrefour** — Victory: 51 stores missing from yaml vs StoresFull XML. Carrefour: 125 stores missing (portal was down June 4, check when back up).
- **Delta for non-Cerberus chains** — Victory (REST API), King Store / Shefa / Shuk Hayir (Bina Projects) need `build_price_index` per portal type.
- **9d-2 city expansion — cleared to start.** No remaining blockers. Needs a fresh PriceFull verification run. Begin in a fresh chat. First step: reconcile the handoff's city list against the live DB before picking new cities (the 58→216 math assumed a 7-city baseline that was already wrong).

---

## ⚠️ Watch Items (low priority, but don't forget)

- **RTL terminal display is cosmetic only.** Hebrew store names render
  reversed in psql/SSH terminal output (e.g. 'קרפור' shows backwards). The
  data in the DB is correct — verified repeatedly. Do not "fix" reversed-looking
  Hebrew in SQL strings; copy Hebrew values from the actual DB query output,
  not from terminal-rendered text.
- **Supabase Data API default change** (email received May 12, 2026): starting May 30 for new projects, October 30 for existing projects, new tables in `public` schema won't be exposed via supabase-js / REST / GraphQL by default. **Existing tables keep their grants**, so super.xxl.co.il is unaffected for current code. For NEW tables created after Oct 30, 2026, must run explicit GRANT statements if they need to be reachable from the frontend. Pattern: `GRANT SELECT, INSERT, UPDATE, DELETE ON public.your_table TO authenticated;` + RLS policy. Backend-only tables (FastAPI direct connection) are unaffected. Review Security Advisor in Supabase dashboard.
- **Carrefour 0-items issue (May 18, 2026)** — ✅ Resolved May 19. Transient upstream gap. Cron picked up 9/9 stores (32,060 items) next day.
- **Shufersal `prices.shufersal.co.il` portal outage (May 19, 2026)** — Server-side outage from ~03:00 IDT through ~16:00 IDT. Confirmed not on our end (timed out from laptop + Kamatera + multiple browsers). Recovered late afternoon — 16:35 IDT cron run got 1/1 files, 4,939 items. Total chain still slow (~28 min in Shufersal phase) due to page-scan bottleneck — accelerates the "Shufersal page-scan cache" pending session priority.

---

## 🔑 Key Architectural Decisions

- **Full Kamatera consolidation (May 18, 2026)** — All production infra on Kamatera Tel Aviv VPS ($17/mo after Jun 17 free trial expires): Postgres + scraper cron + FastAPI behind nginx + Let's Encrypt. Railway fully decommissioned May 18. Single host, single bill, no cross-host network latency, no geo-block issues.
- **SQLAlchemy everywhere** — scrapers are DB-agnostic.
- **Snapshot pricing only** — not yet tracking history (deferred to 9d).
- **Phased city expansion strategy** — currently 58 stores across 14 cities (verified May 24, 2026 — see live city dropdown). Sessions 9d-2+ expand to all 100K+ cities (~216 stores). Sessions 11+ expand to 50K+ cities (~540 stores). Full coverage requires AWS/GCP migration when Railway hits limits.
- **Daily cron at 10am Israel time (7am UTC)** (changed from 3am in session 9n — portals publish 02:09–05:00 UTC; 10:00 IDT clears the window).
- **Canonical names via weighted token voting** — ~93% stability across runs, ~7% updated per fresh canonical run.
- **Skipped Hazi-Hinam scraper** — HTML-scraping is too fragile vs Cerberus JSON APIs.
- **Brand color: emerald-600 (#059669)** — used for primary CTAs, basket-limit toast.
- **Freemium model REDEFINED (session 9a → confirmed 9c)** — Free tier is the honeypot: search, view prices, basket comparison, save baskets, favorites, recent searches — ALL free, ALL unrestricted. Paid tier benefits will be: ordering through us (12+ months out, requires chain partnerships), exclusive deals, price-drop email alerts. The original "freemium = limit free users to 25 basket items" framing was retired in 9a and codified in 9c — only logged-out users see the 25-item cap (as a signup nudge); logged-in users get a generous 150 (effectively unlimited for human use).
- **Verification-before-scrape pattern (9d-1)** — `scheduled_stores.yaml` is the intent/wish-list, `active_stores.yaml` is the actually-scraped list, gated by per-portal `verify_publishes_pricefull()` check. Prevents silent scrape failures from sub-chain heterogeneity (Shufersal Sheli format, warehouse nodes, etc.). Verification reports go in `db/verification_report_9d1.md`.
- **Procfile is authoritative for Railway commands (9d-1)** — was Railway-UI-only before, which caused scraper-cron to silently revert to `fetch_off` on scheduled runs while manual triggers worked. Procfile now defines both `web:` (gunicorn API) and `cron:` (scraper price scrape). Survives service recreation.
- **Carrefour Israel under Global Retail C.I.** — chain_id `7290055700007` publishes Carrefour + Mega + Yenot Bitan stores combined. We display as "קרפור" but accept all sub-brands. Bnei Brak has zero Carrefour/Mega/Yenot Bitan presence (verified manually) — not a data bug.
- **`publishprice` portal type (9d-1)** — new base class `scraper/publishprice.py`. JS-embedded file listing pattern. Currently only Carrefour, but reusable.
- **Geo-blocking discovered (9d-1)** — `prices.carrefour.co.il` and `laibcatalog.co.il` (Victory) block non-Israeli IPs. Confirmed by Eltzur via VPN test. Other 5 chains' portals don't enforce this. Migration path TBD in 9g (EU-West region trial first, Israeli VPS as fallback).
- **Scraper performance bottleneck — resolved 9g-1 + 9g-3 (May 17, 2026)** — Old Railway US-West: ~1.5min/store from per-row INSERT round-trips + cross-continent DB writes. Resolved via (a) batched VALUES inserts at 1000 rows/statement across items, item_chain_names, prices tables, (b) deduplication of source-XML duplicate item_codes to prevent Postgres CardinalityViolation on ON CONFLICT, (c) Postgres on same Kamatera VPS as scraper = localhost writes. Result: 58 stores in 3m31s. Scales fine to 216 stores (estimated ~13 min) and 540 stores (estimated ~30 min) without further changes.
- **Shufersal sub-chain landscape (9d-1, field intel from Eltzur)** — same chain_id `7290027600007` publishes: דיל (Deal, mainstream discount), שלי (Sheli, neighborhood), אקספרס (Express, convenience), יש/יש חסד (Yesh, haredi sector — dominates Jerusalem/Bnei Brak), Universe (hypermarket), BE (pharmacy/health). NOT all sub-formats publish individual PriceFull files. "Lowest store_id" selection rule biased toward old Jerusalem Sheli stores in 9d-1 — needs format-aware refactor in 9e.
- **StoreNext: free CSVs only, paid tier rejected (May 17, 2026)** — Free CSV branch lists at `storenext.co.il/תמיכה-ושירות/` remain usable for 9e Registry (store_id, EDI barcode, store name with format prefix, all 7 EDI-using chains). **Paid tier was investigated and rejected: NIS 30K one-time for a single Excel catalog export — pricing doesn't fit pre-revenue stage.** Revisit at scale. GS1 IL is the better-shaped catalog data source going forward.
- **Master brand (xxl.co.il) is the canonical surface (9f)** — xxl.co.il is the portal; verticals are paths on it (`/vacation`, `/fashion`) NOT subdomains. Earlier plans for `fly.xxl.co.il`, `hotel.xxl.co.il` etc. are obsolete.
- **Portal verticals collapsed: חופשות = flights + hotels (9f)** — earlier 4-tile design reduced to 3-tile (מצרכים, חופשות, אופנה). חופשות is the single travel vertical covering both.
- **AI search bar uses mocked keyword router for now (9f)** — `web/src/utils/portalSearchRouter.ts` exports `classifyAndRoute(query)` with hardcoded Hebrew + English keyword lists. Function signature designed for one-line swap to Claude Haiku in 9h.
- **Hostname-based routing in React (9f)** — `App.tsx` has `isPortalHostname()` checking `window.location.hostname`. When true (xxl.co.il / www.xxl.co.il / localhost?portal=1), `/` renders `PortalPage`. When false, falls through to `AppShell`. Briefly tried .htaccess 302 redirect mid-session but rejected — left `/portal-preview` in URL bar.
- **Email signup on בקרוב pages is intentionally dummy (9f)** — `console.log` only. Wiring to real backend deferred to 9f-followup.
- **Offsite backups via Backblaze B2 (May 19, 2026)** — Daily pg_dump custom-format → local `/var/backups/scrp` (rotation: 7 daily, 4 weekly Sundays, 6 monthly 1st-of-month) → uploaded to B2 bucket `xxl-scrp-backups/daily/`. Uses rclone native B2 backend (NOT S3-compat — S3 layer rejects bucket-scoped keys with "not entitled" error due to object-lock metadata queries). Cost: ~$0/mo (10 GB B2 free tier; current ~10 MB/day × 365 = ~3.6 GB/year max with rotation).
- **Shufersal scraper timeout bumped 30s → 60s (May 19, 2026)** — `scraper/shufersal.py:77`. Shufersal's portal goes through slow patches; 30s was tripping on healthy responses. Committed `389bd3e`. Not a fix for actual outages, but improves resilience to slow-but-up days.
- **Rami Levy canonical `sub_chain_id='001'` (9k)** — split-store duplicates merged onto the `001` row (carries name/city). The legacy `sub='1'` rows were pre-9j-followup artifacts; `upsert_store` padding now prevents recurrence.

---
## Operating patterns Established

### Ground Rules (apply to every new chat)

1. **Short responses.** Status or diagnosis, suggested fixes with the
   recommended option marked, then the tasks/commands. No full thought
   process, no mid-chat pivots.
2. **Fool-proof = delegate to Claude Code.** Maximize work handed to CC.
   All prompts in copy-paste code blocks. Keep manual effort to a minimum.
3. **Read previous chats for context** before starting work, to avoid
   repeating past mistakes.
4. **Handoff maintenance is CC's job.** CC updates handoff.md, commits, and
   pushes automatically at session end (and when asked mid-session). The chat
   assistant drafts the entry content; CC owns writing it to the file and
   committing — it's faster and cleaner.

- **One chat = one session** — Long conversations balloon in token cost (cumulative history is re-read every turn, so turn 60 of a chat costs much more than turn 5 of a new one). At natural breakpoints (end of session, deploy verified, phase complete), START A FRESH CHAT and paste handoff.md as the first message. Yesterday's debugging context isn't useful for today's feature work — it's just expensive baggage. Especially: avoid trying to squeeze a new session into an existing long chat just because we're already talking. Lesson learned in 9c when token budget hit limits faster than expected during Phase 2.

### Operating Policies (codified 9d-3 — apply to every new session)

**A. Investigate the source on the web BEFORE designing a workaround.**
When a task needs information we don't have — an endpoint's behavior, a portal's
structure, what data a chain publishes — Claude does NOT reverse-engineer alone.
Claude first asks Eltzur to check the source on the web (portal page, dropdown,
published credentials, docs). Proven in 9d-3: the Shufersal store dropdown and
the gov.il credentials list each replaced a complex workaround with a five-minute
look at the actual website. Default order: identify unknown → ask Eltzur to check
the source → design against real data. Cheaper for both sides, and humans bring
lateral-thinking AI structurally lacks.

**B. CITY_CODES policy — see comment in cerberus.py.**
Real municipalities only. Never regional councils (מועצה אזורית). Never
bulk-import locality.xls (it mixes cities and regional councils). Authoritative
sources: C:\scrp\data\locality.xls (MOI master) and Israel Post's
סמל_ישוב_דואר_ישראל.pdf. DO NOT use kod_yeshuvim_02.xls — it's the CBS
internal serial system, incompatible number space.

**C. CC's "summary instead of data" pattern — always ask for the raw data.**
CC consistently substitutes a confident summary for the raw data it was asked to
produce. Examples from 9d-3: pf_rows[0] (skipped picking newest), "157 doralon
stores, ship it" (hid city-coverage issue), the locality.xls "wrong code system"
verdict (one sheet, didn't check others), "Nahal Sorek MOI dual-name situation"
(hallucinated explanation), three rounds of Fresh Market / Tiv Taam summaries
without tables. When CC sends a summary, ASK FOR THE RAW DATA explicitly and
don't approve until you see it. Use file-redirect (`> outfile.txt`) when stdout
truncates.

**D. CC file-read collapse — ctrl+o expands it.**
When CC reads a file or produces long output, the result often collapses to
"[Read 1 file]" in the VS Code display. The bytes are still there — pressing
ctrl+o in the CC pane expands them. If CC's third reply on the same ask still
has no data, suspect a collapsed read before suspecting CC.

**E. PowerShell stderr handling.**
PowerShell treats any stderr output (including Python's INFO logs) as a
NativeCommandError and shows it in red. Not a failure — judge scripts by stdout.

**F. Hot-path discipline (4 clean commits in 9d-3):**
Read-and-report-STOP on scraper hot paths. Verify mechanism via read-only script
before adding to cron. Multi-stage prompts with STOPs between stages. Single
coherent commit at the end. Worked for both Shufersal and Tiv Taam.

### Store-count escalation rule (Dude, 2026-09-28)
"if there are issues with 1 or up to 10 specific stores, please flag them for manual review cause running prompts to handle a single store issue is to costly and time consuming. the rule of thumb is that up to 10 - manual only. 10 to 50 flag is and ask if to run a fix or handle manually. over 50, try to fix 2-3 times and if not resolved, consult with me before running another prompt."
- 1–10 stores: manual only. List them (store_fk, chain, store_id, name, issue) and write no fix prompts.
- 11–50 stores: flag them with the same list and ask Dude whether to fix by prompt or handle manually. Wait for his answer.
- More than 50 stores: prompt fixes are allowed, at most 2–3 attempts. If still unresolved, consult Dude before any further prompt.
- The count is distinct stores affected by one issue, not rows.

## 🔗 External Data Source Status

- **gov.il price transparency XML** — primary source. Working.
- **Cerberus portal** (`url.retail.publishedprices.co.il`) — used by Yochananof, Keshet, Osher Ad, etc. Login-based.
- **Shufersal direct** (`prices.shufersal.co.il`) — open HTTP, no auth.
- **Rami Levy direct** — open HTTP.
- **Victory** — REST API, custom scraper (~55 lines).
- **OpenFoodFacts** — ❌ ABANDONED. Tested in past sessions, found it out of date and nearly empty for Israeli barcodes. Code exists in repo but do not invest more effort here.
- **StoreNext** — outreach pending (Eltzur left contact details May 12). Free CSV branch lists per chain confirmed working (`storenext.co.il/תמיכה-ושירות/`). Paid tier scope TBD. Will inform 9e Registry session.
- **OpenIsraeliSupermarkets Kaggle dataset** — bookmarked for future price history (9d).

---

## 📂 File Location Reference (portal files added in 9f)

When asking CC to modify portal/supermarket code, here are the key files and what to look for. Line numbers omitted (they drift) — use the descriptive anchors instead.

| File | Purpose | Anchors when modifying |
|---|---|---|
| `web/src/pages/PortalPage.tsx` | Portal landing page | Search for: `<XxlLogoPortal>` hero, rotating placeholder `useEffect` with 4 examples, the 3 vertical tiles (search "מצרכים"), value-props strip (search "חינם לחלוטין"), sub-header "הפורטל שהופך כסף רגיל לכסף חכם" |
| `web/src/pages/ComingSoonPage.tsx` | Shared template for /vacation and /fashion | Email form, regex validation, `console.log('[ComingSoonPage] Email signup:', ...)` — this is the line 9f-followup replaces with real backend |
| `web/src/pages/VacationPage.tsx` | Thin wrapper passing חופשות + Sun icon to ComingSoonPage | — |
| `web/src/pages/FashionPage.tsx` | Thin wrapper passing אופנה + Shirt icon to ComingSoonPage | — |
| `web/src/components/XxlLogoPortal.tsx` | Portal animated logo (duplicate of XxlLogo.tsx with portal tagline) | Tagline "קונים חכם · חוסכים בענקקק" on SVG textPath, fontSize 28, letterSpacing -0.5. sessionStorage key `xxl_portal_animated_this_session`. |
| `web/src/components/XxlLogo.tsx` | Supermarket app logo — **DO NOT modify for portal changes** | Hardcoded tagline "חוסכים בענקקק". Duplicate this file if a new tagline is needed elsewhere. |
| `web/src/utils/portalSearchRouter.ts` | Mocked AI intent classifier | Exports `classifyAndRoute(query)`. **Swap this function body when wiring Claude Haiku in 9h** — keep the signature. |
| `web/src/App.tsx` | Top-level routing + hostname detection | `isPortalHostname()` at top of file. Top-level `<Routes>` with portal routes, conditional `/`, and `/*` catch-all → `<AppShell />`. AppShell wraps the supermarket app with its own internal `<Routes>`. |
| Hostinger `public_html/.htaccess` | Server-level routing (NOT in repo) | Minimal React Router SPA fallback only. If adding server-level rules later (cache headers etc.), insert BEFORE the SPA fallback block. |

---
## GS1 catalog value assessment (September 23, 2026 — measured, decision pending)

Triggered by a business question: is GS1 integration worth its cost given thin coverage. Measured, not estimated:

- Catalog total: 165,414 items.
- `name_source='gs1'`: 16,161 items (9.77%) — handoff's earlier 10,585 figure was stale.
- `name_source` has exactly two values: `chain` (90.23%) and `gs1` (9.77%), no NULLs, no third source. The weighted token-voting majority-vote algorithm (scraper/canonical.py) is NOT a separate name_source — its output is stored under `chain`. So canonical naming is ~90% solved by that algorithm alone, independent of GS1; GS1 only supplements the remaining ~10%.
- GS1 detail data (kashrut/nutrition/ingredients/images) actively served to users: 11,222 items (6.78% of catalog) — the active-GS1-row-filtered figure, which is what the API actually serves; 11,496 rows carry `full_content` before that filter.
- No usage/analytics tracking exists in the database at all (3 users, 1 favorite, 1 saved basket) — so whether GS1-matched items skew toward popular products, which would materially change the value calculus, is currently unanswerable from any data we hold. Flagged as a gap worth closing independent of the GS1 decision.
- Open and blocking a real decision: actual GS1 subscription/access cost (business fact, not in the codebase) and a manual quality comparison of GS1 names vs. the chain/token-voting names for the ~10% overlap (not yet done).

## "What's Good for Europe" GS1 reform (September 23, 2026 — rollout 12.10.2026, transition through 1.1.2028)

Read-only investigation complete, doc fixed. New retailer-outbound JSON fields (importer/distributor, marketing messages, 4-column nutrition table, additional nutrition table, image-deletion indicators) land intact in the already-stored raw `full_content` JSONB for any product we've detail-fetched — nothing breaks, nutrition parsing just truncates to column 1 silently (works today, would misreport `basis` if GS1 ever reorders columns). The cron-path `content` field was investigated and confirmed always empty (9,350 rows sampled across a quarter of the catalog) — safe to keep ignoring. `docs/gs1_integration.md` was stale (said Phase 2 wasn't built when it is) — fixed, along with a supplier-count correction (77→107, both figures kept with dates).

Two real, pre-existing gaps this surfaced, independent of the Oct 12 date, still awaiting Dude's go-ahead since they touch scraper-adjacent code:
1. No image-deletion handling anywhere — a product whose image is deleted upstream keeps serving the stale cached JPEG indefinitely, to web and mobile both.
2. Serving layer only reads 3 of the ~11 available `product_info` branches from `full_content` — most GS1 detail data (including all the new European-reform fields) is stored but never surfaced.

---

## Mobile /search latency investigation (September 24, 2026 — read-only, no fix applied)

Triggered by the mobile Search tab timing out (see docs/handoff_mobile.md). Read-only EXPLAIN ANALYZE investigation on production, nothing created or modified.

Corrects a standing assumption from SU10A-3 ("no trigram index exists, so the LIKE was already a full seq scan over 139K items" — noted there as performance-neutral). It is not neutral at current data volume, but it is also NOT the bottleneck: for query "חל", find_barcodes_with_relevance's seq scan on items (165,547 rows, 35 MB heap, fully cached) costs 0.15s of a ~27s request — under 1%. pg_trgm is already installed (v1.6, confirmed), so a trigram index is cheap to add, but would only recover that ~0.15s.

The real cost (99% of the ~27s) is fetch_prices: for "חל", 7,543 matching barcodes resolve to 390,325 price rows fetched, sorted, and grouped in Python — before the API slices 30 for the page. Pagination happens AFTER the expensive work, so offset=0 costs the same as offset=300. The _PRICE_SQL plan shows a full parallel seq scan of prices (~7.7M row-visits across 3 workers) plus a disk-spilling sort (ORDER BY p.item_price exceeding work_mem — external merge, ~40 MB/worker, 15,453 temp blocks written) plus 122,139 real (non-cache) buffer reads.

Table sizes at measurement time: items 165,547 rows/58MB total; item_chain_names 348,248 rows/325MB; prices 7,686,194 rows/3,749MB. Existing indexes on items/item_chain_names name columns are plain btrees — none can serve a leading-wildcard LIKE, which is why the planner ignores them regardless.

**Implication for a future fix session:** a trigram index alone would NOT meaningfully fix this — don't ship one expecting it to. The real lever is architectural: push LIMIT/OFFSET before the price fetch so only the ~30 barcodes actually shown get their prices pulled, not all matches. This touches _PRICE_SQL, which SU10A-5 already flags as hot-path-with-regression-history (the enable_nestloop collision) — treat with the same caution.

**Related, free, not yet done:** SU10A-8 flagged Postgres config (shared_buffers, effective_cache_size, work_mem) as still sized for the pre-RAM-bump 1.9 GiB box, "flagged, not fixed... decide deliberately next session" — that session never happened. Retuning for the current 3.8 GiB box is free capacity already paid for, would likely reduce both the disk-spill and the real buffer reads measured here, and should probably happen as part of whichever session tackles this properly.

**Status: parked, not a current priority** (per Dude, Sept 24 2026). This entry is scoping for whenever it's picked back up, not a task in progress.

---

## Session SU10S-21 (September 28, 2026) — stable promo pagination; /promos/{store_fk} no longer 500s

Commit `ed38bf0`. API deployed, curl-verified, and the web promos page checked in a browser. Both SU10S-20 findings are closed — and a worse one surfaced (below, ⚠️).

### 1. `/promos/grouped` pagination

The `ORDER BY` now ends in `store_fk, item_code, promo_id`. That triple is **UNIQUE** (`promos_store_fk_item_code_promo_id_key`, and `promo_id` is never NULL across 1.4M rows), so the order is **total**. `/promos/grouped` is the only offset-paged promo read; `/promos/today` is a single `LIMIT` with no offset.

**Paging King Store fully, 300 per page, `offset = rows.length` (as the web does):**

| | total | paged | duplicated | missing |
|---|---|---|---|---|
| before (production code) | 45,431 | 45,431 | **12,952** | **12,952** |
| after | 45,431 | 45,431 | **0** | **0** |

Via the live API after deploy: 6 pages of 300 equal one fetch of 1,800 **row for row, in order**; the same page fetched twice is identical. **In a browser** (`super.xxl.co.il/promos`, "טען עוד" ×3): the page requested offsets 0/300/600/900, all 200, and those four pages re-fetched from the page equal a single 1,200-row fetch row for row. No frontend change.

(19 rows in the first 1,800 are identical to another row in every visible field — distinct `promo_id`s the chain published with the same description and dates. Genuine data, not paging.)

**EXPLAIN gate — both measurements, honestly:**

| | sequential (old ×5 then new ×5) | interleaved (random order) |
|---|---|---|
| King Store page (300) | +27.8% | **+17.4%** (n=9) |
| default page (500) | +17.2% | **+9.7%** (n=7) |
| offset 15,000 (300) | +20.7% | **−9.9%** (n=3) |

The sequential run was order-biased; this box swings widely (the identical old King query measured 688 ms in one run, 1,075 ms in the next). Interleaved, every case is inside the 20% gate, so it shipped. An index cannot help here — the sort is over computed columns (chain → city → branch plus a discount derived from a join). A single-integer `p.id` tiebreak was also measured and is not better (+6.1% / **+23.7%** / −0.8%). Deep pages were already slow before this change (~24–34 s at offset 15,000 — an external merge sort spilling ~50 MB to disk).

### 2. `/promos/{store_fk}` and `/promos/store/{chain}/{store}`

Now select `discount_pct` (`_PROMO_ITEM_PCT_SQL`, read-time, never stored). Verified on production: **0 of 724 rows fail `PromoItem` validation** across Osher Ad 843, Rami Levy 2108, Hazi Hinam 32698; all return 200 live, and a dead store (23595) returns `[]`.

The expression was chosen from the data, not copied — **neither existing formula was right**:
- `/promos/bulk`'s CASE (same `PromoItem` model, used by the web `ProductCard`) handles weighed items but has no spend guard and gives rate promos nothing.
- the canonical `_UNIT_PRICE_SQL` (grouped, search promo-pick) handles spend and rates but requires `min_qty BETWEEN 1 AND 24` — so it **misses Rami Levy's weighed-item promos**, whose `min_qty` is **0.01** (a minimum weight).

| promo shape | discount_pct |
|---|---|
| `min_qty > 24` (a spend threshold, Rami Levy) | NULL |
| price, `min_qty ≤ 1` (incl. 0.01 weighed) | (shelf − price) / shelf |
| price, `min_qty 2–24` (bundle) | (shelf − price/qty) / shelf |
| rate only, single unit, **rate < 100%** | the rate (bp ÷ 100 above 100) |
| rate = 100% / multi-unit rate / price = 0 | NULL |

A 100% rate is the **free unit** of a "1+1"/"2+1" or a gift coupon (76K Rami Levy rows read "2+1 הזול מבינ"); every Hazi Hinam rate promo is multi-unit (5000–10000 bp on "1+1" / "השני ב50%"). Claiming 100%, or guessing a per-unit split, would be exactly the per-chain assumption CLAUDE.md forbids. **Where a chain publishes its own DiscountRate, the computed value matches it to rounding** (27.5 vs 27.52, 19.2 vs 19.19, 7.6 vs 7.56, 16.8 vs 16.76). Hazi Hinam "2 ב-25₪" → 26%; its "1+1" 10000 bp → NULL.

### ⚠️ Found — search prices ~40,000 quotes at ₪0 (pre-existing, NOT fixed)

`_PROMO_PICK_SQL` (the hot path behind /search, /compare, /product, /basket/compare) prices a rate-only single-unit promo as `shelf × (1 − rate)`. With the ubiquitous **rate = 100** ("2+1", "1+1", coupons) that is **₪0**, and ₪0 then wins as the product's cheapest price. Live example: `/product/7290118071310` "בצק משחק -כלב", Rami Levy אילת, shelf ₪11.00 → `price 0.0`, `cheapest_price 0.0`, promo "מגוון מוצרי חזרה לבית הספר 2+1 הזול מבינ".

| chain | ₪0 quotes | items |
|---|---|---|
| רמי לוי | 38,269 | 1,591 |
| ויקטורי | 1,357 | 38 |
| שופרסל | 490 | 15 |
| קרפור | 195 | 82 |
| שפע ברכת השם | 9 | 9 |
| קשת | 5 | 5 |

The grouped view's `_UNIT_PRICE_SQL` has the same rate branch (with no `min_qty` check at all), so it labels these rows "100% off". **Fix:** the same guard `_PROMO_ITEM_PCT_SQL` uses — a rate counts as a plain discount only when it is below 100% on a single unit. It is a change to the hot-path `_PROMO_PICK_SQL`, so it needs its own EXPLAIN-gated session; not slipped in here. Roadmap, top.

### Also found (pre-existing, not fixed)

- **Weighed-item promos are invisible to search and grouped.** `_PROMO_PICK_SQL` and `_UNIT_PRICE_SQL` both require `min_qty BETWEEN 1 AND 24`, so Rami Levy's `min_qty = 0.01` unit-price promos (e.g. ₪34.90 vs ₪49.90 shelf) are never picked and show as "basket" in grouped.
- **`/promos/bulk` and `/promos/{store_fk}` now compute `discount_pct` differently** for spend rows, `price = 0` rows and sub-100% rate rows (bulk: no spend guard, `price = 0` → 100%, rates → NULL). Recommend moving bulk to `_PROMO_ITEM_PCT_SQL` — it is web-visible (ProductCard), so it was left for its own change.

---

## Session SU10S-21b (September 28, 2026) — 100% rate promos no longer price items at ₪0

> Renamed from SU10S-22 in SU10S-26: that ID was also used for the mobile permission-order session. Git history for commits `abae630` and `c013a8f` keeps the original wording.

Commit `abae630`. API deployed and verified live. Closes the ⚠️ item found in SU10S-21.

### The bug

`_PROMO_PICK_SQL` — the LATERAL behind /search, /compare, /product and /basket/compare — priced a rate-only, single-unit promo as `shelf × (1 − rate)`. The chains publish **rate = 100** for the free unit of "1+1" / "2+1" deals and for gift coupons (Rami Levy: "מגוון מוצרי חזרה לבית הספר 2+1 הזול מבינ"), so those became **₪0 quotes that won as the product's cheapest**. Live example before the fix: `/product/7290118071310` "בצק משחק -כלב", Rami Levy אילת, shelf ₪11.00 → `cheapest_price 0.0`.

### The fix — one guard

The rate branch now also requires the effective rate to be **< 100%**. A 100% promo no longer sets a price; the quote shows the shelf price, or another genuine promo for that store if one exists. Nothing else in the expression changed.

**Deliberately NOT changed: `_UNIT_PRICE_SQL` (the grouped promos view).** Every rate-≥100 promo has `discount_price = 0` (78,335 single-unit + 11,389 multi-unit rows; none NULL), and grouped classifies those as **`gift`** — which is what the web promos page's "1+1 / מתנה" filter selects, rendered via `reward_type`. Nulling their unit price there would have reclassified them as `basket` and broken that filter. Grouped never produced a ₪0 *cheapest price*; only the search path did.

### Verification (production)

| | before | after |
|---|---|---|
| affected (store, item) quotes priced ₪0 | **19,721** over 1,720 items | **0** |
| quotes ≤ ₪0 anywhere in those items | — | 0 |
| `/product/7290118071310` cheapest | ₪0.0 | **₪11.0** |

(19,721 is distinct store/item quotes; SU10S-21's "~40,000" counted promo rows, several per quote.)

Old-vs-old baseline in the same run: 0 differences. The first run showed 8 changes outside the affected set while today's cron was finishing (its last chain started 11:03, the proof ran ~11:14–11:22); a full rerun showed **0** outside changes. Cause not pinned to a specific write — recorded as observed.

**EXPLAIN (ANALYZE), exact non-city price statement, interleaved:** barcode −0.7% (n=15), 10-item basket +3.9% (n=15), `q=חלב` −8.5% (n=3); identical nested-loop counts — the plan did not change.

Live after deploy: one affected item from each of the six chains → 0 zero-priced quotes each; `/basket/compare` normal; `/health` 200.

### For Dude — a product question, not a bug

`/product/7290004131074` (חלב 3% קרטון) now shows cheapest **₪0.90**: Rami Levy's **coupon** "קופון חלב תנובה קרטון 1לי ב1שח". It is a genuine published promo, correctly parsed. Whether coupon- or club-conditional deals should rank as a product's plain "cheapest" — or be shown but not win — is a product decision.

### SU10S-21b — gates run as specified by Dude, and attempt 2 (zero shelf prices)

Dude's gate list arrived after `abae630` was already deployed, so the **"before" count is reconstructed**: the previous code (`abae630^`) run read-only on the same current data. Counts are over **all live price rows**, evaluated in SQL with the real promo-pick (not a sample), plus the zero-shelf rows (`c013a8f`).

**Rows where search returns an effective price ≤ 0, by chain:**

| cause | before | after `abae630` | after `c013a8f` |
|---|---|---|---|
| promo priced at 0 (100% rate "2+1"/"1+1") | **19,684** — רמי לוי 18,160 · ויקטורי 1,357 · קרפור 153 · שפע ברכת השם 9 · קשת 5 | 0 | 0 |
| shelf price published as 0.00 by the feed | **411** — קשת 306 · חצי חינם 101 · רמי לוי 4 | 411 | **0** |
| **total** | **20,095** | 411 | **0** |

**Effective price above shelf: 0** before and after (the promo-pick only attaches a promo that beats the shelf price, and the effective price is the minimum of the two).

**Attempt 2 (`c013a8f`)** was needed because the gate counts *every* ≤ 0 row, and 411 remained that no promo caused: exact ₪0.00 shelf prices in the Keshet / Hazi Hinam / Rami Levy feeds (rice, produce such as avocado and watermelon — 98 of Hazi Hinam's 101 are priced above 0 elsewhere). `fetch_prices` now drops shelf rows with `item_price <= 0`, in the SU10S-20 post-filter wrapper — **no SQL change** — before and independent of the liveness filter, so it holds even when that fails open. Consequence: ~115 items (mostly Keshet) whose ONLY price anywhere was ₪0.00 now have no quotes, so they leave search results instead of showing ₪0.

**Timings, old vs new, random interleaved order:**

| query | pricing statement (EXPLAIN, `abae630`) | whole `fetch_prices` (`c013a8f`) |
|---|---|---|
| `חלב` (3,046 codes) | +3.1% (n=3) | −0.9% (n=3) |
| `במבה` (short, 85 codes) | +1.7% (n=9) | −1.8% (n=15) |
| `שוקולד חלב עם אגוזי לוז` (long, 28 codes) | −7.1% (n=9) | +3.9% (n=15) |

**Live spot-checks:** `/product/7290118071310` → cheapest ₪11.00, the Rami Levy אילת quote ₪11.00, 0 zero-priced quotes. `/basket/compare` with that product + 2× milk 7290004131074 → Rami Levy wins at ₪23.40 = ₪11.00 + 2 × ₪6.20, no chain total ≤ 0. (Basket prices from shelf by design, so it was never exposed to the promo ₪0.) One affected item per chain via `/product`: 0 zero-priced quotes each.

**A testing trap worth knowing:** `curl` from Git Bash on Windows sends Hebrew query strings as `???` — `/search?q=חלב` then returns 0 matches and looks like a broken search. The response echoes `query`; check it. Test Hebrew queries from the server, or URL-encode them explicitly.

Commits: `abae630` (promo rule), `c013a8f` (zero shelf prices).

### Still open (roadmap)

- Weighed-item promos (`min_qty = 0.01`) are invisible to search and grouped.
- `/promos/bulk` `discount_pct` should move to `_PROMO_ITEM_PCT_SQL`.
- Minor, grouped only: Hazi Hinam's multi-unit basis-point rates ("השני ב50%", 5000 bp, `min_qty 2`, `discount_price` NULL — 281 rows) are shown as a flat 50% off, overstating the per-unit saving.

---

## Session SU10S-25 (September 28, 2026) — geocodes accepted by address match, not place type; priority review list cleared

Commits: `c795ce3` (geocoder, exporter, city overrides, roadmap), plus this docs commit. Deployed to the server tree (`git pull`); the API is not affected (no module it imports changed), so no restart.

**The bug.** SU10S-10's acceptance judged each Nominatim result by its OSM class — reject `amenity/*`, flag `shop/*` — and only ever looked at the FIRST result (`limit=1`, no `addressdetails`, so nothing could even be compared with the input). Osher Ad 011 (id 849) came back as "Supermarket Osher Ad, 11, HaKishon, Bnei Brak" — an exact hit — and was flagged because OSM tagged it a supermarket.

**The rule now (`scripts/geo_nominatim.py`, `evaluate()`):** `limit=5` + `addressdetails`/`namedetails`/`extratags`; still 1.1 s/request, same User-Agent. A candidate is

| reason | when | result |
|---|---|---|
| `ADDRESS_MATCH` | road == input street (after stripping רחוב/רח'/שד'/שדרות/דרך, quotes, punctuation; optional leading ה) AND house number equal (a range 7-9 covers 7..9; a letter must agree only when both sides carry one) AND returned city == `city_canonical` AND ≤ 25 km from the **CBS** centroid | `address` |
| `STREET_MATCH` | road matches, candidate has **no** house number | `street` |
| `CITY_MISMATCH` | road matches but Nominatim's city/town/village/municipality differs | never accepted |
| `>25km` / `NO_MATCH` | — | never accepted |

Place type plays no part in acceptance; among several address matches: a shop whose name/brand holds the chain name, then building/house, then anything. SU10S-10's "any `place/*` → street" leniency is gone. **The 25 km guard now measures from the CBS city centroid**, not the store's current pin (which, for a re-geocoded house-level row, was its old location). City names are compared through the same tables `city_canonical` is built from, after folding dashes: Nominatim writes `תל־אביב–יפו` with a maqaf and an en dash — the first dry run misreported 8 Tel Aviv stores as CITY_MISMATCH until that was folded.

**Cache:** the key now includes `limit`/`addressdetails`/`namedetails`/`extratags`, so SU10S-10's single-result entries are never reused (they stay in the file, harmless). **Consequence: the next Sunday `scrp-geocode` re-asks every target — about 212 stores, ~4 min** — once; after that the cache covers it again.

**Manual pins:** `geo_source = 'manual'` rows are never re-geocoded, by any path (`_TARGETS_SQL` and `needs_geocode()` for `--ids-file`). Verified: `select_targets` over all stores selects 212 rows, **0 of the 5 manual rows**. `--include-overrides` additionally forces house-level rows with an `address_override`; without it they are retried only when their input changed (unchanged behavior).

**Dry run** (216 rows = 42 priority + 174 optional from `~/branch_review.xlsx`; 240 requests; `C:\xxl-archive\geocode_dryrun_su10s25.xlsx`): priority → address 35, street 1, CITY_MISMATCH 1 (993), NO_MATCH 4, not geocodable 1 (35348). Optional → 0 upgrades: NO_MATCH 99 (Nominatim returns **nothing at all** for 99 of them — not a matching problem), not geocodable 75.

**Applied** (backup first: `~/backups/pre-su10s25-stores-20260928T141650.dump`; one transaction, every UPDATE guarded on the row's current precision and input):

| | stores |
|---|---|
| priority ADDRESS_MATCH → `address`, `geo_source='nominatim'` | 35 |
| priority STREET_MATCH → `street` (291, Dude: "good enough") | 1 |
| Dude's coordinates → `address`, `geo_source='manual'` | 5 — 991, 993, 2164, 2180, 2204 |
| optional sheet | 0 (skipped by instruction, whatever the result) |

42 priority stores: **before** 41 city + 1 none → **after** 35 address/nominatim + 5 address/manual + 1 street + 1 none (35348). Dude's pins lie 0.8–3.1 km from the corrected city's CBS centroid.

**City fixes** — `STORE_CITY_OVERRIDES` entries AND a direct `city_canonical` set:
- 991 Keshet 005 → חיפה. Its address "תל אביב 11" is a STREET called Tel Aviv, in Kiryat Eliezer; the feed's city is the street name (same trap as Victory 094).
- 993 Keshet 010 → כרמיאל (feed: גבעת רם; OSM found בציר only in Sharigim).
- 2164 Rami Levy 064 → אור עקיבא (feed: חיפה; the store is in David Center, הכרמל 1).

Both chains are Cerberus scrapers, which apply `city_override` to the raw `city` nightly. **Cascade dry evaluation** (`build_city_canonical`'s layers replayed over all 1,197 stores, old vs new override table, `main()` NOT run — it rewrites `data/city_canonical_review.csv`): after tomorrow's nightly scrape writes the overrides into raw `city`, **exactly 991, 993, 2164 change, each to the corrected city; nothing else changes.** Caveat, until the next 10:00 cron only: 2164's raw city is still `חיפה`, an exact CBS name, so Layer 1 wins over the Layer 2 override — a full `build_city_canonical` + apply run before then would put it back to חיפה. Do not run that rebuild before the next cron.

**35348 (Hazi Hinam 219):** `city_canonical = ראשון לציון`, `address_override = הכשרת הישוב 3` (Dude's hand edit in `branch_review.xlsx`). **Coordinates NOT copied: store 201 (id 32697) has no coordinates at all** — `lat`/`lon`/`geo_precision` NULL, no address. Both will be placed by Sunday's run (`geo_centroids` fills any NULL lat that has a city; `geo_nominatim` then tries 35348's street address). 17 live serving physical stores currently have no coordinate (201 and 35348 among them) and are therefore absent from `/stores/coordinates`.

**Verified:** 849 → address/nominatim; 991 → חיפה + manual pin (32.82509, 34.98760), likewise 993/2164/2180/2204 in the API response. `/stores/coordinates` returns **846 = the SQL count** of live physical stores with coordinates (city 626 · street 106 · address 114). Note its `Cache-Control: max-age=86400` — clients may see the old pins for up to a day.

**Review list:** `export_branch_review.py` replays the new rule (new issue `GEOCODE_CITY_MISMATCH`, `GEOCODE_FLAGGED` retired, new `NO_COORDINATES`, manual rows never get a GEOCODE_* issue). Regenerated to a NEW file, **`C:\xxl-archive\branch_review_v2.xlsx`** — Dude's hand-edited `branch_review.xlsx` was not touched (sha256 `55d2ac55…` unchanged). **Priority sheet: 0 rows.** Optional ("לבדיקה"): 189 (GEOCODE_NO_MATCH 99, NO_HOUSE_NUMBER 50, PLACEHOLDER 24, NO_COORDINATES 17, NO_ADDRESS 1); Dude's "מה לעשות" notes carried into `notes` (175 rows). Bulk-awaiting-StoresFull: 467 (35348 left it — it now has an address).

**Roadmap:** under StoresFull — Hazi Hinam and Shufersal scrapers don't apply `STORE_CITY_OVERRIDES`; fix during StoresFull work.

**Known limits:** English street names are matched only for `highway` candidates (via `namedetails`); an address candidate's `road` comes back in Hebrew only. `parse_address` takes the last number in the first comma part that has a street — "שד' 26 באוקטובר 3"-style names with a number inside would mis-parse (none in this set).

---

- **2026-09-28 (SU10S-22):** store-count escalation rule added (CLAUDE.md and "Operating patterns Established" above); mobile first-launch permission order fixed (location before camera) — see docs/handoff_mobile.md.

---

## Session SU10S-26 (September 28, 2026) — ₪0 shelf prices outside search, basket 500, Hazi Hinam pins, rules/docs cleanup, handoff archived; SESSION CLOSE

This chat covered SU10S-21 (promo paging + `/promos/{store_fk}`), SU10S-21b (100% rate promos, ₪0 shelf in search — renamed from SU10S-22, see its note), SU10S-22 (mobile permission order + store-count rule), SU10S-25 (geocode by address match) and SU10S-26 (this entry).

### Part A — ₪0 shelf prices outside search (see the code commit)

Every endpoint that could carry a shelf price, and whether a ₪0 could reach the user (production DB, 411 live ₪0 shelf rows — קשת 306 · חצי חינם 101 · רמי לוי 4; counts rolled back, no API paging):

| path | ₪0 before | ₪0 after | note |
|---|---|---|---|
| `/search`, `/compare`, `/product/{barcode}`, `/basket/compare` (all via `fetch_prices`) | 0 | 0 | already dropped since `c013a8f`; raw SQL returns all 411 |
| `/promos/today` (echoes `item_price`) | 0 of 23,873 | 0 | now blanks a shelf ≤ 0 to NULL; `discount_pct` already needed `item_price > 0` |
| `/promos/grouped` (`shelf_price`, rate-derived `unit_price`, `savings`) | 0 | 0 | prices LEFT JOIN now requires `item_price > 0` — in SQL because type/band filters and the savings sort derive from it |
| `/promos/{store_fk}`, `/promos/store/…`, `/promos/bulk` | 0 | 0 | return no shelf field; `discount_pct` guards `item_price > 0` — no change |

**No active promo sits on a ₪0 shelf pair today**, so the promo changes are defensive; the exposure was already closed for users. The mobile app calls only `/product`, `/search`, `/basket/compare`, `/cities`, `/stores/coordinates`, baskets, ratings and details — no promo endpoints. Web renders `shelf_price` (PromosPage, ProductCard) but never `/promos/today`'s `item_price`.

**Real bug found and fixed — `/basket/compare` 500.** `float(row["item_price"])` with no NULL check: a promo-only quote (no shelf row) that is a chain's only row for an item raised `TypeError` → 500. Reproduced on production data with item `16000548602` (old code: TypeError; new: 10 chains priced). The basket prices from the shelf by design, so such a row — and any shelf ≤ 0 — now counts as **missing** at that chain.

**Basket gate:** Keshet-only-₪0 item `6253507160041` + milk `7290004131074` → Keshet: `6253507160041` found=false price=null, total ₪7.35 (milk only). Same before and after (fetch_prices already dropped it).

**Timings, old vs new, random interleaved:** grouped default page +2.7% (n=7), King Store page +2.9% (n=7), King Store by savings −2.5% (n=7), `/promos/today` −0.5% (n=9), 11-item basket +0.6% (n=9). All within the +20% gate. **API restart needed** to serve it (see below).

### Part B — Hazi Hinam pins (Dude's coordinates)

35348 (Hazi Hinam 219) and 32697 (Hazi Hinam 201): `lat 31.9897499922926, lon 34.7681403`, `geo_precision='address'`, `geo_source='manual'`. 32697 also `address_override='הכשרת הישוב 3'`; its `city_canonical` was already `ראשון לציון` (not NULL), so it was left as is. Dry run first, then applied. `/stores/coordinates` (its own function, called in-process against the DB) **846 → 848**, both ids present. Manual rows now **7** (991, 993, 2164, 2180, 2204, 32697, 35348).

### Part C — rules and docs

- CLAUDE.md operating rules 8-10: ad-hoc scripts under `ulimit -v` (there was no such rule in CLAUDE.md — it lived only in SU10S-20's handoff, so it was added as rule 8), never page a live API in bulk, grep for a session ID before assigning it.
- SU10S-22 → **SU10S-21b** for the promo session, here and in roadmap.md.
- roadmap.md cleaned in place (new "Done (recent)" section; GS1 decision item replaced; post-launch UI polish and mobile ESLint added).
- **This file was archived:** sessions 8L through SU10S-20 moved verbatim, oldest first, to `docs/super/handoff_super_archive.md`. 3,537 lines → 601 kept + 2,942 archive = original + 2 pointer lines + 4 archive-header lines.

### FIRST THING NEXT SESSION

(1) After the 10:00 cron, confirm stores 2164, 991 and 993 still hold the corrected cities, and 35348/32697 the manual pins.
(2) Confirm Sunday's geocode run left the 7 manual rows untouched.

Still do NOT run a full `build_city_canonical` rebuild before the next 10:00 cron has written 2164's override into raw `city` (SU10S-25).

---

## Session SU10S-28 (September 28, 2026) — SESSION CLOSE (reconciliation, docs only)

Supersedes SU10S-26's close as the final state of this chat, which ran SU10S-21, 21b, 22, 25, 26, 27 and this entry. No code, no DB writes.

- **SU10S-21 (`ed38bf0`):** promos paging made stable with a unique tiebreak `(store_fk, item_code, promo_id)` (King Store 12,952 dup/missing → 0/0); `/promos/{store_fk}` 500 fixed.
- **SU10S-21b (`abae630`, `c013a8f`; originally committed as SU10S-22):** 100%-rate promos no longer price items at ₪0; ₪0 shelf prices dropped from price reads. ₪0 prices served: **20,095 → 0**.
- **SU10S-25 (`c795ce3`):** geocodes are accepted by address match, not place type. **40 of 42 priority stores at address precision** after that session (35 Nominatim + 5 manual), 1 street, 1 none — the none (35348) was pinned in SU10S-26, so it is **41 of 42** now. City fixes for 991, 993 and 2164.
- **SU10S-26 (`8a1fb6d`, `a84d9c4`):** ₪0 shelf is "no price" on the promo endpoints too (defensive — no active promo sat on a ₪0 shelf pair); `/basket/compare` no longer 500s on a promo-only quote (it counts as missing at that chain). Hazi Hinam 35348/32697 manually pinned; `/stores/coordinates` 846 → 848; manual rows 5 → **7** (991, 993, 2164, 2180, 2204, 32697, 35348). CLAUDE.md operating rules 8–10; handoff archived to `handoff_super_archive.md`.
- **SU10S-22 (mobile `22a5f78`, scrp `9e5b4d1`):** first-launch permission order (location before camera) — **device-verified on the dev build**; store-count escalation rule added to CLAUDE.md.
- **SU10S-27 (mobile `17e7ba8`, scrp `1981ba0`):** dark-mode TextInput colours (auth/search/rating inputs use the `@/tw` TextInput). **Committed, NOT yet device-verified.** The mobile typecheck hang under CC was fixed by `npm ci` (node_modules left inconsistent after SU10S-22's `expo lint` revert); after it, only the 5 known `src/tw` errors.
- CLAUDE.md: added the Hebrew-from-Windows-shells caveat for API tests and the "patch large handoff files with a script" rule (operating rules 11–12).

### FIRST THING NEXT SESSION

(1) After the 10:00 cron, confirm stores 2164, 991 and 993 keep their corrected cities, and 35348/32697 keep their manual pins.
(2) After Sunday's 15:00 geocode run (`scrp-geocode`), confirm the 7 manual rows are untouched and that ~212 stores were re-queried under the new cache keys.
(3) GS1 image catch-up runs Sunday Oct 4 and Sunday Oct 11 (`scrp-gs1-fetch`, 14:00 IDT) — check `journalctl -u scrp-gs1-fetch` after each.

Next free session ID: see the last line of this file (moved in SU11A-4)

---

## Session SU11A-4 (October 1, 2026) — `/product/{barcode}` returns per-store quotes ("קרוב אלי" real fix)

**Correcting the record.** SU11A-2's roadmap and handoff_mobile lines call the nearby-filter bug "fixed in code". That was premature: the SU10S-30 investigation said `/product/{barcode}` returns one quote per live store, which was wrong — it was read from the docstring and a client comment, not from `group_by_product`. SU11A-2's client change (mobile `b3250ec`, radius first, then cheapest per chain) is correct and still needed, but on its own it changed nothing.

**Real root cause:** `/product/{barcode}` grouped its rows with `group_by_product`, which keeps ONE quote per (item, chain): the chain's cheapest branch nationwide. The phone never received the nearby branches. Eilat is VAT-free, so for milk Rami Levy, Carrefour and Shufersal always sent an Eilat branch.

**Fix (`db/query.py`, `api/routers/product.py`):** `group_by_product(rows, per_store=False)`. With `per_store=True` the dedup key is (item, chain, store_fk), so every live store keeps its own quote; `/product/{barcode}` passes `per_store=True`. `/search` and `/compare` are unchanged (default `False`). Reused the existing function rather than `group_by_store`, which returns one single-quote *product* per store (the wrong shape for `/product`). Summary fields keep their per-chain meaning in both modes — `cheapest_price`, `chains_count`, and `most_expensive_price` = the most expensive chain's cheapest branch — so web's savings badge (`most_expensive - cheapest`, used on FavoritesPage) does not inflate. In per-chain mode the new `most_expensive_price` expression equals the old `quotes[-1]`.

**Consumers checked:** mobile `product-detail`, `scan-result` card and `open-barcode` (scan history) all run `cheapestPerChain` on the quotes; web `FavoritesPage` renders `ProductCard`, which also collapses per chain client-side; web `useProduct` has no callers; `ProductDetailModal` collapses per chain. Nothing assumes one quote per chain.

**Payload (live data, patched code loaded in memory on the server, GET only):** milk `7290004131074` 852 quotes (was 14) / 351 KB / 0.23 s; sour cream `72963746` 291 (was 10) / 122 KB; `7290000066318` 787 (was 11) / 329 KB. Far from search's ~387k-row scale; no LIMIT needed. **API JSON is NOT gzipped** — nginx has `gzip on` but `gzip_types`/`gzip_proxied` are commented out and the app has no GZip middleware — so 351 KB goes over the wire raw. Worth enabling (an nginx change, needs sudo).

**Tests:** `api/tests` 15/15 passed against the patched app (run on the server, modules swapped in memory, nothing written; the local Windows venv is broken — it points at a Python under another user profile). Synthetic check: per-store keeps two stores sharing a `store_id` apart; summary fields identical across modes.

**Deploy:** per CLAUDE.md "Deploy backend" — pull, `xxl-restart.sh scrp-api`, then curl `/product/7290004131074` and confirm the quote count is in the hundreds. NOT device-verified: needs the deploy plus a phone check of "קרוב אלי" at Dude's Ramat Gan spot.

Next free session ID: SU11A-5
