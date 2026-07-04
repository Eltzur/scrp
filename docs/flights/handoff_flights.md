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

---

## Open decisions

- Subdomain vs path: fly.xxl.co.il vs xxl.co.il/flights (recommend fly.xxl.co.il for Phase 1)
- Exact Travelpayouts program to join (Kiwi vs Aviasales — test both)
- Email provider for alerts: SendGrid free tier (100 emails/day) — confirm before 10A-2
- Paid subscription price point (TBD)
- scrp_app password: RESOLVED (new clean password, no special chars; stored in server .env + password manager, NOT committed to repo)
