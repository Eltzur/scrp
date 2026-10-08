# SU10M — Mobile Apps Handoff (super.xxl.co.il)

> New sub-series. Paste at the start of each SU10M chat, alongside `docs/super/handoff_super.md` (shared backend/vision context still applies).
> Last updated: September 26, 2026 (SU10M-3 Search + Basket + preview build; SU10R ratings/reviews — see the "DO NOT SURFACE blocked" warning)

---

## Standing rules

- Store-count escalation rule: see CLAUDE.md

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

---

## Session SU10S-4 (September 26, 2026) — green label + "מידע נוסף" moved above the prices

Commit `bd1f7a3`. Backend and web half is SU10S-4 in `docs/super/handoff_super.md`.

### Green label

The Product Info tab renders the Health Ministry green label as its own positive block beside the warnings section — same Hebrew, same position as web. Text plus a neutral check glyph; **the official ministry graphic is a government mark and is deliberately not reproduced.**

The client does not decide what qualifies: it renders `green_label`, which the backend derives from code FSR5. Do not re-derive it here, and do not merge it into the warnings section — it is the opposite of a warning.

Contrast was measured, and it caught a real defect in the first draft: a hardcoded `emerald-800` icon tint is 7.29:1 on the light badge but **1.97:1 on the dark one**. It is now `emerald-600` — 3.58:1 light, 4.02:1 dark, over the 3:1 bar for non-text UI on both. If that tint is ever changed, re-measure against **both** grounds; a single hardcoded colour sitting on two backgrounds is exactly where this goes wrong.

### "מידע נוסף" moved above the price list

It previously rendered after the whole card and was below the fold on any product carried by 7+ chains — found undiscoverable on device. It now sits beside the basket button in an actions row **ahead of** the chain price rows, because the price list is the long part of this screen.

The entry point moved **into** `ProductCard` behind `showMoreInfo`, defaulting **off**. `scan-result` is currently the only consumer of `ProductCard` at all (Search has its own minimal row and reaches product-detail directly), so nothing else could regress — the prop keeps that true by construction rather than by luck. Behaviour unchanged: opens product-detail on `tab=info`. Touch target stays Platform-aware 48dp/44pt, and the basket button's flat 44 was folded into the same constant, raising it to 48 on Android.

Web was checked and **not** changed: its equivalent button already sits above the price rows.

### Device checklist — for Dude to run

1. Scan `7290000056845` → "מידע נוסף" visible without scrolling → opens Product Info tab.
2. Green-label badge shown with helper text; no red warning for it.
3. A product with a sugar/sodium/sat-fat warning → warnings shown, no green badge.
4. A no-GS1 product → only the quiet "אין מידע נוסף" line.
5. Dark mode: badge still legible.

> **Heads-up on step 2.** `7290000056845` will **not** show the green badge. GS1 publishes `FSR1` ("ללא סימון") for that GTIN even though the physical carton carries the label — verified in the raw payload, and it has `has_gs1_data: true`, so this is bad supplier data rather than a missing record. Step 1 (discoverability) is still valid on that barcode. For step 2 use a GTIN that actually declares FSR5, e.g. `7290003726615` (טופו ויילר 300 גרם, 3 chains) or `7290003726141` (גבינת טופו משק גאיה).

**NOT device-verified** — typecheck adds no new errors (the five pre-existing `src/tw` NativeWind errors are unchanged), Metro export is clean, and all four new/moved strings are present in the Hermes bundle.

---

## Session SU10S-6 (September 26, 2026) — dark mode rendered text black-on-black

Commit `06cfcf6`.

### Root cause

The `@/tw` `Text` wrapper was a bare `useCssElement(RNText, …)` with **no default colour**. Text carrying no colour class fell through to React Native's own default — opaque black — which does not follow `Appearance.setColorScheme()`. In dark mode that is black on a black panel.

The drawer was only where it was noticed. **141 of the 185 `Text`/`TextInput` elements in `src/` carry no colour of their own**, across essentially every screen — settings (22), product-detail (14), product-info (11), basket-compare (10), product-card (10), and so on. The drawer accounts for 5 of them. Fixed once in the wrapper, not screen by screen.

### Why the default is a resolved colour and not a `dark:` class

Both mechanisms are reactive here — react-native-css initialises its colour-scheme observable from `Appearance.getColorScheme()` **and** subscribes to `Appearance.addChangeListener`, so its `dark:` variants do follow the app's toggle. That was checked rather than assumed, and it is also why every existing `dark:bg-*` in the app works.

The deciding factor was **override order**. react-native-css merges as `style = [classNameStyle, inlineStyle]` (`native/styles/index.js`, `deepMergeConfig`) and React Native gives the **last** array entry precedence — so **an inline style beats className**. A default passed down as `style={{ color }}` would have overridden every explicit `text-white` button label, `text-emerald-700` price and `dark:text-rose-200` allergen chip in the app: the exact opposite of a default. And a default expressed as a *class* would have to win or lose against the caller's classes by CSS source order, which a component cannot control.

