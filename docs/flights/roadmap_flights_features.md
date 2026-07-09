# XXL Flights — Feature Roadmap (post-10A-5a)

> Scope: the search/UX features discussed after autocomplete shipped. Ordered by the
> **auth-dependency spine** — some features can't be *gated* until 10A-5b (Supabase
> auth + tiers) exists. This doc covers only these features, not the full Phase 1/2/3
> product vision (see handoff_flights.md for that).

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

## Tier 1 — Quick wins (NEXT SESSION, no auth dependency)

These need no auth and mostly reuse data/UI already in place.

### 1.1 — Trip-type control (one-way / round-trip)
- **What:** a segmented toggle framing the search. One-way makes the return date field
  disappear; round-trip restores it.
- **Effort:** Small. UI already has an *optional* return date — this formalizes it.
- **API:** SerpApi supports one-way via its `type` param. Backend `/search` passes it through.
- **Dependency:** none. Also the natural container for multi-city later.

### 1.2 — City "all airports" grouping (Kayak's NYC metacode)
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

## Suggested next-session scope (quick wins)

Recommend bundling into one "10A-Q" quick-wins session:
1. Trip-type toggle + one-way (1.1)
2. Results sort/filter (1.3)
3. Passengers + cabin class (1.4)

Defer city "all airports" (1.2) to its own session — the multi-code `/search` change is
enough surface area to warrant STOP checkpoints and API-cost testing on its own.
