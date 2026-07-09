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
