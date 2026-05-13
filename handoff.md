# SCRP — Project Handoff

> A living document. Update at the end of each session. Paste at the start of each new chat.
> Last updated: May 12, 2026 (end of session 9d-1)
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
| Scraper cron | Python (`scraper.cron_main`) | Railway `scraper-cron` service (EU-West, Amsterdam) | ✅ Daily 1am UTC |
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

- **7 chains** scraping daily: Shufersal, Rami Levy, Osher Ad, Victory, Yochananof, Keshet, **Carrefour** (added 9d-1)
- **49 stores across 7 cities**: Jerusalem, Bnei Brak, Tel Aviv, Haifa, Be'er Sheva, Rishon LeZion, Ashdod (verify with `/stats`)
- **~372,000 prices** as of last cron run
- **Verification gate**: `active_stores.yaml` (verified to publish PriceFull) is what cron uses; `scheduled_stores.yaml` is the wish-list. See `db/verification_report_9d1.md` for excluded stores.
- **Canonical names** computed via weighted token voting (session 8b)
- **Search** uses canonical names only, numeric/percentage tokens filtered (session 8b)
- **Known coverage gap**: Bnei Brak has no Carrefour/Yenot Bitan/Mega presence (verified via carrefour.co.il store locator) — accepted, not a bug.

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

---

## 🧭 Pending Sessions

| Session | What | Notes |
|---|---|---|
| **9g** | **Scraper Infrastructure: Performance + Geographic Correctness** | (1) Bulk inserts (Postgres COPY or batched VALUES) — current ~1.5min/store driven by per-row INSERT round-trips. (2) Parallel chain execution via `concurrent.futures`. (3) Geographic fix for Victory + Carrefour geo-blocking — if EU-West region change isn't enough, migrate scraper-cron to Israeli VPS ($5-12/mo). Target: 58 stores in <10 min vs current ~70 min. Unblocks 9d-2 and beyond. **Priority: do this FIRST after 9d-1**, before more city expansion. |
| 9e | StoreNext Registry Ingestion | Ingest StoreNext branch lists (all 7 chains available, free CSV export) into a new `chain_stores_registry` table with sub-format classification (Sheli/Deal/Express/Yesh/Universe/BE for Shufersal; similar for others). Refactor Phase B selection to be format-aware. Solves Shufersal sub-chain heterogeneity systematically. **StoreNext outreach pending** — if their paid tier includes product catalog, re-prioritize 9e ahead of 9g. |
| 9d-2 | City expansion Phase 2 | Remaining 12 cities >100K pop (Petah Tikva, Netanya, Holon, Ramat Gan, Ashkelon, Rehovot, Bat Yam, Beit Shemesh, Kfar Saba, Herzliya, Modi'in). Target ~216 stores total. **Requires 9g first** — running 216-store cron at current 1.5min/store = 5+ hours. |
| 9d-3 | City expansion Phase 3 | 50K+ cities (~25-30 more). Target ~540 stores. |
| 9f | XXL Portal Page (xxl.co.il root) | Build the multi-vertical landing page. Hero (XXL logo + tagline "קונים חכם · חוסכים בענק"). AI-powered universal search bar (Claude Haiku for intent classification, ~$5/mo at 1K daily queries). Vertical tiles: Groceries (live), Flights/Hotels/Fashion (coming soon). Parallel track — can happen anytime after 9e. |
| CITY_CODES audit | Patch missing gov.il city codes | 9d-1 surfaced 23 NULL-city Carrefour stores (Or Akiva, Tel Mond, Dimona, Maalot, Kiryat Ata, Even Yehuda, Kfar Yona, Karkur, Tamra, Daliyat al-Karmel, Arad, Atlit, Kiryat Tivon, Matan, Tzur Yitzhak). Pre-existing dict gap in `scraper/cerberus.py`. Small fix, defer to alongside 9d-2 or as a quick patch session. |
| Promotions + price history | Parse Promo XML files, build history charts | Sample Promo XML files captured in 9d-1 for future analysis. Requires sufficient daily snapshots first. |
| Google OAuth | Wire up deferred-from-9b option | Requires Google Cloud Console OAuth client setup |
| Investigate disappearing tables | Risk hygiene | Deferred pending future AWS/GCP migration (decided in 9c planning) |

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
- **Freemium model REDEFINED (session 9a → confirmed 9c)** — Free tier is the honeypot: search, view prices, basket comparison, save baskets, favorites, recent searches — ALL free, ALL unrestricted. Paid tier benefits will be: ordering through us (12+ months out, requires chain partnerships), exclusive deals, price-drop email alerts. The original "freemium = limit free users to 25 basket items" framing was retired in 9a and codified in 9c — only logged-out users see the 25-item cap (as a signup nudge); logged-in users get a generous 150 (effectively unlimited for human use).
- **Verification-before-scrape pattern (9d-1)** — `scheduled_stores.yaml` is the intent/wish-list, `active_stores.yaml` is the actually-scraped list, gated by per-portal `verify_publishes_pricefull()` check. Prevents silent scrape failures from sub-chain heterogeneity (Shufersal Sheli format, warehouse nodes, etc.). Verification reports go in `db/verification_report_9d1.md`.
- **Procfile is authoritative for Railway commands (9d-1)** — was Railway-UI-only before, which caused scraper-cron to silently revert to `fetch_off` on scheduled runs while manual triggers worked. Procfile now defines both `web:` (gunicorn API) and `cron:` (scraper price scrape). Survives service recreation.
- **Carrefour Israel under Global Retail C.I.** — chain_id `7290055700007` publishes Carrefour + Mega + Yenot Bitan stores combined. We display as "קרפור" but accept all sub-brands. Bnei Brak has zero Carrefour/Mega/Yenot Bitan presence (verified manually) — not a data bug.
- **`publishprice` portal type (9d-1)** — new base class `scraper/publishprice.py`. JS-embedded file listing pattern. Currently only Carrefour, but reusable.
- **Geo-blocking discovered (9d-1)** — `prices.carrefour.co.il` and `laibcatalog.co.il` (Victory) block non-Israeli IPs. Confirmed by Eltzur via VPN test. Other 5 chains' portals don't enforce this. Migration path TBD in 9g (EU-West region trial first, Israeli VPS as fallback).
- **Scraper performance bottleneck (9d-1)** — current ~1.5min/store driven by per-row INSERT round-trips to Railway Postgres. At 58 stores = ~70 min; at 216 stores = ~5 hours (untenable). Fix planned in 9g via bulk inserts + parallel chains.
- **Shufersal sub-chain landscape (9d-1, field intel from Eltzur)** — same chain_id `7290027600007` publishes: דיל (Deal, mainstream discount), שלי (Sheli, neighborhood), אקספרס (Express, convenience), יש/יש חסד (Yesh, haredi sector — dominates Jerusalem/Bnei Brak), Universe (hypermarket), BE (pharmacy/health). NOT all sub-formats publish individual PriceFull files. "Lowest store_id" selection rule biased toward old Jerusalem Sheli stores in 9d-1 — needs format-aware refactor in 9e.
- **StoreNext as canonical chain registry source (9d-1 discovery)** — `storenext.co.il/תמיכה-ושירות/` publishes free CSV branch lists for every EDI-using chain (all 7 of ours). Includes store_id, EDI barcode, store name with format prefix. Could become the basis for the `chain_stores_registry` table in 9e. Paid tier (product catalog?) under investigation.
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
