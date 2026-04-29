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

## 🛠️ Common Operations Cookbook

### Build & deploy frontend