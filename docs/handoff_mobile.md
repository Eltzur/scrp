# SU10M — Mobile Apps Handoff (super.xxl.co.il)

> New sub-series. Paste at the start of each SU10M chat, alongside `docs/super/handoff_super.md` (shared backend/vision context still applies).
> Last updated: September 26, 2026 (SU10M-3 Search + Basket + preview build; SU10R ratings/reviews — see the "DO NOT SURFACE blocked" warning)

---

## Vision (mobile-specific, inherited from handoff_super.md)

Native iOS + Android client for super.xxl.co.il. Medium-term differentiator per the product vision: barcode scanner (scan in-store → prices nearby) and GPS "cheapest within 500m." Build ON the existing FastAPI backend and Supabase auth — the app is a client, not a rebuild.

**Correction (SU10M-1 inspection, Aug 8 2026):** the "powered by store GPS coordinates from StoresFull XMLs" premise above does not hold. `stores` has no coordinate column (9 columns total: id, chain_id, sub_chain_id, store_id, store_name, city, city_norm, address, city_canonical); no coordinate column exists anywhere in `public.*` or `gs1.*`; PostGIS is not installed. Checked all 34 store XMLs on disk: 33 carry no coordinate tag at all, and the one that does (StoresFull7290455000004) emits `<Latitude />`/`<Longitude />` as empty self-closing tags. The 500m feature's real path is geocoding from `address` + `city_canonical`, not extraction from the feeds. Sample dated 2026-05-31 — worth a live re-pull before committing engineering time, but don't carry the old premise into SU10M-2.

---

## Session SU10M-1 (August 8, 2026) — Research + stack decision teed up, NO app code yet

### Stack decision — ✅ APPROVED (Dude, Aug 8 2026): React Native + Expo (managed workflow, EAS Build)

| Option | Code reuse from web/ | iOS build without local Mac | CC-driveability | Native feel (camera/GPS) | Verdict |
|---|---|---|---|---|---|
| **React Native + Expo** | TS types, API client, business logic reusable as-is; UI rebuilt (NativeWind ports Tailwind classes) | **Yes — EAS Build is a cloud service**, no Xcode/Mac needed at all | **Best fit** — Expo ships an official first-party Claude Code plugin + MCP server + Skills purpose-built for exactly this (terminal-driven build/debug/deploy) | Full native, first-class camera/geo libraries | **Recommended** |
| Capacitor (wrap web build) | Highest — near 100%, one Tailwind codebase | No — still needs a Mac, Xcode Cloud, or a separately-configured CI (Codemagic/GitHub Actions) with no comparable CC-native tooling | Workable but no purpose-built agent integration | WebView-based; camera/GPS via bridge plugins (ML Kit barcode plugin exists and is solid) | Fastest to ship, weaker on the "native experience" the vision calls for, and the iOS build story stays manual |
| Flutter | None (Dart, different paradigm) | Needs Mac or CI, same as Capacitor | Generic CC support only, no special tooling | Best raw performance | Not recommended — zero reuse and no CC-tooling edge to offset it |
| Two native codebases | None | N/A | N/A | Best possible | Rejected — most work, doesn't fit a one-operator/CC workflow |

