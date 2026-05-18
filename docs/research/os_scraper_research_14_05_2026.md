# OS Scraper Research — Findings & Recommendations

**Date:** May 14, 2026 (session 9f-followup)
**Time spent:** ~30 min web research, no code touched
**Verdict:** Skim, borrow ideas, do NOT integrate as a dependency.

---

## TL;DR

1. **License is MIT** (both `il-supermarket-scraper` v1.0.1 and `il-supermarket-parser`). The handoff worried about GPL/AGPL — it's not. We can copy-paste code if useful. Attribution required, share-alike is NOT required.
2. **They have the same geo-block problem we do.** Their PyPI page says verbatim: "Some of the scrapers sites are blocked from being accessed from outside of Israel." → confirms 9g geo-block is industry-wide, not a fix we missed.
3. **They cover ~40+ chains** (Bareket, Yayno Bitan, etc) — significantly more than our 7. Worth borrowing the chain list as a future-expansion roadmap, not as code.
4. **Maintainer himself says "development stopped until new issues found"** (PyPI page). Last release v1.0.1 was April 24, 2026. Not actively evolving — borrowing patterns is safer than depending on the package.
5. **Kaggle dataset is real but not a Carrefour/Victory stopgap.** It's published from their MongoDB pipeline → still scraped from the same geo-blocked sources from inside Israel. Doesn't bypass geo-block for fresh data; could be used for historical price-history backfill (deferred topic).
6. **They do NOT solve the canonical-naming problem.** Their `entity-matching` repo exists as an aspirational TODO in their org roadmap, not as working code. Our session 8b weighted-token voting is ahead of them on this.

---

## What's in their stack

| Repo | What it does | Useful to us? |
|---|---|---|
| `israeli-supermarket-scarpers` | Downloads XML files from chain portals → dumps to disk or Kafka. MIT. | **Maybe** — borrow Cerberus/Shufersal portal patterns we don't have, e.g. retries, queue mode for streaming. Don't add as dependency. |
| `israeli-supermarket-parsers` | Reads downloaded XMLs → pandas CSVs with unified schema. MIT. | **Yes — read for ideas.** This is the "schema linking" layer we'd need eventually. Useful for: what fields exist in XML that we're not extracting. |
| `entity-matching` | Cross-chain product matching | **No.** Empty/aspirational repo. We're ahead of them. |
| `daily-publish-supermarket-data` | Publishes daily snapshots to Kaggle | **Future, not now.** Useful if we ever want historical price-history before having years of our own snapshots. |
| Kaggle dataset `erlichsefi/israeli-supermarkets-2024` | Daily-published snapshots | Same — historical backfill only. Not a geo-block bypass. |

---

## What our scrapers might be missing (fields-wise)

Caveat: I couldn't load their `scrappers_factory.py` directly (GH blocked the raw fetch), so this is from PyPI README + their roadmap docs. Best guess based on standard gov.il PriceFull schema:

- **ItemCode + variations** — we have this.
- **ItemName / ManufacturerName / ManufactureCountry** — we have ItemName, unclear on Manufacturer fields.
- **UnitQty, Quantity, UnitOfMeasurePrice, bIsWeighted, QtyInPackage** — we may be partially parsing these; OS parser pulls them all.
- **AllowDiscount** — promo eligibility flag. We don't track.
- **ItemStatus** — active/discontinued. We may not track.
- **PriceUpdateDate per item** — finer-grained than snapshot timestamp.

**None of this is images, categories, or brands** — which is what the handoff hoped for. The gov.il XML feed simply doesn't carry images or category trees. Those need a separate source (chain websites' product catalogs, StoreNext paid tier, or barcodes-lookup like OFF which we already abandoned).

**Verdict on fields:** the OS parser doesn't unlock images/categories/brands because the source XMLs don't contain them. The handoff's hope here was based on a wrong premise. Stick with StoreNext outreach for enrichment.

---

## Patterns worth borrowing (NOT code, just ideas)

1. **Queue output mode** (Kafka or in-memory) — instead of writing XML files to disk between scrape + parse, they support streaming. Relevant to your 9g performance work: could let us skip the "write XML → re-read XML" disk round-trip our scrapers do today.
2. **`NUMBER_OF_PROCESSES=5` parallel default** — they parallelize chains by default. Validates the 9g plan (parallel chain execution via `concurrent.futures`).
3. **`TODAY` env var for backfill** — they let you pass a date to download data "from". We don't have backfill capability. Future-useful when promotions/history sessions land.
4. **Daily test suite checking if chain interfaces broke** — automated canary. Worth considering as a `health-check` cron once the scraper infra is stable.

---

## What we should NOT do

- **Don't depend on `il-supermarket-scraper` as a package.** "Development stopped" status + their own scraper hit by the same geo-block + their architecture (Mongo, Kafka, Docker) is heavier than our needs.
- **Don't use the Kaggle dataset to fill Carrefour/Victory gap.** It's downstream of the same geo-blocked sources. The fix for those chains is still Israeli VPS migration in 9g.
- **Don't rebuild canonical naming with their approach.** Their entity-matching is unbuilt; ours works (~93% stability).

---

## What to do (concrete next steps)

1. **9g (Scraper Infrastructure) prep**: when designing parallel execution, look at their `main.py` for a reference impl of `concurrent.futures` over chains. No code copy — just structural reference.
2. **Field gap closure**: in your existing parsers, audit whether `AllowDiscount`, `bIsWeighted`, `UnitOfMeasurePrice`, `QtyInPackage`, `ManufacturerName`, `ManufactureCountry` are being extracted. If not, add — they're already in the XMLs you're downloading. **No new source needed.** Small win, ~30 min in a future session.
3. **Future "expand chains" session** (post-9d-3): their factory file (40+ chains) is the canonical list of what's left. Bareket, Tiv Taam, Hazi Hinam, Super-Pharm, AM:PM, King Store, Maayan 2000, Stop Market, Zol VeBegadol, Freshmarket, Politzer, Quik, Yellow, Super Yuda, Salah Dabah, Super Cofix etc. Most have low traffic; prioritize by city presence later.
4. **StoreNext outreach remains the right path for images/categories/brands.** OS scraper research didn't find a free alternative source for these.
5. **No reason to revisit OFF.** Confirmed.

---

## License attribution (if we ever copy a snippet)

MIT requires preserving copyright notice. If we ever lift a function from their codebase, add a `# Adapted from il-supermarket-scraper (MIT, Sefi Erlich)` comment + their LICENSE.txt in `/scraper/THIRD_PARTY_LICENSES`. Not needed for inspiration-only reading.