So the wrapper inspects the resolved style **after** the interop has run and fills the colour in only when it is still absent, placing it first in the array. Anything the caller set — class or style — is left untouched. Verified across seven cases: no colour, `text-white`, `text-emerald-700`, a resolved `dark:` variant, an inline colour, inline-beats-className, and an opacity-only class.

`TextInput` gets the same treatment for its text, **plus `placeholderTextColor`** — that is a prop, not a style, so no className can ever reach it. Three of the app's five `TextInput`s had neither a text colour nor a placeholder colour.

### Contrast (IS 5568 / WCAG AA, ≥4.5:1)

| | light | dark |
|---|---|---|
| default text on background | 21:1 | 21:1 |
| `opacity-60` | 5.74:1 | 7.37:1 |
| `opacity-50` (before) | **3.95:1 FAIL** | 5.32:1 |
| `theme.textSecondary` | 5.94:1 | 10.08:1 |

Note the failing case is **light** mode, not dark as expected — `opacity-50` on text is 3.95:1 against white. Bumped to `opacity-60` across 9 files, which passes in both modes. This was a pre-existing light-mode defect, unrelated to the dark-mode bug, found only because the contrast was measured.

### Note for new components

This sits alongside the existing warning that `className` only works through the `src/tw/` wrappers: **text colour now has a theme-aware default, so do not reintroduce a hardcoded black** — no `color: "#000"`, no `text-black` without a `dark:` counterpart. Text that should follow the theme needs no colour at all. And if the wrapper is ever refactored, preserve the "only fill in when absent" rule: setting the colour unconditionally silently breaks every explicitly-coloured label in the app.

### Verification status

Typecheck adds no new errors (the same five pre-existing `src/tw` TS2589/TS2590, at shifted line numbers) and the Metro export is clean.

**A web preview would not prove this fix and is deliberately not offered as evidence** — web resolves text colour through CSS, while the bug is React Native's *native* default. Only a device can confirm it.

### Device checklist — for Dude

Dark mode ON, then check each:

1. Drawer: every label and section header readable.
2. Scan tab: camera-permission screen text, manual entry field (typed text + placeholder).
3. Scan result: product name, chain names, prices, branch lines, "מידע נוסף" and "בסל" buttons.
4. Product detail, all 3 tabs — incl. the green badge on `7290003726615` and warning chips on `7290107944366`.
5. Search: input + results list. Basket: items, quantity controls, compare results.
6. Settings, Account (sign-in form), My Ratings, Scan History, Help, Terms/Privacy.
7. Switch back to light mode — nothing that was fine has changed.

Item 7 is the one that matters most: the fix only *adds* a colour where none existed, so light mode should be pixel-identical apart from the `opacity-50` → `opacity-60` change making some secondary text slightly darker.

---

## Store coordinates are now available (SU10S-10) — mobile work pending

The backend half of nearby-stores shipped on September 27, 2026. Full detail is SU10S-10 in `docs/super/handoff_super.md`; what matters here:

- **`GET /stores/coordinates`** returns `[{store_fk, lat, lon, precision}]` for 965 physical stores. 63 KB, `max-age=86400`. **It takes no parameters, deliberately** — download it once, cache it, and compute distance on device.
- **The user's location must never be sent to the server.** gunicorn and nginx both log full request paths, so any lat/lon in a URL is written to disk on every request. Distance is an on-device calculation against the cached table; do not "simplify" this by adding a radius parameter to the API.
- `store_fk` matches the field already present on every price quote row in `/product/{barcode}` and `/search`, so joining prices to coordinates needs no API change.
- **`precision` matters for the UI.** 780 of 965 are `'city'` — a municipal centroid, not the shop. Only 185 are street- or house-level. A "stores within 1 km" filter would be actively misleading for the majority, so either do not offer a radius below city-centroid error, or mark city-level results as approximate.

### ⚠️ OSM attribution is owed before this ships

Street/house coordinates are OpenStreetMap data via Nominatim, **ODbL-licensed**. Any screen that shows them — a nearby list, a distance label, a map — owes a visible **"© OpenStreetMap contributors"**. It is not present anywhere in the app yet.

---

## Session SU10S-11 (September 27, 2026) — nearby stores (on-device distance)

Commit `87b73fa`. Backend half is SU10S-11 in `docs/super/handoff_super.md` (one optional field on `/basket/compare`).

### What shipped

