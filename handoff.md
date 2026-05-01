# SCRP — Project Handoff

> A living document. Update at the end of each session. Paste at the start of each new chat.
> Last updated: April 30, 2026 (during session 9b)
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


## 🛠️ Common Operations Cookbook

### Build & deploy frontend