# XXL Flights — Handoff

> Companion to handoff_super.md (supermarket vertical).
> This file tracks the flights vertical exclusively. Separate repo, separate session numbering.

---

## Product context

XXL Ltd. is expanding into flight price comparison as part of the xxl.co.il multi-vertical
vision (groceries live → flights → hotels → fashion, freemium model).

Vision: combine the best of Skyscanner + KAYAK with unique modules:
- Budget-first search (set max price, see all reachable destinations)
- Continent browser (I want to go to Europe in August — what's cheapest?)
- Open/anywhere search (no destination, just dates)
- Price drop alerts — email for paid subscribers
- TLV deals banner — routes from TLV with >50% price drop vs 30-day avg (paid only)

---

## Repo & infra (decided in 10A-1)

- **Repo:** New separate repo — github.com/Eltzur/xxl-flights
- **Infra:** Same Kamatera VPS initially — separate when traffic justifies
- **Auth:** Shared Supabase — reuse existing users, same login across verticals
- **DB:** Separate `flights` schema on same Kamatera Postgres server
- **Stack:** FastAPI + React/Vite/Tailwind — same as supermarket

---

## Session numbering

Prefix: `10A-` — e.g. 10A-1, 10A-2. Independent of supermarket track (9d-x).

---

## API stack (decided in 10A-1, validated in 10A-1)

| Provider | Role | Phase | Access | Cost |
|---|---|---|---|---|
| SerpApi Google Flights | Primary fare search | 1 | Self-serve, verified working | 250 searches/month free (non-commercial dev only → $50/mo at launch) |
| Travelpayouts | Affiliate monetization + cached price data | 1 | Self-serve | 3% commission/booking |
| AirLabs IATACodes | Airport autocomplete | 1 | Self-serve | 1,000 free calls/month |
| AeroDataBox | Flight status, alerts scaffold | 1 | Self-serve | 600 units/month free |
| Kiwi Tequila | "Anywhere" search, budget search, LCCs | 2 | Requires 50K MAU | Commission-based |
| Skyscanner official | Full metasearch, price calendar | 3 | Requires 100K MAU | Revenue share |
| Duffel | In-app booking (no click-through) | 3 | Self-serve sandbox | $3/booking + 1% |

**Dead ends:**
- Amadeus Self-Service: shutting down July 17, 2026 — do not build on it
- SerpApi free tier: non-commercial only — use for dev/testing, switch to paid ($50/mo) at launch

**SerpApi response validation (10A-1):**
- TLV confirmed as valid departure_id
- Returns best_flights + other_flights arrays
- Per result: price (ILS), airline, logo URL, flight_number, duration, stops, layovers, legroom, often_delayed flag
- price_insights: lowest_price, typical_range, price_history (60+ days of unix_timestamp+price pairs)
- price_history array is the alert/deals banner data source — store on first search

---

## Feature / tier matrix (confirmed 10A-1)

| Feature | Guest | Free subscriber | Paid subscriber |
|---|---|---|---|
| Search | ✅ | ✅ | ✅ |
| Default origin | TLV | TLV | TLV |
| Custom origin | ✅ | ✅ | ✅ |
| Currency display | NIS only | NIS / USD / EUR | NIS / USD / EUR |
| Destinations per search | 1 | 3 | 5 |
| Saved searches | 0 | 3 | 5 |
| Price alerts (email) | ❌ | ❌ | ✅ |
| Price alerts (SMS) | ❌ | ❌ | Phase 2 |
| TLV deals banner (>50% drop) | ❌ | ❌ | ✅ |

---

## DB schema (flights schema on Kamatera Postgres)

```sql
-- Airport reference (populated from AirLabs)
CREATE TABLE flights.airports (
    iata_code       VARCHAR(3) PRIMARY KEY,
    name            TEXT NOT NULL,
    city            TEXT,
    country         TEXT,
    country_code    VARCHAR(2),
    latitude        NUMERIC,
    longitude       NUMERIC
);

-- Route reference
CREATE TABLE flights.routes (
    id              SERIAL PRIMARY KEY,
    origin          VARCHAR(3) NOT NULL REFERENCES flights.airports(iata_code),
    destination     VARCHAR(3) NOT NULL REFERENCES flights.airports(iata_code),
    UNIQUE(origin, destination)
);

-- Raw flight search results (cached, TTL 2 hours)
CREATE TABLE flights.flight_prices (
    id              BIGSERIAL PRIMARY KEY,
    route_id        INTEGER NOT NULL REFERENCES flights.routes(id),
    price           NUMERIC NOT NULL,
    currency        VARCHAR(3) NOT NULL DEFAULT 'ILS',
    airline         TEXT,
    airline_logo    TEXT,
    flight_number   TEXT,
    outbound_date   DATE NOT NULL,
    return_date     DATE,
    total_duration  INTEGER,  -- minutes
    stops           INTEGER DEFAULT 0,
    travel_class    TEXT DEFAULT 'Economy',
    often_delayed   BOOLEAN DEFAULT FALSE,
    raw_json        JSONB,    -- full SerpApi result stored for flexibility
    source_api      TEXT DEFAULT 'serpapi',
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_flight_prices_route ON flights.flight_prices(route_id, outbound_date);
CREATE INDEX idx_flight_prices_scraped ON flights.flight_prices(scraped_at);

-- 60-day price history per route per date (from price_insights.price_history)
CREATE TABLE flights.price_history (
    id              BIGSERIAL PRIMARY KEY,
    route_id        INTEGER NOT NULL REFERENCES flights.routes(id),
    outbound_date   DATE NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL,
    min_price       NUMERIC NOT NULL,
    currency        VARCHAR(3) NOT NULL DEFAULT 'ILS',
    UNIQUE(route_id, outbound_date, recorded_at)
);

CREATE INDEX idx_price_history_route ON flights.price_history(route_id, outbound_date);

-- Price alerts (paid subscribers only)
CREATE TABLE flights.alerts (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID NOT NULL,  -- Supabase auth user id
    route_id        INTEGER NOT NULL REFERENCES flights.routes(id),
    outbound_date   DATE,           -- null = any date
    threshold_pct   INTEGER DEFAULT 10,  -- alert when price drops X%
    channel         TEXT DEFAULT 'email',  -- email | sms (sms = phase 2)
    active          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alerts_user ON flights.alerts(user_id);

-- Saved searches (free: 3 max, paid: 5 max)
CREATE TABLE flights.saved_searches (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID NOT NULL,
    origin          VARCHAR(3) NOT NULL,
    destinations    VARCHAR(3)[] NOT NULL,  -- array, up to 5 for paid
    outbound_date   DATE,
    return_date     DATE,
    currency        VARCHAR(3) DEFAULT 'ILS',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_saved_searches_user ON flights.saved_searches(user_id);

-- GRANTs
GRANT USAGE ON SCHEMA flights TO scrp_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA flights TO scrp_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA flights TO scrp_app;
```

---

## Monetization model

| Stream | Phase | Mechanism |
|---|---|---|
| Affiliate commissions | 1 | 3% per booking via Travelpayouts/Kiwi |
| Price drop alerts (email) | 1 | Paid subscription gate |
| TLV deals banner (>50% drop) | 2 | Paid subscribers only |
| SMS alerts | 2 | Paid upsell |
| In-app booking margin | 3 | Duffel booking delta |

---

## Phase roadmap

**Phase 1 (weeks 1-8) — MVP:**
SerpApi for search, Travelpayouts for monetization, AirLabs for autocomplete.
Standard search from TLV (customizable), one-way/return/flexible dates,
multi-destination (tier-gated), currency toggle (tier-gated), saved searches (tier-gated),
affiliate click-through, price drop alert signup (paid). Store price_history from day 1.

**Phase 2 (weeks 9-20) — Differentiation:**
Kiwi Tequila (once 50K MAU), "fly anywhere" open search, budget-first search,
continent browser, TLV deals banner (paid, >50% drop vs 30-day avg), SMS alerts.

**Phase 3 (month 6+) — Scale:**
Skyscanner official (100K MAU), Duffel in-app booking,
multi-source deduplication, hotels bundling.

---

## Session log

### Session 10A-1 (July 4, 2026) — Research + floorplan + API validation

**Completed:**
- Full API landscape research
- Confirmed Amadeus Self-Service sunsetting July 17, 2026 — excluded
- Confirmed SerpApi Google Flights: working, TLV validated, returns real prices in ILS
- Confirmed SerpApi free tier is non-commercial — use for dev only, switch to $50/mo at launch
- Defined 3-phase product + API architecture
- Defined full DB schema
- Defined feature/tier matrix (confirmed with Dude)
- Decided infra/repo approach
- Registered on SerpApi (250 free searches/month dev tier)
- Registered on Travelpayouts (Drive install deferred — not needed yet)

**Next session (10A-2):**
- Create github.com/Eltzur/xxl-flights repo
- Scaffold FastAPI backend + React/Vite frontend
- Run DB migration (flights schema + all tables)
- Wire up /search endpoint calling SerpApi
- Test end-to-end: browser search → FastAPI → SerpApi → results displayed

### Session 10A-2 (July 4, 2026) — Repo scaffold + live search endpoint — ✅ COMPLETE

**Completed:**
- Repo created: github.com/Eltzur/xxl-flights (private)
- Backend scaffolded: FastAPI, /search endpoint, SerpApi integration
- Frontend scaffolded: React/Vite/Tailwind v3 (used v3 not v4 — v4 removed npx tailwindcss init -p)
- DB migration run on Kamatera: 6 tables created in flights schema (ran as postgres superuser)
- /search endpoint verified live: TLV->BCN returns real prices, Bluebird Airways 1947 ILS confirmed
- Git identity set: Eltzur / etokenpsm@yahoo.com
- GitHub SSH key added to known_hosts (fingerprint verified against GitHub published value)

**Notes:**
- SerpApi key in backend/.env (gitignored, never committed)
- scrp_app password auth failing interactively on Kamatera — migration ran via sudo -u postgres instead. Investigate scrp_app password for flights DB writes in next session.
- Tailwind v3 used (not v4)

**Additional completed in 10A-2 (extended session):**
- .gitignore cleaned up: 93 untracked files → 0 (binaries, CSVs, temp scripts, PDFs, YMLs all covered)
- env.upload deleted (contained credentials, was untracked — security risk eliminated)
- handoff files reorganized into docs/super/ and docs/flights/ subfolders
- scrp_app DB password reset to clean value (no special characters) — verified working via PGPASSWORD test
- scrp-api restarted and confirmed active (running) with new password
- CLAUDE.md updated with permissions prompt policy

**Next session (10A-3):**
- Deploy flights FastAPI backend as systemd service on Kamatera (port 8001)
- Add nginx server block for fly.xxl.co.il
- Add DNS A record at box.co.il pointing to 185.229.226.190
- SSL via certbot for fly.xxl.co.il
- Build frontend (npm run build) and deploy dist/ to nginx
- Verify full stack end-to-end on live URL: browser → nginx → FastAPI → SerpApi → results
- Begin UI polish after live deployment confirmed

**Deferred to 10A-4 (post-deployment):**
- Currency toggle: guests get NIS only, free/paid subscribers get NIS/USD/EUR selector
- Tier-gating logic: Supabase auth integration, user tier detection
- Save search to DB after successful result (free: 3 saved, paid: 5 saved)
- price_history storage: store SerpApi price_insights.price_history on each search call
- Multi-destination search (guests: 1, free: 3, paid: 5)
- Price alert signup UI (paid subscribers only)

---

### Session 10A-3 (July 5, 2026) — Deployment to fly.xxl.co.il

**Completed — flights vertical is LIVE at https://fly.xxl.co.il:**
- Discovered server was bare (10A-2 "live search" was the Windows dev box, not Kamatera). This was a from-zero provision, not a redeploy.
- Server had NO git SSH identity; scrp pulls via HTTPS. Created a dedicated read-only deploy key for xxl-flights, cloned to /home/dude/xxl-flights.
- Built venv at /home/dude/xxl-flights/venv, installed backend/requirements.txt.
- Server .env created manually (SERPAPI_KEY, DATABASE_URL, plus Supabase/CORS vars for shared stack). DATABASE_URL uses postgresql+asyncpg:// scheme (asyncpg driver) with the known-good scrp_app DSN. NOTE: DB is not yet wired into the search path — db/connection.py defines an engine but nothing imports it. No DB writes happen yet.
- systemd service flights-api.service: uvicorn main:app on 127.0.0.1:8001, EnvironmentFile from backend/.env, enabled + auto-restart.
- nginx server block /etc/nginx/sites-available/fly.xxl.co.il: proxies /api/ -> 127.0.0.1:8001/ (trailing slash strips /api prefix; browser calls /api/search -> backend /search). SPA fallback for frontend.
- DNS A record fly.xxl.co.il -> 185.229.226.190 added at box.co.il (TTL 300), propagated.
- SSL via certbot --nginx, cert expires 2026-10-03, auto-renew active.
- Frontend served from /var/www/fly.xxl.co.il (moved OUT of /home/dude because home dir is 700 and www-data cannot traverse it -> was causing nginx 500). Future frontend deploys must target /var/www/fly.xxl.co.il with sudo, NOT the home-dir dist path.
- End-to-end verified in browser: TLV->BCN 2026-08-10/2026-08-17 ILS returns real results (Bluebird 1947 ILS, Aegean 2119, El Al 2466) with logos. /api/search returns 200.

**Deviations from the original 10A-3 plan:**
- Two code fixes required and pushed to xxl-flights: CORS origin flights.xxl.co.il -> fly.xxl.co.il (commit 56394f9); API_BASE localhost:8000 -> /api (commit 9ab3f71).
- Local flights repo relocated from C:\xxl-flights to C:\scrp\xxl-flights (under master folder). scrp .gitignore now excludes /xxl-flights/. Repos remain independent (separate remotes).
- Frontend root is /var/www/fly.xxl.co.il, not the home-dir path in the original plan.

**Repo/infra facts for next session:**
- Server deploy key: read-only, xxl-flights only. Server pulls via git@github.com:Eltzur/xxl-flights.git.
- Local repo: C:\scrp\xxl-flights. Frontend build: C:\scrp\xxl-flights\frontend, npm run build.
- Frontend deploy: scp dist/* to a staging path, then sudo cp to /var/www/fly.xxl.co.il (root-owned). Reload not needed for static files.
- Backend restart: sudo systemctl restart flights-api. Logs: sudo journalctl -u flights-api.

**Next session (10A-4) — UI polish + tier-gating:**
- Date format: force dd/mm/yyyy (Israeli locale). Native <input type=date> follows browser locale; needs a custom date component or locale handling.
- Currency toggle (guests ILS only; subscribers ILS/USD/EUR).
- Supabase auth integration + tier-gating (destinations per search, saved searches).
- Save search to DB after successful result; begin price_history storage (wire db/connection.py into the search path — currently unused).

---

### Session 10A-4 (July 6, 2026) — Frontend rebuild — Hebrew/RTL + XXL branding + calendar picker

**Completed:**
- Rebuilt frontend/src/App.tsx onto the super app's architecture: react-i18next (he default, en toggle, applyDir RTL/LTR), component split (Header + shared XxlLogo copied verbatim from web), emerald/XXL branding replacing the old blue theme.
- Added i18n scaffold: src/i18n/config.ts + he.json/en.json (search/results/header keys). main.tsx imports config before index.css.
- Replaced native date inputs with a react-day-picker v10 popover: Hebrew locale (date-fns he), Sunday-first, past-disabled, 12-months-forward, stores YYYY-MM-DD for the API (permanently fixes mm/dd vs dd/mm locale ambiguity), displays dd/MM/yyyy.
- Custom RTL-aware NavChevron (v10 components.Chevron) so calendar arrows face the correct direction in Hebrew.
- Origin/destination kept as self-contained IataField slot; Supabase client copied to src/lib/supabase.ts and @supabase/supabase-js installed, but NOT imported/used yet — both pre-stage 10A-5.
- Built, committed (446c3f4 + chevron fix), pushed, deployed to /var/www/fly.xxl.co.il. Verified live in-browser: RTL, branding, calendar, TLV->BCN and TLV->CDG(JFK) searches all return results.

**Gotchas / infra notes (discovered 10A-4):**
- DEPLOY: fly.xxl.co.il web root is www-data-owned. Plain `scp dude@...:/var/www/...` and `ssh dude ... rm` FAIL with permission denied. Deploy path that works: scp to ~/fly_deploy staging dir, then `ssh -t dude@185.229.226.190 "sudo rm -rf /var/www/fly.xxl.co.il/* && sudo cp -r ~/fly_deploy/* /var/www/fly.xxl.co.il/ && rm -rf ~/fly_deploy"`. The `ssh -t` is required for the sudo password prompt.
- react-day-picker is v10 (major rewrite). v8/v9 examples break. Use startMonth/endMonth + disabled matchers (not fromDate/toDate); import "react-day-picker/style.css"; RTL needs a custom components.Chevron.
- ORIGIN VALIDATION: free-text city codes like "NYC" return empty results from SerpApi (needs a specific airport, e.g. JFK). This is the core reason 10A-5a autocomplete (validated AirLabs codes) is next.

**Next session:**
- **10A-5a** — origin/destination AirLabs autocomplete (Hebrew/EN/code alias dropdown), swapped into the existing IataField slot.
- **10A-5b** — Supabase auth + tier-gating (destinations per search, saved searches; wire in the pre-staged src/lib/supabase.ts + Header auth slot).
- **10A-6** — price heatmap on the calendar: PARKED. Seam reserved in the DateField day cells (use react-day-picker modifiers/modifiersClassNames; do not hard-style day cells).

---

### Session 10A-5a (July 8, 2026) — Origin/destination airport autocomplete

**Completed — full-stack autocomplete for origin/destination:**
- DB migration (flights.airports on xxl_super): added name_he TEXT, aliases TEXT[], popularity NUMERIC; two pg_trgm GIN indexes (idx_airports_name_trgm on name, idx_airports_name_he_trgm on name_he). Migration file backend/db/10A-5a_airports_autocomplete.sql (run as postgres); folded into schema.sql for from-scratch rebuilds. pg_trgm extension enabled.
- AirLabs bulk seed (backend/db/seed_airports.py, run once as scrp_app): 9,808 airports loaded — English name + city + country + lat/lng + popularity. 3 AirLabs calls/run (airports, cities, countries). Idempotent upsert (ON CONFLICT DO UPDATE, COALESCE on name_he/popularity so re-seed never wipes manual/curated backfill).
- Endpoint GET /api/airports?q=&limit= (backend/api/routers/airports.py): single-pass ranked SQL — priority 1 exact IATA, 2 Hebrew prefix, 3 English prefix, 4 alias prefix, 5 substring; ordered so a typed IATA wins, then curated cities (name_he IS NOT NULL) float above name-prefix matches, then match quality, then name. Params bound; ILIKE wildcards escaped. First router to use db.connection/AsyncSession (async SQLAlchemy 2.0.31).
- Frontend AirportAutocomplete (src/components/AirportAutocomplete.tsx) replaces the old IataField for both fields: 250ms debounce, stale-response guard (reqId + AbortController), RTL layout, Hebrew name primary + muted LTR IATA-code badge (disambiguates the 3 "ניו יורק" rows), city/country subtext, ↑/↓/Enter/Esc keyboard nav, outside-click close, TLV prefill on mount. Forgiving commit: blur / Enter auto-selects the top result; empty-on-blur reports "".
- Fixed results.stops i18n plural: Hebrew (i18next v26, Intl.PluralRules) needs stops_two (and stops_many) categories — only stops_one/stops_other existed, so a 2-stop flight rendered the literal "results.stops". Added stops_two/stops_many; 2 stops now shows "2 עצירות".

**Gotchas discovered (critical for future sessions):**
- AirLabs v9 FREE tier does NOT return Hebrew: lang=he is silently ignored, no names.he object. Hebrew airport names come from a CURATED map — backend/db/airports_he.py (163 top cities, one Hebrew city name per airport, shared across a city's airports) + backend/db/airports_city_en.py (matching English cities, used for the city column AND English aliases). AirLabs is the English-name / popularity / country source ONLY.
- db.connection creates the async engine at import and REQUIRES DATABASE_URL with the +asyncpg driver scheme (postgresql+asyncpg://...). The seed uses psycopg2 and strips "+asyncpg" from the same DATABASE_URL. Both read the same backend/.env.
- .env corruption fixed: a stray UUID had merged onto the SERPAPI_KEY line (no newline between values), so systemd's EnvironmentFile parse gave SerpApi the wrong value and search failed. Every key MUST be on its own line in backend/.env.
- Backend service is flights-api (uvicorn on 127.0.0.1:8001). Restart: sudo systemctl restart flights-api.
- Frontend deploy to fly.xxl.co.il still needs the staging + sudo path (www-data-owned web root): scp dist/* to ~/fly_deploy, then ssh -t "sudo rm -rf /var/www/fly.xxl.co.il/* && sudo cp -r ~/fly_deploy/* /var/www/fly.xxl.co.il/ && rm -rf ~/fly_deploy".

**SECURITY — key rotation:**
- AirLabs key was ROTATED (it had leaked via an API echo in logs).
- SerpApi key ALSO leaked (appeared in journalctl output during the .env debug) and — OUTSTANDING — must be rotated if not already done. Update backend/.env (own line) and restart flights-api after rotating.

**SerpApi cost constraint (for Phase-2 feature costing):**
- Flexible-date and budget/"anywhere" searches multiply API calls: ±5 days ≈ 11x calls per search. Factor this into the paid tier / rate-limit design before building flexible-date or budget search.

**Next session:**
- **Quick-wins** — one-way/round-trip toggle, city "all airports" grouping in results, results sort/filter.
- **10A-5b** — Supabase auth + tier-gating (destinations per search, saved searches; wire in the pre-staged src/lib/supabase.ts + Header auth slot).
- **10A-6** — price heatmap on the calendar: PARKED. Seam reserved in the DateField day cells (react-day-picker modifiers/modifiersClassNames; do not hard-style day cells).

---

### Session 10A-Q (July 9, 2026) — Search quick wins (trip-type, passengers, cabin, sort/filter) + all-flights fix

**Completed:**
- Trip-type segmented control (round-trip default / one-way); one-way hides + clears the return-date field. Backend already forwarded SerpApi `type` — frontend-only.
- Passenger stepper (adults, 1-9) and cabin-class select (Economy=1 / Business=3). Required a backend change: search.py now accepts + forwards `adults` and `travel_class` to SerpApi (backward-compatible defaults adults=1, travel_class=1; clamped: adults>=1, travel_class in {1,3} else 1).
- Results sort (price low->high default / duration / stops) + filter (max stops: any/non-stop/1-stop; airline from distinct results). Pure frontend via useMemo, results state never mutated, filters reset on each new search.
- Airport autocomplete dropdown subtitle now includes the airport NAME (e.g. "Luton Airport · London, United Kingdom") so multiple airports in one city are distinguishable (was showing identical "London, United Kingdom" for all).

**KEY FIX (most impactful):** handleSearch was only rendering data.best_flights (SerpApi's ~3-flight recommended subset) and DISCARDING data.other_flights (~10 more, incl. most non-stops). Now merges both: setResults([...best_flights, ...other_flights]). This ~4x'd the flights shown per search and made the stop/airline filters meaningful. Every prior search across the whole vertical had been showing ~25% of available results. ALWAYS merge both arrays.

**DECLINED (do not resurface as a TODO):** "search both cabin classes in one query" — SerpApi travel_class is single-value, so it needs 2 API calls merged per search. Judged not worth the dev-tier API cost for low user value. Cheap alternative if ever wanted: a "כל המחלקות" option that omits travel_class entirely (SerpApi returns its default mix).

**Next session (options):**
- **10A-5b** — Supabase auth + tier-gating (unlocks flexible dates, budget search, saved searches per roadmap_flights_features.md).
- **City "all airports" grouping** (1.2 in roadmap_flights_features.md) — synthetic "כל שדות התעופה" row + multi-code /search merge.
- Both still pending.

---

## Open decisions

- Subdomain vs path: RESOLVED — fly.xxl.co.il (not flights.xxl.co.il); live in Phase 1
- Exact Travelpayouts program to join (Kiwi vs Aviasales — test both)
- Email provider for alerts: SendGrid free tier (100 emails/day) — confirm before 10A-2
- Paid subscription price point (TBD)
- scrp_app password: RESOLVED (new clean password, no special chars; stored in server .env + password manager, NOT committed to repo)

## Test user

Confirmed Supabase test account for exercising the authenticated free/paid path headlessly — closes the "authenticated path unexercised" blocker hit in every session since auth shipped (FL10A-6a, FL10A-7a, and FL10A-7b all had to skip live free/paid verification because Supabase requires email confirmation and there was no way to mint a token without a real inbox).

Credentials (`TEST_USER_EMAIL` / `TEST_USER_PASSWORD`) live only in `backend/.env` on Kamatera — never in this repo. Scripts: `xxl-flights/scripts/kamatera/get_test_token.sh` and `set_test_tier.sh`.

- **Get a bearer token:** `ssh dude@185.229.226.190 "~/xxl-flights/scripts/kamatera/get_test_token.sh"` — prints only the `access_token` to stdout (capture with `TOKEN=$(...)`); on failure it prints Supabase's raw response to stderr instead of dying with an opaque JSONDecodeError.
  - ⚠️ **BROKEN as of FL10A-7c** until `backend/.env` line 5 is repaired — the corrupted `SUPABASE_ANON_KEY` makes `source .env` fail with `No such file or directory`. See the FL10A-7c section for the diagnosis and fix. Workaround used in 7c: read `VITE_SUPABASE_ANON_KEY` from `frontend/.env.production` (the intact key) and do the password grant directly.
- **Set the test user's tier:** `ssh dude@185.229.226.190 "~/xxl-flights/scripts/kamatera/set_test_tier.sh <free|paid>"` — runs the `UPDATE users SET tier=…` as the postgres superuser. Interactive sudo password each time — deliberately NOT in the passwordless xxl-ops whitelist, since it's rare (once per verification session, not every deploy) and touches raw SQL as superuser.

Typical flow: set tier → get token → `curl -H "Authorization: Bearer $TOKEN" https://fly.xxl.co.il/api/me` to confirm the tier took effect, then hit whichever endpoint is actually under test the same way.

## Session 10A-5b — City "all airports" grouping + results filter rail

**Goal:** synthetic "כל שדות התעופה" option so a city group (e.g. New York) searches all its airports (JFK+EWR+LGA) in one go; plus a Kayak-style results filter rail. No auth.

**Shipped (all live on fly.xxl.co.il, all committed):**
- `backend/db/airport_groups.py` (NEW) — inverts AIRPORTS_CITY_EN into city→[codes] groups. Inverts the ENGLISH map deliberately: it is a strict superset of AIRPORTS_HE (which lacks CIA, MXP, BRU, CRL, EIN, OSL, BKK, DMK, HKT, KUL). AIRPORTS_HE supplies only the Hebrew label per group; None → English fallback. Yields 14 groups (Eilat, London, Paris, Rome, Milan, Istanbul, Brussels, Warsaw, New York, Chicago, Washington, Dubai, Bangkok, Tokyo). Computed once at import; CITY_GROUPS + CODE_TO_GROUP exported.
- `/api/airports` (airports.py) — prepends a synthetic `kind:"city_group"` row for matching multi-airport cities (Hebrew-label prefix / English-city prefix / member-code match). Group row's `iata_code` is the comma-joined list (e.g. "JFK,EWR,LGA"); member airports still listed below. Existing airport rows now carry `kind:"airport"`.
- `/search` (search.py) — origin/destination now accept a comma-joined code list (max_length 31). `_normalize_codes()` upper-cases, validates 3-alpha tokens, de-dups, clamps to MAX_CODES=4; passes the list straight to SerpApi as ONE call (SerpApi merges + de-dups server-side — no fan-out, no cost multiplier). Also added per-flight `departure_id`/`arrival_id` to parse_flights (additive) for the per-airport filter.
- `AirportAutocomplete.tsx` — renders `city_group` rows: `displayLabel` shows the group label without the code suffix; `rowBadge` shows member count "N ✈" instead of the overflowing code list. `Airport` interface gained optional `kind`.
- `App.tsx` — results filter bar refactored into a right-side rail (RTL-natural). Set-based multi-select filters: עצירות (0/1/2+ buckets via Math.min(stops,2)), חברת תעופה (per-airline checkboxes), שדות תעופה (per-arrival-airport checkboxes; only shown when >1 arrival airport present — pairs with all-airports search). Empty Set = show all. `sortBy` stays a dropdown atop the rail. `toggleSetFilter<T>` generic helper. New i18n keys: results.stops_one, results.stops_two_plus, results.filter_airports (he + en).

**Verified live:** autocomplete "ניו יורק"/"לונדון" surface group rows with correct badges; TLV→JFK,EWR,LGA one-way returned flights across all three airports (11 JFK / 5 EWR / 1 LGA in one call); rail filters (per-airport EWR, stops, airline) all narrow results correctly on the live site.

**Gotchas confirmed this session:**
- Frontend deploy MUST run from Windows PowerShell/VS Code (`C:\scrp\xxl-flights\frontend`), NOT from the server SSH session — running the `[Bash - VS Code]` deploy block inside the server shell silently pushes a STALE dist (the `cd C:\...` fails on Linux and scp runs from the wrong cwd). Verified by bundle-hash mismatch (got old index-hgiTPkFh 190KB instead of new build). Always confirm the served JS hash after deploy.
- SerpApi departure_id/arrival_id natively accept comma-separated codes → all-airports is ONE call, not N. The roadmap's "NYC = 3× calls" assumption was wrong for the backend-multi-code approach.
- curl to /search must URL-encode commas as %2C and use -m 40 (multi-airport merge is slower); bare commas + short timeout gave HTTP 000.
- Real i18n locale path is `frontend/src/i18n/locales/`, NOT `frontend/src/locales/`.
- Bare `->` is invalid as JSX text (TS1382); use `{"->"}`.

**Roadmap status:** item 1.2 (city all-airports grouping) DONE. Next per roadmap: 10A-5b was reserved for auth in the roadmap doc — auth/tier-gating is now the next keystone session (suggest numbering 10A-5c). Tier note for auth: an all-airports city counts as ONE destination against tier caps; the rail is ungated for now.

## Session FL10A-5c — Amenities, child/infant passengers

**Goal:** enrich results with premium-service indicators and support family searches.

**Shipped (live on fly.xxl.co.il, committed):**
- `search.py` — new params `children`, `infants_in_seat`, `infants_on_lap` (clamped >=0, forwarded to SerpApi). New amenity derivation in `parse_flights` via `_amenities()`: `has_wifi`, `has_power`, `has_video`, `extra_legroom`, `min_legroom_in`. Also added `price_level` to price_insights (NOTE: SerpApi returned None for it on our routes — may need deep_search; do not rely on it).
- `App.tsx` — `AmenityIcons` component: Wi-Fi / power / video SVG icons + legroom indicator with minimum inches. Icons render ONLY when present (no greyed placeholders), so the strip reads as a genuine premium signal. Combined passengers dropdown replacing the single adults stepper (adults / children / infant-in-seat / infant-on-lap).
- i18n: `search.pax_*` (8 keys) + `results.amenity_*` (4 keys) in he.json + en.json.

**KEY DESIGN RULES (do not regress these):**
- **ALL-LEGS RULE:** an amenity is claimed only if EVERY leg has it. A 12h leg without Wi-Fi plus a 1h hop with it must NOT show a Wi-Fi icon. Verified live: only El Al returned has_wifi=True on TLV-JFK; flydubai/Etihad returned power+video; TAROM/Condor/LOT returned none. The spread proves the AND logic discriminates correctly.
- **LEGROOM IS THE MINIMUM ACROSS LEGS**, shown as inches, NOT a binary "extra legroom" badge. Rationale: Google's legroom figure is the aircraft's standard economy pitch, not a per-seat guarantee, and it varies per leg. Showing the best leg's number would mislead. The strict all-legs "above average" badge was built but proved unreachable on real multi-leg routes (always False) - so the numeric minimum is displayed instead. `extra_legroom` still returns from the backend but is NOT rendered.
- **INFANT-IN-SEAT AND INFANT-ON-LAP MUST STAY SEPARATE.** They are different products at very different prices (lap ~10% of adult fare; seat ~75%). SerpApi takes them as separate params because Google prices them differently. Merging them would quote the wrong price for half of family searches. Labels clarify: "עם מושב" vs "ללא מושב".

**Amenity source data (from a live SerpApi probe, TLV-JFK):**
`extensions` is an array of human-readable English strings, matched by keyword (hl=en, so matching is stable). Real observed values: "Free Wi-Fi", "Wi-Fi for a fee", "In-seat USB outlet", "In-seat power & USB outlets", "On-demand video", "Stream media to your device", "Above/Average/Below average legroom (NN in)", "Lie flat seat", "Carbon emissions estimate: NNN kg". NO MEAL DATA EXISTS - a meal icon was requested and dropped after the probe confirmed the field is never returned. `legroom` is its own top-level field ("31 in"), separate from extensions.
- Wi-Fi: free and paid share ONE icon (deliberate product call - users assume paid; free is a pleasant surprise).
- Not yet used but available: `Lie flat seat` (business-class signal), `carbon_vs_typical_pct` (already parsed, unrendered).

**Gotchas:**
- Bash history expansion mangles `!s:<5` style Python format specs inside double-quoted shell strings (`-bash: <: unrecognized history modifier`). Write the Python to a file via a quoted heredoc (`<< 'PYEOF'`) instead of inlining it in curl pipelines.

**Next:** XXL-1.0.1 (portal legal/privacy: liability disclaimer, privacy policy, Amendment 13 compliance), then FL10A-6a (price heatmap).

## Session FL10A-6a — Supabase auth + cross-vertical tier-gating

**Naming note:** this FL10A-6a shipped AUTH + tier-gating (it jumped ahead of the price heatmap, which is now **FL10A-6b**). Earlier docs list "FL10A-6a (price heatmap)" — that heatmap is FL10A-6b going forward.

**Goal:** add Supabase auth to the flights vertical and a cross-vertical subscription tier that gates search behavior, without any billing.

**Tier model decision (cross-vertical):**
- `tier` is a column on the SHARED `users` table (`db/migrations/add_user_tier.sql` in the scrp master repo), NOT a new profiles table — every vertical (super, flights, future fashion/electronics) reads ONE value with no extra join. `TEXT NOT NULL DEFAULT 'free'` + CHECK constraint `tier IN ('free','paid')`. Migration is idempotent (applied to prod xxl_super as scrp_app).
- **No billing this session.** Every authenticated user is `'free'`; `'paid'` is set manually via SQL until a dedicated billing session exists. No Stripe/checkout/upgrade flow was built.
- The ladder lives in `backend/api/auth.py` as `TIER_MAX_DESTINATIONS = {"guest": 1, "free": 3, "paid": 5}` (max distinct destination airports per search). An "all airports" city group counts against this cap by its member count.

**Shipped (backend, xxl-flights repo):**
- `backend/api/auth.py` (NEW) — async port of scrp's sync `api/auth.py`: Supabase ES256 + JWKS verification (asyncio.Lock, httpx.AsyncClient), against the SAME shared Supabase project (dwohlwmiejgjlsbuegeu). `get_current_user` / `get_current_user_optional` (optional returns None so guests keep using `/search`), both upsert the `users` row on every authenticated request. `get_current_tier` → `'guest'` when unauthenticated else `users.tier`.
- `backend/api/routers/me.py` (NEW) — `GET /me` → `{authenticated, email, tier}`. Wired in `main.py`.
- `backend/api/routers/search.py` — `_normalize_codes(raw, max_codes=MAX_CODES)`; destination now `_normalize_codes(destination, max_codes=TIER_MAX_DESTINATIONS[tier])` (origin stays ungated at MAX_CODES=4). Guests forced to `currency="ILS"` after the existing currency validation — never trust a client-supplied currency for guests.
- `requirements.txt` — added `python-jose[cryptography]>=3.3.0`. `SUPABASE_URL` already present in prod `backend/.env` (confirmed, unchanged).

**Shipped (frontend, xxl-flights repo):**
- `AuthContext.tsx` (trimmed port of web's), `hooks/useTier.ts` (fetches `/api/me` with the bearer token), `AuthModal.tsx` (self-contained login/signup modal — no router in this app), `Header.tsx` (login button ↔ email + sign-out popover), `main.tsx` wrapped in `<AuthProvider>`, `App.tsx` currency selector gated (guest = ILS-only + signup hint; resets to ILS on sign-out). i18n keys added to he.json + en.json. `.env.development`/`.env.production`/`.env.example` created (shared public anon key, same as web).

**Ops (passwordless deploy — xxl-flights `scripts/kamatera/`):**
- `xxl-restart.sh <flights-api|scrp-api>` and `xxl-deploy-webroot.sh <flights>` — root-owned `/usr/local/bin/` scripts, case-matched on a fixed whitelist (no wildcards). `/etc/sudoers.d/xxl-ops` grants dude NOPASSWD for exactly those three invocations. Extend by adding one case branch + one sudoers line, reviewed each time — never a wildcard. This removes the interactive sudo prompt for flights backend restarts and web-root deploys. `.gitattributes` forces these `*.sh`/sudoers files to LF (CRLF breaks bash/sudoers).

**Deploy commands now (no -t, no password):**
- `ssh dude@185.229.226.190 "sudo /usr/local/bin/xxl-restart.sh flights-api"`
- `ssh dude@185.229.226.190 "sudo /usr/local/bin/xxl-deploy-webroot.sh flights"` (after scp of new dist → ~/fly_deploy)

**Verified live:**
- All 3 passwordless sudo ops run with no prompt (flights-api restart, webroot deploy, scrp-api restart).
- New bundle `index-DtBZmSxP.js` live on fly.xxl.co.il; flights-api restarted clean (no import error from api/auth.py — `/api/me` responds).
- `GET /api/me` no auth → `{"authenticated":false,"email":null,"tier":"guest"}`.
- **Guest server-side enforcement** (no token): a `/api/search` with 5 destination codes + `currency=USD` was clamped by the server to a single destination (JFK) and forced to ILS — proving the cap/lock are enforced regardless of client input.
- **NOT verified — free/paid authenticated caps:** the Supabase project **requires email confirmation**, so a REST signup returns no session token (no service-role key available to bypass). The `users.tier=free` row + the manual `paid` → cap-5 test need a confirmed login. To close this: sign up via the live UI with a real inbox, confirm the email, then `UPDATE users SET tier='paid' WHERE email='…'` and re-run a 5-code destination search with that user's bearer token.

**Next:** FL10A-6b (price heatmap) — the calendar heatmap seam is already staged in `App.tsx`'s `DateField` (see the HEATMAP SEAM comment).

## Session FL10A-6b — price calendar heatmap (free for all, incl. guests)

**Goal:** paint a per-day price heatmap on the outbound date picker. price_history was never being written — wire caching first (as a byproduct of normal search traffic, zero extra SerpApi cost), then read it back for the calendar. No tier gating — free for everyone, guests included.

**Shipped (xxl-flights repo):**
- `search.py` — best-effort price_history cache write after each search, wrapped in try/except (MUST NOT break a live search). Only **single-code** routes are cached (`"," not in origin/destination`) — `flights.routes.origin/destination` are VARCHAR(3); a comma-joined multi-code string isn't a well-defined route. Caches `min(all prices)` (or `price_insights.lowest_price` fallback) in whatever currency was searched. Route upserted via `INSERT … ON CONFLICT (origin,destination) DO UPDATE … RETURNING id`; history via `INSERT … ON CONFLICT (route_id,outbound_date,recorded_at) DO NOTHING`.
- `api/routers/price_calendar.py` (NEW) — `GET /price-calendar?origin&destination&currency`. Single 3-letter codes only (422 otherwise). Reads the latest price per outbound_date (`DISTINCT ON (outbound_date) … ORDER BY recorded_at DESC`) for the currency, over a 365-day horizon; buckets into cheap/mid/pricey by terciles (`prices[n//3]`, `prices[2n//3]`; all "mid" when n<3). Returns `{days:[{date,price,bucket}]}`, `[]` when the route/data is absent. Wired in `main.py`.
- `App.tsx` — `calendarDays` state; effect keyed on [origin,destination,currency] fetches `/api/price-calendar` (skips silently for empty/comma destinations). Derives cheap/mid/pricey `Date[]` (parses `YYYY-MM-DD` as LOCAL dates to avoid a UTC off-by-one) → `modifiers`/`modifiersClassNames` on the OUTBOUND `DateField` only (props threaded through; return picker untouched). Legend (3 dots + i18n) shown only when data exists.
- `index.css` — additive `.rdp-price-cheap/mid/pricey:not(.rdp-selected)` classes (never hard-styling day cells, per the reserved-seam rule). i18n: `search.price_legend_*` (he+en).

**BUG found + fixed during STEP 8 verification (important asyncpg gotcha):**
- Symptom: searches ran fine but the calendar stayed empty — every cache write was silently swallowed by the try/except.
- Root cause: **asyncpg requires a real `datetime.date` for a DATE column and will NOT cast a `'YYYY-MM-DD'` string** (`'str' object has no attribute 'toordinal'`). psycopg2 (scrp's sync driver) auto-casts strings, which is why the pattern "just works" in the super repo but not here. The provided snippet bound the raw string.
- Fix (commit `1dde74a`): bind `date.fromisoformat(outbound_date)`. **Rule for this async backend: always bind `date`/`datetime` objects, never strings, for DATE/TIMESTAMP params.** (The `/price-calendar` read side was already correct — it binds `date.today()`/horizon as date objects.)
- Debugging note: the swallowed exception wasn't visible because `journalctl` was NOT in the passwordless sudoers whitelist at the time — had to reproduce the exact write via the app's venv (`~/xxl-flights/venv/bin/python`) to surface the traceback. **RESOLVED (follow-up ops task):** added `xxl-logs.sh {flights-api,scrp-api}` (read-only `journalctl -u <svc> -n 200`, root-owned, in `/etc/sudoers.d/xxl-ops`, xxl-flights commit `b312644`). Read live logs passwordlessly now with `ssh dude@185.229.226.190 "sudo /usr/local/bin/xxl-logs.sh flights-api"` — no venv-repro dance needed next time.

**Verified live (fly.xxl.co.il, bundle `index-C41wzUXq.js`):**
- Seeded 4 real TLV→BCN searches → `/api/price-calendar?origin=TLV&destination=BCN&currency=ILS` returns 4 days with plausible buckets (546/666 cheap, 721/817 pricey).
- Currency isolation: USD calendar empty (only ILS seeded).
- City-group all-NYC search → HTTP 200, no error; `0` comma-containing routes ever cached (a guest all-airports search clamps to a single code and caches that, correctly). Calendar endpoint rejects multi-code input (422); the frontend skips comma destinations anyway.
- Visual layer confirmed deployed by bundle inspection (CSS heatmap classes + JS price-calendar fetch + modifier classes + legend labels all present live). Rendered colored cells not eyeballed in a browser (no browser here) — verified via deployed-code + live API buckets instead.

**Currency ↔ heatmap coupling (behavioral note, added post-`b822907`):** `price_history` is stored per searched currency and `/price-calendar` filters by currency at read time (no conversion). So the heatmap only shows for a currency that has actually been searched — TLV→BCN currently has ILS data only, so selecting **USD shows an empty calendar** (no colored cells) until USD searches accumulate. This is by design and self-heals with traffic. It was masked until the FL10A-6b→search-auth fix (`b822907`): before that, logged-in users were wrongly force-downgraded to guest → always ILS → always saw the ILS heatmap. Now that logged-in users correctly get their selected currency, a USD user sees USD results but no heatmap for a route with only ILS history. Not a bug — but if "heatmap missing" is reported, check the selected currency against what's in `price_history` for that route first.

**Next:** tier-gated feature build-out now that auth+tier (FL10A-6a) and the price cache (this session) both exist — flexible-date / budget / saved-search features per roadmap.

## Session FL10A-7a — Flexible date search (tier-gated)

**Goal:** price-per-day around a chosen outbound date, N days before/after by tier (guest 0 / free ±3 / paid ±5), reusing the `flights.price_history` cache and only calling SerpApi live for misses, hard-capped so one search can't burn the monthly quota. Roadmap **item 2.1 — DONE**.

**Shipped (xxl-flights, commit `f5bfcea`):**
- `auth.py` — `TIER_FLEX_DAYS = {"guest": 0, "free": 3, "paid": 5}` next to `TIER_MAX_DESTINATIONS`, same cross-vertical pattern.
- `search.py` — extracted `fetch_oneway_min_price(origin, destination, outbound_date, currency) -> float | None` (one-way / 1 adult / economy SerpApi probe → min price, mirroring the existing cache-write min logic; returns None on non-200/empty). The live `/search` handler's own inline call was left untouched (it needs full flight lists) — no risk to the live path. This is the "reuse not duplicate" resolution flagged in Step 0 recon (there was no pre-existing reusable single-date function).
- `api/routers/flexible_dates.py` (NEW) — `GET /flexible-dates?origin&destination&outbound_date&currency`. Single 3-letter codes only (422 on multi-code, matching price_calendar). Tier via `get_current_tier`; N = `TIER_FLEX_DAYS[tier]`. Candidate dates in **proximity order** (exact date, then ±1, ±2, …) so the fresh-call budget is spent nearest the request. Route looked up (never created on the read path). **Batched** cache read over all candidates with the same `DISTINCT ON (outbound_date) … ORDER BY recorded_at DESC` shape as price_calendar, via `outbound_date = ANY(:dates)` (confirmed working under asyncpg with a Python `date[]`). Misses filled by `fetch_oneway_min_price` up to the cap; each fill written back to `price_history` (same upsert shape; binds the `date` object directly — respects the FL10A-6b asyncpg gotcha). Response `{"dates":[{date,price,currency,source}], "cheapest_date"}` where source ∈ `cache|fresh|unavailable`; **never fabricates/interpolates** — capped-out or failed dates return `price:null, source:"unavailable"`. Guests forced to ILS (same rule as /search). Wired in `main.py`.
- Frontend `App.tsx` — "תאריכים גמישים"/"Flexible dates" toggle by the outbound picker (guests: disabled + signup hint, reusing the guest currency-lock pattern). On search (when enabled, single-code only) fetches `/flexible-dates` with the auth token; renders a horizontal date-pill strip (date + price, cheapest highlighted emerald, unavailable greyed/disabled). Clicking a pill sets that outbound date and re-runs `/search` (handleSearch gained an optional `overrideDate` arg). i18n: `search.flexible_dates_toggle`, `search.flexible_dates_signup_hint`, `search.price_unavailable` (he+en).

**MAX_FRESH_CALLS = 5** (module const in `flexible_dates.py`). Rationale: a paid ±5 search is 11 candidate dates; without a cap a cold route could fire 11 live SerpApi calls in one request. Capping fresh fills at 5 (nearest the requested date, since candidates are proximity-ordered) bounds worst-case quota burn per search while still returning cached values for every hit; the rest come back `unavailable` and get filled over time by subsequent searches. Easy to tune later.

**Verified live (bundle `index-BXbvYISF.js`):**
- Guest (N=0) path exercised end-to-end through the real endpoint: TLV→BCN 2026-08-17 → 1 date, `source:cache`, 666 (the FL10A-6b seed); a non-seeded date (2026-10-15) → `source:fresh` (635, real call) and a re-query flips it to `source:cache` (**write-back confirmed**); `currency=USD` forced to ILS (guest lock); multi-code destination → 422. Clean startup confirmed (endpoint responds → `flexible_dates.py` + the `search.py` helper imported without error).
- Multi-date read path (paid ±5 → 11 candidates, batched `ANY(:dates)` cache read) confirmed at the query level (matched the seeded 08-17 within the ±5 window during a read-only repro); `TIER_FLEX_DAYS[paid]=5` → 11 candidates.
- **STILL OPEN (same blocker as FL10A-6a):** the full authenticated free/paid HTTP response (11 dates with a live cache+fresh mix, MAX_FRESH_CALLS cap in action) was NOT exercised — the Supabase project requires email confirmation and there's no confirmed test user / service-role key to mint a token headlessly. The cap is code-bounded (loop stops fresh fills at 5, rest `unavailable`) but not exercised live. To close: confirm a test account, then `GET /api/flexible-dates` with its bearer token on a cold route and check 11 dates = up to 5 fresh + remainder unavailable.

**Next:** FL10A-7b — anywhere/budget search (roadmap 2.2).

## Session FL10A-7b — Explore search (anywhere + budget, tier-gated)

**Goal:** one `/api/explore` endpoint powered by SerpApi `engine=google_travel_explore` (NOT google_flights — different engine/shape) returning a tiered-length destination list sorted cheapest-first, feeding results into `price_history` as a free byproduct. Roadmap **item 2.2 — DONE**.

**Step 0 recon reality (recorded so nobody assumes 50 is always reachable):**
- `google_travel_explore` works on the **same** SerpApi key/plan and bills from the **same credit pool** as google_flights — one call = 1 credit (verified via `serpapi.com/account` usage delta 51→52).
- Destination count is **variable and not guaranteed ≥ 50**: an unfiltered TLV "anywhere" returned **78** in recon and **56** during verification (Explore's count shifts with date window/availability). Budget filtering shrinks it further (`max_price=800` → total_available 15). So the paid cap of 50 is a *ceiling*, often not reached — `total_available` is the honest denominator, always return it.
- Per-destination shape (actual field names): airport code is **nested** `destination_airport.code`; `name`=city, `country`, `flight_price`, `hotel_price`, `flight_duration` (**minutes**), `number_of_stops`, `airline`, `start_date`/`end_date`, `thumbnail`. Also a `destination_id` (Google entity id like `/m/0947l`) which is **not** an airport code — don't use it as one. Some destinations have null `flight_price` (car-only) — dropped.

**Shipped (xxl-flights, commit `6c63ab9`):**
- `auth.py` — `TIER_EXPLORE_RESULTS = {"guest": 5, "free": 10, "paid": 50}`.
- `api/routers/explore.py` (NEW) — `GET /explore?origin&max_price?&month?&travel_duration?&currency`. Single 3-letter origin (`Query(max_length=3)` → 422 on multi-code, same style as price_calendar/flexible_dates — NOT `_normalize_codes`, which *accepts* comma lists). Guests forced ILS. Calls `google_travel_explore` (departure_id, currency, `gl=il`, `hl=en` mirroring search.py's hardcoded hl, `travel_duration`, plus `max_price`/`month` when set). Drops null-price / codeless destinations, sorts by `flight_price`, returns `total_available` (pre-truncation) then truncates to the tier cap. Imports `SERPAPI_KEY`/`SERPAPI_URL` from search.py (single source).
- **Byproduct caching:** every parsed destination (pre-truncation — free, no extra calls) upserts `flights.routes` + writes `flights.price_history` (outbound_date = `start_date` bound as a **`date` object**, the FL10A-6b asyncpg rule), same ON CONFLICT shapes as search.py/flexible_dates.py, one commit at the end, best-effort (rollback + log on failure, never breaks the response).
- Frontend `App.tsx` — "לאן שתרצו"/"Explore anywhere" mode toggle by the trip-type control. In explore mode the destination field, date pickers, passengers, and cabin are hidden; a budget input, a month dropdown (current month + next 5), and a weekend/1wk/2wk trip-length radio appear. Results render as a **destination card grid** (thumbnail, city/country, flight price, hotel-from teaser, code · duration · stops, date range), cheapest-first. When `total_available > returned`, shows a "showing X of Y" line + (for non-paid) the reused signup-hint. i18n: new `explore.*` namespace (he+en).

**Verified live (bundle `index-5Jcg_9Vi.js`):**
- Guest TLV explore, no budget → exactly **5** destinations, `total_available: 56`, cheapest-first (ATH 384 → …).
- Budget `max_price=800` → all returned ≤ 800, `total_available` 56 → **15** (engine-level budget filter works).
- `currency=USD` (guest) → forced ILS.
- **Byproduct write-back proven downstream:** after the explore call, `TLV→ATH` shows in `/price-calendar` (2026-11-16 = 384) and `TLV→MXP` shows in `/flexible-dates` as `source:cache` (390). DB grew to 53 routes / 185 price_history rows.
- Note: tier truncation for free(10)/paid(50) is code-identical to the verified guest(5) path (same `TIER_EXPLORE_RESULTS[tier]` slice) but the authenticated HTTP path is not exercised headlessly — same email-confirmation blocker as FL10A-6a/7a.
- **CLOSED in FL10A-7c:** the authenticated path is now exercised live — paid explore returns **50**, paid flexible-dates returns the full ±5 window. The 6a/7a/7b "authenticated path unexercised" caveat is resolved for guest+paid; only the `free` row remains unverified (needs the interactive-sudo tier flip).

**Next:** roadmap 2.3+ (saved searches / alerts) — auth, tier, price cache, and now a destination-discovery surface all exist.

## Session FL10A-7c — Flexible-date window picker + calendar heatmap

**Goal:** let the user choose *how* flexible they are (instead of always getting the tier maximum), and retire the 7a pill strip in favour of colouring the outbound calendar itself. Extends roadmap item 2.1.

**Shipped (xxl-flights, commit `f5afdeb`):**
- `flexible_dates.py` — optional `flex_days` query param (`ge=0`). `n = tier_max if flex_days is None else min(flex_days, tier_max)`. The tier cap is a **ceiling, never a floor**: a client can only *narrow* the window (fewer live SerpApi calls), never widen it. Omitting the param preserves the exact pre-7c behaviour.
- `hooks/useTier.ts` — `TIER_FLEX_DAYS = {guest: 0, free: 3, paid: 5}` exported client-side, mirroring `auth.py`. Server clamps regardless, so this map only decides what the **UI offers** — keep the two in sync.
- `App.tsx` — flexibility dropdown next to the flex-dates toggle, options **generated** from `TIER_FLEX_DAYS[tier]` (`Array.from({length: …})`), never a hardcoded per-tier array; raising the backend ladder widens the dropdown with no UI edit. Selection state is `null` = "tier default", which **omits** `flex_days` from the request entirely rather than sending the max.
- **Pill strip removed.** Flexible-date prices now colour the outbound day cells via the existing `rdp-price-cheap/mid/pricey` modifiers, bucketed client-side by a deliberate mirror of `price_calendar.py::_bucket()` (sorted prices, split at `n/3` and `2n/3`, `n < 3` → everything "mid"). Unavailable dates are dropped before bucketing so they get **no modifier and stay uncoloured**. Flex buckets are merged *over* the long-range calendar buckets (`{...calendarDays, ...flexBuckets}`) since they're priced live for that exact route/window.
- Click-to-select preserved: with the flex heatmap on screen, picking a day in the picker re-runs the search on it (the strip's old behaviour), via the outbound `DateField` `onChange`.
- Cheapest-date caption retained below the legend — tercile colouring alone can't single out one day, which the strip used to do explicitly.
- Dropdown changes only refetch a strip that's **already on screen**; otherwise the new window waits for the next search rather than spending SerpApi quota on a dropdown click.

**Verified live (bundle `index-DUlGgrQd.js`, hash-matched against local `dist/`):**
- Backend restarted clean (`Application startup complete`, no import error — server is Python 3.12.3, so the `int | None` annotation is fine).
- **Guest (no token):** every `flex_days` value 0/1/2/3/5/10/99 → **1 date**. A guest cannot widen the window. Explore → 5.
- **Paid (test user):** omitted → **11** (±5, tier default); `flex_days` 0/1/2/3/5 → **1/3/5/7/11** dates (exact narrowing); `flex_days` 10 and 99 → **clamped to 11**. Explore → 50.
- **Gap:** the `free` row (±3 → 7 dates, explore 10) is *not* live-verified — flipping the test user's tier needs `set_test_tier.sh`, which requires an interactive sudo password by design. Same `min(flex_days, TIER_FLEX_DAYS[tier])` code path proven at both ends of the ladder.

**SERVER CONFIG BUG found (not introduced here, still open):** `~/xxl-flights/backend/.env` line 5 is corrupted —
`SUPABASE_ANON_KEY=<jwt>>SUPABASE_URL=https://…`. A stray `>` truncated the anon key to **101 chars / 2 JWT segments** (needs 3) and glued a duplicate `SUPABASE_URL=` onto the same line. Consequences:
- `source .env` treats it as a redirect → `get_test_token.sh` dies with `No such file or directory` on line 5. **The script has never actually run on the live box** — it only landed there with this deploy, which is why 7b never caught it.
- The truncated key returns `{"message": "Invalid API key"}` from Supabase.
- The API itself is unaffected (`auth.py` verifies via JWKS, not the anon key), which is why `/me` still works.
- **Fix:** split line 5 back into `SUPABASE_ANON_KEY=<full 3-segment jwt>` on its own line and drop the duplicate `SUPABASE_URL` (line 4 already has it). The intact key is in `xxl-flights/frontend/.env.production` as `VITE_SUPABASE_ANON_KEY` (208 chars — the anon key is a public client key, shipped in the browser bundle). This session's tier verification used that intact key directly rather than mutating production config.

**Also fixed:** `get_test_token.sh` / `set_test_tier.sh` arrived from git `-rw-rw-r--` (not executable) — `chmod +x` applied on the server. LF endings verified with `od -c` first, per the CLAUDE.md hand-edited-`.sh` rule.

**Next:** repair `backend/.env` line 5, then re-run `get_test_token.sh` to confirm it works unaided; free-tier row of the matrix still open.