**Why RN + Expo wins on your two gating constraints specifically:**
1. **Windows-primary + optional Mac:** EAS Build removes the iOS blocker entirely — cloud-builds and can even submit to TestFlight/App Store (`eas submit`), so the whole pipeline stays on the Windows machine where CC already lives. The Mac becomes optional (nice for interactive Simulator debugging), not required. *(Still worth confirming: Xcode 26.x now requires macOS 15.6+ / Tahoe 26.2 for local builds — check the Mac's current macOS version if you ever want the local-Xcode option; hardware, Apple Silicon, is not a constraint.)*
2. **CC-driveable:** Expo's Claude Code integration (`claude plugin install expo@claude-plugins-official`, Expo MCP server, EAS CLI skill) is purpose-built for agent-driven terminal workflows — reading EAS build logs, running `eas build`/`eas submit`, upgrading SDKs, scaffolding navigation — all from prompts, matching the existing "monoblock CC prompt" operating model closely.

**Capacitor's edge (fastest code reuse) is real but doesn't offset the above** — the vision explicitly wants a *native* experience and a barcode scanner as the differentiator, and Capacitor's WebView ceiling cuts against that, while its iOS build story stays manual (Mac or bespoke CI) with none of Expo's CC-native tooling.

**Decision:** approved as-is.

---

### v1 scope proposal

**Reprioritized (Dude, Aug 10 2026): barcode scan leads, not just "in scope."** It's the one v1 feature that's actually native-only — everything else in this list is parity with what the web app already does. Build order changes accordingly: once the app can bundle/render at all (see the SU10M-2 section for NativeWind/lightningcss status — resolved Aug 10), the scan flow is the first screen built, and it's likely the app's landing experience rather than a secondary tab. Flow stays as scoped: scan → barcode is the GTIN → GTIN is the item_code → same product/search endpoint the web app already calls. Testing note: real camera testing needs a device (EAS development build or Expo Go), not just a browser/simulator preview.

**In v1 (parity + the one differentiator that's cheap because barcode = GTIN = item_code already):**
- Search (reuse ranking/relevance logic via existing API)
- Compare (`/compare`)
- Promos (`/promos/grouped`)
- Product detail + image (`/product/{item_code}/details`, `/product/{item_code}/image`) incl. GS1 kashrut/nutrition/ingredients blocks
- Basket
- Auth (Supabase — email/password at minimum, matching web; Google OAuth if easy via `expo-auth-session`)
- City/geo selection (manual + coarse IP/device-location city detect, matching web UX)
- **Barcode scanner → search by scanned code.** Low complexity: GTIN *is* item_code, so a scan is just a direct hit against the existing search/detail endpoint. High-value native differentiator, in scope for v1.

**GPS "cheapest within 500m" — CONFIRMED OUT of v1, pushed to v1.1.** SU10M-1 inspection (Aug 8 2026): no lat/lon exists anywhere in the DB, and the source XMLs don't carry usable coordinates either (see Vision correction above). This is now a backend geocoding sub-project (address + city_canonical → coordinates, likely via a geocoding API), not a simple distance filter. Scope and vendor choice for that sub-project are open for a future session; does not block v1 ship.

**Deferred to v1.1+:** favorites, recent searches, saved baskets sync UI polish (all exist server-side already, just need native screens) — not differentiators, lower priority than the scanner/geo work.

---

### Repo + toolchain proposal

- **✅ APPROVED: new sibling repo `xxl-super-mobile`** (not a subfolder of `scrp`) — separate build/signing/CI pipeline, separate store credentials, avoids the "stray file rides along into an unrelated commit" failure mode CLAUDE.md already documents for the main repo. Shared TS types (Product, Store, PromoGroup, etc.) get duplicated/hand-synced rather than monorepo-linked — small enough surface area not to need workspace tooling.
- **Implication:** this needs its own VS Code window / CC working directory (`C:\xxl-super-mobile` alongside `C:\scrp`), separate from the existing `[CC]` tag's `C:\scrp` default. Worth an explicit tag convention update (e.g. `[CC - mobile]`) once this repo exists, to avoid the exact cross-directory ambiguity CLAUDE.md warns about elsewhere.
- **Build/signing:** EAS Build (cloud) for both platforms; `eas submit` for store delivery. No Fastlane/Xcode Cloud/Codemagic config needed.
- **Prerequisites to acquire before store submission:**
  - Apple Developer Program — $99/year (individual or org)
  - Google Play Console — $25 one-time registration + ID verification; **personal accounts need 12 testers for 14 days of closed testing before production access** (organization accounts skip this) — worth deciding personal vs. org account early since it changes the timeline
  - Privacy policy covering camera (barcode scan, client-side only, no image upload) and location (distance calc only) — likely an extension of the existing xxl.co.il privacy policy rather than a new document
  - Store listing assets: icon, screenshots, short/long descriptions (Hebrew primary)

---

### API readiness

- **CORS: non-issue for React Native.** Native networking (`fetch`/native modules) doesn't run in a browser context, so browser-CORS enforcement doesn't apply — no backend CORS changes needed for RN. (This would NOT have been true for Capacitor, whose WebView-based requests are CORS-checked on some platforms — one more point in RN's favor.)
- **Auth:** backend already verifies Supabase JWTs; mobile just needs `@supabase/supabase-js` + a session-storage adapter (`expo-secure-store`) — no backend change expected.
- **Store GPS coordinates — CONFIRMED ABSENT.** No coordinate column on `stores` or anywhere else in the DB; source XMLs don't carry usable coordinates either. See Vision correction and v1 scope above.
- **Pagination on search/compare/promos endpoints — CONFIRMED, offset-based.** `/search` and `/compare`: `limit`/`offset`, default limit=30, cap le=100. `/promos/grouped`: default limit=500, cap le=5000. All three: offset uncapped, no cursor param, search/compare return `total` + computed `has_more`. **Caveat for mobile infinite-scroll:** an existing code comment at `search.py:51` notes one branch orders items arbitrarily, so offset pages can overlap between requests — more visible in a mobile feed than in web pagination. Worth a stable sort key before building infinite-scroll on top of this.

---

### First concrete step — ✅ DONE (Aug 8, 2026)

Inspection completed, no changes made. Results folded into the sections above.

---

## Carried forward / open decisions for Dude

1. ~~Approve or override the React Native + Expo stack decision.~~ ✅ Approved Aug 8, 2026.
2. ~~Approve `xxl-super-mobile` as a new sibling repo.~~ ✅ Approved Aug 8, 2026.
3. **Personal vs. organization Google Play account** — affects whether the 12-tester/14-day closed testing gate applies.
4. **Mac's current macOS version** — not a blocker (EAS Build doesn't need it), but worth knowing for future local-Xcode/Simulator debugging. Xcode 26.x wants macOS 15.6+ (Sequoia) or Tahoe 26.2 depending on patch version; hardware (Apple Silicon) is not a constraint.
5. ~~Pending DB/code inspection results (GPS coords, pagination) may reshape v1 scope for the 500m feature specifically.~~ ✅ Done Aug 8, 2026 — see corrections above. GPS coords confirmed absent; pagination confirmed offset-based and adequate.

## Next session (SU10M-2)

Inspection is done (see SU10M-1 corrections). v1 scope is settled: 500m feature is out, everything else stands. Next: scaffold `xxl-super-mobile` (new repo, `npx create-expo-app`, Expo Skills + MCP server + official Claude Code plugin install, NativeWind setup, port shared TS types from `web/src`). Scaffolding is unblocked.

---

## Session SU10M-2 checkpoint (August 9-10, 2026) — scaffold + EAS + MCP done; NativeWind unblocked (lightningcss pinned); mobile paused for the SU10A incident

**Status: paused mid-session, not abandoned.** Work stopped because the supermarket vertical hit a production incident (three consecutive OOM-killed cron runs) that took priority — see `docs/super/handoff_super.md` § SU10A-8. Nothing here is broken by that; it is simply parked.

**DONE:**
- **Repo scaffolded** — `npx create-expo-app`, SDK 57 default template, Expo Router, React Compiler enabled (`6c7e091`). Nested under `C:\scrp` per the repo-layout policy; `github.com/Eltzur/xxl-super-mobile`.
- **Expo Skills + MCP server + Claude Code plugin installed**, NativeWind wired, shared API types ported from `web/src` (`908d859`), plus a `TouchableHighlight` `underlayColor` typing fix (`429678b`).
- **EAS project linked** (`4f8b7ac`) — `projectId 91289426-105a-4901-a515-a2159388f5ee`. **Note `eas init` also silently rewrote two other fields:** `slug` `xxl-super-mobile` → **`xxl`**, and added `owner: xxlcoils-team`. Both are load-bearing for update channels and store submission — confirm they are what you want before the first build. **No `eas.json` was created**; only `app.json` changed.
- **`expo-env.d.ts` confirmed generated** on first `expo start` and already gitignored. `expo start` additionally creates `nativewind-env.d.ts` and edits `tsconfig.json`; the former is now gitignored, the latter committed (`3677d02`).
- **Typecheck 7 → 5 errors.** The 2 template errors cleared once `expo-env.d.ts` existed. The 5 remaining are all `src/tw/` type-complexity (`TS2589`/`TS2590`) — not runtime-blocking, deliberately untouched.

**NativeWind/Tailwind — WAS blocked, now RESOLVED (`98846fa`, xxl-super-mobile repo). Nothing is gated on it.**

Every Metro bundle used to die in the CSS transformer with `failed to deserialize; expected an object-like struct named Specifier, found ()`. **Fixed by pinning `lightningcss` to `1.30.1`** via a `package.json` `overrides` block — an override rather than a plain install, because npm would otherwise re-resolve upward on the next install.

**Root cause: a breaking AST change in lightningcss `1.30.2` that `react-native-css@3.0.7` was never built against.** `react-native-css` declares `"lightningcss": ">=1.27.0"` with no upper bound, so npm resolved **1.33.0**. It drives lightningcss through the **visitor API**, which round-trips the stylesheet AST between JS and Rust via serde; 1.30.2 changed AST representations, so optional fields that previously serialized as unit no longer deserialize. Two distinct symptoms, one cause — `Specifier` (dashed-ident `var()` origin, `@expo/log-box`) and `SupportsCondition` (`@import … layer()`, our own `src/global.css`).

**Bisected, not guessed — and the break is a PATCH bump:**

| Version | Result |
|---|---|
| 1.33.0 / 1.32.0 / 1.31.1 / 1.31.0 / 1.30.2 | FAIL |
| **1.30.1** | **OK** |

Why 1.30.1 is the correct pin rather than merely a working one: **`react-native-css@3.0.0` shipped 2025-09-25, four days before `1.30.2` landed on 2025-09-29**, so the whole 3.x line was developed against 1.30.1 and its own lockfile kept it there — no later patch was ever exercised. The pin also **dedupes the tree**: `@tailwindcss/node` and `@expo/metro-config` now share the single 1.30.1 copy instead of a 1.32.0/1.33.0 split.

**Verified, not assumed:**
- **iOS bundle succeeds** — `iOS Bundled 19142ms … (1684 modules)`, HTTP 200, forced via `curl` against `/.expo/.virtual-metro-entry.bundle`; zero `deserialize`/`Specifier`/`SupportsCondition` matches in the Metro log.
- **`src/global.css` itself compiles** — this was previously *unproven*, since the old failure hit `@expo/log-box`'s CSS before ever reaching it. Proven now by its distinctive `@media ios` / `@media android` blocks landing in the native stylesheet as platform-conditional vars: `["font-rounded", [["ui-rounded", [["=","platform","ios"]]], ["normal", [["=","platform","android"]]], …]]`, likewise `font-mono` / `font-serif` / `font-sans`. Nothing else in the tree emits those.
- **Tailwind classes actually apply at runtime, on both platforms.** Native stylesheet registry: `p-4 → padding 14`, `text-2xl → fontSize 21`, `rounded-lg → borderRadius 7`, `font-bold → fontWeight 700`, `text-white → color #fff`, `bg-red-500 → var(color-red-500)` defined as `#fb2c36`. Web `getComputedStyle`: `padding 16px`, `fontSize 24px`, `borderRadius 8px`, `fontWeight 700`, `color rgb(255,255,255)`, background resolving to **`#fb2c36`** — matching native exactly. The 14/16 and 21/24 split is correct, not a discrepancy: rem base is 14 on native and 16 on web.
- **Typecheck unchanged at 5** (`src/tw/` `TS2589`/`TS2590`) — unaffected by this fix.

> **`className` only works through the `src/tw/` wrappers.** `metro.config.js` sets `globalClassNamePolyfill: false` ("We add className support manually"), so putting `className` on a raw `react-native` `View` **silently no-ops** — no error, no style. This cost real time during verification. Import from `@/tw`, not `react-native`.

**Environment gotchas worth not rediscovering:**
- `expo start` alone does **not** bundle; it waits for a client. Force one with a `curl` against the dev server (`/.expo/.virtual-metro-entry.bundle?platform=ios&dev=true&…`) or you will conclude everything is fine when it is not.
- Git Bash's MSYS path conversion silently rewrites an env var like `VITE_API_URL=/apiproxy` into `C:/Program Files/Git/apiproxy`. Use `MSYS_NO_PATHCONV=1` or an absolute URL. This cost real time on the web side the same day and will bite here too.

**Next session (SU10M-3): the barcode scan flow is unblocked and starts immediately — it is not gated on anything.** The toolchain question that used to sit in front of it is closed: Metro bundles, `global.css` compiles, and NativeWind classes apply at runtime. Per the v1 reprioritization, scan is the first screen built and likely the landing experience. Remaining prerequisite is hardware, not code — **real camera testing needs a physical device (EAS development build or Expo Go); a browser or simulator preview will not exercise it.**

---

## Session SU10M-2 (continued) — Full UI wrap shipped, icon/branding done, versioning fixed

**Navigation shell**: expo-router tabs (Scan default / Search / Basket / Settings), Search and Basket are placeholder "coming soon" screens — real functionality not yet built, this is the largest remaining gap.

**Scan screen**: framing overlay, torch toggle, manual barcode entry fallback, Hebrew camera-permission-denial screen with Linking.openSettings().

**Result screen**: ported web's 3-row ProductCard layout (chain+price / promo / branch+city). Two rounds of spacing bugs fixed — first a text-duplication bug in the city picker, then a real layout bug where `flex-1` on the chain-name element (not `justify-between`, which was the initial guess) consumed all spare row width and pushed price/chain apart; fixed by matching web's `shrink` + `px-3 py-2` padding exactly. Column price-alignment was a trade-off of that fix — flagged, not yet resolved which way to land.

**Settings**: GPS requested first with manual city/chain/branch fallback, "use my location" always available to re-enable. City picker got a search/autocomplete filter. Account/auth: native in-app Sign In/Sign Up/Forgot Password using Supabase directly (the previous "browser redirect" turned out to be the unmodified Expo template's Explore tab, not a real auth bug — nothing to fix there). Session persistence via expo-secure-store with a chunked adapter (Android's 2KB SecureStore value cap otherwise silently drops Supabase's JWT+refresh token pair and logs the user out every cold start).

**Icon/branding**: app renamed "SUPER XXL" everywhere. Icon/splash regenerated from `brand/favicon.svg` (XXL wordmark, two-tone green) on a #FF9335 orange background across all 7 icon references (app icon, Android adaptive foreground/background/monochrome, favicon, splash). `expo.ios.icon` removed so iOS falls back to the main icon instead of Expo's own placeholder branding.

**Versioning bug found and fixed**: `autoIncrement` was only set on the production EAS profile, not development — meaning two different builds (Aug 11, Sep 22) both reported version 1.0.0/versionCode 1, so Android silently failed to recognize the newer build as an update on install. Fixed: `autoIncrement: true` added to all profiles, version bumped to 1.1.0. Settings screen now shows both the native (baked-into-APK) and JS-bundle version numbers with a Hebrew warning banner if they diverge — directly addresses the failure mode that caused this bug in the first place.

**Drawer menu** (hamburger + XXL icon header, custom slide-in panel — not expo-router's Drawer navigator, to avoid restructuring the native tab bar around a JS navigator still marked unstable): Account (primary sign-in/up entry point, Settings keeps a secondary link), Favorites (placeholder), Lists (placeholder), My Scan History (real — AsyncStorage, capped at 50, re-scanning moves an item to the top rather than duplicating), Help (static Hebrew tips + contact), Terms of Use / Privacy Policy (draft placeholder text with a visible amber "draft" banner — real legal text is a separate, non-dev task), Rate us/Share (native Share API, placeholder store link since unpublished), Dark Mode (real working theme via `Appearance.setColorScheme()` + NativeWind's existing `dark:` classes — not stubbed), Recommendations (preference toggle only, no logic behind it yet).

**Permission priming**: Hebrew explainer screens shown once, immediately before the native camera/GPS permission dialogs fire (skipped if already granted or permanently denied).

**Hebrew**: full Hebrew UI throughout. A few strings (build-number label, some of the newest additions) still want a native-speaker confirmation pass — not yet done.

**Build/distribution learning**: all builds so far are the `development` EAS profile, which requires Metro (`npx expo start`) running on the PC and the phone on the same network — this is why testing has required the QR-connect dance each time. Next step for a standalone, PC-independent app: cut a `preview` profile build instead (already configured in eas.json, unused so far) — it bundles the JS into the APK at build time; the API calls already go straight to the live backend regardless of build type.

## Carried forward / open decisions

→ See [docs/roadmap.md](roadmap.md) for the current prioritized list.

1. ~~Search and Basket tabs — placeholders.~~ **Both shipped in SU10M-3 (see below).** Search is text-only, no city/chain filters; Basket has quantity, compare, registered-user sync and caps.
2. Favorites/Lists — placeholders, no backend built yet.
3. iOS — `ios.bundleIdentifier` still unset (blocks any iOS build), device registration (`eas device:create`) queued but not run, no iOS build attempted yet.
4. Store submission — Google Play Console account setup (lad.co.il org account mentioned, not confirmed done), real privacy policy/terms text (legal task), store listing assets (screenshots, descriptions) — none done yet.
5. Price-comparison row alignment — resolve the justify-between/column-alignment trade-off noted above: column-aligned prices (scannable down the list) vs. the tighter chain/price pairing shipped now. Open, needs a decision.

---

## Session SU10M-3 (September 23-25, 2026) — Search and Basket shipped, first standalone build, four bugs fixed

The two placeholder tabs became real features, and the app ran without a PC attached for the first time. Four bugs were found and fixed along the way; three of the four were misdiagnosed on first attempt, and the corrections are recorded below because the wrong explanations were plausible.

### Preview EAS build — the app finally runs standalone

An Android `preview`-profile build was cut and verified working on device. This is the first build that does **not** need Metro running on the PC and the phone on the same network: `preview` bundles the JS into the APK at build time, whereas every previous build used the `development` profile and required the QR-connect dance each session. API calls already went straight to the live backend regardless of profile, so nothing else had to change.

### Search tab

Debounced text search (300ms, matching web's `SearchBar`), `PAGE_SIZE` 30 (matching web's `HomePage`), infinite scroll on `onEndReached`, and states for idle / loading / no-results / error in Hebrew reusing web's wording.

**Shared card extracted.** `/search` returns `items` as `ProductWithPrices` — the same shape a barcode lookup returns — so the scan card renders them untranslated. Rather than copy it, the card was lifted out of `scan-result.tsx` into `components/product-card.tsx`, and both screens now use it. Its quote rows became a plain `View` stack with scrolling owned by the caller, because the previous nested `ScrollView` would have broken the `FlatList`.

**Defensive dedup on pagination.** `/search` is offset-paginated and one backend code path orders ties arbitrarily, so a product can land in two consecutive pages. Incoming pages are filtered by `item_code` before appending. A subtlety worth not rediscovering: the request offset is tracked **separately** from `items.length`, because dedup drops rows and using the rendered count as the offset would re-request a window already held, discard it as duplicates, and leave the list apparently stuck. Web never hits this because web does not dedup.

**Timeout bug — the client was aborting its own requests.** Search failed on every query with a Hebrew "cannot reach the server", which looked like a network fault; the same device could scan barcodes and browse super.xxl.co.il fine. It was neither the base URL nor the client: `searchProducts` reused `TIMEOUT_MS = 15s`, sized for `/product/{barcode}` (6 KB, 0.24s). Measured against production, `/search` takes far longer and scales with how broad the query is — `q=קו` 90.4s, `q=חל` 27.1s, `q=חלב` 18-25s, `q=במבה` 1.7s. Worse, `MIN_QUERY_LEN` was 2, so with a 300ms debounce the **first** request fired for any word was its two-character prefix — the broadest and slowest query possible. Fixed with a dedicated search timeout (45s, later tuned to 30s) and `MIN_QUERY_LEN` raised 2 to 3. The browser was unaffected because web's axios instance sets no `timeout` at all and simply waits.

Two dead ends checked first and ruled out, so nobody repeats them: `URLSearchParams` **is** polyfilled as a global in RN (`setUpXHR.js`) and its `toString()` output is byte-identical to Node's for Hebrew, Latin and multi-word input.

**The backend is the real constraint.** A read-only `EXPLAIN ANALYZE` investigation found the `items` seq scan is 0.15s of a ~27s request — under 1% — and `pg_trgm` is already installed, so **a trigram index alone would not meaningfully fix this**. 99% of the time is `fetch_prices` pulling every price row for every matching barcode (390,325 rows for 7,543 barcodes on `q=חל`) and paginating only afterwards, so `offset=0` costs the same as `offset=300`. Full plan, table sizes and the architectural recommendation are in `docs/super/handoff_super.md` under "Mobile /search latency investigation" — **parked, not a current priority.**

**Collapsible results (later change).** A page of 30 fully-expanded cards, each with up to a dozen chain rows, was thousands of pixels before the second result. `ProductCard` gained a `collapsible` prop defaulting to **false**, so scan-result keeps opening straight to the price comparison without passing anything; Search opts in. Only the quote rows collapse — the header and add-to-basket stay, and a collapsed card still shows `cheapest_price` + `chains_count` so a price-comparison list never shows a row with no price.

### Basket tab — completed over two passes

**Pass 1 (foundation):** list + remove, add-to-basket on the shared product-card (so it appeared on Search and scan-result from one definition), and AsyncStorage guest persistence under `basket_items`, matching web's localStorage key.

**Pass 2 (completion):**

- **Quantity controls** — `updateQuantity` matching web (`qty <= 0` removes, so minus doubles as delete), stepping 1 for normal items and 100g for weighted. Also fixed `addItem`, which previously **no-opped** when the item was already present; web increments, and the old behaviour made a second tap look broken.
- **Compare** — `POST /basket/compare`, filters null (no city/chain in v1, same scope call as Search). The server does all pricing and returns `winner_chain_id`; nothing is re-priced client-side. The results screen **deliberately does not copy web's products x chains matrix** — that needs horizontal room a phone does not have. Same data, re-laid-out one card per chain, cheapest first, breakdown inside.
- **Registered-user sync** — local-first, backend as durable mirror. AsyncStorage stays the source of truth for rendering (guests have no backend at all, and reading from the network first would leave the basket empty until a round trip finishes and unusable offline — in an app people open inside a supermarket). Uses **`PUT /baskets/{id}`**, which exists on the backend but web's client never exposed, so the row updates in place instead of accumulating one per change. `/baskets` is a collection of *named* baskets rather than a single "current basket" slot, so the working basket maps onto one reserved row named `__xxl_mobile_basket__` — no endpoint invented.
- **Guest-to-registered merge on login** — silent, no dialog, union by `item_code` with the local entry winning and the higher quantity of the two, capped at 150, once per sign-in (guarded by user id so a token refresh does not re-run it).
- **Cap enforcement** — 25 guest / 150 registered, matching web exactly and gating only *new* items (bumping one already in the basket is always allowed). Hand-rolled toast, since RN has no toast primitive and there is no `sonner`: emerald `#047857` + lock + "להרשמה" CTA for guests, amber `#C2410C` + warning + no CTA for registered — both colours and both Hebrew strings taken verbatim from web.

**Known lossy edge:** the saved-basket wire shape is `{barcode, name, qty}` and carries no `is_weighted`, so an item pulled from the server that is not already known locally comes back non-weighted. Local always wins on merge, so this only bites for an item added on another device. It is deliberately **not** inferred from qty — "100 units" and "100g" are indistinguishable.

**"Cheapest" mislabeling — mobile-only, now fixed.** The compare screen labelled the server's winner `הזול ביותר` ("the cheapest"). It is not: `api/routers/basket.py` sorts by `(items_found desc, total_price asc)`, so the top chain is the most **complete** basket and price is only a tiebreaker among equals — intentional and documented there. Confirmed false on production: a 6-item basket ranked רמי לוי first at 30.00 while אושר עד sat further down at 24.50 with 5 of 6 items, i.e. two chains were strictly cheaper than the one labelled cheapest. **Web never made this claim** — it marks the winner with a trophy and no words (`BasketResults.tsx`) and shows the coverage fraction underneath. Mobile now matches: trophy plus the claim-free `המומלץ`, with the coverage line already present on every chain card.

### Two bugs fixed, both misdiagnosed first

**Camera permission priming removed.** The "נדרשת גישה למצלמה" screen already carries the explanation, so the extra priming modal was a second screen restating it before the same OS dialog. Removed from the camera flow only — four touchpoints in `(tabs)/index.tsx`. `components/permission-primer.tsx` is a **stateless presentational Modal** with no permission logic of its own; every flow supplies its own state, copy and handler, so the component and `settings.tsx` are untouched and **GPS keeps its primer** (that toggle has no explanatory screen in front of it, so there the primer is the only thing explaining the request).

**Tab bar icon misalignment — not a per-tab style at all.** One icon sat visibly higher than the other three. There is no margin, padding, transform or style override anywhere in `app-tabs.tsx`, and no per-screen tab options in any of the four tab files. The cause is Android's `NavigationBar` default, **`LABEL_VISIBILITY_AUTO`**: it shows every label only while there are 3 or fewer items, and at 4+ shows the label for the **selected** item alone. With exactly four tabs we sit one past that threshold, so the selected item renders icon + label and its icon lifts to make room while the other three render icon-only and centre in the full height. That is why the "broken" tab appeared to move between reports — it was always simply the *selected* tab (Settings while Settings was open, Scan on launch). Fixed with `labelVisibilityMode="labeled"`.

> This also corrects an earlier diagnosis in this file's SU10M-2 section: the labels were never wrapping — three of them were not being rendered at all. Pinning `labelStyle` `fontSize` was harmless but did not address it.

### Known gaps — investigated, not started

- **Weighted-item barcode scanning is structural, not a bug.** Israeli in-store scale-printed barcodes (prefix 2, price or weight embedded in the later digits) have no fixed base product to resolve to — every label is a different code. They pass client validation (13 digits) and then 404, because the catalog holds only 95 such codes in total. Resolving them needs backend parsing and per-chain mapping of the embedded fields. **Roadmap item, not started.**
- **~11,119 catalog items are unreachable by any barcode path.** 6.7% of `items` have codes shorter than 8 digits — and 8,472 of those are `is_weighted=1`. Examples: `2627` (גבינה קשה), `244644` (פילה סלמון). The client rejects them via `isPlausibleBarcode` (8-14 digits), but so does the API itself — verified **HTTP 400**, so this is not a mobile-side restriction to relax. Affects web equally. **Known, unaddressed.**
- **Basket compare savings banner is arithmetically loose — on both platforms.** `savings` is `maxTotal - winner.total_price`, and `maxTotal` is taken across all chains regardless of coverage. If the most expensive chain covers fewer items, the figure compares two different baskets. **Pre-existing on web** (`BasketResults.tsx`) and copied to mobile from it, so this is not mobile-introduced. Not fixed anywhere yet.

---

## Session SU10R (September 25-26, 2026) — Ratings/reviews shipped; one invariant that must not be broken

Item ratings on a 1-3 scale (X / XX / XXX), shown as a percentage computed at read time. Mobile surfaces: a rating summary on the shared product card (Search + scan-result, collapsed and expanded), a new product-detail screen with the submission form and public comments, per-comment reporting, and a My Ratings screen listing the user's own reviews including ones held for moderation.

### ⚠️ DO NOT SURFACE `blocked` IN THE UI

`POST /items/{code}/rating` returns `{id, status, blocked}`. **`blocked: true` means the blacklist filter auto-hid the submission.** The mobile app receives this field on every submit and deliberately ignores it — `product-detail.tsx` treats any 200 as a plain success and shows the same `הדירוג נשמר` confirmation either way.

**That silence is the feature, not an oversight.** The whole point of hiding a flagged comment without telling its author is that an abusive user cannot learn *that* they were filtered, and therefore cannot binary-search their way to *which word* tripped it and rephrase around it. Telling them "your review was hidden" hands them the feedback loop the filter exists to deny.

So: if any future change makes this field visible — an error toast, a red status chip, a "pending review" banner on submit, a disabled button, anything that renders differently when `blocked` is true — **it silently breaks the moderation model**, and it will look like a helpful UX improvement while doing so. The server-side comment in `api/routers/ratings.py` says the same thing from the other end. Do not "fix" the fact that nothing happens.

Note the asymmetry that makes this safe today: `blocked` is the ONLY channel through which an author's own client learns the outcome, and it is consumed and discarded in exactly one place (`onSubmit` in `product-detail.tsx`). That is the single line to watch in review.

### Verified live: no reason leak to the author

The blacklist match reason IS recorded server-side — `rating_reports.reason` holds e.g. `blacklist term matched: זבל`, naming the term — but it is reachable only through `GET /admin/ratings/pending`, which is gated on an `ADMIN_USER_EMAILS` allowlist.

Confirmed by submitting a real blacklist-tripping comment against production and inspecting every surface the author can reach, not by reading the code:

- `GET /me/ratings` returns the author's own hidden row so they can edit it, carrying `status: "hidden"` and **no** `reason` key, no `blacklist`, no `term matched`.
- Public `GET /items/{code}/ratings` excludes the hidden row entirely — **including from its own author** — so it never appears in the comments list either.
- Nothing in mobile `src/` reads a server-side report reason or calls the admin queue. Every `reason` in the client is either the HTTP error discriminant or the *outgoing* reason a user types when reporting someone else's comment.

The author sees only the neutral `בבדיקה` ("under review") tag on My Ratings, which says a review is held and never why.

---

## Session SU10R (continued, September 26, 2026) — product-detail split into three tabs, GS1 wired for the first time, Search condensed

Everything below follows the ratings ship recorded above, in the same calendar session.

### Product-detail: ratings-only → three tabs, and GS1 finally reaches mobile

The screen now carries the same three tabs as web — **מחירים** / **פרטי מוצר** / **ביקורות ודירוגים**. The reviews tab keeps its logic untouched, including the `blocked` invariant above. Prices reuse scan-result's own `QuoteRow` rather than a second copy of it.

**`פרטי מוצר` is the first time this app consumes GS1 data at all.** It was previously completely unwired — confirmed two ways before building: the screen's own prior header comment said so outright, and no details-fetcher existed anywhere in the API client. Kashrut, nutrition, ingredients and allergens now render from `GET /product/{barcode}/details` and `GET /product/{barcode}/image`, porting web's section order and Hebrew copy so the two cannot drift. Every section self-hides when empty, and the ~92% of products with no GS1 match degrade to a quiet "no additional info" line — **not** an error and not a blank screen. The fetch is lazy, firing only when the tab is first opened.

### Search condensed — and this reverses SU10M-3

Search results are now a minimal list: **item name plus manufacturer name in parentheses, nothing else** — no image, no price, no rating badge on the row, and therefore no per-row network request. Tapping a row opens product-detail.

> **This deliberately reverses the "Collapsible results" decision recorded in SU10M-3 above**, per further product direction from Dude. That entry stands as the record of why the collapsible card was built; this is the record of it being replaced. Note also that SU10R's opening paragraph describes the rating summary as appearing on the shared product card "(Search + scan-result, collapsed and expanded)" — that is now true of scan-result only.

The `collapsible` prop was **confirmed dead** once Search stopped using it — Search was its only consumer, scan-result never passed it — so the prop, its expand state, the chevron, the collapsed price summary, two orphaned imports and four now-unreferenced `he.ts` strings were removed outright rather than left dormant. Each string was grepped to zero references before deletion.

### Manufacturer dedup — built from real data, not a guessed rule

The obvious rule ("hide the manufacturer when the name already contains it") is wrong here, and measuring said so. Across **788 sampled catalog rows**, most values in the manufacturer field are not duplicated brand names at all but placeholder junk — `לא ידוע`, a bare comma, `---`, `כללי`, `הפריט בפיקוח` (a price-control notice) — enough that the naive rule would have printed something useless on roughly a third of rows.

The shipped rule in `src/lib/product-name.ts` strips corporate boilerplate (`מחלבת`, `בע"מ`) from both sides, filters the known placeholders, rejects any value containing no letters, and only then suppresses genuine duplicates. Result: shown on ~43-47% of products, suppressed on the rest. The measurements are recorded in that file so the placeholder list can be extended from data rather than guesswork.

### Navigation

- **Search row tap** → product-detail, landing on **Pricing**.
- **Scan-result keeps its always-expanded inline price display, unchanged** — only Search's list was condensed. A new **מידע נוסף** entry point was added there, landing on **Product Info**. That button is how GS1 data became reachable from the scan flow for the first time; before it there was no path to it at all.
- **The existing rating-badge tap still lands on Reviews**, unchanged.

### Deliberate accessibility divergence from web

Web's keyboard tab navigation (roving `tabIndex`, Arrow/Home/End) was **not** ported, and that is intentional rather than an oversight: there is no keyboard focus model on a touch device. `accessibilityRole`/`accessibilityState` plus screen-reader swipe navigation is the correct mobile equivalent. The reasoning is written into `components/segmented-tabs.tsx` itself so nobody later "restores" dead key handling.

### Device verification — two rounds this session

**Round 1 — the Search + Basket completion pass.** Confirmed working on device by Dude: quantity controls, compare, guest/registered sync, silent merge-on-login, the tiered cap toasts, the corrected `המומלץ` winner label, and the tab-bar icon alignment fix. **The technical detail for all of these is already written up in SU10M-3 above and is not repeated here** — what this adds is only that the pass was device-verified.

**Round 2 — this 3-tab / GS1 / condensed-search pass.** Confirmed working by Dude via screenshots showing correct tab isolation, correct kashrut and nutrition rendering, the condensed Search list, and correct default-tab landing from each entry point.

---

## Session SU10S-2 (September 26, 2026) — GS1 warning labels + unit-price basis

Two sections added to the Product Info tab, in the same order as web and with the Hebrew ported from web's `he.json` rather than re-invented: **סימון אזהרה** (Israel's mandated front-of-pack warnings) and **בסיס להשוואת מחיר** (the declared unit-price basis). Both self-hide when absent, like every other GS1 block here. Commit `dd77034`; the backend and web half is SU10S-2 in `docs/super/handoff_super.md`.

Warning badges reuse the existing rose `Chip` tone already used for the "contains" allergen list, so severity reads consistently within the tab.

**The client does not decide what counts as a warning.** The backend filters both the "no marking" sentinel and — less obviously — the positive green label FSR5 (`סמל ירוק`), which is a *healthy* marker and would be actively misleading as a red badge. Anything in `warning_labels` is already a real warning. Do not re-derive this client-side from raw values, and do not add the green label to this section if it is ever surfaced; it needs its own field and its own copy.

`src/types/api.ts` was regenerated from the live schema rather than hand-edited, per that file's own instruction. +350 lines, purely additive — it had gone stale and predated the ratings endpoints.

**NOT device-verified** — no device attached and `adb` unavailable, the same caveat as every other mobile change this session. Typecheck adds no new errors (the five pre-existing `src/tw` NativeWind errors are unchanged), the Metro export is clean, and both new headings are present in the Hermes bundle with no warning *values* hardcoded — those arrive from the API.

