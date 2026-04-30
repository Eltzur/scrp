# SCRP — Project Handoff

> A living document. Update at the end of each session. Paste at the start of each new chat.
> Last updated: April 30, 2026 (end of session 8L)
---

## 🎯 Vision

**Short-term:** Israeli supermarket price comparison app at `super.xxl.co.il`.

**Long-term:** `xxl.co.il` as a portal — "האתר שהופך את הכסף שלך לכסף חכם" (the site that turns your money into smart money). Subdomains for verticals:
- `super.xxl.co.il` — supermarket prices ✅ live
- `fly.xxl.co.il` — flights (future)
- `hotel.xxl.co.il` — hotels (future)
- `fashion.xxl.co.il` — shoes/clothing (future)

Brand tagline candidates: "תקנה חכם", "כל מחיר. כל מקום.", "השוואה חכמה. קנייה חכמה."

---

## 🏗️ Architecture

| Layer | Tech | Where | Status |
|---|---|---|---|
| Frontend | React + Vite + TypeScript + Tailwind | Hostinger static (`public_html/`) | ✅ Live |
| Backend | FastAPI (Python) | Railway `web` service | ✅ Live |
| Database | Postgres | Railway `Postgres` service | ✅ Live |
| Scraper cron | Python (`scraper.cron_main`) | Railway `scraper-cron` service | ✅ Daily 1am UTC |
| DNS | box.co.il (ns1/2/3.box.co.il) | — | ✅ |

**Local dev:** `C:\scrp` on Windows 10/11. PowerShell + VS Code + Claude Code in VS Code terminal.

**Repo:** github.com/Eltzur/scrp (main branch is production)

**Production URLs:**
- Frontend: https://super.xxl.co.il
- Backend: https://api-super.xxl.co.il

**Key Railway commands:**
- `web` start: `gunicorn -k uvicorn.workers.UvicornWorker api.main:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
- `scraper-cron` start: `python -m scraper.cron_main`
- DATABASE_URL uses `${{Postgres.DATABASE_PUBLIC_URL}}`

**Folder layout (matters because some folders are misleadingly named):**
- `web/` — React frontend (NOT the backend, despite the name)
- `api/` — FastAPI backend
- `scraper/` — scraper code + cron entrypoint
- `db/` — schema, migrations, helper scripts
- `frontend/` — empty stub, leftover from skeleton commit, ignore

**Hostinger deployment:**
- Document root is `public_html/` at the account root (NOT `super.xxl.co.il/` folder)
- Deploy = build `web/` → zip `dist/*` contents → upload+extract in `public_html/`
- `.htaccess` for SPA routing lives in `web/public/` (auto-copied to `dist/` on build)

---

## 📊 Current Production State

- **6 chains** scraping daily: Shufersal, Rami Levy, Osher Ad, Victory, Yochananof, Keshet
- **26 stores** (varies slightly by session — verify with `/stats` endpoint)
- **214,064 prices** as of last cron run
- **Canonical names** computed via weighted token voting (session 8b)
- **Search** uses canonical names only, numeric/percentage tokens filtered (session 8b)

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

---

## 🧭 Pending Sessions

| Session | What | Notes |
|---|---|---|
| **9b** | **User authentication** | Next up. Email/pass primary, Google OAuth as option. Prerequisite for 9c. |
| 9c | Freemium gating | Enforce 25-item limit server-side per-account, paid tier benefits |
| 9d | More chains, promotions, price history | Add Mega/Carrefour/AM:PM etc., parse Promo XML files, history charts |

---

## 🔑 Key Architectural Decisions

- **Railway for hosting** — staying until $0–5/month tier outgrown. No premature AWS migration.
- **SQLAlchemy everywhere** — scrapers are DB-agnostic.
- **Snapshot pricing only** — not yet tracking history (deferred to 9d).
- **Phased city expansion strategy** — currently 26 stores in Jerusalem/Bnei Brak. Session 9d-1 expands to 7 cities (~86 stores). Sessions 9d-2+ expand to all 100K+ cities (~216 stores). Sessions 11+ expand to 50K+ cities (~540 stores). Full coverage requires AWS/GCP migration when Railway hits limits.
- **Daily cron at 3am Israel time (1am UTC)**.
- **Canonical names via weighted token voting** — ~93% stability across runs, ~7% updated per fresh canonical run.
- **Skipped Hazi-Hinam scraper** — HTML-scraping is too fragile vs Cerberus JSON APIs.
- **Brand color: emerald-600 (#059669)** — used for primary CTAs, basket-limit toast.

---

## 🔗 External Data Source Status

- **gov.il price transparency XML** — primary source. Working.
- **Cerberus portal** (`url.retail.publishedprices.co.il`) — used by Yochananof, Keshet, Osher Ad, etc. Login-based.
- **Shufersal direct** (`prices.shufersal.co.il`) — open HTTP, no auth.
- **Rami Levy direct** — open HTTP.
- **Victory** — REST API, custom scraper (~55 lines).
- - **OpenFoodFacts** — ❌ ABANDONED. Tested in past sessions, found it out of date and nearly empty for Israeli barcodes. Code exists in repo but do not invest more effort here.
- **StoreNext** — outreach pending. Could be a silver bullet for catalog/categories/images. Status: waiting on response.
- **OpenIsraeliSupermarkets Kaggle dataset** — bookmarked for future price history (9d).

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

## 🛠️ Common Operations Cookbook

### Build & deploy frontend