- **Scan-result + product-detail Pricing**: a scope chip row `[קרוב אליי · N ק״מ] [הכל]` with a 1-5 km segmented control. Nearby is **ON by default** when a position and the coordinate table are both available; the existing cheapest-first order is preserved, filtering only removes rows.
- **Basket compare**: `רק סניפים קרובים`, **OFF by default** — a basket comparison is a deliberate "where should I shop" question, and silently scoping it to 5 km would change the answer without being asked. When on, the radius is stated in the results.
- **Settings**: default radius, shown only in GPS mode since it is meaningless without one.
- **Help**: a data-sources section carrying the ODbL credit.

### Invariants — do not "simplify" these

1. **The user's position never leaves the device.** There is no "stores near me" endpoint and there must not be one: gunicorn and nginx log full request paths, so a lat/lon in a URL is written to disk on every request, in two places, forever. `src/lib/geo.ts` states this at the top.
2. **City-precision stores show no distance number.** 780 of 965 stores are located only to their municipal centroid. Rendering "2.4 ק״מ" for one would be a precise-looking claim about an imprecise coordinate. They still filter — a city 30 km away is not near you — but they say `מיקום משוער`.
3. **On a filtered list the winner is `הכי זול באזור`.** Never plain `הכי זול` — see the SU10M-3 mislabel.
4. **Permission reuses `LocationProvider`**, reached from Settings. Do not add a second prompt. Note coordinates exist only in `'gps'` mode, so a manually-picked city means no position and the same quiet unavailable state as a denial.

### No rebuild required

`expo-location` was already a dependency, an `app.json` plugin and in use by Settings, so nothing native changed — **a JS reload is enough**. The 5-button segmented control rather than a slider was partly chosen for this: a native slider would have forced an EAS rebuild before anything could be tested.

### Device checklist — for Dude

1. Location allowed: scan a common product at home → nearby list with distances; street/house stores show km, city-level show "מיקום משוער".
2. Tap 1 km → list narrows; 5 km → widens; setting survives app restart.
3. "הכל" shows every store; "הכי זול באזור" only appears when filtered.
4. Deny location in Android settings → nearby hidden, hint shown, app otherwise normal.
5. Basket: toggle "רק סניפים קרובים" → results + header show the radius; toggle off → identical to before.
6. Help screen shows the OpenStreetMap credit.
7. Dark mode: chips, segmented control and labels readable.

**Not device-verified.** Typecheck adds no new errors (the same five pre-existing `src/tw`), Metro export is clean, and all seven new strings are in the Hermes bundle — but none of that proves the layout or the GPS path on a real phone.


---

## Session SU10S-15 (September 27, 2026) — drawer dark-mode text, first-launch location ask, GPS banner

Commit `c88a596` (xxl-super-mobile). JS-only — **a reload is enough, no rebuild** (`app.json`/`package.json` untouched; `expo-location` and `Linking` were already in use).

### Drawer labels invisible in dark mode — root cause (proven, and NOT a Modal issue)

The SU10S-6 default text colour was applied by cloning a `color` onto **the element `useCssElement()` returns**. That element is not always the Text: when any class on it declares a CSS custom property, `useNativeCss` (react-native-css 3.0.7, `native/react/useNativeCss.js`) returns `<VariableContext.Provider>{<Text/>}` instead. Compiling the drawer's classes with react-native-css's own compiler shows `font-medium`/`font-bold` declare `--tw-font-weight` and `text-xs` declares `--__rn-css-em`. So the colour was cloned onto the Provider, never reached the Text, and the Text fell back to React Native's black. Light mode looked fine only because the fallback black happens to be correct there.

The Modal hypothesis was checked and ruled out: the drawer icons (`useTheme()`) and the Text default already read the **same** `useColorScheme()`, so they could not disagree. The bug hits any colourless Text carrying one of those classes, anywhere — the drawer was just where it was most visible (every label is `font-medium`, the header `font-bold`).

**Fix** (`src/tw/index.tsx`): the default now lives in leaf components (`DefaultColorText`, `DefaultColorTextInput`) that the interop renders, so they always receive the final resolved style whatever wraps them, and the colour comes from `useTheme()` — one source of truth with the icons/surfaces. "Fill in only when absent" is preserved.

Other modals audited: permission-primer (title `font-bold` — same bug, now fixed by the same change), product-info, segmented-tabs, product-detail (its comment input sets `theme.text` explicitly — fine). Two **raw RN `TextInput`s with no colour** were found and moved to the `@/tw` TextInput: the Scan manual-entry modal and the Settings city search.

**A web preview cannot prove this** — web resolves text colour through CSS, and the bug was React Native's native default. Only a device confirms it.

### Location: one first-launch ask

`components/location-onboarding.tsx`, mounted in the root layout. Once per install (AsyncStorage `xxl_location_asked`, written **when the primer is shown**, so killing the app mid-dialog never earns a second prompt): the existing primer → OS dialog through `LocationProvider.enableGps()` — no second permission path. Granted → `'gps'`. Denied / "not now" → stays manual, never auto-prompted again. Skipped entirely if already granted or permanently denied. Existing installs have no flag, so their next launch counts as first, once.

