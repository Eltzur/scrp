# SCRP — Project Handoff

> A living document. Update at the end of each session. Paste at the start of each new chat.
> Last updated: May 18, 2026 (end of session 9g complete — Phase 7 done, Railway fully decommissioned, all infra on Kamatera Tel Aviv)

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
| Frontend | React + Vite + TypeScript + Tailwind | Hostinger static (`public_html/`) — serves BOTH xxl.co.il and super.xxl.co.il | ✅ Live |
| Backend | FastAPI + gunicorn + uvicorn | Kamatera `scrp-prod-il` via systemd `scrp-api.service`, behind nginx + Let's Encrypt | ✅ Live since May 18, 2026 |
| Database | Postgres 18.4 | Kamatera `scrp-prod-il` (`185.229.226.190`), localhost-only (5432 closed at UFW) | ✅ Live |
| Scraper cron | Python (`scraper.cron_main`) | Kamatera `scrp-prod-il` via systemd timer | ✅ Daily 03:00 IDT, DST-aware |
| DNS | box.co.il (ns1/2/3.box.co.il) | — | ✅ |
| Auth | Supabase | Supabase project (auth only — no Data API usage from client) | ✅ Live |

**Local dev:** `C:\scrp` on Windows 10/11. PowerShell + VS Code + Claude Code in VS Code terminal.

**Repo:** github.com/Eltzur/scrp (main branch is production)

**Production URLs:**
- Portal: https://xxl.co.il (and https://www.xxl.co.il)
- Supermarket app: https://super.xxl.co.il
- Backend: https://api-super.xxl.co.il
- Scraper/DB server (SSH only): `ssh dude@185.229.226.190` (Kamatera Tel Aviv, scrp-prod-il)

**Hostinger setup (added 9f):**
- One website (`super.xxl.co.il`) serves both domains
- `xxl.co.il` is **parked** on top of `super.xxl.co.il` via hPanel → Domains → Parked Domains
- DNS: A records at box.co.il for `xxl.co.il` and `www.xxl.co.il` → `82.198.227.247`
- SSL: Lifetime SSL auto-provisioned by Hostinger for both
- **Routing logic lives in React, NOT .htaccess.** `App.tsx` has `isPortalHostname()` that checks `window.location.hostname` and renders `PortalPage` at `/` when on xxl.co.il, else renders `AppShell` (supermarket app).

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

**Folder layout (matters because some folders are misleadingly named):**
- `web/` — React frontend (NOT the backend, despite the name)
- `api/` — FastAPI backend
- `scraper/` — scraper code + cron entrypoint
- `db/` — schema, migrations, helper scripts
- `frontend/` — empty stub, leftover from skeleton commit, ignore

**Hostinger deployment:**
- Document root is `public_html/` at the account root (NOT `super.xxl.co.il/` folder)
- Deploy = build `web/` → zip `dist/*` contents → upload+extract in `public_html/`
- .htaccess for SPA routing lives in web/public/ (auto-copied to dist/ on build). Current production .htaccess is minimal React Router SPA fallback only — no hostname rewrites (handled in React)

---

## 📊 Current Production State

- **7 chains** scraping daily: Shufersal, Rami Levy, Osher Ad, Victory, Yochananof, Keshet, Carrefour — ✅ ALL working from Kamatera Tel Aviv IP as of May 17, 2026 (geo-block resolved)
- **58 stores across 7 cities**: Jerusalem, Bnei Brak, Tel Aviv, Haifa, Be'er Sheva, Rishon LeZion, Ashdod
- **~430,000 prices** as of May 17, 2026 full cron run
- **Cron runtime**: 3 min 31 sec (down from ~90 min on Railway US-West — 25× improvement via bulk inserts + localhost Postgres + Israeli IP)
- **Verification gate**: `active_stores.yaml` (verified to publish PriceFull) is what cron uses; `scheduled_stores.yaml` is the wish-list. See `db/verification_report_9d1.md` for excluded stores.
- **Canonical names** computed via weighted token voting (session 8b)
- **Search** uses canonical names only, numeric/percentage tokens filtered (session 8b)
- **Known coverage gap**: Bnei Brak has no Carrefour/Yenot Bitan/Mega presence (verified via carrefour.co.il store locator) — accepted, not a bug.
- **Live site status**:  ✅ super.xxl.co.il + xxl.co.il fully operational, all API calls served from Kamatera over HTTPS.

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
| 9d-1 | City expansion Phase 1 + Carrefour scraper + verification system | ✅ Carrefour scraper + `publishprice.py` base class shipped. 5 new cities added. PriceFull-verification gate (`active_stores.yaml`) shipped. 58 verified / 14 excluded. Cron-command persistence bug found and fixed (Procfile now authoritative). Surfaced: geo-blocking on 2 chains, ~2min/store scrape bottleneck, Shufersal sub-chain heterogeneity. |
| **9f** | **XXL Portal Page — live on xxl.co.il** | ✅ Portal landing live at https://xxl.co.il with 3 vertical tiles, AI search bar (mocked router), 2 בקרוב sub-pages, hostname-based routing in React. Hebrew defaults fixed. DNS + parked domain + SSL + clean root URL all working. |
| **9f-followup** | **Portal polish: SEO, OG, email signup backend, GA4 + cookie banner** | ✅ SEO/OG meta tags hostname-aware. Email signup writes to Supabase portal_email_signups table. GA4 wired (pending Eltzur measurement ID swap). Minimal Hebrew cookie banner with X-dismiss-as-consent. |
| **9g** | **Scraper performance + full Railway → Kamatera migration** | ✅ Bulk inserts (9g-1). Scraper + Postgres migrated to Kamatera (9g Phases 2-6). FastAPI web service migrated to Kamatera with nginx + Let's Encrypt (9g Phase 7). Railway fully decommissioned. Cron 3m31s, 7 chains, all geo-blocks resolved. |

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

