# XXL Roadmap

A living, priority-ordered list of pending work across all verticals. Unlike docs/super/handoff_super.md and docs/handoff_mobile.md (chronological session history), this file is forward-looking and gets reordered/edited in place as priorities shift. Update this file directly rather than appending dated entries.

## In Progress
_Nothing currently in progress._ The web 3-tab product-detail restructure and the mobile condensed-Search / 3-tab / first-time-GS1 pass both shipped and were device-verified on September 26, 2026 — written up as SU10R-2 in docs/super/handoff_super.md and "SU10R (continued)" in docs/handoff_mobile.md respectively.

## Next (agreed priority, ready to schedule)
- iOS build — after Android mobile app is fully wrapped up (per standing "Android first, then iOS" decision). Blocked on: ios.bundleIdentifier still unset, no Apple Developer account confirmed yet.
- SendGrid email integration for ratings moderation — wire _notify_moderation() to actually send mail to info@xxl.co.il on blacklist auto-hide (currently only logs to journalctl). One API key + requests (already a dependency), no new infra needed. Chosen over raw SMTP for deliverability; unifies with flights vertical's already-floated SendGrid choice.

## Needs a decision from Dude before scoping
- GS1 catalog subscription cost — measured coverage numbers are in handoff_super.md's Sept 23 entry; blocked on an actual subscription cost figure (business fact, not in the codebase) before deciding whether to trim or keep the GS1 integration.
- GS1 serving-layer gaps — only 3 of the 17 `product_info` branches in `full_content` are read by `fetch_gs1_details()`. **No longer waiting on a decision: SU10S-1 recon confirmed the real field names and fill rates** (see handoff_super.md), so this is ready to scope as a build. Image-deletion handling, previously bundled with this item, shipped in SU10S-1 (`fd324c5`).
- Google Play Console account type — Organization account requires a DUNS number (applied for, pending, ~3-5 business days as of Sept 26 2026); Personal account has no DUNS requirement but gates production release behind a 12-tester/14-day closed testing period. Revisit once DUNS resolves either way.

## Scoped but deliberately deferred
- Categories + cross-brand substitute-product recommendations (e.g. Tnuva milk 3% suggesting Tara milk 3% as a cheaper/better-rated alternative). Two sub-problems: (1) category data audit needed first — GS1's group_id/group_name only covers ~10% of catalog (GS1-matched items), no category source confirmed for the rest; (2) substitute matching is structurally the same risk class as the already-deferred cross-chain PLU-matching problem in handoff_super.md ("a wrong match is worse than no match") — treat with equal caution, high-confidence-only matching, no best-guess fallback. Sequenced deliberately AFTER ratings & reviews shipped, since "better rating" as a ranking signal has a cold-start problem and needed real rating data to exist first.
- GPS / store-distance geocoding — mobile wants user-location-based nearby-store recommendations, configurable 1-25km radius (default 5km). BLOCKED on a backend geocoding sub-project that was scoped and explicitly deferred back in SU10M-1: no lat/lon exists anywhere in the DB or source XMLs, PostGIS not installed. Needs: provider research + real cost estimate for batch-geocoding ~1,200 stores' address + city_canonical, schema change (new lat/lon columns), ongoing geocoding for new stores. Not started; treat as its own dedicated session, not an add-on to mobile work.
- Weighted-item barcode scanning (scale-printed codes) — Israeli in-store scale barcodes (prefix 27 confirmed, likely varies by chain the same way promo encodings do) embed price/weight per-label, so no base product exists to resolve to. Needs backend parsing per chain, mapping to underlying catalog item. Not started, not trivial — treat similarly to the promo unit-mismatch problem (per-chain verification required, no universal format).
- Price history (4th product-detail tab, monthly/yearly price trend) — requested Sept 26 2026. NOT buildable today: the scraper cron overwrites price rows on every run rather than preserving dated records ("Snapshot pricing only" — a standing architectural decision). Requires: (a) new price_history table (preferred over making `prices` itself append-only, which would have much wider blast radius across the read path), (b) accepting there is NO backfill possible — history only accumulates from whenever it's turned on, (c) real storage-growth consideration (prices is already ~3.7GB at snapshot-only, re-measure at build time). Connects to the older, already-listed "Promotions + price history" pending item — same prerequisite, don't duplicate scoping. Decision made this session: do NOT build a placeholder 4th tab ahead of the data existing — an empty tab reads as broken, not as "coming soon."

## Known bugs / flaws, not urgent
- Basket compare savings banner — maxTotal-minus-winner compares totals across chains with different item coverage, so "savings" can compare two different baskets. Pre-existing on web, inherited (not introduced) by mobile. Needs a product decision on what "savings" should even mean when coverage differs, not just a code fix.
- /search backend architecture — investigated read-only Sept 24 2026 (see handoff_super.md for full detail, don't duplicate here): the actual bottleneck is fetch-everything-then-paginate in fetch_prices (pulls all matching price rows before slicing a page), NOT the text-matching seq scan a trigram index would fix. Real fix is pushing LIMIT/OFFSET before the price fetch — touches _PRICE_SQL, a hot path with documented regression history (SU10A-5's enable_nestloop collision). Related, free, not yet done: Postgres config (shared_buffers/effective_cache_size/work_mem) still sized for the pre-RAM-bump 1.9GB box, flagged since SU10A-8, never retuned.

## Long-term / someday (pre-existing, from handoff_super.md's own Pending Sessions table — see that file for full detail)
- 9h: Claude Haiku integration for real portal search (currently a mocked keyword router)
- 9i: Real contact form + email notifications on xxl.co.il
- Server hardening (sudo NOPASSWD, disable root SSH, HSTS, compress OG images)
- City expansion phases 2-3 (remaining 100K+ and 50K+ population cities)
- Google OAuth (deferred since session 9b)
- Hebrew search precision (kosher-marker leak: חלבי/חלב bleed)

---

Superseded pending-items tracking: this file is now the canonical priority list. handoff_super.md and handoff_mobile.md's own "Pending Sessions"/"Carried forward" sections remain as historical record of when each item was first raised, but should not be treated as the current priority order — check here instead.