**Dialog sequencing:** every OS permission request (camera button on Scan, `enableGps`) goes through `lib/permission-queue.ts`, and the primer only opens while no request is pending and the app is active. While the primer is up it covers the camera button. Two system dialogs cannot be on screen together.

`LocationProvider` now tracks `canAskAgain` and `locationUsable` (gps mode + granted), re-reads permission on every return to foreground, and drops coords if permission is revoked. This supersedes SU10S-11 invariant 4's "reached from Settings" — permission is now reached from onboarding, Settings and the banner, **still through the one `enableGps()`**.

### "Turn on location" banner

`components/location-banner.tsx`, one shared component on Scan (top overlay) and Search (above the search box). Shown when location is not usable, after the first-launch ask, and not within 14 days of ✕ (`xxl_location_banner_dismissed_at`; shared store in `lib/location-prompt-store.ts`, so ✕ on one tab hides both). "הפעלה": granted-but-manual → switch to GPS with no dialog; askable → OS dialog; permanently denied → `Linking.openSettings()`, and on return permission is re-read and GPS switched on if granted. Theme tokens (text on `backgroundElement` ≥15:1 both modes; white on emerald-700 5.5:1), 48dp/44pt targets, `accessibilityRole="button"`, icon + words, not colour alone.

### Verification status

Typecheck: only the 5 pre-existing `src/tw` TS2589/TS2590. Metro Android export clean; the banner strings and new storage keys are in the Hermes bundle. **Not device-verified.**

### Device checklist — for Dude

 1. Fresh install / cleared data → primer → OS dialog once; allow →
    nearby works on the next scan; no banner.
 2. Clear data, deny → no further auto-prompts; banner on Scan + Search.
 3. Banner "הפעלה" after a permanent deny → opens Android app settings;
    enable there, return → banner gone, nearby works.
 4. Banner ✕ → gone, stays gone after relaunch (within 14 days).
 5. Manual city chosen with permission granted → banner "הפעלה" switches
    to GPS without a dialog.
 6. Drawer in dark mode: every label + section header readable; light mode
    unchanged. Other modals readable in dark mode.
 7. Camera + location permission dialogs never appear on top of each other.

---

## Session SU10S-19 (September 27, 2026) — theme-aware city picker; a barcode typed in Search opens the product

Commit `5980355` (xxl-super-mobile). JS-only — **a reload is enough, no rebuild** (`app.json`/`package.json` untouched).

### City picker white in dark mode

Settings → "בחרו עיר" is a **non-transparent** `<Modal>`, which Android renders as its own native window with a **white default background, whatever the colour scheme**. Nothing painted over it — the panel is a raw `SafeAreaView` — so the panel stayed white, and so did the search input, which is transparent and shows the panel through. The city rows looked right only because each carries its own `dark:` background.

Fix: the panel and the input take `theme.background` from `useTheme()`, the same source of truth as the SU10S-15 `@/tw` text default (text and placeholder colours already came from there). Light mode is unchanged (still white). Row "separators" are the rows' own `dark:`-aware backgrounds with a gap; nothing to change.

Other pickers: none has this shape. `RadiusPicker` (1–5 km) is an inline segmented control, already checked in dark mode in SU10S-11; there is no chain or branch picker. A sweep for light surfaces with no dark counterpart found only the `#D1D5DB` input borders (a border, readable on dark) and the intentionally white button on the dark basket toast.

### A barcode typed into Search

`/search` matches names only (`q=7290003726615` → 0 matches; `/product/7290003726615` → 200). Now a query that is **only digits, 8–14 long** skips the name search and shows a "ברקוד …" panel with a **"הצגת המוצר"** button; **the keyboard's search key opens it directly**. Mixed text/digits, or digits outside 8–14, stay a normal name search.

It goes through `src/lib/open-barcode.ts`, the **exact path Scan's manual entry uses** — extracted from the Scan screen and now shared by both. So a typed barcode lands on `/scan-result` (found → the product; unknown → the scan flow's own not-found message) and is recorded in scan history like a manual scan. No backend change.

**Deliberately not opened from the 300 ms debounce:** 8 digits is already a valid barcode length, so auto-opening would fire on a pause mid-way through typing a 13-digit code and land on the wrong product (or a false not-found).

### Verification status

Typecheck: only the 5 pre-existing `src/tw` errors. Metro Android export clean; the new strings are in the Hermes bundle. **Not device-verified** — and a web preview would not prove the picker fix, which is about Android's native Modal window background.

### Device checklist — for Dude

1. Dark mode → Settings → "בחרו עיר": the panel, the search input (typed text + placeholder) and the city rows are all dark and readable.
2. Search tab: type `7290003726615`, press the keyboard's search key (or "הצגת המוצר") → the product opens, with the green badge.
3. Search tab: type a barcode that is not in the catalog (e.g. `7290000000000`) → the scan flow's not-found message.
4. Search tab: type "חלב" → a normal name search, as before.
5. Light mode: city picker and Search look exactly as before.