| Session | What | Notes |
|---|---|---|
| **9f-followup** | ~~Portal polish~~ | ✅ Done May 14, 2026. See session detail below. |
| **9h** | **Claude Haiku integration for portal search** | Replace `web/src/utils/portalSearchRouter.ts` mock classifier with real Claude Haiku API call. Function signature already designed for one-line swap. Budget: ~$5/mo at 1K daily queries. |
| **9g Phase 9** | pg_dump backups for Kamatera Postgres | Daily 04:00 IDT, offsite to Backblaze B2. ~45 min. |
| **9i** | Contact form on xxl.co.il | Real form with Supabase backend + spam protection + email notifications. Currently footer has mailto link only. |
| **Server hardening** | sudo NOPASSWD for dude, disable root SSH, HSTS header, compress OG images (~5.6MB each) | Small cleanups, batch into one ~30 min session. |
| **9g-2** (deferred) | **Parallel chain execution** | Skipped after 9g-1 results. Sequential cron now 3m31s; parallelism would save ~2.8 min. Low ROI until something specific unblocks it. Revisit when full cron pressure returns. |
| **Shufersal page-scan cache** | **Reduce Shufersal store-discovery from 200 pages to 1-2** | Shufersal's portal forces paginating up to 200 listing pages to find a store's PriceFull. Cache "last known page for store X" in SQLite. Drops Shufersal from ~41s to ~5s per store. Total cron from 3m31s to ~1m. ~30 min session. |
| 9e (rescoped) | StoreNext FREE branch CSV ingestion | Original 9e premise (paid product catalog) dead — StoreNext paid tier rejected (NIS 30K one-time, May 2026). Free CSV branch lists at `storenext.co.il/תמיכה-ושירות/` remain usable. Rescoped to: ingest free branch CSVs only into `chain_stores_registry` table with sub-format classification (Sheli/Deal/Express/Yesh/Universe/BE for Shufersal; similar for others). Refactor Phase B selection to be format-aware. Solves Shufersal sub-chain heterogeneity systematically. No longer urgent since verification gate (9d-1) already prevents silent failures — quality-of-life, not blocker. |
| 9d-2 | City expansion Phase 2 | Remaining 12 cities >100K pop (Petah Tikva, Netanya, Holon, Ramat Gan, Ashkelon, Rehovot, Bat Yam, Beit Shemesh, Kfar Saba, Herzliya, Modi'in). Target ~216 stores total. **Requires 9g first** — running 216-store cron at current 1.5min/store = 5+ hours. |
| 9d-3 | City expansion Phase 3 | 50K+ cities (~25-30 more). Target ~540 stores. |
| CITY_CODES audit | Patch missing gov.il city codes | 9d-1 surfaced 23 NULL-city Carrefour stores (Or Akiva, Tel Mond, Dimona, Maalot, Kiryat Ata, Even Yehuda, Kfar Yona, Karkur, Tamra, Daliyat al-Karmel, Arad, Atlit, Kiryat Tivon, Matan, Tzur Yitzhak). Pre-existing dict gap in `scraper/cerberus.py`. Small fix, defer to alongside 9d-2 or as a quick patch session. |
| Promotions + price history | Parse Promo XML files, build history charts | Sample Promo XML files captured in 9d-1 for future analysis. Requires sufficient daily snapshots first. |
| Google OAuth | Wire up deferred-from-9b option | Requires Google Cloud Console OAuth client setup |
| Investigate disappearing tables | Risk hygiene | Deferred pending future AWS/GCP migration (decided in 9c planning) |
| **Search Quality** | Hebrew search precision fixes | Word-boundary matching, kosher-marker filtering ("חלבי"/"פרווה"/"בשרי" leaking into "חלב"/"בשר" searches — example: jelly appearing under "חלב" because it's labeled "חלבי"). Stretch: Hebrew stemming. Defer until after StoreNext data is in hand (may solve upstream via better categorization). |
| **OS scraper research** | ~~Review OpenIsraeliSupermarkets repos + Kaggle dataset~~ | ✅ Done May 14, 2026. Writeup at docs/research/os_scraper_2026_05_14.md. Key findings: MIT-licensed (not GPL/AGPL as feared), geo-block is industry-wide (confirms 9g VPS plan), Kaggle dataset NOT a Carrefour/Victory stopgap, no new sources for images/categories/brands (StoreNext still the path). |

---

## ⚠️ Watch Items (low priority, but don't forget)

- **Supabase Data API default change** (email received May 12, 2026): starting May 30 for new projects, October 30 for existing projects, new tables in `public` schema won't be exposed via supabase-js / REST / GraphQL by default. **Existing tables keep their grants**, so super.xxl.co.il is unaffected for current code. For NEW tables created after Oct 30, 2026, must run explicit GRANT statements if they need to be reachable from the frontend. Pattern: `GRANT SELECT, INSERT, UPDATE, DELETE ON public.your_table TO authenticated;` + RLS policy. Backend-only tables (FastAPI direct connection) are unaffected. Review Security Advisor in Supabase dashboard.
- **Carrefour 0-items on May 18, 2026 cron run** — Upstream gov.il published only 1 PriceFull file (vs 7 expected). May be transient (weekend/Monday publishing gap) or persistent. Recheck May 19 logs.

---

## 🔑 Key Architectural Decisions

- **Full Kamatera consolidation (May 18, 2026)** — All production infra on Kamatera Tel Aviv VPS ($17/mo after Jun 17 free trial expires): Postgres + scraper cron + FastAPI behind nginx + Let's Encrypt. Railway fully decommissioned May 18. Single host, single bill, no cross-host network latency, no geo-block issues.
- **SQLAlchemy everywhere** — scrapers are DB-agnostic.
- **Snapshot pricing only** — not yet tracking history (deferred to 9d).
- **Phased city expansion strategy** — currently 26 stores in Jerusalem/Bnei Brak. Session 9d-1 expands to 7 cities (~86 stores). Sessions 9d-2+ expand to all 100K+ cities (~216 stores). Sessions 11+ expand to 50K+ cities (~540 stores). Full coverage requires AWS/GCP migration when Railway hits limits.
- **Daily cron at 3am Israel time (1am UTC)**.
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

---
## Operating patterns Established

- **One chat = one session** — Long conversations balloon in token cost (cumulative history is re-read every turn, so turn 60 of a chat costs much more than turn 5 of a new one). At natural breakpoints (end of session, deploy verified, phase complete), START A FRESH CHAT and paste handoff.md as the first message. Yesterday's debugging context isn't useful for today's feature work — it's just expensive baggage. Especially: avoid trying to squeeze a new session into an existing long chat just because we're already talking. Lesson learned in 9c when token budget hit limits faster than expected during Phase 2.

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
  - 0.45–1.45s: XXL slams in from above with 1.85× overshoot, deep squash to 0.78×, hard rebound to 1.18×, settle to 1×. Camera shake on impact (7px range), white flash (95% opacity), shadow layer materializes in sync.
  - 1.45–2.15s: Tagline appears above with fade + subtle slide-down
- React component `XxlLogo.tsx` with three variants: `hero` (large animated), `header` (small static), `favicon` (XXL-only stripped down). Accepts `lang` prop for Hebrew/English tagline switch.
- Hero section added above search bar on homepage.
- Header text "השוואת מחירים בסופרמרקט" replaced with static XXL header logo. Removed redundant ShoppingCart decorative icon.
- Custom favicon.svg created (XXL wordmark + shadow, no tagline).
- Page title updated to `XXL — חוסכים בענקקק`.

**Decisions made:**
- Master-brand-first strategy (Option B) chosen over per-vertical branding to ensure visual coherence across future xxl.co.il subdomains (fly, hotel, fashion).
- "Pure slam" animation chosen over "paper banner break" variant — pure version ages better, less visual complexity, more brand-mark-iconic.
- English tagline kept as 2× size jump (SAVING vs BIG) rather than 3× — clean ratio, avoids verticality issues.
- Animation runs once per session (via `sessionStorage.getItem('xxl_animated_this_session')`), not per page load — encourages "first impression" feel without becoming annoying on navigation.
- React `useId()` hook used for unique SVG path IDs (with colon-stripping to ensure XML validity) — prevents id clashes when both header and hero variants are on the same page.

**Outcome:** Site now has a distinctive, ownable brand identity. Animated hero on first session load, static logo in header, custom favicon, browser tab title updated. All brand decisions documented and codified in code (no more loose hex codes scattered through the app).

**Next:** Session 9b — User authentication (signup flow, login, account management). The "הירשמו" CTA button on the basket-limit toast will finally do something real.

### Planning Session (April 30, 2026) — Strategy & Roadmap Refinement

**Done (no code shipped, planning only):**
- Discussed multi-PC continuation workflow (clone repo + handoff.md = ready to work)
- Confirmed GitHub backup status — code safe, but Railway DB is single-point-of-failure (mitigation deferred to post-9c)
- Detailed analysis of "all 700 stores" tradeoff — decided to expand in tiers
- **Long-term vision clarified:** Premium tier will eventually include cross-chain ordering (~12+ months out), which requires full coverage and chain partnerships. Documented as future direction, not in current scope.
- Confirmed OpenFoodFacts is **abandoned** (was already in handoff but reinforced) — out of date, nearly empty for Israeli barcodes.
- Researched Israeli city populations (CBS data via web search): 18 cities >100K, ~45-50 cities >50K
- Locked the **city expansion plan**:

**City Expansion Plan (Sessions 9d-1 through 9d-N):**

Phase 1 — Session 9d-1 (Option C, geographic diversity):
- New cities: Tel Aviv-Yafo, Haifa, Be'er Sheva, Rishon LeZion, Ashdod
- Existing: Jerusalem, Bnei Brak (unchanged)
- 2 stores per chain per city → ~60 new stores
- Total post-rollout: ~86 stores across 7 cities
- Goal: validate scraper performance + Cerberus rate limits before scaling

Phase 2+ — Sessions 9d-2 onward:
- Expand to remaining 100K+ cities (12 more): Petah Tikva, Netanya, Holon, Ramat Gan, Ashkelon, Rehovot, Bat Yam, Beit Shemesh, Kfar Saba, Herzliya, Modi'in
- Target end-state for "100K+ tier": 18 cities × 6 chains × 2 stores = ~216 stores

Phase 3+ — Sessions 11+:
- Expand to 50K+ population cities (~25-30 more)
- Total target: ~540 stores

**Decisions made:**
- **Tier-based city expansion** beats "everything at once" — controls risk, gives natural scaling milestones, validates infra at each step
- **Defer infrastructure migration** — stay on Railway until $20+/mo costs OR DB > 8GB OR scrape > 4hrs OR >1000 active monthly users. Then migrate to AWS/GCP.
- **9b (user auth) remains the priority** — keystone for 9c (freemium) and unlocks the "save my basket" retention feature. Will be tackled before city expansion phases.
- **Auth approach for 9b:** Email/password primary + Google OAuth as option (decided yesterday).
- **OpenFoodFacts:** Will not retry. Code stays in repo for archaeological purposes only.
- **Premium ordering vision:** Acknowledged as long-term (12+ months), not blocking near-term sessions.

**Outcome:** Roadmap clarified, scope locked, ready to execute. No code changes, but the next session can start immediately with a clear plan.

**Next:** Session 9b — User authentication (email/password + Google OAuth). After 9b, evaluate whether to do 9c (freemium gating) or 9d-1 (city phase 1) next based on energy/mood.

### Session 9b (April 30, 2026) — User Authentication via Supabase + Saved Baskets

**Done:**
- **Supabase project provisioned** at https://dwohlwmiejgjlsbuegeu.supabase.co (Frankfurt region, free tier, ~50K MAU limit)
- **Database migration applied to Railway Postgres**: new `users` table (PK = Supabase UUID) and `saved_baskets` table (FK to users with ON DELETE CASCADE, JSONB items column, indexed by user_id). Migration file at `db/migrations/add_users_saved_baskets.sql`.
- **Backend (FastAPI):**
  - `api/auth.py` — JWT verification dependency + idempotent user upsert on every authed request
  - `api/routers/saved_baskets.py` — full CRUD (`POST/GET/GET-by-id/PUT/DELETE`) with ownership enforcement (404 on user_id mismatch, NOT 403, to avoid leaking basket existence)
  - Endpoints exposed at `/baskets` (no `/api/` prefix — matches existing `/basket/compare` pattern)
- **Frontend (React + Vite):**
  - Supabase client at `web/src/lib/supabase.ts` (anon public key in `VITE_SUPABASE_ANON_KEY`)
  - `AuthContext.tsx` — exposes `useAuth()` with user, signIn, signUp, signOut, accessToken
  - React Router added with routes `/`, `/login`, `/signup`, `/baskets`
  - HomePage extracted from old App.tsx into `pages/HomePage.tsx`
  - LoginPage, SignupPage, MyBasketsPage created (all RTL Hebrew, brand-emerald CTAs)
  - Header.tsx made auth-aware: logged-out shows "להרשמה" (emerald button) + "התחברות" links; logged-in shows User icon dropdown with email + "הסלים שלי" + "התנתקות"
  - BasketDrawer.tsx: "שמור סל" button (enabled when logged in, disabled with tooltip when logged out)
  - BasketContext.tsx: 25-item-limit toast CTA wired to `navigate('/signup')` (was placeholder console.log in 9a)
  - api/client.ts: axios interceptor automatically attaches `Authorization: Bearer <token>` to all requests when user is logged in
  - display_name field removed from signup (was being collected but not persisted — UX wart, removed per Eltzur direction)

**Deployment notes:**
- `.gitignore` had a generic `lib/` rule that accidentally caught `web/src/lib/supabase.ts`. Fixed by adding `!web/src/lib/` and `!web/src/lib/**` whitelist rules.
- `web/.env.development` and `web/.env.production` both contain `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`. Properly gitignored — keys never reach the public repo.
- Railway env vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` all set on the `web` service.
- Frontend bundle grew from 402 KB → 665 KB (+260 KB Supabase SDK). Worth code-splitting later but not urgent.

**Decisions made:**
- **Auth library: Supabase** (Option B from the planning session) — battle-tested, free up to 50K MAU, handles password hashing / sessions / reset emails / OAuth providers. Vendor dependency accepted.
- **User data stays in Railway Postgres**, not Supabase DB — Supabase is auth-only. Foreign keys to baskets/favorites/etc. all live in Railway. Single source of truth for app data.
- **Routes over modals** for signup/login — easier to build correctly in RTL, better SEO, easier to deep-link.
- **Email confirmation: KEPT ENABLED** despite original spec to disable. Reasoning: security best practice, low friction, Supabase enforces it for the first user creation regardless of toggle. Decision: leave it on permanently.
- **Google OAuth: DEFERRED.** Email/password is working; Google requires a Google Cloud Console OAuth client setup. Will be added in a follow-up session, NOT 9c.
- **JWT verification migrated to ES256/JWKS** mid-deploy. Supabase recently switched from HS256 (shared secret) to ES256 (asymmetric public-key crypto). Original CC code assumed HS256, which caused all authed requests to 401. Backend rewrite to use `https://{SUPABASE_URL}/auth/v1/.well-known/jwks.json` for verification. Fixed in-session.
- **404 not 403 on basket ownership mismatch** — security pattern, prevents leaking that a basket exists.
- **No `/api/` prefix** on basket endpoints — matched existing `/basket/compare` pattern.

**Bugs encountered & resolved:**
1. ✅ CC's terminal report displayed Hebrew strings reversed character-by-character (RTL/LTR rendering bug). The actual code was correct. Verified via VS Code Find.
2. ✅ `web/src/lib/supabase.ts` was caught by the catch-all `lib/` rule in `.gitignore`. Whitelisted with `!web/src/lib/`.
3. ✅ JWT signing algorithm mismatch (Supabase ES256 vs backend HS256) — fixed via JWKS-based public-key verification in api/auth.py.
4. ✅ Email confirmation flow — Supabase still required email verification for the first signup despite the dashboard toggle. Resolved by clicking the confirmation link in email.
5. ⚠️ Favicon stale in some browsers — file is correct on Hostinger and source code, but browser cache holds onto the old Vite lightning bolt favicon. Will resolve naturally for new visitors. Local fix: clear site data + reload.
6. ✅ Database tables disappeared between morning and evening of session 9b (root cause unknown — Railway Postgres may have been reprovisioned, or migration ran on a stale connection). Re-ran migration manually via Railway Query editor — both tables came back, no data loss since tables were never populated. Investigate before next session.
7. ✅ SQL parameter binding bug in saved_baskets endpoints — original code mixed psycopg2-style `%(name)s` with SQLAlchemy `:name` style, AND used `::jsonb` cast which collided with SQLAlchemy's parameter scanner. Fixed by standardizing on SQLAlchemy `:name` style and using `CAST(:items AS jsonb)` instead of `:items::jsonb`. Both POST and PUT endpoints had the bug; both fixed.
**Files changed:**
- New: `api/auth.py`, `api/routers/saved_baskets.py`, `db/migrations/add_users_saved_baskets.sql`, `web/src/components/AuthContext.tsx`, `web/src/lib/supabase.ts`, `web/src/pages/HomePage.tsx`, `web/src/pages/LoginPage.tsx`, `web/src/pages/SignupPage.tsx`, `web/src/pages/MyBasketsPage.tsx`
- Modified: `api/main.py`, `requirements.txt`, `web/package.json`, `web/package-lock.json`, `web/src/App.tsx`, `web/src/main.tsx`, `web/src/api/client.ts`, `web/src/components/BasketContext.tsx`, `web/src/components/BasketDrawer.tsx`, `web/src/components/Header.tsx`, `.gitignore`

**Outcome:**
- ✅ Email/password signup + login working in production
- ✅ User auth state correctly reflected in header (account icon dropdown when logged in)
- ✅ 25-item toast CTA correctly navigates to /signup
- ✅ Save-basket: working end-to-end — POST /baskets returns saved basket with id, frontend renders success toast
- ✅ My-baskets list view: working — basket appears at /baskets with name, item count, last updated date, "טען" and "מחק" buttons
- ✅ Favicon: confirmed working in incognito after the recent deploy. Hard reload was needed for already-cached browsers; new visitors see XXL favicon by default

**Next:** Once save-basket verified working in production, update the Outcome bullets above. Then move to either:
- **9c (Freemium gating)** — differentiate free vs paid tier (the 25-item limit currently applies to logged-in users too, which doesn't make sense for paying customers)
- **9d-1 (City phase 1)** — add 5 new cities × 6 chains × 2 stores = ~60 new stores, brings total to ~86 stores across 7 cities
- **Google OAuth follow-up** — wire up the option that was deferred from 9b

Recommended order: 9c next (small, completes the auth → freemium picture before building more features). Then either 9d-1 or Google OAuth.


### Planning Session (May 2, 2026) — 9c Scope Refinement

**Done (planning + scoping, code coming next):**
- Reviewed handoff and confirmed 9b shipped successfully (auth + saved baskets all green in production)
- Reviewed the original 9c plan ("freemium gating, server-side 25-item limit per account") and concluded it was misaligned with the freemium model that was actually decided in session 9a (everything-but-ordering is free)
- Restructured 9c into two phases:
  - **Phase 1 (Mini-9c):** Lift 25-item basket cap to 150 for logged-in users. Logged-out users stay at 25 with the existing emerald להרשמה toast. Logged-in users at 150 see a brief amber/orange toast "הסל הגיע למקסימום של 150 פריטים" — no CTA, no signup nudge.
  - **Phase 2 (Engagement features):** Favorites (server-side, logged-in only) + Recent Searches (localStorage, search-bar dropdown only).

**Scope decisions for Phase 2:**
- **Favorites:** Logged-in only (cleanest). New `favorites` table (user_id, barcode, created_at, composite PK). Endpoints `POST /favorites/{barcode}`, `GET /favorites`, `DELETE /favorites/{barcode}`. Star icon on ProductCard. New `/favorites` route + page. "המועדפים שלי" link in account dropdown.
- **Recent Searches:** Client-side only (localStorage, max 10 items, deduped). Dropdown shown when search input is focused and empty. Path 1 from earlier scoping — Path 2 (server-side sync) deferred indefinitely; if users ask for cross-device sync, we add it then.

**Decisions made:**
- **Logged-in basket cap = 150** — generous enough that no real human will hit it, low enough to prevent runaway client memory in pathological cases.
- **No server-side enforcement of basket cap** — frontend check is sufficient; we'll add server-side validation only if/when we see abuse.
- **No CTA button on the 150-cap toast** — different intent from the signup nudge; this is just a "you've hit the ceiling, sorry" message. Orange/amber instead of brand emerald to visually differentiate.
- **Favorites is server-side from day 1** — unlike recent searches, favorites are about cross-device persistence. Users expect their stars to follow them.
- **Skipped: Database migration mystery investigation** — Eltzur decided to defer pending future AWS/GCP migration, where this becomes moot.

**Out of scope for 9c (deferred to future sessions):**
- Multiple named baskets (e.g., "Weekly", "Shabbat") — interesting but no clear user demand yet
- Saved-basket renaming/duplication — minor polish
- Basket sharing via public link — interesting but post-monetization
- Price-drop notifications UI — paid tier feature, comes with the email infrastructure
- Google OAuth — still deferred from 9b, will tackle separately when we have appetite for Google Cloud Console setup
- Server-side recent searches sync — only if users ask

**Outcome:** 9c scope locked, two CC prompts ready (Phase 1 surgical, Phase 2 larger). Each phase ships independently — Phase 1 is frontend-only (one file), Phase 2 touches multiple files (backend migration + endpoints + frontend pages).

**Next:** Run Phase 1 → deploy → test → run Phase 2 → deploy → test. Then session 9d-1 (city + chain expansion).


### Session 9c (May 2, 2026) — Mini-9c + Favorites + Recent Searches

**Done:**
- **Phase 1 (Mini-9c)**: Logged-in users now have a 150-item basket cap (vs 25 for logged-out). Logged-in cap-hit fires an amber/orange (#EA580C) Sonner toast "הסל הגיע למקסימום של 150 פריטים" with no CTA. Logged-out 25-item toast with "להרשמה" emerald CTA preserved exactly as before.
- **Phase 2A (Favorites — server-side, logged-in only)**:
  - New `favorites` table (composite PK on user_id + barcode, FK to users with ON DELETE CASCADE)
  - New endpoints: `POST /favorites/{barcode}` (toggle, idempotent), `GET /favorites` (list with item details), `DELETE /favorites/{barcode}` — all auth-required, queries inherently scoped via composite PK
  - New `FavoritesContext` with optimistic toggle + revert-on-error
  - Heart icon (lucide-react `Heart`) on every ProductCard, top-right of badge row. Brand orange (#EA580C) when filled, gray-300 outlined when not
  - Logged-out users clicking heart get a toast "התחברו כדי לסמן מועדפים" with "להתחברות" CTA → /login
  - New `/favorites` page rendering favorited items as ProductCards (auth-required, redirects to /login if not authed)
  - "המועדפים שלי" link added to account dropdown in Header
- **Phase 2B (Recent Searches — client-side, dropdown only)**:
  - New `useRecentSearches` hook backed by localStorage (key: `xxl_recent_searches`)
  - Stores up to 10 most recent unique queries (case-insensitive dedup, trims, ignores < 2 char), most recent first
  - Dropdown appears when search input is FOCUSED + EMPTY + has at least one entry
  - Each row: query text + × to remove that one. "נקה הכל" link to clear all
  - Click row → fills input + triggers search. `onMouseDown: e.preventDefault()` on dropdown items prevents blur-before-click race
- **Cheapest indicator visual fix**: Replaced the in-row star (which collided visually with the favorite star) with `CheckCircle2` (outlined, emerald-600). No more double-star ambiguity.

**Decisions made:**
- **Logged-in cap = 150**: generous enough no human hits it, low enough to prevent runaway memory in pathological cases.
- **No server-side enforcement of basket cap**: frontend check sufficient until abuse seen.
- **Favorites server-side, recent searches client-side**: favorites are about cross-device persistence (users expect stars to follow them); recent searches are ephemeral and per-device. Path 1 (localStorage) for searches kept scope tight.
- **FavoritesPage uses N+1 fetch pattern** (Promise.allSettled per favorite): acceptable for typical usage (<50 favorites). If users hit much higher counts, build a `/product/batch?barcodes=...` endpoint.
- **Heart in brand orange (#EA580C), not red**: cohesive with XXL palette (orange already used in logo speed lines + basket-limit toast). Avoids red's "danger" connotation in a savings-positive context.
- **CheckCircle2 outlined, not filled**: subtler than a filled badge. Lets the row itself (with emerald-50 background) carry the "cheapest" signal; the icon is just confirmation.
- **Original "freemium gating" 9c framing retired**: no server-side per-account 25-item enforcement. The free tier is the honeypot; only logged-out users see the 25-item nudge as a signup driver.

**Files changed:**
- New: `db/migrations/add_favorites.sql`, `api/routers/favorites.py`, `web/src/components/FavoritesContext.tsx`, `web/src/pages/FavoritesPage.tsx`, `web/src/hooks/useRecentSearches.ts`
- Modified: `api/main.py`, `web/src/api/client.ts`, `web/src/App.tsx`, `web/src/components/Header.tsx`, `web/src/components/ProductCard.tsx`, `web/src/components/SearchBar.tsx`, `web/src/components/BasketContext.tsx`

**Bugs encountered & resolved:**
1. ✅ Initial CC implementation reused the existing `Star` icon for both "favorites" and "cheapest indicator" — visually ambiguous. Caught during sanity check, swapped to `Heart` (favorites) and `CheckCircle2` (cheapest) before deploy.
2. ⚠️ False alarm: CC's terminal report rendered Hebrew strings reversed (e.g., `ילש םיפדעומה` instead of `המועדפים שלי`). Verified via VS Code Find that file content is correct. Same RTL terminal display bug seen in 9b and 9c Phase 1. **From now on, treat reversed-Hebrew in CC reports as a non-issue unless VS Code Find can't locate the correctly-spelled string.**

**Outcome:**
- ✅ Phase 1 verified: logged-out 25-cap toast unchanged (regression test passed); logged-in 150-cap toast fires correctly with orange styling
- ✅ Phase 2A verified: heart toggles, persists across reload, /favorites page renders, dropdown link works
- ✅ Phase 2B verified: recent searches stored, dropdown appears on empty-focused input, click re-runs search, × removes individual, "נקה הכל" clears all
- ✅ Cheapest indicator visual fix in production

### Session 9f-followup (May 14, 2026) — Portal Polish

**Done:**
- Hostname-aware SEO meta tags (title/description/OG/Twitter cards differ for xxl.co.il vs super.xxl.co.il). Static tags in index.html default to portal; runtime override in App.tsx via `seoMeta.applyHostnameMeta()` switches to supermarket-app variant on super.xxl.co.il.
- OG image URLs reference `/og-portal.png` (xxl.co.il) and `/og-super.png` (super.xxl.co.il) — 1200×630 PNGs uploaded separately by Eltzur to Hostinger public_html/.
- Portal email signup (ComingSoonPage on /vacation + /fashion) now writes to Supabase `portal_email_signups` table via supabase-js. Anonymous insert allowed via RLS + explicit GRANT (future-proof for Oct 30 Data API policy change).
- GA4 wired via VITE_GA_MEASUREMENT_ID env var. Pageviews tracked manually on SPA route changes (gtag config has send_page_view: false). Idempotent init, gated on cookie consent.
- Minimal Hebrew cookie banner ("נמשיך, אנו משתמשים בעוגיות לשיפור החוויה") with X-dismiss-as-consent. localStorage key: `xxl_cookie_consent`. Banner only renders when key absent.
- `isPortalHostname()` refactored from App.tsx-inline to `web/src/utils/hostname.ts` for reuse by seoMeta.ts.

**Decisions made:**
- Cookie banner X-dismiss = implicit consent (per Eltzur, soft-launch UX over strict GDPR-style explicit opt-in). IL-targeted product; revisit if/when expanding to EU users.
- One GA4 property covers both hostnames; filter in reports by page_location host.
- Supabase direct write from frontend (not via FastAPI endpoint) — anonymous signup, no auth flow needed, simpler. Explicit GRANT statements in migration to future-proof against Oct 30 Data API policy default change.
- Static fallback meta tags default to portal version (xxl.co.il) since it's the new marketing surface; super.xxl.co.il SEO is well-established already and SPA crawlers (Google) execute the JS overrides anyway.
- Did NOT modify XxlLogo.tsx or XxlLogoPortal.tsx — favicon decision was "same XXL logo for both," which means no work needed since existing favicon already serves both.

**Files changed:**
- New: `web/src/utils/seoMeta.ts`, `web/src/utils/hostname.ts`, `web/src/utils/analytics.ts`, `web/src/components/CookieBanner.tsx`, `db/migrations/9f_followup_portal_email_signups.sql`, `web/.env.example`
- Modified: `web/index.html` (meta tags), `web/src/App.tsx` (hostname import + useEffect for meta/GA + CookieBanner mount), `web/src/pages/ComingSoonPage.tsx` (Supabase insert + vertical prop), `web/src/pages/VacationPage.tsx` + `FashionPage.tsx` (vertical prop), `web/.env.production` (VITE_GA_MEASUREMENT_ID), `web/.gitignore` (!.env.example exception)

**Outcome:**
- ✅ SEO meta tags hostname-aware
- ✅ OG image refs in place (PNGs to be uploaded separately by Eltzur)
- ✅ Email signups persist to Supabase
- ✅ GA4 stub wired, awaiting Eltzur's real G-XXXXXXXXXX
- ✅ Cookie banner shipped

**Pending Eltzur post-deploy:**
1. Run `db/migrations/9f_followup_portal_email_signups.sql` in Supabase SQL Editor
2. Upload `og-portal.png` + `og-super.png` to Hostinger public_html/ (1200×630 each)
3. Create GA4 property → grab G-XXXXXXXXXX → swap into `web/.env.production` → rebuild + redeploy
4. Mobile QA: test /vacation + /fashion signup on real phone, verify WhatsApp link preview after PNGs uploaded, verify cookie banner dismiss works
**Post-deploy state (end of session):**
- ✅ SQL migration ran successfully in Supabase
- ✅ GA4 wired with real Measurement ID G-YB4X4E5ZKM (baked into web/.env.production)
- ✅ OG images uploaded to Hostinger public_html/ (og-portal.png, og-super.png)
- ✅ Cookie banner verified live on xxl.co.il
- ✅ Test email signup verified landing in portal_email_signups table
- ⏳ Mobile QA pass on real device — deferred
- ⏳ WhatsApp link preview shows title+desc but no image on first scrape — likely Facebook scraper cache. Fix via https://developers.facebook.com/tools/debug → paste URL → Scrape Again. Defer until pre-marketing-push.

**Incident note:** og-super.png initially returned blank/404 due to filename typo during upload to Hostinger. Re-uploaded correctly via File Manager. Lesson: when uploading single files manually to Hostinger, double-check filenames against the index.html meta references — a typo there fails silently (blank response, not 404).

---

### Session 9f (May 12-13, 2026) — XXL Portal Page → Live on xxl.co.il

**Done:**
- **Designed and built the xxl.co.il portal landing page**: hero with animated logo, AI search bar (rotating placeholders), 3 vertical tiles (מצרכים live, חופשות + אופנה בקרוב), value-props strip, footer.
- **3-tile design (down from initial 4-tile)**: collapsed flights + hotels into "חופשות — טיסות ומלונות" with Sun icon. אופנה uses Shirt icon. מצרכים uses ShoppingCart with emerald LIVE badge.
- **Mocked AI search router shipped**: `portalSearchRouter.ts` with Hebrew + English keyword lists. Groceries → external nav to super.xxl.co.il, vacation/fashion → internal React Router, unknown → Hebrew error hint.
- **2 בקרוב sub-pages live** at `/vacation` and `/fashion`: hero + email signup card + "חזרה לדף הבית" link. Email signup `console.log` only (intentional, real wiring deferred to 9f-followup).
- **XxlLogoPortal component created** as duplicate of XxlLogo.tsx with tagline "קונים חכם · חוסכים בענקקק" arching above wordmark. fontSize 28 + letterSpacing -0.5 to fit longer string. Distinct sessionStorage key.
- **Sub-header polish**: "XXL — הפורטל שהופך כסף רגיל לכסף חכם" → final "הפורטל שהופך כסף רגיל לכסף חכם" (dropped XXL prefix; logo above establishes brand). `text-2xl md:text-4xl font-bold`.
- **Hebrew default fixed**: app was loading English on first visit. Now defaults Hebrew with localStorage preservation of user's explicit choice.
- **DNS setup**: A records at box.co.il for `xxl.co.il` and `www.xxl.co.il` → `82.198.227.247`. MX records for Titan email kept untouched.
- **Hostinger parked domain**: `xxl.co.il` parked on top of `super.xxl.co.il`. Both serve from same `public_html/`.
- **SSL**: Lifetime SSL auto-provisioned for `xxl.co.il` within ~30 min of parking.
- **Hostname-based routing in React (final approach)**: `App.tsx` checks `window.location.hostname`; on xxl.co.il, `/` renders PortalPage. Clean URL — `xxl.co.il/` shows portal at `xxl.co.il/`, no `/portal-preview` suffix.
- **Local dev override**: `localhost?portal=1` simulates portal hostname for testing.
- **Two deploys to Hostinger this session**: first got portal pages onto production; second finalized clean URLs after hostname routing change.

**Decisions made:**
- **Multi-vertical portal = paths on xxl.co.il, NOT subdomains**. Simpler routing, one codebase, one deploy.
- **חופשות collapses flights + hotels** — cleaner UX, matches how Israeli travelers actually shop (package vacations).
- **Mocked keyword router over real Haiku for MVP** — ships UI without API key complexity; Haiku becomes its own clean session (9h).
- **Email signup intentionally dummy at launch** — soft-launch acceptance: low signup volume expected, easier to wire backend later than delay launch.
- **Hostname-based routing in React (not .htaccess)** — `.htaccess` 302 redirect approach worked but left `/portal-preview` in URL bar. Final: hostname detection in React, .htaccess back to minimal SPA fallback only.
- **Softened "freemium" claim on value-props**: "ההשוואה תמיד חינם, ללא הגבלות" → "ההשוואה תמיד חינם" (no "unlimited" claim, since 25-item cap exists for logged-out users).
- **XxlLogo.tsx untouched, XxlLogoPortal duplicated** — keeps super.xxl.co.il logo 100% safe from portal changes. Code duplication accepted as right tradeoff for visual isolation.

**Files changed:**
- New: `web/src/pages/PortalPage.tsx`, `web/src/pages/ComingSoonPage.tsx`, `web/src/pages/VacationPage.tsx`, `web/src/pages/FashionPage.tsx`, `web/src/components/XxlLogoPortal.tsx`, `web/src/utils/portalSearchRouter.ts`
- Modified: `web/src/App.tsx` — added `isPortalHostname()` at top, restructured top-level `<Routes>` to include portal routes + conditional `/` for portal hostname + catch-all to `AppShell`. Existing supermarket logic preserved inside AppShell.
- Modified: supermarket app's language initialization logic — now defaults Hebrew when no localStorage preference, preserves user choice when set.
- Hostinger-side (not in repo): `.htaccess` briefly held portal-rewrite block mid-session, ended at minimal SPA fallback only.

**Bugs encountered & resolved:**
1. ✅ **Tagline clipping on portal logo arc** — "קונים חכם · חוסכים בענקקק" is ~60% longer than original. First fix (fontSize 42 → 36) insufficient. Final: fontSize 28 + letterSpacing -0.5.
2. ✅ **First parked domain typo** — entered `xxk.co.il` instead of `xxl.co.il` in Hostinger. Caught before clicking nameserver-change guide (would have wiped DNS records). Deleted typo entry, re-added correctly.
3. ✅ **.htaccess 302 redirect approach** — initial `^$` pattern didn't match Apache root requests on Hostinger's config. Fixed with `^/?$` + `[R=302]`, which worked but left "/portal-preview" in URL bar. Final work replaced this entirely with React hostname detection.
4. ✅ **English-by-default on first load** — language init defaulted to 'en'. Fixed to default Hebrew while preserving localStorage choice.
5. ✅ **Two `.htaccess` files after zip extraction** — Vite generates `.htaccess` in dist/. Resolved by deleting redundant copy.

**Outcome:**
- ✅ https://xxl.co.il loads portal at clean root URL
- ✅ https://www.xxl.co.il same
- ✅ https://xxl.co.il/vacation and /fashion show בקרוב pages
- ✅ https://super.xxl.co.il/ unchanged, Hebrew default
- ✅ SSL active on both (Lifetime)
- ✅ All React Router routes work on both hostnames
- ✅ Mobile responsive
- ✅ Rotating placeholder cycles 4 examples

**Next:** Session 9g — Scraper Infrastructure (performance + geo correctness). Sessions 9f-followup (portal polish) and 9h (Claude Haiku integration) are parallel tracks, can happen anytime.

### Session 9d-1 (May 11-12, 2026) — City Expansion Phase 1 + Carrefour + Verification System

**Done:**
- **New chain shipped: Carrefour Israel** (chain_id `7290055700007`, operated by Global Retail C.I. — includes Carrefour + Mega + Yenot Bitan sub-brands under one publisher).
- **New portal type abstracted**: `scraper/publishprice.py` base class (~130 lines) for JS-embedded file listing portals. `scraper/carrefour.py` is a 6-line subclass. Reusable for future chains.
- **City expansion Phase 1**: added 5 new cities (Tel Aviv, Haifa, Be'er Sheva, Rishon LeZion, Ashdod) on top of existing Jerusalem + Bnei Brak. Total: 7 cities.
- **Store selection rule documented**: lowest 2 `store_id` integers per (chain_id, city) from chain's `stores` table. Deterministic, reproducible. Falls back to store_name pattern matching for chains with NULL city data (Victory, Yochananof, Keshet — pre-existing 8a issue).
- **Verification-before-scrape system (Path C)**: new `scraper/active_stores.yaml` populated by per-store `verify_publishes_pricefull()` check. `scraper/scheduled_stores.yaml` retained as intent/wish-list. `scraper/cron_main.py` reads from active_stores. **58 of 72 stores verified.** 14 excluded breakdown:
  - 11 Shufersal (mostly Sheli format — old Jerusalem stores without per-store PriceFull files; 1 Universe-format unknown; 1 BE-format not found in scan; 1 store missing from local DB)
  - 1 Rami Levy 004 (warehouse, no city)
  - 2 Osher Ad 002, 004 (warehouses, no city)
- **Verification report**: `db/verification_report_9d1.md` documents excluded stores by category for 9e replacement work.
- **Shufersal page-limit patch**: scraper's hardcoded `start_page + 25` cutoff replaced with "scan until all requested stores found, OR safety cap at 200 pages with logged not-found list."
- **Procfile fix**: added `cron: python -m scraper.cron_main` process type so Railway commands are repo-authoritative, not UI-only. Root cause of weeks of OFF-enrichment-instead-of-price-scrape silent failure.
- **Sample Promo XML captured** for future promotions session: `Promo7290661400001-250-202605112159-001.xml.gz` and `Price7290055700007-3210-202605112200.gz` saved as reference samples.

**Decisions made:**
- **Carrefour publisher returns Mega + Yenot Bitan stores too — take them all under "קרפור" display name.** Cleaner UX than trying to split.
- **Bnei Brak zero-Carrefour-stores is real**, not a CITY_CODES dict gap — verified via carrefour.co.il store locator manually.
- **Store_name inference approved** for Victory/Yochananof/Keshet city assignment when `stores.city` is NULL. YAML entries get a "city inferred from store_name" comment for future audit.
- **Keshet Haifa includes Hadar (real Haifa neighborhood) but EXCLUDES Nesher (separate municipality)** — sets a precedent: when sub-city names are ambiguous, prefer narrow interpretation over wide.
- **Path C (verification gate) chosen over Path A (Shufersal-specific patch)** — surfaces heterogeneity across all chains at once; sets architecture for 9e Registry work.
- **Sub-chain heterogeneity ("Yesh" = Shufersal haredi, "Mega" = Carrefour publisher) is a class of problem, not chain-specific.** Solving via systemic StoreNext-based registry (9e) rather than per-chain patches.
- **9g (Scraper Infrastructure) prioritized AHEAD of 9e (StoreNext Registry)** — performance + geographic correctness unblocks all subsequent sessions; registry's payoff is architecturally cleaner selection but doesn't unblock anything urgent.

**Files changed:**
- New: `scraper/publishprice.py`, `scraper/carrefour.py`, `scraper/active_stores.yaml`, `db/verification_report_9d1.md`
- Modified: `scraper/registry.py` (added Carrefour), `scraper/scheduled_stores.yaml` (added 46 new-city entries), `scraper/shufersal.py` (page-limit patch), `scraper/cron_main.py` (read from active_stores.yaml), `Procfile` (added cron: line)

**Bugs encountered & resolved:**
1. ✅ **Shufersal `start_page + 25` silent cutoff** — page-limit on `build_pricefull_index` was hiding the real issue (Sheli-format heterogeneity). Patched to 200-page safety cap with explicit not-found logging.
2. ✅ **Phase B "lowest 2 store_ids" selection picked stores that don't publish PriceFull** — primarily affected Shufersal (11 of 12 new-city stores excluded). Path C verification gate now catches this before runtime.
3. ✅ **Procfile missing `cron:` process type** — scraper-cron service was silently running `python -m scraper.fetch_off` from Railway UI config, not the actual price scrape. Last successful price load before fix was April 25 (16 days stale). Production prices were intact but not refreshing. Caught by reviewing build logs after first 9d-1 cron run "succeeded" in ~5 min instead of expected 15-25 min.
4. ⚠️ **Geo-blocking on Victory + Carrefour** — both `laibcatalog.co.il` (Victory) and `prices.carrefour.co.il` (Carrefour) reject Railway US-West IPs. Confirmed via VPN test (works from Israeli IP, fails from US/India). Other 5 chains' portals don't enforce this. **Status at session close: trying Railway EU-West region as zero-cost mitigation; if insufficient, Israeli VPS migration planned in 9g.**

**Outcome:**
- ✅ Carrefour scraper shipped and verified locally (153 stores in StoresFull catalog, 130 city-mapped, 23 NULL-city for cities not in CITY_CODES dict)
- ✅ Verification system shipped — 58/72 store gate working as designed
- ✅ Procfile bug fixed, repo now source of truth
- ✅ 5 of 7 chains successfully loaded fresh prices to production: Shufersal, Rami Levy, Osher Ad, Yochananof, Keshet (Carrefour + Victory blocked pending 9g geo fix)
- ✅ Production state at session close: 7 chains, 49 stores, 372,159 prices (5 chains with fresh data from 5/11 evening; Carrefour + Victory pending 9g geo-fix). EU-West region experiment failed — caused 30× slowdown on Cerberus chains and didn't bypass geo-block. Reverted to US-West.
- 📝 New session 9g queued for infrastructure work; 9e (StoreNext Registry) queued behind it
- 📝 New session 9f queued for portal page (parallel track)
- 📝 CITY_CODES audit added as small follow-up patch session

**Next:** Session 9g — Scraper Infrastructure (performance + geographic correctness). Priority over 9e because (a) bulk inserts + parallelism unblocks all future city expansions, and (b) Victory + Carrefour need a geographic fix to get fresh data. StoreNext investigation continues in parallel; if their paid tier offers product catalog, 9e may re-prioritize ahead of 9g.

### Session 9g (May 17, 2026) — Scraper Performance + Kamatera Migration

**Scope at session start:** Three workstreams — (1) bulk inserts replacing per-row INSERTs, (2) parallel chain execution, (3) geographic fix for Victory/Carrefour geo-block. Chose order: bulk inserts → parallel → geo fix.

**What actually happened (order shifted by reality):**

**9g-1: Bulk inserts** — Implemented as batched `INSERT ... VALUES (...), (...)` at 1000 rows/statement across items, item_chain_names, prices tables. Local SQLite tests passed (5.8s per store, 15× speedup over baseline). First Railway production run crashed with Postgres `CardinalityViolation: ON CONFLICT DO UPDATE command cannot affect row a second time` — Rami Levy's source XML had 9 duplicate item_codes per store with identical prices. SQLite tolerated this silently; Postgres did not.

Dedup hotfix: deduplicate by `item_code` once per store before all three bulk calls in `scraper/base.py`. Last-wins semantics matches existing ON CONFLICT DO UPDATE. Added warning log for the rare case where duplicates have *differing* values (genuine data quality signal). Commit `4678207`. Local SQLite + Postgres-via-Docker validation passed.

**Railway Postgres disk-full crash** — Second Railway production attempt failed differently: scraper couldn't even connect because Postgres was in a crash loop. Root cause: Railway free trial 0.5 GB volume exhausted by accumulated WAL from previous failed runs. Postgres logs showed `FATAL: could not write to file "pg_wal/xlogtemp.33": No space left on device` looping. Investigated Railway dashboard — trial status was "6 days or $2.45 left", no easy fix without paid tier upgrade.

**Decision: skip Path C "Railway Hobby probation" and go directly to Path B "all-in on Kamatera."** Reasoning: Railway's tier curve doesn't fit a data-ingestion workload; we'd outgrow Hobby's 5GB in ~3 months anyway. GCP free tier rejected after fact-check (Always-Free e2-micro is US-only, doesn't solve geo-block). Kamatera chosen: Tel Aviv DC, 30-day free trial, ~$17/mo for 1 vCPU / 2 GB RAM / 30 GB SSD, simple operational model.

**Kamatera migration (Phases 2-6):**
- Provisioned `scrp-prod-il` at `185.229.226.190` (Tel Aviv, Type B General, Ubuntu 24.04 LTS)
- Server hardening: non-root `dude` user with sudo, SSH key auth, password SSH disabled, UFW firewall (22 + 5432), fail2ban, timezone Asia/Jerusalem
- Postgres 18.4 from PGDG official repo (not Ubuntu's default), tuned for 2GB RAM (shared_buffers 512MB, effective_cache_size 1GB, work_mem 16MB, wal_compression on)
- Database `xxl_super` owned by `scrp_app` user (password generated via `openssl rand -base64 32`, stored in password manager)
- Scrp repo cloned to `/home/dude/scrp`, venv created, requirements installed, `.env` at `~/scrp/.env` with permissions 600
- All 9 expected tables created (chains, stores, items, item_chain_names, prices, favorites, fetch_runs, saved_baskets, users)
- systemd timer `scrp-cron.timer` scheduled daily 03:00 IDT (DST-aware via OnCalendar). Service exits inactive on success; `Restart=no` so failures are visible.

**Validation results — the moment of truth:**

Three-chain geo-block test:
| Chain | Store | Prices | Time | Result |
|---|---|---|---|---|
| Victory | 008 | 4,684 | 4.2s | ✅ Geo-block resolved |
| Carrefour | 6 | 3,943 | 3.0s | ✅ Geo-block resolved |
| Shufersal | 073 | 4,823 | 40.3s | ✅ (page-scan bottleneck unrelated to geo) |

Full cron run, 7 chains × 58 stores:
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

Exit code 0, no errors. Keshet logged 2 stores with duplicate item_codes having differing values (dedup last-wins applied, warning logged — working as designed).

**Decisions made:**
- **All-in on Kamatera (Path B) over Path C "Railway Hobby probation"** — sunk-cost-fallacy avoidance; Railway tier curve wrong for our shape regardless of immediate fix
- **GCP free tier rejected** — Always-Free e2-micro is US-only (wrong region, geo-block remains); $300 credit burns in ~4 weeks under real load; complexity tax not worth saving $4/mo
- **9g-2 (parallel chains) deferred indefinitely** — sequential is 3m31s; parallelism saves ~2.8 min; low ROI vs other levers
- **Shufersal page-scan caching identified as higher-leverage future optimization** than parallelism — would drop full cron from 3m31s to ~1m
- **Postgres tuning explicitly captured in postgresql.conf** rather than left at defaults — 2GB RAM box needs hand-tuning to perform well

**Files changed:**
- `scraper/base.py` — added `valid_deduped = list({item['item_code']: item for item in valid}.values())` dedup before bulk insert calls + warning log for differing-value duplicates
- `db/db.py` — bulk insert functions for items, item_chain_names, prices (batched VALUES at 1000 rows/statement)
- Server-side new files (not in git, on Kamatera only):
  - `/etc/systemd/system/scrp-cron.service` — runs `cron_main` as `dude` user, sources `.env`
  - `/etc/systemd/system/scrp-cron.timer` — daily 03:00 IDT, DST-aware
  - `/etc/postgresql/18/main/postgresql.conf` — tuned for 2GB RAM
  - `/etc/postgresql/18/main/pg_hba.conf` — temporary `0.0.0.0/0` for scrp_app (to be narrowed in Phase 7)
  - `/home/dude/scrp/.env` — DATABASE_URL with localhost Postgres connection

**Bugs encountered & resolved:**
1. ✅ Postgres CardinalityViolation on ON CONFLICT — duplicate item_codes in source XML, fixed via dedup in base.py (commit 4678207)
2. ✅ SQLite vs Postgres semantic mismatch — SQLite tolerates ON CONFLICT duplicates in a single statement, Postgres rejects. Local SQLite tests were insufficient. Going forward, Docker Postgres test recommended for any DB-touching code change.
3. ✅ Railway Postgres disk-full → crash loop — accepted data loss (reproducible from gov.il), migrated to Kamatera with proper disk sizing (30 GB vs 0.5 GB)
4. ⚠️ CC's automated SSH password auth failed on Kamatera even though manual SSH worked — root cause unclear (possibly special chars in password or rate limiting). Worked around by manually installing SSH key on server, then having CC use key-based auth thereafter. **Note for future sessions**: use SSH key auth from day 1, don't fight password auth through CC's transport layer.

**Outcome:**
- ✅ Scraper migrated end-to-end to Kamatera Tel Aviv
- ✅ Geo-block resolved (all 7 chains working)
- ✅ 25× performance improvement (90 min → 3m31s)
- ✅ Postgres on same host as scraper = localhost writes, no network latency for bulk inserts
- ✅ systemd cron scheduled daily 03:00 IDT
- ✅ Server hardened (key-only SSH, UFW, fail2ban)
- ⏸️ Phase 7 (frontend reroute) deferred to next session — touches live site, better with fresh focus
- ⏸️ Phase 9 (backups) deferred — important but not urgent
- 📝 super.xxl.co.il is currently broken until Phase 7 lands. Acceptable: it was already broken from Railway Postgres crash, so this isn't new user-facing breakage.

**Cost summary:**
- Kamatera: $0 (in 30-day free trial, ~$17/mo after Jun 17, 2026)
- Railway: ~$2.45 trial credit remaining, will expire ~May 23, 2026 — let it lapse naturally rather than actively cancel (web service still needed until Phase 7 completes)
- Net cost: $0 this month, $17/mo from Jun onwards (vs estimated $25+/mo if we'd stayed on Railway Hobby + paid for bigger volume)

**Credentials added to password manager this session:**
- `scrp-prod-il root` (Kamatera root user)
- `scrp-prod-il dude` (sudo user, daily driver)
- `scrp_app Postgres password` (used in DATABASE_URL — will go into Railway web env var in Phase 7)

**Next:** Session 9g Phase 7 — Reroute Railway web service `DATABASE_URL` env var to point at Kamatera Postgres (`185.229.226.190:5432/xxl_super`). Pre-work: identify Railway's egress IP to narrow `pg_hba.conf` from temporary `0.0.0.0/0`. Risk: touches live site, do with fresh focus. After Phase 7, super.xxl.co.il is healthy again. Then Phase 9 (pg_dump backups + Backblaze B2 offsite).