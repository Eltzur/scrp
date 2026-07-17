# XXL Flights — Feature Roadmap

> Scope: the search/UX features discussed after autocomplete shipped. Ordered by the
> **auth-dependency spine** — some features can't be *gated* until 10A-5b (Supabase
> auth + tiers) exists. This doc covers only these features, not the full Phase 1/2/3
> product vision (see handoff_flights.md for that).
>
> **Status (last updated after FL10A-6a):** Tier 1 quick wins SHIPPED (trip-type/one-way,
> passengers, cabin class, results sort/filter). Item **1.2 city "all airports" grouping
> SHIPPED** in FL10A-5b, together with a Kayak-style right-side results filter rail
> (stops / airline / per-arrival-airport checkboxes). **FL10A-5c** then shipped amenity
> icons (Wi-Fi / power / video / legroom) and child+infant passenger types.
> **FL10A-6a SHIPPED Supabase auth + cross-vertical tier-gating** (users.tier free-default,
> no billing; guest/free/paid destination caps + guest currency lock) — the tier-gating
> keystone is now DONE, so tier-gated features (flexible dates, budget search, saved
> searches) are unblocked.
> **FL10A-6b SHIPPED the price calendar heatmap** — price_history caching wired as a
> byproduct of search traffic (single-code routes, zero extra SerpApi cost) + a
> `/price-calendar` endpoint painting cheap/mid/pricey buckets on the outbound date picker
> (free for all, guests included).
> **Next: tier-gated feature build-out** (flexible dates / budget / saved searches) — both
> prerequisites (auth+tier, price cache) now exist. See "Session sequencing" at the bottom.

---

## The sequencing spine (read this first)

The single most important constraint: **most requested features are tier-gated, and
tier-gating doesn't exist yet.** Flexible dates, budget search, and saved searches all
differ by guest / free / paid — and none can be *gated* until 10A-5b lands auth.

So the order isn't "hardest to easiest" — it's "what unlocks what":

```
  QUICK WINS  ──►  10A-5b AUTH  ──►  TIER-GATED FEATURES  ──►  10A-6 HEATMAP
  (no auth)        (unlocks gates)   (need the tier check)     (parked, seam ready)
```

1. **Quick wins** — no auth needed, high visibility. Do first (next session).
2. **10A-5b — auth + tier-gating.** The gate mechanism everything downstream needs.
3. **Tier-gated features.** Only buildable once (2) exists.
4. **10A-6 — price heatmap.** Already parked; calendar seam reserved in 10A-4.

---

## Tier 1 — Quick wins ✅ SHIPPED in 10A-Q

These needed no auth and mostly reused data/UI already in place. All four shipped
(1.1, 1.3, 1.4) plus a major bonus fix. City "all airports" (1.2) was deferred to its
own session — it's the immediate next item (see Session sequencing below).