---

- **2026-09-28 (SU10S-22) first-launch permission order:** root cause — Scan (the initial route) rendered its camera-permission gate at once, while the location primer waited ~1.2 s to settle, so "נדרשת גישה למצלמה" flashed and was then covered (a render, not an OS dialog; the camera dialog is tap-only). Fix — a `resolved` flag in the location prompt store, exposed as `locationOnboardingResolved` on the nearby context; Scan shows a blank theme-background placeholder until the first-launch flow ends in any outcome (true at once when `xxl_location_asked` is already persisted; a 5 s watchdog covers a flow that never starts). Files: src/lib/location-prompt-store.ts, src/components/location-onboarding.tsx, src/lib/nearby-context.tsx, src/app/(tabs)/index.tsx. Not device-verified; typecheck shows only the 5 pre-existing src/tw errors; no ESLint set up in the repo (expo lint would scaffold it). Merged, not yet in a build — see roadmap "Next mobile build (batch)".

- **2026-09-28 (SU10S-26, session close):** no mobile code changed. Backend: `/basket/compare` no longer 500s when an item's only quote at a chain is promo-only (it now counts as missing there) — the mobile Basket tab benefits once scrp-api restarts. The app uses no `/promos/*` endpoint. Two Hazi Hinam branches (32697, 35348) got manual pins, so `/stores/coordinates` now returns 848 stores (clients may hold the old list up to a day, `max-age=86400`). Roadmap: ESLint for this repo added as low priority (23 existing errors). FIRST THING NEXT SESSION: (1) after the 10:00 cron, confirm stores 2164, 991 and 993 still hold the corrected cities, and 35348/32697 the manual pins; (2) confirm Sunday's geocode run left the 7 manual rows untouched.

- **2026-09-28 (SU10S-27) dark-mode TextInput colors:** device test (dev build, dark mode) — typed text in the login email field was invisible, black on black. Root cause: the `@/tw` `TextInput` has applied a theme-aware default text colour (`theme.text`) and `placeholderTextColor` (`theme.textSecondary`) since SU10S-19, but three inputs imported `TextInput` straight from `react-native` and bypassed it. The auth form's field (sign-in, sign-up, forgot-password all use `AuthField`) set no colour at all, so it fell to the native default. Search and the rating comment were unaffected — they pass `theme.text` / `theme.textSecondary` explicitly. Fix: all three now import `TextInput` from `@/tw`; no new styling, and explicit colours still win (the default is only prepended when the resolved style has no `color`). Why the password dots were white isn't explained by our code (no colour on either field); it comes from native rendering. Files: `src/components/auth-form.tsx`, `src/app/(tabs)/search.tsx`, `src/app/product-detail.tsx`. Every `TextInput` in `src/` now comes from `@/tw`. Not device-verified; ships in the next batch build. The dev client on Dude's phone is native 1.1.0 (build 2). The version-mismatch banner is expected until the next batch build. Typecheck: tsc hung under CC, likely a node_modules left inconsistent after SU10S-22's expo lint revert. Fixed by npm ci. Dude's run showed only the 5 known src/tw errors. Device check pending.

- **2026-09-28 (SU10S-28, session close):** no code. Status going into the next session: **SU10S-22** (first-launch permission order) is **device-verified on the dev build** (location before camera, no flash) — this updates its entry above, which was written before the test. **SU10S-27** (dark-mode TextInput) is committed (mobile `17e7ba8`, scrp `1981ba0`) and **NOT yet device-verified**. The typecheck hang was fixed by `npm ci`. The dev client on Dude's phone is native 1.1.0 (build 2); the version-mismatch banner is expected until the next batch build (1.2.1 / versionCode 5).

- **2026-10-01 (SU11A-2) "קרוב אלי" dropped nearby branches:** Dude, at a Ramat Gan address with precise location, got ONE 5 km result for sour cream 72963746 (Tiv Taam Msger, 3.4 km) while Carrefour Uzi'el (0.4 km), Tiv Taam Tfutsot Yisrael (1.2 km) and others were much closer. Not a data or distance bug — the read-only investigation found 56 live shelf quotes within ~5 km of him, and `haversineKm` is correct. Root cause: product-detail and the scan-result card ran `cheapestPerChain` (each chain's cheapest branch NATIONWIDE) and only then filtered by radius, so a chain showed nearby only if its single cheapest branch in the country was within range. Eilat is VAT-free, so for milk Rami Levy, Carrefour and Shufersal always kept an Eilat branch and never appeared nearby anywhere. Fix: one shared pure function, `scopeQuotes(quotes, classify)` in `src/lib/nearby-quotes.ts`, returns both scopes — `all` (cheapest per chain nationwide, unchanged) and `nearby` (radius filter FIRST, then cheapest per chain among in-range branches) — each cheapest-first, so "הכי זול באזור" still marks the cheapest nearby row. The "nothing in range" empty state and the chip counts are unchanged in form; the nearby count now counts chains with any in-range branch. Files: `src/lib/nearby-quotes.ts` (new), `src/app/product-detail.tsx`, `src/components/product-card.tsx`. No app.json/native change. Typecheck: only the 5 known `src/tw` errors (via `node node_modules/typescript/bin/tsc --noEmit`; `npx tsc` hung again under CC, the direct call completed). **NOT device-verified**; ships in the next batch build.

