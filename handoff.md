# SCRP — Project Handoff

> A living document. Update at the end of each session. Paste at the start of each new chat.
> Last updated: June 5, 2026 (end of session 9d-9)

---

## 🎯 Vision

**Short-term:** Israeli supermarket price comparison app at `super.xxl.co.il`. ✅ Live.

**Live now:** `xxl.co.il` portal — multi-vertical savings landing page with AI-powered universal search bar. Sub-header: "XXL — הפורטל שהופך כסף רגיל לכסף חכם". ✅ Live as of session 9f.

**Verticals (paths on xxl.co.il, NOT subdomains):**
- `xxl.co.il/` → portal landing ✅ live
- מצרכים (Groceries) → routes to `super.xxl.co.il` ✅ live
- חופשות (Vacations — flights + hotels combined) → `/vacation` בקרוב page live, real comparison engine planned
- אופנה (Fashion) → `/fashion` בקרוב page live, real comparison engine planned

Brand tagline (codified in 8L, finalized in 9f): logo's own tagline arches "קונים חכם · חוסכים בענקקק" above the XXL wordmark.

---

## 🏗️ Architecture

| Layer | Tech | Where | Status |
|---|---|---|---|
| Frontend | React + Vite + TypeScript + Tailwind | Kamatera nginx (`185.229.226.190`) — serves super.xxl.co.il | ✅ Live (migrated from Hostinger in 9d-6) |
| Portal | Static HTML | Hostinger `public_html/` — serves xxl.co.il | ✅ Live |
| Backend | FastAPI + gunicorn + uvicorn | Kamatera `scrp-prod-il` via systemd `scrp-api.service`, behind nginx + Let's Encrypt | ✅ Live since May 18, 2026 |
| Database | Postgres 18.4 | Kamatera `scrp-prod-il` (`185.229.226.190`), localhost-only (5432 closed at UFW) | ✅ Live |
| Scraper cron | Python (`scraper.cron_main`) | Kamatera `scrp-prod-il` via systemd timer | ✅ Daily 10:00 IDT — parallel chains (max_workers=6) + parallel stores (STORE_WORKERS=4) |
| Backups | pg_dump → rclone → Backblaze B2 | Kamatera systemd timer `scrp-backup.timer` (daily 04:00 IDT) + B2 bucket `xxl-scrp-backups` | ✅ Live since May 19, 2026 |
| Supabase keep-alive | systemd `supabase-keepalive.timer` | Kamatera, every 4h | ⏳ Files in deploy/systemd/ — needs `enable + start` on server |
| DNS | box.co.il (ns1/2/3.box.co.il) | — | ✅ |
| Auth | Supabase | Supabase project (auth only — no Data API usage from client) | ✅ Live |

**Local dev:** `C:\scrp` on Windows 10/11. PowerShell + VS Code + Claude Code in VS Code terminal.

**Repo:** github.com/Eltzur/scrp (main branch is production)

**Production URLs:**
- Portal: https://xxl.co.il (and https://www.xxl.co.il)
- Supermarket app: https://super.xxl.co.il
- Backend: https://api-super.xxl.co.il
- Scraper/DB server (SSH only): `ssh dude@185.229.226.190` (Kamatera Tel Aviv, scrp-prod-il)

**Key infrastructure commands:**

*Kamatera (all production infra):*
- SSH: `ssh dude@185.229.226.190` (or `ssh root@...` via key for admin)
- API service: `systemctl status scrp-api.service` (gunicorn on 127.0.0.1:8000, nginx proxy on 443)
- Reload API: `systemctl restart scrp-api.service`
- nginx config: `/etc/nginx/sites-available/api-super.xxl.co.il` (managed by certbot)
- Manual scrape: `cd ~/scrp && venv/bin/python -m scraper.cron_main`
- Scheduled scrape: `systemctl start scrp-cron.service` (daily 10:00 IDT timer)
- Scrape logs: `journalctl -u scrp-cron.service --since "yesterday" | tail -50`
- API logs: `journalctl -u scrp-api.service -f`
- Postgres console: `sudo -u postgres psql xxl_super`
- Cert renewal: auto via `certbot.timer` (next ~02:30 IDT daily), expires 2026-08-16
- UFW open ports: 22, 80, 443
- Manual backup: `systemctl start scrp-backup.service`
- Backup logs: `journalctl -u scrp-backup.service --since "yesterday"`
- List B2 backups: `rclone ls b2:xxl-scrp-backups/daily/`
- Restore (scratch DB): `sudo -u postgres createdb test_restore && sudo -u postgres pg_restore -d test_restore /var/backups/scrp/xxl_super-YYYY-MM-DD.dump`
- Run one chain: `python3 -m scripts.run_one <chain_id> [--yaml active|scheduled] [--full]`

**Folder layout (matters because some folders are misleadingly named):**
- `web/` — React frontend (NOT the backend, despite the name)
- `api/` — FastAPI backend
- `scraper/` — scraper code + cron entrypoint
- `db/` — schema, migrations, helper scripts
- `frontend/` — empty stub, leftover from skeleton commit, ignore

**Frontend deployment:**
- `.\scripts\deploy_frontend.ps1` from repo root (builds + scps to Kamatera nginx)

---

## 📊 Current Production State (post 9d-9)

- **14 chains** in registry: Shufersal, Rami Levy, Osher Ad, Victory, Yochananof, Keshet, Carrefour, Tiv Taam, King Store, Shefa Birkat Hashem, Shuk Hayir, Fresh Market, Super Yuda, Hazi Hinam
- **~1,200 stores** in active_stores.yaml (post 9d-9 missing-store additions)
- **city_canonical** is the source of truth for all city data (rebuilt from CBS 2024 in 9d-8). city_norm is legacy/broken — do not use.
- **City dropdown** response: ~0.13s (stores table only, no prices JOIN; rebuilt in 9d-8)
- **Delta mode**: 8 chains active — Shufersal, Rami Levy, Osher Ad, Yochananof, Keshet, Fresh Market, Super Yuda, Hazi Hinam
- **Cron performance** (post per-store parallelism, 9d-9):
  - Shufersal: 4436s → 544s (8×)
  - Tiv Taam: 6913s → 93s (74×)
  - Full cron target: <30 min — to be confirmed by next 10:00 IDT run
- **Supabase keep-alive**: files deployed to `deploy/systemd/` — still needs `enable + start` on server
- **Live site**: ✅ super.xxl.co.il + xxl.co.il fully operational

---

## 🎯 Current Session: 9d-9 (in progress)

### What was done

**9d-8 (completed prior session):**
- city_canonical rebuilt from CBS 2024 — 1057 stores, 0 NULLs. city_canonical is now source of truth.
- Paz and Dor Alon removed (422 stores, 887K prices deleted).
- City dropdown reads from city_canonical, 0.13s response (was 3.7s — prices JOIN removed).
- Chain-level parallelism: `cron_main.py` ThreadPoolExecutor(max_workers=6).
- Shufersal 403 fix: lazy per-store URL fetch via `fetch_pricefull_entry`.

**9d-9 priority 1 (done):**
- **Delta Price file support**: 8 chains (Shufersal + 7 Cerberus). `build_price_index` in `cerberus.py`. `DELTA_CHAINS` in `registry.py`.
- **Per-store parallelism**: `STORE_WORKERS=4` in `base.py` and `shufersal.py`. Each worker opens its own DB connection, writes `fetch_store_runs` immediately. `fetch_runs` inserted upfront (status='running'), updated with final counts.
- **Generator exhaustion fix**: `items = list(items)` in `shufersal.py`.
- **Hazi Hinam scraper**: `scraper/hazihinam.py` — 12 physical stores, delta-enabled, custom portal listing parser.
- **`docs/portals.md`**: portal credentials and delta status for all 14 chains.
- **Missing stores added**: Rami Levy (+72→98), Osher Ad (+11→23), Yochananof (+35→50), Keshet (+12→22), Hazi Hinam (+1→12).
- **`scripts/seed_hazihinam.py`**: one-off seed from store 103 PriceFull to physical stores.
- **`scripts/run_one.py`**: `--full` flag to force PriceFull even for delta chains; passes `delta` flag from registry.

### Pending

1. **Confirm full cron run** — check 10:00 IDT tomorrow. Expected <30 min with per-store parallelism.
2. **Supabase keep-alive** — still needs enabling on server:
```bash
sudo systemctl daemon-reload
sudo systemctl enable supabase-keepalive.timer
sudo systemctl start supabase-keepalive.timer
```
3. **Seed Hazi Hinam** on server: `python3 -m scripts.seed_hazihinam`
4. **Delta for remaining chains** — Victory (REST API), King Store / Shefa / Shuk Hayir (Bina Projects) need `build_price_index` per portal type. Carrefour (portal was down 2026-06-04).

