# SCRP — Project Handoff

> A living document. Update at the end of each session. Paste at the start of each new chat.
> Last updated: April 29, 2026 (end of session 9a)

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

---

## 🧭 Pending Sessions

| Session | What | Notes |
|---|---|---|
| **8L** | **Logo + banner + brand identity** | Next up. Creative break before 9b. |
| 9b | User authentication | Prerequisite for 9c. Save baskets, favorites, history. |
| 9c | Freemium gating | Enforce 25-item limit server-side per-account, paid tier benefits |
| 9d | More chains, promotions, price history | Add Mega/Carrefour/AM:PM etc., parse Promo XML files, history charts |

---

## 🔑 Key Architectural Decisions

- **Railway for hosting** — staying until $0–5/month tier outgrown. No premature AWS migration.
- **SQLAlchemy everywhere** — scrapers are DB-agnostic.
- **Snapshot pricing only** — not yet tracking history (deferred to 9d).
- **5 stores per chain × 6 chains** — covers main geography without over-scraping.
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
- **OpenFoodFacts** — enrichment for Hebrew names + images. Partial coverage.
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

===END===
## 🛠️ Common Operations Cookbook

### Build & deploy frontend