- **2026-10-01 (SU11A-4) correction to SU11A-2:** the SU11A-2 entry above was premature — the client fix was necessary but not sufficient, because `/product/{barcode}` itself sent only one quote per chain. SU11A-4 changed the server to return every store's quote; see handoff_super.md SU11A-4. Nearby filter becomes effective once the API is deployed; still NOT device-verified.

- **2026-10-04 (SU11A-9) hidden location diagnostics screen "אבחון מיקום":** opened by tapping the version row in Settings 7 times (each tap within 3 s of the previous); no menu entry, nothing visible in a normal session. Shows: (a) foreground permission, Android fine/coarse, canAskAgain, `hasServicesEnabledAsync()`, gps/manual mode; (b) the position the "קרוב אלי" filter actually uses — the same `coords` from LocationProvider, now with `fixInfo` (accuracy, fix timestamp + live age, `mocked`, origin: OS last-known fix with no age/accuracy check, fresh Balanced fix at launch, or fresh Balanced fix when GPS was turned on); (c) "קבל מיקום עדכני" — one `getCurrentPositionAsync` at Accuracy.High with a 20 s timeout, plus its distance in metres from (b); (d) the 5 nearest stores from the cached coordinate table, from the fresh fix if taken, else (b), with km and precision and a note on city-level coordinates. The cached table has no chain or store names, so rows show store ids. expo-clipboard is not installed, so values are selectable text, no copy button. Privacy: no network calls, no logging, nothing stored; the fresh fix lives in screen state only. Files: `src/app/location-diagnostics.tsx` (new), `src/lib/location-context.tsx` (additive `fixInfo` beside `coords` — the near-me filter is unchanged), `src/app/(tabs)/settings.tsx` (7-tap entry), `src/app/_layout.tsx` (route), `src/i18n/he.ts` (strings). JS-only; app.json and package.json untouched. Typecheck (`node node_modules/typescript/bin/tsc --noEmit`): only the 5 known `src/tw` errors. **NOT device-verified.** Context: SU11A-8 (read-only) showed the app's position is right and the near-me rows are picked by API row order among equal prices — not fixed yet.

