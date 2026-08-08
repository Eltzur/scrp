# SU10M — Mobile Apps Handoff (super.xxl.co.il)

> New sub-series. Paste at the start of each SU10M chat, alongside `docs/super/handoff_super.md` (shared backend/vision context still applies).
> Last updated: August 8, 2026 (end of session SU10M-1)

---

## Vision (mobile-specific, inherited from handoff_super.md)

Native iOS + Android client for super.xxl.co.il. Medium-term differentiator per the product vision: barcode scanner (scan in-store → prices nearby) and GPS "cheapest within 500m," powered by store GPS coordinates from StoresFull XMLs. Build ON the existing FastAPI backend and Supabase auth — the app is a client, not a rebuild.

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

**In v1 (parity + the one differentiator that's cheap because barcode = GTIN = item_code already):**
- Search (reuse ranking/relevance logic via existing API)
- Compare (`/compare`)
- Promos (`/promos/grouped`)
- Product detail + image (`/product/{item_code}/details`, `/product/{item_code}/image`) incl. GS1 kashrut/nutrition/ingredients blocks
- Basket
- Auth (Supabase — email/password at minimum, matching web; Google OAuth if easy via `expo-auth-session`)
- City/geo selection (manual + coarse IP/device-location city detect, matching web UX)
- **Barcode scanner → search by scanned code.** Low complexity: GTIN *is* item_code, so a scan is just a direct hit against the existing search/detail endpoint. High-value native differentiator, in scope for v1.

**Conditional on DB inspection (see below) — GPS "cheapest within 500m":**
- If `stores` already carries usable lat/lon: in scope for v1, straightforward distance filter over the existing store list.
- If not populated: push to v1.1 — becomes a backend geocoding sub-project (parse StoresFull XML fields properly, or geocode addresses), non-trivial, shouldn't block v1 ship.

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
- **Store GPS coordinates — UNCONFIRMED, gates the 500m feature.** Vision doc says StoresFull XMLs carry coordinates, but no evidence yet that a `stores` column is populated (or exists) in production. **Needs a direct DB inspection — see CC prompt below.**
- **Pagination on search/compare/promos endpoints — UNCONFIRMED.** Needs a direct code inspection — see CC prompt below.

---

### First concrete step (read-only inspection, no code/scope decisions implied)

Paste the CC prompt below to confirm the two open API-readiness items. This is inspection only — report back, no edits, no commits. Stack/scope approval can happen in parallel; this doesn't need to wait.

---

## Carried forward / open decisions for Dude

1. ~~Approve or override the React Native + Expo stack decision.~~ ✅ Approved Aug 8, 2026.
2. ~~Approve `xxl-super-mobile` as a new sibling repo.~~ ✅ Approved Aug 8, 2026.
3. **Personal vs. organization Google Play account** — affects whether the 12-tester/14-day closed testing gate applies.
4. **Mac's current macOS version** — not a blocker (EAS Build doesn't need it), but worth knowing for future local-Xcode/Simulator debugging. Xcode 26.x wants macOS 15.6+ (Sequoia) or Tahoe 26.2 depending on patch version; hardware (Apple Silicon) is not a constraint.
5. Pending DB/code inspection results (GPS coords, pagination) may reshape v1 scope for the 500m feature specifically — run the CC inspection prompt from this session before scaffolding.

## Next session (SU10M-2)

Once the read-only inspection above comes back: finalize v1 scope (confirm/deny the 500m feature), then scaffold `xxl-super-mobile` (new repo, `npx create-expo-app`, Expo Skills + MCP server + official Claude Code plugin install, NativeWind setup, port shared TS types from `web/src`). No scaffolding before that inspection.