### Priority 2 (next session)

Missing stores for Victory (51 stores) and Carrefour (125 stores) — compare against StoresFull XMLs.

---

## ✅ Sessions Completed

| Session | What | Status |
|---|---|---|
| 1–6 | Project skeleton, SQLite schema, XML parser, Shufersal scraper, search CLI, Rami Levy + Osher Ad scrapers, basic API + UI | ✅ |
| 7a | Railway backend + Postgres migration | ✅ |
| 7b | Frontend deploy + custom domains + DNS | ✅ |
| 8a | Victory/Yochananof/Keshet scrapers + SQLAlchemy port + snapshot mode + cron | ✅ |
| 8b | Canonical naming via majority/weighted voting + search filtering | ✅ |
| 8c | OpenFoodFacts enrichment (Hebrew names, images) | ✅ Code ready, partial production data |
| 8d | (skipped/deferred — was about Shufersal image scraping) | — |
| 9a | Basket feature (UI + API) + Hostinger deployment fix + 25-item limit toast | ✅ |
| 8L | Brand identity + animated XXL logo + custom favicon | ✅ |
| 9b | User authentication via Supabase + saved baskets | ✅ Email/pass + saved baskets in production. Google OAuth deferred. |
| 9c | Mini-9c + Favorites + Recent Searches | ✅ 150-item logged-in cap, server-side favorites with heart icon, localStorage recent searches dropdown, cheapest-indicator visual fix |
| 9d-1 | City expansion Phase 1 + Carrefour scraper + verification system | ✅ Carrefour scraper + `publishprice.py` base class shipped. 5 new cities added. PriceFull-verification gate (`active_stores.yaml`) shipped. 58 verified / 14 excluded. Cron-command persistence bug found and fixed. Surfaced: geo-blocking on 2 chains, ~2min/store scrape bottleneck, Shufersal sub-chain heterogeneity. |
| **9f** | **XXL Portal Page — live on xxl.co.il** | ✅ Portal landing live at https://xxl.co.il with 3 vertical tiles, AI search bar (mocked router), 2 בקרוב sub-pages, hostname-based routing in React. Hebrew defaults fixed. DNS + parked domain + SSL + clean root URL all working. |
| **9f-followup** | **Portal polish: SEO, OG, email signup backend, GA4 + cookie banner** | ✅ SEO/OG meta tags hostname-aware. Email signup writes to Supabase portal_email_signups table. GA4 wired (G-YB4X4E5ZKM). Minimal Hebrew cookie banner with X-dismiss-as-consent. |
| **9g** | **Scraper performance + full Railway → Kamatera migration** | ✅ Bulk inserts (9g-1). Scraper + Postgres migrated to Kamatera (9g Phases 2-6). FastAPI web service migrated to Kamatera with nginx + Let's Encrypt (9g Phase 7). Railway fully decommissioned. Cron 3m31s, 7 chains, all geo-blocks resolved. |
| **9k** | Rami Levy split-store reconciliation | ✅ 14 Rami Levy stores existed as duplicate stores rows (sub_chain_id='1' legacy + '001' canonical), prices split. Merged onto '001', 89,298 duplicate price rows removed. No scraper code change needed. |
| **City-data fix** | store→city correction | ✅ Victory wrote full store name into city column; Yochananof name-guessing picked streets. 17 stores corrected in DB. Added STORE_CITY_OVERRIDES in city_names.py. |
| **9d-3** | Shufersal per-store fetch + Tiv Taam onboarding | ✅ Shufersal global page-scan eliminated; per-store fetch (1 req/store). TivTaam Cerberus scraper shipped: 46/46 stores verified, 0 city NULLs, wired as 8th chain in cron. CITY_CODES: 12 new MOI codes + 7 spelling/name overrides. |
| **9d-4** | King Store (bina-projects) + Supabase keep-alive fix | ✅ King Store live as 9th chain: 28 publishing stores, 148,016 prices, Arab-sector cities. BinaProjectsScraper reusable base class (ZIP-not-gzip fix). Supabase ping fixed to hit real Postgres via /rest/v1/. scripts/run_one.py added. |
| **9d-5** | Shefa Birkat Hashem + Shuk Hayir onboarding | ✅ Chains 10 & 11 via BinaProjectsScraper base class. 50 stores added, ~141K items in production Postgres. |
| **9d-6** | CITY_VARIANTS cleanup + Shufersal sweep + 4 new chains + Kamatera frontend migration | ✅ Shufersal 25→320 stores. Fresh Market, Super Yuda, Dor Alon/AM:PM, Paz/Alonit added. Frontend migrated to Kamatera nginx. Registry now 15 chains. |
| **9d-7** | StoresFull XML ingestion + cron fixes | ✅ 244 city_norm rows updated. systemd timeout → infinity + 4G swap. Cron ran successfully (429 stores, 2.45M prices, 11 chains after swap fix). |
| **9d-8** | city_canonical rebuild + parallel chains + Shufersal 403 fix | ✅ CBS 2024 city_canonical: 1057 stores, 0 NULLs. Paz/Dor Alon removed (422 stores, 887K prices deleted). City dropdown 0.13s. Chain-level ThreadPoolExecutor(max_workers=6). Shufersal lazy URL fetch. |
| **9d-9** | Delta Price files + per-store parallelism + Hazi Hinam + missing stores | ✅ Delta for 8 chains. STORE_WORKERS=4. Shufersal 4436s→544s (8×), Tiv Taam 6913s→93s (74×). Hazi Hinam scraper. +131 missing stores added. docs/portals.md. |

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

**Status:** Outreach completed May 2026. StoreNext quoted **NIS 30,000 (~$8,000 USD) for a one-time Excel export** of their catalog data. Hard pass at current stage.

**Why rejected:**
- Price is one-time, not subscription — no obvious "grow into it" tier
- Single Excel export means data goes stale; not an ongoing relationship
- ROI doesn't work pre-revenue
- GS1 IL is the better-shaped data source — barcode-keyed canonical product master data with images, kashrut, nutrition

**Future:** Revisit only if (a) GS1 path doesn't pan out AND (b) scrp has revenue or funding to absorb the cost. Re-engage StoreNext at scale (5K+ MAU, paying premium tier exists) when the value calculation flips.

**Free StoreNext data still usable:** Branch CSVs at `storenext.co.il/תמיכה-ושירות/` remain usable for 9e Registry concept independently of the paid catalog.

---

### OpenFoodFacts (status: abandoned)

Tried during earlier catalog enrichment exploration. Abandoned due to poor Israeli barcode coverage (most IL grocery SKUs absent from the global OFF database). **Do not revisit.**

---

## 🧭 Pending Sessions