> **Bonus fix discovered during 10A-Q:** /search was only rendering `best_flights`
> (SerpApi's ~3-flight recommended subset) and discarding `other_flights`. Now merges
> both — ~4x the flights per search, and it's what makes the stop/airline filters
> meaningful. **Always merge both arrays.**
>
> **Declined (do not resurface):** "search both cabin classes in one query" — SerpApi
> `travel_class` is single-value, needs 2 API calls merged. Not worth the dev-tier cost.
> Cheap alternative if ever wanted: a "כל המחלקות" option that omits `travel_class`.

### 1.1 — Trip-type control (one-way / round-trip)
- **What:** a segmented toggle framing the search. One-way makes the return date field
  disappear; round-trip restores it.
- **Effort:** Small. UI already has an *optional* return date — this formalizes it.
- **API:** SerpApi supports one-way via its `type` param. Backend `/search` passes it through.
- **Dependency:** none. Also the natural container for multi-city later.

### 1.2 — City "all airports" grouping ✅ SHIPPED in FL10A-5b
- **SHIPPED.** Implemented as a BACKEND multi-code param, not a frontend fan-out. Key finding: SerpApi's `departure_id`/`arrival_id` natively accept COMMA-SEPARATED codes (`JFK,EWR,LGA`) in ONE call — Google merges and de-dups server-side. **The "NYC = 3x SerpApi calls" cost multiplier assumed below was WRONG. There is no multiplier.**
- **Grouping source:** `backend/db/airport_groups.py` inverts `AIRPORTS_CITY_EN` (deliberately the ENGLISH map — it is a strict superset of `AIRPORTS_HE`). 14 multi-airport groups. `/api/airports` prepends a synthetic `kind:"city_group"` row whose `iata_code` is the comma-joined list.
- **What:** a synthetic "ניו יורק — כל שדות התעופה" row that searches JFK+EWR+LGA in one go.
- **Effort:** Medium. Data mostly exists (`airports_city_en.py` groupings + aliases).
  Needs: a city→airports map surfaced as a selectable row, and a `/search` that accepts
  **multiple** origin/destination codes and merges results.
- **API cost:** ⚠️ one "all airports" search = N airport searches under the hood
  (NYC = 3× SerpApi calls). Factor into the dev-tier budget.
- **Dependency:** none, but pairs naturally with results-merging (1.3).

### 1.3 — Results sort & filter
- **What:** sort by price / duration / stops; filter by max stops, airline.
- **Effort:** Small — **pure frontend.** The data is already returned (`price`,
  `total_duration`, `stops`, `airline`).
- **API:** none — operates on results already fetched.
- **Dependency:** none. Highest value-to-cost ratio on the list.

### 1.4 — Passengers + cabin class
- **What:** passenger count and Economy/Business selector (Kayak's "1 Economy").
- **Effort:** Small. SerpApi supports both params; add controls + pass through.
- **Dependency:** none.

---

## Tier 2 — Requires 10A-5b (auth + tier-gating) first

Buildable only after the tier check exists. Listed in suggested build order.

### 2.1 — Flexible dates (±3 free / ±5 paid)
- **What:** search a date *window*, show the cheapest day. Guest = exact date only;
  free = ±3; paid = ±5. **Explicitly tier-gated → hard-blocked on 10A-5b.**
- **Effort:** Medium (logic) + the tier gate.
- **API cost:** ⚠️⚠️ **the expensive one.** ±5 days ≈ up to **11× SerpApi calls per
  search**. On the $50/mo dev tier this is a real constraint — needs caching
  (price_history table helps) or a cheaper source (Kiwi, but that needs 50K MAU per
  handoff). **Cost-model this before building.**
- **Dependency:** 10A-5b.

### 2.2 — Budget search ("TLV up to $300, sorted low→high")
- **What:** set origin + max price, see all reachable destinations under budget. This is
  the handoff's **"Budget-first search"** Phase-2 differentiator. Likely a paid feature.
- **Effort:** Large. Fundamentally different search shape (one origin → many destinations).
- **API cost:** ⚠️⚠️ very high — scanning many destinations per search. Realistically wants
  Kiwi Tequila (handoff: needs 50K MAU) or a heavily cached/precomputed approach.
- **Dependency:** 10A-5b (for the paid gate) + a data-source decision.

### 2.3 — Multi-city / multi-leg
- **What:** TLV→BCN, BCN→FCO, FCO→TLV in one itinerary.
- **Effort:** Large. New search payload, new results shape, more complex UI. Lives inside
  the trip-type control (1.1).
- **API cost:** Moderate-high (multiple legs per search).
- **Dependency:** not strictly auth-gated, but big enough to sequence after the quick
  wins and auth land. Trip-type toggle (1.1) is its UI home.

### 2.4 — Saved searches
- **What:** save a search to re-run. Guest 0 / free 3 / paid 5 (per handoff tier matrix).
- **Effort:** Small-medium. DB table already exists (`flights.saved_searches`).
- **Dependency:** 10A-5b (per-user, tier-limited).

---

## Tier 3 — Parked

### 3.1 — Price heatmap on the calendar (10A-6)
- Already planned; the react-day-picker day-cell seam was reserved in 10A-4.
- Needs: `flights.price_history` confirmed populating + a `/price-calendar` endpoint.
- Open decision: free or paid-tier feature?

---

## Cross-cutting notes

- **SerpApi budget is the recurring constraint.** Anything that multiplies searches
  (flexible dates, budget, multi-city, all-airports) eats the quota fast. The
  `price_history` cache and a sane TTL are the mitigation; a cheaper data source (Kiwi)
  is gated on scale (50K MAU). Cost-model the multiplier features before committing.
- **Trip-type control (1.1) is the spine of the search UI** — one-way, round-trip, and
  multi-city are all modes of it. Worth building the container early even if multi-city
  comes later.
- **Sort/filter (1.3) is the cheapest big win** — no API cost, data already present.

---

## Session sequencing (short & mid term)

> Live plan as of post-10A-Q. Order chosen for dependency, not difficulty.

### Short term — the next 1–3 sessions

**NEXT: City "all airports" grouping (item 1.2).** Self-contained, no auth.
- Goal: a synthetic "כל שדות התעופה" option so searching "ניו יורק — all airports"
  returns JFK+EWR+LGA in one go. Grouping data already exists in airports_city_en.py /
  airports_he.py.
- **The design fork to decide in recon:** frontend fan-out (fire N searches, merge) vs
  backend multi-code param (one request, server fans out). Backend is cleaner — one
  request, server controls the SerpApi budget, easier to cache — but more work.
- **Constraint:** SerpApi cost multiplier. NYC = 3 airports = 3× calls. Decide caching
  strategy *with* this feature, not after. Also de-dup merged results.

**THEN: 10A-5b — Supabase auth + tier-gating. The keystone.**
- Highest-leverage session on the board: it *unblocks everything tier-gated*. Nothing
  below can be built until it lands.
- Groundwork already done: Supabase client pre-staged (src/lib/supabase.ts),
  @supabase/supabase-js installed (both since 10A-4), header auth slot reserved.
- **Phase 0 recon = the one real unknown:** how the super app models tiers in Supabase
  (profiles table? subscription field? Stripe metadata?). Everything downstream depends
  on this answer — read the super app first.
- Shape: auth context + login/logout in the header slot → `useTier()` hook
  (guest|free|paid) → gates wired into existing UI → backend verifies Supabase JWT and
  enforces tiers server-side (never trust the client).

### Mid term — unlocked once 10A-5b lands, in priority order

1. **Saved searches** — smallest tier-gated feature; `flights.saved_searches` table
   already exists. Good low-risk first build once auth works. (Guest 0 / free 3 / paid 5.)
2. **Flexible dates (±3 free / ±5 paid)** — high value, but the expensive one:
   ±5 days ≈ up to 11× SerpApi calls/search. **Needs price_history caching working
   first**, or it blows the budget. Cost-model before building.
3. **Budget search ("TLV up to $300")** — the flagship differentiator, but heaviest:
   one origin → many destinations. Realistically wants Kiwi Tequila (gated at 50K MAU)
   or heavy precomputation. Mid-to-long term.
4. **10A-6 price heatmap** — calendar day-cell seam already reserved (10A-4). Needs
   price_history populating + a /price-calendar endpoint. Pairs naturally with flexible
   dates (same price-history data source).

### The through-line: SerpApi quota governs the mid term

Three coming features multiply API calls (flexible dates, budget, heatmap — all-airports turned out to be ONE call, no multiplier)
against a 250/mo dev tier ($50/mo at launch). **The unlock that changes the economics is
`price_history` caching** — treat it as a prerequisite investment before the multiplier
features, not an afterthought. It's currently only "slated to populate" per the handoff;
confirm it actually writes on each search early in one of these sessions.