- **2026-10-04 (SU11A-10) "קרוב אלי" lists individual branches:** root cause (SU11A-8, read-only): every branch of a chain charges the same price, so "cheapest branch per chain" was decided by a tie, and `cheapestPerChain` (strict `<`) kept the FIRST row — the API's arbitrary order among equal prices. That is how Carrefour Lev Dizengoff at 4.6 km beat Carrefour Uzi'el next door. New behaviour: "קרוב אלי" lists **every precisely located (address/street) branch in range**, nearest first, ties by price, 15 rows at a time with "הצג עוד". **City-precision branches** go into a collapsed section at the bottom ("סניפים במיקום משוער (N)"), one row per chain, no distance, and never compete for cheapest. **"הכי זול באזור"** marks every row at the lowest in-area price; **"+₪x"** is measured from that in-area cheapest (not the API's nationwide `delta_from_cheapest`). The **chip count** is the number of precise branches in range. "הכל" is unchanged (cheapest per chain nationwide). The list is one shared component, `NearbyQuoteList` in `product-card.tsx`, used by product-detail and the scan-result card; the scope logic is `scopeQuotes` in `src/lib/nearby-quotes.ts`. Files: `src/lib/nearby-quotes.ts`, `src/components/product-card.tsx`, `src/app/product-detail.tsx`, `src/i18n/he.ts`. Acceptance (milk 7290004131074, Dude's measured point near Carrefour Uzi'el, 5 km, real functions against live API data): 44 precise branches in range, in-area cheapest ₪7.20; first rows Carrefour 205 (0.27 km), Fresh Market 21869 (0.88), Tiv Taam Korazin 17109 (0.89), Rami Levy Giv'atayim 2182 (1.07, ₪7.20, tagged cheapest); 10 chains in the approximate section. Known leftover: the approximate section still picks a chain's representative by API order on a tie (Shufersal showed Tel Aviv, not Ramat Gan) — fixed next in SU11A-11. Typecheck (`node node_modules/typescript/bin/tsc --noEmit`): only the 5 known `src/tw` errors. **Observed working on Dude's dev client on Oct 4 (milk, 1% milk, Sano); not yet in a build; the sort toggle comes next.**

- **2026-10-04 (SU11A-11) sort toggle on both price lists; build info on the diagnostics screen:**
  - **Sort toggle "הכי קרוב" / "הכי זול"** above the "קרוב אלי" list and the "הכל" list, on product-detail and the scan-result card (both use the shared `NearbyQuoteList` / new `AllQuoteList` in `product-card.tsx`). Ordering code: `orderNearby` / `orderAll` in `src/lib/nearby-quotes.ts`. "קרוב אלי": קרוב = km asc, ties price asc; זול = price asc, ties km asc; "הכי זול באזור" stays on every row at the lowest in-area price whatever the sort. **"הכל" now lists every branch quote** the API returns (not one per chain), 15 rows at a time with "הצג עוד"; זול = price asc, ties km asc where known; קרוב = precise branches by km, then city-precision branches, then branches with no coordinate (the last two by price); km shown only for precise coordinates, "+₪x" is still the API delta. Defaults: nearest for "קרוב אלי", cheapest for "הכל". **Hidden when there is no device position** (manual city or permission denied) — price order. Switching between the two views resets to that view's default. Sort choice is screen state only (not persisted, reset on a new product); pagination resets on sort, radius or product change.
  - **Approximate section:** rows ordered by price, then distance to the city centre. That distance comes from a new `rawKm` on the nearby context (existing `haversineKm` against the stored coordinate) and is used for ordering only, never shown. A chain's representative on a price tie is now the branch nearest the user: Shufersal's is a Ramat Gan branch (fk 334, Shli Bialik), no longer Tel Aviv (fk 311).
  - **Build info on the diagnostics screen** ("הקוד שרץ": short commit hash, a "dirty" marker, and "זמן הפעלת Metro (npm start)"). `scripts/write-build-info.js` writes the gitignored `src/generated/build-info.json` and is hooked into the `start` script in package.json (that one line only; no dependency or lockfile change). `src/lib/build-info.ts` reads it with an optional `require()` in try/catch (Expo's Metro config sets `allowOptionalDependencies: true`; tsc does not resolve `require()`), and shows "לא ידוע" when the file is missing. Verified by an Android export with the file present (the hash is in the bundle) and missing (bundles clean). **Metro MUST be started with `npm start`**, not `npx expo start` — otherwise the line shows the previous run's values or "לא ידוע".
  - **Acceptance** (milk 7290004131074, test point 32.065861, 34.822135, radius 5 km, real functions against live API data): "קרוב אלי" by distance 205 (0.27 km), 21869 (0.88), 17109 (0.89), 2182 (1.07), 17101, 2200, 858, 2193; by price the first 8 are all ₪7.20 (2182, 2200, 858, 2193, 2181, 2204, 849, 2122), nearest first; "הכל" by price starts with the Rami Levy Eilat coupon ₪0.90, then four Rami Levy branches at ₪1.00; "הכל" by distance ordering: 220 precise, then 617 city-precision, then 14 without coordinates.
  - Files: `src/lib/nearby-quotes.ts`, `src/lib/nearby-context.tsx`, `src/components/product-card.tsx`, `src/app/product-detail.tsx`, `src/app/location-diagnostics.tsx`, `src/i18n/he.ts`, `src/lib/build-info.ts` (new), `scripts/write-build-info.js` (new), `package.json` (start script), `.gitignore`. app.json, eas.json, package-lock.json untouched.
  - Typecheck (`node node_modules/typescript/bin/tsc --noEmit`, Dude's machine, 343 s): only the 5 known `src/tw` errors. Not in a build yet. **Device check of the sort toggle and build-info line: pending.**

- **2026-10-04 (SU11A-12) third sort option in "הכל": "הכי זול והכי קרוב":**
  - **Definition:** in the "הכל" view only, the sort toggle gains a third option. It shows the near-me list in its "הכי זול" order — only address/street-precision branches inside the current radius setting (default 5 km), price ascending, ties by km ascending; "הכי זול באזור" on every row at the lowest price in that set; "+₪x" measured from that in-area cheapest (the SU11A-10 `delta` prop); 15 rows with "הצג עוד"; city-precision branches stay in the same collapsed "סניפים במיקום משוער" section; same empty state as near-me (its "הצגת כל הסניפים" button switches "הכל" back to plain "הכי זול"). No logic of its own: `AllQuoteList` renders `NearbyQuoteList` with a new controlled `sort="cheap"` prop (which hides that list's own toggle), so the order comes from `orderNearby(nearby, 'cheap')`. New type `AllSortMode` in `src/lib/nearby-quotes.ts`; `SortToggle` / `useSortMode` now take their options as a parameter. Defaults unchanged ("הכל" = הכי זול, near-me = הכי קרוב); toggle still hidden without a device position; sort still screen state, reset with product and view.
  - **Why it exists:** plain "הכל" + "הכי זול" stays nationwide and so starts with far-away coupons (milk: Rami Levy Eilat ₪0.90, 278 km) — kept by decision (Dude, Oct 4). The third option steps around them without leaving the view.
  - **Why near-me keeps two options:** near-me's own "הכי זול" already is exactly this list; a third option there would duplicate it.
  - **Acceptance** (milk 7290004131074, test point 32.065861, 34.822135, radius 5 km, real functions against live API data): first 8 rows 2182 (1.07 km), 2200 (2.47), 858 (2.61), 2193 (2.65), 2181 (3.28), 2204 (3.36), 849 (3.75), 2122 (4.05), all ₪7.20 and tagged "הכי זול באזור" (11 rows at ₪7.20); first other row Carrefour 205 "+₪0.15"; 44 rows, max 4.91 km, no city-precision rows, no Eilat coupon; identical to near-me "הכי זול". Unchanged: "הכל" + "הכי זול" still starts with the Eilat coupon ₪0.90; near-me by distance still 205, 21869, 17109, 2182, 17101. Live-data drift since SU11A-11 (not code): Shufersal's approximate representative is now fk 24093 (Express Negba Ramat Gan, ₪7.28, wins on price), and the coordinate table has 860 rows, moving a few distances by ≤0.1 km.
  - Files: `src/lib/nearby-quotes.ts`, `src/components/product-card.tsx`, `src/app/product-detail.tsx`, `src/i18n/he.ts`. app.json, eas.json, package.json, package-lock.json untouched.
  - Typecheck: Dude reported "typecheck ok" (the agreed bar: only the 5 known `src/tw` errors). Not yet in a build; device check pending.

- **2026-10-07 (SU11A-22, docs sync) - mobile state after SU11A-2 to SU11A-12:**
  - **Near-me:** radius filter first, then cheapest per chain (SU11A-2); the server returns per-store quotes (SU11A-4); "קרוב אלי" lists individual branches nearest first, city-precision stores in a collapsed "מיקום משוער" section (SU11A-10); sort toggle "הכי קרוב" / "הכי זול" (SU11A-11) and, in "הכל", a third option "הכי זול והכי קרוב" (SU11A-12).
  - **Privacy (decided Oct 4):** the user's position goes only in a POST body, rounded to 500 m or finer, never logged or stored; no coordinates in query strings; the privacy policy and the store privacy labels must be updated before the search redesign ships.
  - **Build facts:** next batch build is 1.2.1 / versionCode 5 (preview APK); iOS parked until Android is stable. Start the dev server with `npm start` (build-info line). Typecheck `node node_modules/typescript/bin/tsc --noEmit` takes 6-8 minutes; exit 2 with only the 5 `src/tw` errors is a pass. The dev client needs Metro on the laptop and the home Wi-Fi; a preview APK has the code baked in.
  - **Small batch pending:** GPS fresh-fix refresh (one request when the saved fix is older than ~2 minutes), screen-stays-awake check, street-level distances shown as "≈", then the 1.2.1 preview APK.
  - **Search redesign (Issue B) pending:** the read-only measurement prompt is written but not sent. Decided: score = min(relevance, distance), 10 km cap, ties by relevance, blended tiers.
  - **Store positions:** the coordinates plan of 2026-10-07 (rooftop-level stored coordinates for all stores, no Google coordinates) is in CLAUDE.md "Store positions"; near-me uses only the stored coordinates.

- **2026-10-08 (SU11A-24) mobile preview build prep (1.2.1):** batch since the last build (03d7e5a, 1.2.0 GPS field test): SU10S-22 (22a5f78), SU10S-27 (17e7ba8), SU11A-2 (b3250ec), SU11A-9 (1f7eed6), SU11A-10 (7e0e2f4), SU11A-11 (01b469d), SU11A-12 (cc0fd98), plus the GPS fresh-fix refresh below. **Found before the change:** at launch the app used the OS last-known fix with no age or accuracy check and asked for a fresh fix only when there was no last-known one; nothing refreshed the position on return to the foreground. **Change (`src/lib/location-context.tsx`):** a fix older than 2 minutes triggers one Balanced `getCurrentPositionAsync` capped at 15 s, before `coords` is set at launch, and again when the app returns to the foreground with a stale fix (one request at a time, never retried). On failure/denial the saved fix stays, with its own timestamp. New diagnostics origins: `fresh-refresh` and `stale-fallback`; the `last-known` label now says "under 2 minutes old". Position stays on the phone: no network call, no logging, nothing stored. The "≈" street-level item is dropped (no street-level rows remain). **Versioning:** app.json `version` 1.2.1; versionCode is remote in EAS (`appVersionSource: remote`) and the preview profile auto-increments it - check the build log shows 5. Typecheck and the preview build are Dude's to run; **NOT device-verified.**