| Session | What | Notes |
|---|---|---|
| **9m** | Cron hardening + post-holiday cleanup | ✅ Shufersal parse_filename store_id padding bug FOUND & FIXED (commit 63ec27e). City dropdowns sorted alphabetically. Stale Railway DATABASE_URL removed from local .env. .gitattributes added (*.py eol=lf). Carrefour store 1167 split-pair resolved. |
| **9m-followup** | Shufersal verification + Carrefour padding fix | ✅ Shufersal padding fix (63ec27e) verified. Carrefour PriceFull lookup padding bug found & fixed: base.py now normalizes target store_id via _pad_store_id before index lookup (commit 0812bdc). Hostinger frontend deploy: alphabetical city sort live (85ee335). |
| **9n** | 3-chain diagnostic + cron timing fix + FreshnessStrip deploy | ✅ Root cause of Victory/Osher Ad/Carrefour daily zero-loads identified: timing race — cron at 03:00 IDT fires before portals publish. Cron timer moved to 10:00 IDT (07:00 UTC). Catch-up run succeeded all 7 chains. |
| **9f-followup** | ~~Portal polish~~ | ✅ Done May 14, 2026. See session detail below. |
| **9h** | **Claude Haiku integration for portal search** | Replace `web/src/utils/portalSearchRouter.ts` mock classifier with real Claude Haiku API call. Function signature already designed for one-line swap. Budget: ~$5/mo at 1K daily queries. |
| **9i** | Contact form on xxl.co.il | Real form with Supabase backend + spam protection + email notifications. Currently footer has mailto link only. |
| **Server hardening** | sudo NOPASSWD for dude, disable root SSH, HSTS header, compress OG images (~5.6MB each) | Small cleanups, batch into one ~30 min session. |
| 9e (rescoped) | StoreNext FREE branch CSV ingestion | Rescoped to: ingest free branch CSVs only into `chain_stores_registry` table with sub-format classification. No longer urgent since verification gate (9d-1) already prevents silent failures. |
| 9d-2 | City expansion Phase 2 | Remaining 12 cities >100K pop (Petah Tikva, Netanya, Holon, Ramat Gan, Ashkelon, Rehovot, Bat Yam, Beit Shemesh, Kfar Saba, Herzliya, Modi'in). Now unblocked — cron handles 1200 stores. |
| **stores table data hygiene** | **Add format guard to `sub_chain_id` / `store_id`** | Rami Levy split resolved in 9k; Carrefour store_id padding resolved in 9j-followup. CHECK constraint is now optional/nice-to-have. |
| Promotions + price history | Parse Promo XML files, build history charts | Sample Promo XML files captured in 9d-1 for future analysis. |
| Google OAuth | Wire up deferred-from-9b option | Requires Google Cloud Console OAuth client setup |
| **Search Quality** | Hebrew search precision fixes | Word-boundary matching, kosher-marker filtering ("חלבי"/"פרווה"/"בשרי" leaking into "חלב"/"בשר" searches). Stretch: Hebrew stemming. |
| **Missing stores — Victory + Carrefour** | Victory: 51 stores missing from yaml vs XML. Carrefour: 125 stores missing. | Next session priority. Carrefour portal was down 2026-06-04 — check when back. |
| **Delta for non-Cerberus chains** | Victory (REST API), King Store/Shefa/Shuk Hayir (Bina Projects) need `build_price_index` | Implement per portal type. |

---

## 📌 Open Items

- **Supabase keep-alive** — timer files deployed, needs `enable + start` on server (see Current Session section).
- **Hazi Hinam seed** — run `python3 -m scripts.seed_hazihinam` on server to seed physical stores from store 103 PriceFull before cron can delta-update them.
- **9d-2 city expansion — cleared to start.** No remaining blockers. Needs fresh PriceFull verification run. First step: reconcile the handoff's city list against the live DB before picking new cities.

---

## ⚠️ Watch Items (low priority, but don't forget)

- **RTL terminal display is cosmetic only.** Hebrew store names render reversed in psql/SSH terminal output. The data in the DB is correct — verified repeatedly. Do not "fix" reversed-looking Hebrew in SQL strings.
- **Supabase Data API default change** (email received May 12, 2026): starting May 30 for new projects, October 30 for existing projects, new tables in `public` schema won't be exposed via supabase-js / REST / GraphQL by default. **Existing tables keep their grants**. For NEW tables created after Oct 30, 2026, must run explicit GRANT statements. Pattern: `GRANT SELECT, INSERT, UPDATE, DELETE ON public.your_table TO authenticated;` + RLS policy.
- **Carrefour 0-items issue (May 18, 2026)** — ✅ Resolved May 19. Transient upstream gap.
- **Carrefour portal down (June 4, 2026)** — Portal `prices.carrefour.co.il` was unreachable. Check before adding missing Carrefour stores.

---

## 🔑 Key Architectural Decisions

- **Full Kamatera consolidation (May 18, 2026)** — All production infra on Kamatera Tel Aviv VPS ($17/mo after Jun 17 free trial expires): Postgres + scraper cron + FastAPI behind nginx + Let's Encrypt. Railway fully decommissioned May 18. Single host, single bill, no cross-host network latency, no geo-block issues.
- **city_canonical is the source of truth (9d-8)** — Rebuilt from CBS 2024 official settlement list. city_norm is legacy/broken. All city queries, dropdown, and scraper output use city_canonical.
- **Delta (Price) files for daily scraping (9d-8/9d-9)** — 8 chains use Price delta files instead of PriceFull. PriceFull is for seeding/full-replace. Controlled by `DELTA_CHAINS` in `registry.py` and `uses_delta()`.
- **Per-store ThreadPoolExecutor parallelism (9d-9)** — `STORE_WORKERS=4` in base class. Each worker creates own DB connection, writes `fetch_store_runs` immediately. `fetch_runs` inserted upfront (status='running'), updated at end.
- **Chain-level parallelism (9d-8)** — `cron_main.py` uses `ThreadPoolExecutor(max_workers=6)`. Each chain gets its own DB connection.
- **SQLAlchemy everywhere** — scrapers are DB-agnostic.
- **Snapshot pricing only** — not yet tracking history (deferred to future session).
- **Daily cron at 10am Israel time (7am UTC)** (changed from 3am in session 9n — portals publish 02:09–05:00 UTC; 10:00 IDT clears the window).
- **Canonical names via weighted token voting** — ~93% stability across runs, ~7% updated per fresh canonical run.
- **Brand color: emerald-600 (#059669)** — used for primary CTAs, basket-limit toast.
- **Freemium model REDEFINED (session 9a → confirmed 9c)** — Free tier is the honeypot: search, view prices, basket comparison, save baskets, favorites, recent searches — ALL free, ALL unrestricted. Paid tier benefits will be: ordering through us (12+ months out, requires chain partnerships), exclusive deals, price-drop email alerts. Only logged-out users see the 25-item cap (as a signup nudge); logged-in users get a generous 150 (effectively unlimited for human use).
- **Verification-before-scrape pattern (9d-1)** — `scheduled_stores.yaml` is the intent/wish-list, `active_stores.yaml` is the actually-scraped list, gated by per-portal `verify_publishes_pricefull()` check.
- **Carrefour Israel under Global Retail C.I.** — chain_id `7290055700007` publishes Carrefour + Mega + Yenot Bitan stores combined. We display as "קרפור" but accept all sub-brands.
- **`publishprice` portal type (9d-1)** — new base class `scraper/publishprice.py`. JS-embedded file listing pattern. Currently only Carrefour.
- **Geo-blocking discovered (9d-1)** — `prices.carrefour.co.il` and `laibcatalog.co.il` (Victory) block non-Israeli IPs. Resolved by migrating to Kamatera Tel Aviv VPS (9g).
- **Scraper performance bottleneck — resolved 9g-1 + 9g-3 (May 17, 2026)** — Old Railway US-West: ~1.5min/store. Resolved via bulk inserts + localhost Postgres. Result: 58 stores in 3m31s. Scales to 1200 stores with per-store parallelism in 9d-9.
- **Shufersal sub-chain landscape (9d-1, field intel from Eltzur)** — same chain_id `7290027600007` publishes: דיל (Deal), שלי (Sheli), אקספרס (Express), יש/יש חסד (Yesh, haredi), Universe (hypermarket), BE (pharmacy/health). BE stores EXCLUDED from main chain (pharmacy/beauty only).
- **StoreNext: free CSVs only, paid tier rejected (May 17, 2026)** — Paid tier NIS 30K one-time — doesn't fit pre-revenue stage. GS1 IL is the better-shaped catalog data source going forward.
- **Master brand (xxl.co.il) is the canonical surface (9f)** — xxl.co.il is the portal; verticals are paths on it (`/vacation`, `/fashion`) NOT subdomains.
- **AI search bar uses mocked keyword router for now (9f)** — `web/src/utils/portalSearchRouter.ts` exports `classifyAndRoute(query)`. Function signature designed for one-line swap to Claude Haiku in 9h.
- **Hostname-based routing in React (9f)** — `App.tsx` has `isPortalHostname()` checking `window.location.hostname`. When true (xxl.co.il / www.xxl.co.il / localhost?portal=1), `/` renders `PortalPage`. When false, falls through to `AppShell`.
- **Offsite backups via Backblaze B2 (May 19, 2026)** — Daily pg_dump custom-format → local `/var/backups/scrp` (rotation: 7 daily, 4 weekly Sundays, 6 monthly 1st-of-month) → uploaded to B2 bucket `xxl-scrp-backups/daily/`. Uses rclone native B2 backend (NOT S3-compat). Cost: ~$0/mo (10 GB B2 free tier).
- **Rami Levy canonical `sub_chain_id='001'` (9k)** — split-store duplicates merged onto the `001` row. Legacy `sub='1'` rows were pre-9j-followup artifacts; `upsert_store` padding now prevents recurrence.
- **Paz and Dor Alon removed (9d-8)** — both chains deleted from registry, active_stores.yaml, and DB. 422 stores and 887K prices deleted.

---

## Operating Patterns Established

### Ground Rules (apply to every new chat)

1. **Short responses.** Status or diagnosis, suggested fixes with the recommended option marked, then the tasks/commands. No full thought process, no mid-chat pivots.
2. **Fool-proof = delegate to Claude Code.** Maximize work handed to CC. All prompts in copy-paste code blocks. Keep manual effort to a minimum.
3. **Read previous chats for context** before starting work, to avoid repeating past mistakes.
4. **Handoff maintenance is CC's job.** CC updates handoff.md, commits, and pushes automatically at session end (and when asked mid-session). The chat assistant drafts the entry content; CC owns writing it to the file and committing — it's faster and cleaner.

- **One chat = one session** — Long conversations balloon in token cost (cumulative history is re-read every turn, so turn 60 of a chat costs much more than turn 5 of a new one). At natural breakpoints (end of session, deploy verified, phase complete), START A FRESH CHAT and paste handoff.md as the first message. Yesterday's debugging context isn't useful for today's feature work — it's just expensive baggage. Especially: avoid trying to squeeze a new session into an existing long chat just because we're already talking. Lesson learned in 9c when token budget hit limits faster than expected during Phase 2.

### Operating Policies (codified 9d-3 — apply to every new session)

**A. Investigate the source on the web BEFORE designing a workaround.**
When a task needs information we don't have — an endpoint's behavior, a portal's structure, what data a chain publishes — Claude does NOT reverse-engineer alone. Claude first asks Eltzur to check the source on the web (portal page, dropdown, published credentials, docs). Proven in 9d-3: the Shufersal store dropdown and the gov.il credentials list each replaced a complex workaround with a five-minute look at the actual website. Default order: identify unknown → ask Eltzur to check the source → design against real data.

**B. CITY_CODES policy — see comment in cerberus.py.**
Real municipalities only. Never regional councils (מועצה אזורית). Never bulk-import locality.xls (it mixes cities and regional councils). Authoritative sources: C:\scrp\data\locality.xls (MOI master) and Israel Post's סמל_ישוב_דואר_ישראל.pdf. DO NOT use kod_yeshuvim_02.xls — it's the CBS internal serial system, incompatible number space.

**C. CC's "summary instead of data" pattern — always ask for the raw data.**
CC consistently substitutes a confident summary for the raw data it was asked to produce. Examples from 9d-3: pf_rows[0] (skipped picking newest), "157 doralon stores, ship it" (hid city-coverage issue), the locality.xls "wrong code system" verdict (one sheet, didn't check others), "Nahal Sorek MOI dual-name situation" (hallucinated explanation), three rounds of Fresh Market / Tiv Taam summaries without tables. When CC sends a summary, ASK FOR THE RAW DATA explicitly and don't approve until you see it. Use file-redirect (`> outfile.txt`) when stdout truncates.

**D. CC file-read collapse — ctrl+o expands it.**
When CC reads a file or produces long output, the result often collapses to "[Read 1 file]" in the VS Code display. The bytes are still there — pressing ctrl+o in the CC pane expands them. If CC's third reply on the same ask still has no data, suspect a collapsed read before suspecting CC.

**E. PowerShell stderr handling.**
PowerShell treats any stderr output (including Python's INFO logs) as a NativeCommandError and shows it in red. Not a failure — judge scripts by stdout.

**F. Hot-path discipline (4 clean commits in 9d-3):**
Read-and-report-STOP on scraper hot paths. Verify mechanism via read-only script before adding to cron. Multi-stage prompts with STOPs between stages. Single coherent commit at the end. Worked for both Shufersal and Tiv Taam.

## 🔗 External Data Source Status

- **gov.il price transparency XML** — primary source. Working.
- **Cerberus portal** (`url.retail.publishedprices.co.il`) — used by Yochananof, Keshet, Osher Ad, Rami Levy, Fresh Market, Super Yuda, Tiv Taam. Login-based (username-only).
- **Shufersal direct** (`prices.shufersal.co.il`) — open HTTP, no auth. Per-store catID=0 (PriceFull) or catID=1 (Price delta).
- **Victory** — REST API at laibcatalog.co.il, custom scraper (~55 lines). No auth.
- **Bina Projects** (`*.binaprojects.com`) — used by King Store, Shefa Birkat Hashem, Shuk Hayir. JSON API, no auth. ZIP files (not gzip despite .gz name).
- **Hazi Hinam** (`shop.hazi-hinam.co.il/Prices`) — custom portal, Azure Blob links, no auth. Delta files via `?t=Price`.
- **Carrefour** (`prices.carrefour.co.il`) — PublishPrice portal, JS-embedded file listing. No auth. Portal was down 2026-06-04.
- **OpenFoodFacts** — ❌ ABANDONED. Out of date, nearly empty for Israeli barcodes.
- **StoreNext** — Free CSV branch lists per chain confirmed working (`storenext.co.il/תמיכה-ושירות/`). Paid tier (NIS 30K one-time) rejected.
- **GS1 Israel** — Pending contact. See Potential Data Sources section.

---

## 📂 File Location Reference

| File | Purpose | Notes |
|---|---|---|
| `scraper/registry.py` | Chain registry (14 chains) + `DELTA_CHAINS` (8 chains) + `uses_delta()` | Add new chains here |
| `scraper/active_stores.yaml` | Verified stores for cron (~1200 stores) | What cron actually runs |
| `scraper/scheduled_stores.yaml` | Intent/wish-list (all stores we wish to scrape) | Not used by cron |
| `scraper/cron_main.py` | Cron entry point — chain-level ThreadPoolExecutor(max_workers=6) | |
| `scraper/base.py` | ChainScraper base class — `_process_store` + `STORE_WORKERS=4` per-store parallelism | |
| `scraper/shufersal.py` | Shufersal — lazy per-store URL fetch, `_process_store_shufersal`, delta via catID=1 | |
| `scraper/cerberus.py` | Cerberus base — `build_pricefull_index` + `build_price_index` | |
| `scraper/hazihinam.py` | Hazi Hinam — custom portal listing parser, 12 physical stores | |
| `scraper/city_names.py` | CITY_VARIANTS, STORE_CITY_OVERRIDES (legacy — city_canonical is now authoritative) | |
| `db/query.py` | All DB queries — city dropdown uses `fetch_cities()` (stores table only, no prices JOIN) | |
| `api/routers/` | FastAPI routes | |
| `scripts/apply_city_canonical.py` | Apply city_canonical CSV (UPDATE + DELETE actions) | |
| `scripts/build_city_canonical.py` | Rebuild city_canonical from CBS data | |
| `scripts/seed_hazihinam.py` | One-off seed: copy store 103 PriceFull to 11 physical stores | Run once on server |
| `scripts/run_one.py` | Single-chain runner — `--yaml active|scheduled`, `--full` flag | |
| `deploy/systemd/` | Systemd unit files (supabase-keepalive.service + .timer) | Still needs enable+start |
| `docs/portals.md` | Portal credentials and delta status for all 14 chains | |
| `web/src/App.tsx` | Top-level routing + city fetch on app mount (AppShell) | |
| `web/src/components/Filters.tsx` | City/chain dropdown — receives cities as prop from HomePage | |
| `web/src/pages/PortalPage.tsx` | Portal landing page | Search for `<XxlLogoPortal>` hero, 3 vertical tiles |
| `web/src/utils/portalSearchRouter.ts` | Mocked AI intent classifier | Swap this body when wiring Claude Haiku in 9h |
| `scripts/deploy_frontend.ps1` | Frontend deploy to Kamatera | |

---

### Session 9d-9 (June 4-5, 2026) — Delta Price Files + Per-Store Parallelism + Hazi Hinam

**Priority 1 — DONE:**

- **Delta Price file support** — 8 chains now use Price (delta) files for daily scraping instead of PriceFull full-replace. DELTA_CHAINS in registry.py. `build_price_index` added to cerberus.py (same as build_pricefull_index but matches `Price{chain_id}` filenames, not `PriceFull{chain_id}`). Shufersal uses catID=1 lazy fetch. Hazi Hinam uses custom `_fetch_listing("Price")`.

- **Per-store parallelism** — `STORE_WORKERS: int = 4` class attribute on ChainScraper. `_process_store(sid, entry, store_id_to_fk, ...)` method on base.py: creates own DB connection, does all work, writes `fetch_store_runs` immediately. `fetch_runs` inserted upfront with status='running'; updated to final counts after all workers complete. Shufersal override has `_process_store_shufersal` (fetches entry lazily, no pre-built index).

- **Generator exhaustion fix** — `items = list(items)` added in shufersal.py load_prices_for_stores override before delta split.

- **Hazi Hinam scraper** — `scraper/hazihinam.py`: 12 physical stores hardcoded from StoresFull XML, store 103 (online delivery, StoreType=2) excluded. Portal: `https://shop.hazi-hinam.co.il/Prices?d=YYYY-MM-DD&t=Price`. Blob download URL parsed via lxml xpath. `scripts/seed_hazihinam.py` seeds all physical stores from store 103's PriceFull (run once before cron takes over with delta).

- **Missing stores added from StoresFull XML comparison**:

| Chain | Before | After | Added |
|---|---|---|---|
| Rami Levy | 26 | 98 | +72 |
| Osher Ad | 12 | 23 | +11 |
| Yochananof | 15 | 50 | +35 |
| Keshet | 10 | 22 | +12 (Kulinarik 102/104/105 excluded) |
| Hazi Hinam | 11 | 12 | +1 (store 219) |

- **`docs/portals.md`** — portal credentials and delta status for all 14 chains. Confirmed: Yochananof username is `yohananof` (one 'n').

- **`scripts/run_one.py` updates** — `--full` flag forces PriceFull even for delta chains; `delta` flag read from registry via `uses_delta()`.

**Performance results:**

| Chain | Before | After | Speedup |
|---|---|---|---|
| Shufersal | 4436s | 544s | 8× |
| Tiv Taam | 6913s | 93s | 74× |
| Full cron | ~2.1h | <30 min (target) | TBC at 10:00 IDT |

---

### Session 9d-8 (June 3-4, 2026) — city_canonical + Parallel Chains + Shufersal 403 Fix

- **city_canonical rebuild** — column rebuilt from CBS 2024 official settlement list. 1057 stores, 0 NULLs. city_canonical is now the source of truth for all city data (not city_norm).
- **Paz and Dor Alon removed** — both chains deleted from registry and active_stores.yaml. 422 stores and 887K prices deleted from DB. Registry: 15 → 13 chains.
- **City dropdown** now reads from city_canonical. Response time 0.13s (was 3.7s — prices JOIN removed). Fetch hoisted to app mount level (no per-open delay). API: `fetch_cities()` uses stores table only.
- **Parallel chain scraping** — `cron_main.py` now uses `ThreadPoolExecutor(max_workers=6)`. Each chain gets its own DB connection. `update_canonical_names` and `ping_supabase` remain sequential after all chains finish.
- **Shufersal 403 fix** — `ShufersalScraper.load_prices_for_stores` overrides the base class to fetch signed Azure URLs lazily per-store (`fetch_pricefull_entry`) instead of building the full index upfront. Eliminates 403s from URL expiry during parallel runs. 315/320 stores now loading.
- **Supabase keep-alive timer** — systemd `supabase-keepalive.timer` files deployed to `deploy/systemd/` (every 4h). Still needs `enable + start` on server.
- **Scripts**: `scripts/apply_city_canonical.py` (UPDATE + DELETE from CSV), `scripts/build_city_canonical.py`.

---

### Session 9d-7 (June 1, 2026) — StoresFull XML ingestion + cron fixes

**Commits:**
- a6c2edb: scripts/ingest_store_xml.py — StoresFull XML city ingestion script (dry-run safe, --apply to write)
- fddc113: fix — never overwrite good city_norm with NULL (safety guard)
- 2533161: fix — קרית/קריית variants for missing canonicals (קריית מוצקין, קריית שמונה, קריית אתא)
- d0b0129: fix(ui) — enable chain filter in compare mode

**Data fixes applied:**
- 244 city_norm rows updated from StoresFull XMLs across Shufersal, Victory, Carrefour, King Store, Rami Levy, Keshet, Tiv Taam
- תל אביב consolidated from 3 entries → 1 (90 stores)
- NULL city_norm: down to 23 (all intentional — online/phantom stores)
- קשת טעמים name fix in chains table

**Infrastructure fixes:**
- systemd TimeoutStopSec + TimeoutStartSec set to infinity (cron was being killed by 1min30s timeout)
- Added 2G swap (/swapfile2) — total swap now 4G, persisted in /etc/fstab
- Root cause of OOM kill: Shufersal 320-store scrape peaks at 1.6G RAM + 933M swap

**Cron status:**
- Ran successfully May 30 (429 stores, 2.45M prices, 11 chains)
- Killed twice June 1 — first by timeout, then by OOM during Shufersal 320-store scrape
- Third attempt running successfully with timeout=infinity + 4G swap

**Decision: switch to delta (Price) files for daily scraping in 9d-8** — reduces per-run data volume and avoids OOM risk from full PriceFull for large chains.

---

## Session 9d-6 — CITY_VARIANTS cleanup + Shufersal sweep + 4 new chains + Kamatera frontend migration

### Commits
- 7fae88a: CITY_VARIANTS cleanup — 14 new canonicals, 5 variants added, 17 STORE_CITY_OVERRIDES
- cab4094: Shufersal full sweep — 25 → 320 stores (95 BE excluded, 2 wholesale excluded, 878 deleted from DB)
- add0932: 4 new Cerberus scrapers — Dor Alon/AM:PM (157), Paz/Alonit (262), Fresh Market (45), Super Yuda (26). Registry now 15 chains.
- 74f9880: scripts/deploy_frontend.ps1 — Kamatera frontend deploy script

### Infrastructure
- super.xxl.co.il frontend migrated from Hostinger to Kamatera (185.229.226.190)
- nginx static file server configured at /var/www/super.xxl.co.il/
- SSL cert issued via certbot (expires 2026-08-29, auto-renews)
- DNS A record updated at box.co.il: super.xxl.co.il → 185.229.226.190
- Hostinger remains active (2yr subscription paid) — available as cold backup for xxl.co.il portal
- Deploy process: run scripts/deploy_frontend.ps1 from repo root (builds + scps to Kamatera)

### Key decisions
- BE-branded Shufersal stores (95) excluded — pharmacy/beauty only, not groceries. Onboard as separate chain later.
- Dor Alon = AM:PM only (157 stores, IDs 401–992 + 901–905, 991–992)
- Paz = Alonit gas station stores (262 stores, EV charging nodes 891/4101/4102 excluded)
- Fresh Market (7290876100000) = federation of 7 sub-brands under one chain_id: Fresh Market, Machsanei Mazon, Machsanei Lahav, Hyper Dudu, Super Dush, Tip Tov, Chaviv
- סביון is an independent municipality, not part of Petah Tikva
- מודיעין עילית must NEVER be merged with מודיעין-מכבים-רעות — separate Haredi municipality

---

### Session 9d-5 — Shefa Birkat Hashem + Shuk Hayir onboarding (2026-05-28)

**Scope pivot:** Session opened with Paz + Dor Alon brand-filtering as the locked priority. Eltzur surfaced two bina-projects portals (Shuk Hayir + Shefa Birkat Hashem) that were structurally identical to King Store (9d-4), so scope shifted to the cheaper, mechanical onboarding. Paz + Dor Alon deferred to a dedicated brand-filtering session.

**Delivered:**
- Two new chains live in production Postgres:
  - **שפע ברכת השם** (chain_id 7290058134977) — 30 stores configured, 22 publishing PriceFull. Haredi-sector coverage: Beitar Ilit (8 stores), Jerusalem (10), Beit Shemesh (3), Modi'in Ilit (2), Bnei Brak (2), plus Givat Ze'ev, Elad, Tel Tzion, Netivot, Ofakim, Ashdod, Afula. Items: 59,971.
  - **שוק העיר** (chain_id 7290058148776) — 20 stores configured, 19 publishing. Mixed mainstream coverage: Ashkelon, Ashdod, Kiryat Gat, Kfar Saba, Bnei Brak, Ramla, Holon, Timorim, Efrat, Netivot, Or Akiva, Ra'anana, Hadera, Jerusalem. Store 304 = online fulfillment hub (Ramot); 10 online duplicates deliberately excluded. Items: 81,586.

**Commit:** `44441b6` — "feat(scrapers): Shefa Birkat Hashem + Shuk Hayir (bina-projects, chains 10 & 11)"

**Process learnings:**
- **Cheapersal (https://cheapersal.co.il)** is a competitor reference site with full chain/branch/city/items coverage. Consult when scoping new chain waves or making brand-split decisions.
- **CC compact-summary screen** is NOT tool output — it's CC summarizing its own context to itself when context fills up. If it appears, immediately start a fresh CC chat.
- **PowerShell 5.1 `Set-Content -Encoding utf8` prepends a UTF-8 BOM** that lands as a stray character at the start of commit subjects. Use `[System.IO.File]::WriteAllText($path, $msg, [System.Text.UTF8Encoding]::new($false))`. Do NOT amend + force-push to fix a BOM after the fact.
- **Modi'in Ilit ≠ Modi'in-Maccabim-Re'ut.** These are two different municipalities ~15km apart. Never merge cities sharing a name fragment without confirming they're the same municipality.

---

### Session 9d-4 (May 28, 2026) — King Store (bina-projects) + Supabase Keep-alive Fix

### ⚠️ SEVERE — RTL IS NEVER A BUG. STOP FLAGGING IT.
Across multiple sessions the chat assistant has repeatedly raised false alarms that Hebrew strings are "reversed/corrupted" in code, yaml, DB names, or repr() output. EVERY instance has been a false positive — a terminal/paste RTL rendering artifact, never a real data bug. Hebrew in repr/screenshots/pasted output frequently APPEARS reversed; the underlying bytes are correct. Do NOT flag reversed/corrupted Hebrew as a bug or suspected bug. Do NOT propose codepoint rebuilds, byte checks, or "just to be safe" verifications. If a string parses and the app runs, it is correct. Address ONLY if a genuine reversed-text problem is seen in PRODUCTION on the live site.

**King Store — LIVE (9th chain)**
- chain_id 7290058108879 (confirmed live from filenames; the old 9j scar mislabeling this as Rami Levy is RESOLVED — it is genuinely King Store's).
- Coverage: Arab-sector + northern/mixed towns no other chain has.
- Production Postgres: 28 publishing stores, 148,016 prices, all cities resolved (050 אינטרנט intentionally NULL). Rides daily cron.
- 31 stores in yaml; 338 (small village) deliberately excluded.

**bina-projects — REUSABLE BASE CLASS (the real prize)**
- scraper/binaprojects.py — BinaProjectsScraper(ChainScraper). Several other chains use this portal platform; adding one = ~4-line subclass (BASE_URL, CHAIN_NAME, CHAIN_ID).
- 3 JSON endpoints, all POST:
  - {BASE}/Select_Store.aspx (empty) -> [{"Kod","Nm"}]
  - {BASE}/MainIO_Hok.aspx (form WStore="",WDate="",WFileType="4") -> file list. WFileType: 0=all 1=stores 2=prices 3=promos 4=PriceFull 5=PromoFull. Returns FULL HISTORY (~1000 files); order unreliable.
  - {BASE}/Download.aspx?FileNm=<name> (empty) -> [{"SPath":"<gz url>"}] (LIST, take [0])
- Newest-per-store: select by the 12-digit YYYYMMDDHHMM stamp in FileNm, NOT the DateFile display string (display doesn't sort across days).
- KEY GOTCHA: bina files are ZIP (magic b'PK'), NOT gzip, despite .gz name. binaprojects._decompress overrides base to detect magic bytes; base.py untouched (other chains still gzip).

**Supabase keep-alive — FIXED**
- Old ping hit /auth/v1/health → 200 without touching Postgres → never counted as activity.
- Now reads 1 row from public.keepalive via /rest/v1/ (real DB read); success requires non-empty body.

**Tooling added**
- scripts/run_one.py — standalone single-chain runner.

**Commits (9d-4)**
ea03cf5 Supabase cron fix · 71a335a bina base + KingStore + registry · 917c555 store lists · 70218d7 ZIP-not-gzip fix · 3304062 NULL-city overrides · 2c3d531 run_one.py · cfaa942 King Store city overrides (8 branches)

---

### Session 9d-3 (May 27, 2026) — Shufersal Per-Store Fetch + Tiv Taam Chain

**Priority 4 — DONE (Shufersal page-scan eliminated, not just optimized):**

The original P4 task was "build a page-scan cache." A cache was already in shufersal.py (undocumented). More importantly — the whole approach was replaced. Eltzur noticed the Shufersal portal has a STORE DROPDOWN. DevTools confirmed the selector posts a clean GET:
  GET /FileObject/UpdateCategory?catID=0&storeId={N}&sort=Time&sortdir=DESC
returns ONLY that store's files (~6-10 rows) as the same HTML table the existing parser already handles.

Shufersal now fetches per-store, one request per store, flat as the chain grows — same shape as the other chains. No longer the weird one.

Changes (scraper/shufersal.py, commit 4c70a1d):
- build_pricefull_index rewritten: loops target store IDs, one _fetch_url per store via ?storeId=N.
- Newest PriceFull picked via max(pf_rows, key=filename). REVIEW CATCH: CC first used pf_rows[0] trusting server sort — server sorts the full mixed file listing, not the PriceFull subset, so [0] grabbed the STALE 03:00 file instead of the 04:31 republish. Fixed to max().
- DELETED: the page-scan cache entirely — _CACHE_FILE, _load/_save_cached_start_page, _CACHE_MARGIN, _DEFAULT_START_PAGE, safety cap, page loop.
- load_stores UNCHANGED — still page-walks for store name/city metadata.

Verification: 17/17 stores FOUND. 12 existing actives + 014/018 (verified 9d-2 deferred items, added to active_stores.yaml, commit 206a562) + spot-check of 318 (אקספרס), 270 (BE), 035 (יוניברס) — all FOUND. The handoff's old assumption that Shufersal sub-formats (אקספרס/BE/יוניברס) don't publish PriceFull is WRONG across the board — they all publish.

**Priority 5 — DONE for Tiv Taam (deferred for others, see below):**

Tiv Taam SHIPPED (commit 6f234b4):
- chain_id 7290873255550, 46 retail stores (53 in Stores XML, minus 7 ליקוט warehouses: 502, 503, 512, 514, 515, 519, 523).
- scraper/tivtaam.py — 5-line subclass.
- Verification: 46/46 PriceFull FOUND, 53/53 cities resolved, 0 NULLs.

CITY_CODES rebuilt from official sources (same commit):
- 12 new MOI codes added
- 7 spelling/name overrides applied from the authoritative Israel Post locality PDF
- POLICY COMMENT added above CITY_CODES: NEVER include regional councils (מועצה אזורית). Do NOT bulk-import locality.xls — it mixes cities and regional councils.

Locality file caveats discovered this session:
- C:\scrp\data\kod_yeshuvim_02.xls is the CBS internal serial code system, NOT the Ministry of Interior locality codes. Different number space. DO NOT USE for CITY_CODES work.
- C:\scrp\data\locality.xls IS the correct MOI master.
- Israel Post's סמל_ישוב_דואר_ישראל.pdf cross-confirms the MOI codes.

---

### Session 9j-followup (May 21, 2026) — City Matcher Ported to Scrapers + store_id Padding

**Done:**
- Created `scraper/city_matcher.py` — the 9j matcher logic extracted into a reusable module. Public API: `resolve_city(store_name, address, chain_id) -> (city, confidence)`. Verified against the 355-store 9j dataset: identical results (296 high-confidence matches).
- Wired `resolve_city` as a fallback into both scraper store-load paths (`cerberus.py`, `publishprice.py`): when the numeric government city-code lookup returns nothing, the matcher fills `city` if confidence ≥0.80.
- `store_id` / `sub_chain_id` padding normalization: changed `publishprice.py` to zero-pad; `db.py` `upsert_store` now defensively pads via `_pad_store_id`. Ran `migrate_store_id_padding.py` — **40 Carrefour rows migrated** to canonical 3-digit format.
- Server hotfix committed: Shufersal `_fetch_raw_page` timeout 30s→60s.

**NEW BUG FOUND (logged as session 9k):**
- The padding migration surfaced 14 "collision" rows — Rami Levy stores that exist twice (`sub_chain_id='1'` and `'001'`). Investigation showed **both copies carry prices** (~8K rows each). See 9k session above.

**Files changed:** `scraper/city_matcher.py` (new), `scraper/publishprice.py`, `scraper/cerberus.py`, `db/db.py`, `scraper/shufersal.py`, `migrate_store_id_padding.py` (new).

**Note on Claude Code:** CC initially generated its own simplified `city_matcher.py` from scratch (the real file wasn't in its prompt) — caught and overwritten with the correct tested version. Lesson: when handing CC a pre-built file, save it first and tell CC explicitly not to recreate it.

---

### Session 9j (May 21, 2026) — City Field Normalization

**Goal:** resolve 355 stores with NULL `city` via progressive auto-matching.

**Done:**
- Built `normalize_cities.py` — a per-chain city matcher: city dictionary (~190 Hebrew cities), abbreviation expansion, Shufersal sub-format prefix stripping, Hebrew-safe word-boundary matching.
- Auto-matcher resolved 299/355 (84%), 296 at confidence ≥0.80. Eltzur manually reviewed `matches.csv` in Excel and corrected/filled ~50 rows.
- Built `apply_matches.py` — dry-run + `--commit` modes, updates `city`/`city_norm` only where currently NULL. Committed: 318 rows + 1 online store moved to `sub_chain_id=1234`.
- Built `fix_9j_residual.py` — fixed 14 Carrefour stores skipped due to `store_id` format mismatch + deleted 2 orphaned Yochananof rows (150/152, renumbered to 50/52).
- Built `fix_ramilevy.py` — fixed 14 Rami Levy stores skipped because the DB stored them with `sub_chain_id='1'` while the apply script padded to `'001'`.
- **Result: 349/355 resolved. 6 NULL remain, all intentional** — Shufersal 000, Yochananof 002 (יוחננוף ישן), Keshet 102-105 (Kulinarik). Final city coverage: 827/833 stores = 99.3%.

**Decisions made:**
- Online stores (e.g. Shufersal ONLINE) → `city='אונליין'`, moved to reserved `sub_chain_id='1234'`.
- Kulinarik (Keshet store_ids 102-105) — identified as a separate chain, but **left as Keshet rows for now**.
- Yochananof pickup points 150/152 were the wrong store codes — corrected to 50/52, old rows deleted.

**Corrections to this handoff:**
- Rami Levy chain_id was wrong here (`7290058108879` — that's actually KingStore per Kaggle). **Correct Rami Levy chain_id: `7290058140886`.** Fixed throughout where it appears.

---

### Session 8L (April 29, 2026) — Brand Identity & Animated Logo

**Done:**
- Brand strategy: chose master `xxl.co.il` brand-first approach (Option B). Bold/energetic personality. Hebrew-native naming.
- Brand identity finalized:
  - **Name:** XXL (Latin wordmark)
  - **Hebrew tagline:** חוסכים בענקקק (with stretched ק's for "saving big" emphasis — tagline arches over the wordmark)
  - **English tagline:** SAVING **BIG** (2× size ratio between SAVING and BIG)
  - **Personality:** Fast & Furious — speed lines, hard slam entrance, basketball-team-banner-break energy
- Color palette codified:
  - Primary emerald: `#059669` (Tailwind emerald-600)
  - Shadow emerald: `#064E3B` (Tailwind emerald-900)
  - Accent orange: `#EA580C` (Tailwind orange-600)
  - Dark text: `#022C22`
- Typography: **Rubik** (Hebrew + Latin) at weight 900 italic for the wordmark, weight 900 upright for tagline. Font preloaded from Google Fonts.
- Animation choreography (1.5s total, plays once per session via `sessionStorage`):
  - 0.0–0.4s: Speed lines streak in from both sides (orange left, emerald right, staggered)
  - 0.45–1.45s: XXL slams in from above with 1.85× overshoot, deep squash to 0.78×, hard rebound to 1.18×, settle to 1×. Camera shake on impact (7px range), white flash (95% opacity).
  - 1.45–2.15s: Tagline appears above with fade + subtle slide-down
- React component `XxlLogo.tsx` with three variants: `hero` (large animated), `header` (small static), `favicon` (XXL-only stripped down). Accepts `lang` prop for Hebrew/English tagline switch.
- Hero section added above search bar on homepage.
- Custom favicon.svg created (XXL wordmark + shadow, no tagline).
- Page title updated to `XXL — חוסכים בענקקק`.

**Decisions made:**
- Master-brand-first strategy (Option B) chosen over per-vertical branding.
- "Pure slam" animation chosen over "paper banner break" variant.
- Animation runs once per session (via `sessionStorage.getItem('xxl_animated_this_session')`), not per page load.
- React `useId()` hook used for unique SVG path IDs (with colon-stripping to ensure XML validity).

---

### Session 9b (April 30, 2026) — User Authentication via Supabase + Saved Baskets

**Done:**
- **Supabase project provisioned** at https://dwohlwmiejgjlsbuegeu.supabase.co (Frankfurt region, free tier, ~50K MAU limit)
- **Database migration applied**: new `users` table (PK = Supabase UUID) and `saved_baskets` table (FK to users with ON DELETE CASCADE, JSONB items column, indexed by user_id).
- **Backend (FastAPI):** `api/auth.py` — JWT verification dependency. `api/routers/saved_baskets.py` — full CRUD with ownership enforcement (404 on user_id mismatch, NOT 403).
- **Frontend:** Auth context, Login/Signup/MyBaskets pages, header auth-aware, basket save button. axios interceptor attaches `Authorization: Bearer <token>` to all requests when user is logged in.

**Decisions made:**
- **Auth library: Supabase** — auth-only. User data stays in Kamatera Postgres, not Supabase DB.
- **Routes over modals** for signup/login.
- **Email confirmation: KEPT ENABLED** — security best practice.
- **Google OAuth: DEFERRED.** Email/password is working.
- **JWT verification migrated to ES256/JWKS** — Supabase recently switched from HS256 (shared secret) to ES256 (asymmetric public-key crypto).
- **404 not 403 on basket ownership mismatch** — security pattern, prevents leaking that a basket exists.

---

### Session 9c (May 2, 2026) — Mini-9c + Favorites + Recent Searches

**Done:**
- **Phase 1 (Mini-9c)**: Logged-in users now have a 150-item basket cap (vs 25 for logged-out). Logged-in cap-hit fires an amber/orange (#EA580C) Sonner toast with no CTA. Logged-out 25-item toast with "להרשמה" emerald CTA preserved.
- **Phase 2A (Favorites)**: New `favorites` table, new endpoints `POST/GET/DELETE /favorites/{barcode}`, `FavoritesContext` with optimistic toggle + revert-on-error, Heart icon on every ProductCard.
- **Phase 2B (Recent Searches)**: `useRecentSearches` hook backed by localStorage (key: `xxl_recent_searches`). Stores up to 10 most recent unique queries. Dropdown appears when search input is FOCUSED + EMPTY.
- **Cheapest indicator visual fix**: Replaced the in-row star with `CheckCircle2` (outlined, emerald-600). No more double-star ambiguity.

**Key decisions:**
- Logged-in cap = 150. No server-side enforcement. Favorites server-side, recent searches client-side.
- Heart in brand orange (#EA580C), not red.
- **Original "freemium gating" 9c framing retired**: no server-side per-account 25-item enforcement. The free tier is the honeypot.

---

### Session 9f-followup (May 14, 2026) — Portal Polish

**Done:**
- Hostname-aware SEO meta tags (title/description/OG/Twitter cards differ for xxl.co.il vs super.xxl.co.il).
- Portal email signup now writes to Supabase `portal_email_signups` table via supabase-js.
- GA4 wired via VITE_GA_MEASUREMENT_ID env var. Measurement ID: G-YB4X4E5ZKM.
- Minimal Hebrew cookie banner ("נמשיך, אנו משתמשים בעוגיות לשיפור החוויה") with X-dismiss-as-consent.
- `isPortalHostname()` refactored to `web/src/utils/hostname.ts`.

---

### Session 9f (May 12-13, 2026) — XXL Portal Page → Live on xxl.co.il

**Done:**
- Designed and built the xxl.co.il portal landing page: hero with animated logo, AI search bar (rotating placeholders), 3 vertical tiles (מצרכים live, חופשות + אופנה בקרוב), value-props strip, footer.
- Mocked AI search router shipped: `portalSearchRouter.ts` with Hebrew + English keyword lists. Groceries → external nav to super.xxl.co.il, vacation/fashion → internal React Router, unknown → Hebrew error hint.
- 2 בקרוב sub-pages live at `/vacation` and `/fashion`.
- XxlLogoPortal component created as duplicate of XxlLogo.tsx with tagline "קונים חכם · חוסכים בענקקק".
- Hebrew default fixed: app was loading English on first visit. Now defaults Hebrew with localStorage preservation of user's explicit choice.
- DNS setup: A records at box.co.il for `xxl.co.il` and `www.xxl.co.il` → `82.198.227.247`.
- Hostinger parked domain: `xxl.co.il` parked on top of `super.xxl.co.il`. Both serve from same `public_html/`.
- SSL: Lifetime SSL auto-provisioned for `xxl.co.il` within ~30 min of parking.
- Hostname-based routing in React: `App.tsx` checks `window.location.hostname`; on xxl.co.il, `/` renders PortalPage. Local dev override: `localhost?portal=1`.

**Decisions made:**
- Multi-vertical portal = paths on xxl.co.il, NOT subdomains. חופשות collapses flights + hotels.
- Mocked keyword router over real Haiku for MVP — ships UI without API key complexity.
- Hostname-based routing in React (not .htaccess).
- XxlLogo.tsx untouched, XxlLogoPortal duplicated — keeps super.xxl.co.il logo 100% safe from portal changes.

---

### Session 9g (May 17, 2026) — Scraper Performance + Kamatera Migration

**9g-1: Bulk inserts** — Implemented as batched `INSERT ... VALUES (...), (...)` at 1000 rows/statement across items, item_chain_names, prices tables.

Dedup hotfix: deduplicate by `item_code` once per store before all three bulk calls in `scraper/base.py`. Last-wins semantics matches existing ON CONFLICT DO UPDATE.

**Railway Postgres disk-full crash** — Railway free trial 0.5 GB volume exhausted. Decision: skip Path C "Railway Hobby probation" and go directly to Path B "all-in on Kamatera." Kamatera chosen: Tel Aviv DC, 30-day free trial, ~$17/mo for 1 vCPU / 2 GB RAM / 30 GB SSD.

**Kamatera migration (Phases 2-6):**
- Provisioned `scrp-prod-il` at `185.229.226.190` (Tel Aviv, Type B General, Ubuntu 24.04 LTS)
- Server hardening: non-root `dude` user with sudo, SSH key auth, password SSH disabled, UFW firewall (22 + 5432), fail2ban, timezone Asia/Jerusalem
- Postgres 18.4 from PGDG official repo, tuned for 2GB RAM (shared_buffers 512MB, effective_cache_size 1GB, work_mem 16MB, wal_compression on)
- Database `xxl_super` owned by `scrp_app` user
- Scrp repo cloned to `/home/dude/scrp`, venv created, requirements installed, `.env` at `~/scrp/.env` with permissions 600
- systemd timer `scrp-cron.timer` scheduled daily 03:00 IDT (DST-aware via OnCalendar).

**Full cron run, 7 chains × 58 stores: 3m 31s — 25× improvement over Railway US-West (~90 min).**

| Chain | Stores | Prices | Time |
|---|---|---|---|
| Shufersal | 1/1 | 4,823 | 41s |
| Rami Levy | 14/14 | 101,620 | 39s |
| Osher Ad | 8/8 | 57,713 | 24s |
| Victory | 9/9 | 74,675 | 29s |
| Yochananof | 9/9 | 62,666 | 25s |
| Keshet | 8/8 | 96,301 | 35s |
| Carrefour | 9/9 | 33,392 | 15s |
| **Total** | **58 stores** | **430,190 prices** | **3m 31s** |

**Bugs encountered & resolved:**
1. ✅ Postgres CardinalityViolation on ON CONFLICT — duplicate item_codes in source XML, fixed via dedup in base.py
2. ✅ SQLite vs Postgres semantic mismatch — SQLite tolerates ON CONFLICT duplicates; Postgres rejects.
3. ✅ Railway Postgres disk-full → crash loop — accepted data loss, migrated to Kamatera

---

### Session 9n (May 25, 2026) — 3-Chain Diagnostic + Cron Timing Fix + FreshnessStrip Deploy

**Root cause — confirmed timing race:** Cron fired at 03:00 IDT = midnight UTC. All three failing portals publish PriceFull files AFTER midnight UTC:
- Carrefour (publishprice.py): publishes ~02:09 UTC daily
- Osher Ad (Cerberus): publishes ~03:00–04:00 UTC
- Victory (laibcatalog.co.il): publishes ~04:00–05:00 UTC

**Fix — cron moved to 10:00 IDT (07:00 UTC):**
```bash
sed -i 's/OnCalendar=\*-\*-\* 03:00:00/OnCalendar=*-*-* 10:00:00/' /etc/systemd/system/scrp-cron.timer
systemctl daemon-reload
```

**Catch-up run results — all 7 chains loaded successfully.**

---

### Session 9d-2 (May 25-26, 2026) — Per-Store Coverage Metric + City Expansion

**Priority 1 — DONE (per-store coverage metric):**
- New table `fetch_store_runs` (per-store sibling to per-chain `fetch_runs`): one row per store per cron run, status enum loaded/no_file/error. Migration: `db/migrations/9d2_fetch_store_runs.sql` (includes scrp_app GRANTs).
- New view `v_store_coverage_72h` + `/coverage` API endpoint.
- **Lesson — new tables need explicit GRANTs:** Any new table created via `sudo -u postgres psql` MUST include `GRANT ... TO scrp_app` (table + sequence + any views) in the same migration file.

**Priority 2 — DONE (city expansion, 9 new 100K+ cities):**
- 9 cities: Petah Tikva, Holon, Bnei Brak, Ashkelon, Rehovot, Bat Yam, Beit Shemesh, Herzliya, Modi'in.
- 60 candidates verified, 55 PASSED, added to active_stores.yaml. Store count: 58 → 113.
- Surprise finding: Shufersal יש חסד sub-format DOES publish PriceFull.
- Rami Levy store 016 (Bnei Brak Ayalon branch): catalog store_name says "רמת גן" but address מבצע קדש 68 confirms Bnei Brak municipality. Comment added in active_stores.yaml — do not "correct" it.

**Priority 3 — bar met:** Proof cron run (326s, errors none) → /coverage shows all 7 chains ≥90%.

**GS1 — incoming workstream (not started):**
GS1 Israel can license canonical item data: names, images, barcodes, nutrition, kosher, ingredients. ~₪6,000, affordable. This is the canonical product layer the project lacks. GS1 constraint: some chains are not GS1 members; GS1 doesn't want non-members getting GS1 data via xxl as a backdoor. Before signing: get the eligible-chain list explicit and in writing. Needs a dedicated scoping session.

---

### Session 9d-1 (May 11-12, 2026) — City Expansion Phase 1 + Carrefour + Verification System

**Done:**
- **New chain shipped: Carrefour Israel** (chain_id `7290055700007`, operated by Global Retail C.I. — includes Carrefour + Mega + Yenot Bitan sub-brands under one publisher).
- **New portal type abstracted**: `scraper/publishprice.py` base class (~130 lines) for JS-embedded file listing portals.
- **City expansion Phase 1**: added 5 new cities (Tel Aviv, Haifa, Be'er Sheva, Rishon LeZion, Ashdod) on top of existing Jerusalem + Bnei Brak. Total: 7 cities.
- **Verification-before-scrape system (Path C)**: new `scraper/active_stores.yaml` populated by per-store `verify_publishes_pricefull()` check. `scraper/scheduled_stores.yaml` retained as intent/wish-list. **58 of 72 stores verified.** 14 excluded breakdown:
  - 11 Shufersal (mostly Sheli format)
  - 1 Rami Levy 004 (warehouse, no city)
  - 2 Osher Ad 002, 004 (warehouses, no city)
- **Verification report**: `db/verification_report_9d1.md` documents excluded stores.
- **Procfile fix**: added `cron: python -m scraper.cron_main` process type so Railway commands are repo-authoritative.

**Decisions made:**
- Carrefour publisher returns Mega + Yenot Bitan stores too — take them all under "קרפור" display name.
- Bnei Brak zero-Carrefour-stores is real, not a CITY_CODES dict gap — verified via carrefour.co.il store locator manually.
- Path C (verification gate) chosen over Path A (Shufersal-specific patch).

---

**OPERATING NOTES (important for all future sessions):**
- Terminal RTL display of Hebrew is EXPECTED and normal — it does not indicate a bug, no verification needed for display mangling. Only verify logic when a Hebrew string comparison is load-bearing (use repr() / JSON.stringify, or open the file in VS Code).
- CC cannot reliably surface file contents back to the operator — its file reads collapse ("Read 1 file / ctrl+o to expand") and don't paste through. Workaround: for any code review, the operator opens the file in VS Code and pastes it directly.
- PowerShell → ssh → bash quoting mangles Hebrew, special characters, and long strings (JWTs). For ad-hoc DB queries with Hebrew: SSH in interactively first, run the query at the server bash prompt. To get a file/credential onto the server: build it locally and scp it — never interpolate it into an ssh "..." command string.
