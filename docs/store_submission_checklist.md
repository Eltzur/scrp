# Store submission checklist — SUPER XXL (SU11A-39)

Prepared 2026-10-18 from `docs/store_privacy_inventory.md` (SU11A-38). Updated 18 Oct 2026 (SU11A-43) and 24 Oct 2026 (SU11A-53) with the Google Play status below.
Tick items as they are done. **TO CONFIRM** marks facts that are not verified yet; they must not go into published text until confirmed.

## Status (24 Oct 2026)

- **Google Play:** organisation account. All App-content declarations and the Hebrew (iw-IL) default listing were **approved and published on 18 Oct 2026**.
- **Production: LIVE since 23 Oct 2026.** Build 8 (1.2.1, versionCode 8, mobile `c2fa72d`), full rollout, Israel; developer name "XXL Team"; content rating IARC / PEGI 3.
- **Website:** the official Hebrew Play badge links to the listing (SU11A-53). The iPhone label is text only: Apple's badge and logo appear only after the iOS app is live (`IOS_APP_URL` in `web/src/config/apps.ts`).
- **Next build: versionCode 9.** Every `eas build` run burns a versionCode (`autoIncrement`); don't run it twice for one release.
- **Apple:** not started (no account yet).

## 0. Identity

| Item | Value |
|---|---|
| App name (both stores) | **SUPER XXL** (`app.json` `expo.name`) |
| Android package | `il.co.xxl.supermarket` |
| iOS bundle ID | `il.co.xxl.supermarket` |
| Version | `1.2.1` (`app.json`); build numbers are remote (`eas.json` `appVersionSource: remote`, `autoIncrement: true`) |
| Developer / legal name | XXL Enterprises (XXL אנטרפרייזס); Play developer name: XXL Team. Confirmed 18 Oct 2026 from the verified Play organisation account; check the Apple account matches when it exists |
| Privacy policy URL | https://super.xxl.co.il/privacy |
| Account deletion URL | https://super.xxl.co.il/account/delete |
| Support URL / email | https://super.xxl.co.il (or a /help page) — info@xxl.co.il |
| Category | Shopping |
| Target age (Play) | 18+ |

## 1. Before any store build

- [x] Deploy the web policy and deletion page (SU11A-39 changes in `web/src/pages/PrivacyPolicyPage.tsx`, `DeleteAccountPage.tsx`) — the in-app summary now restates them.
- [x] Commit the mobile changes (`app.json`, `eas.json`, `src/i18n/he.ts`) (`fe67d8b`); run the typecheck (exit 2 with only the 5 known `src/tw` errors is a pass).
- [x] Production build profile (`eas.json`): `developmentClient: false`, `distribution: store`, `autoIncrement: true`, Android `buildType: app-bundle` (AAB). iOS uses store distribution through the shared `distribution: store`.
- [ ] Android permissions in the production build (prebuild of a temp copy + library manifests, SU11A-39):
  - kept: `INTERNET`, `CAMERA`, `ACCESS_COARSE_LOCATION`, `ACCESS_FINE_LOCATION`, `VIBRATE` (Expo default), `ACCESS_NETWORK_STATE` (from expo-image), plus AndroidX's own `il.co.xxl.supermarket.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION` (signature-level, not user-facing)
  - removed by `android.blockedPermissions`: `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE` (also requested by expo-file-system / expo-image manifests, removed in the merge), `SYSTEM_ALERT_WINDOW`
  - debug builds only: `CHANGE_WIFI_MULTICAST_STATE` (expo-dev-launcher)
  - [ ] After the first production build, confirm in Play Console → App bundle explorer → Permissions that the list matches.
- [ ] **Fine location is kept on purpose.** The radius goes down to 1 km (`src/lib/geo.ts` `RADIUS_OPTIONS = [1..5]`), distances are shown per branch and "הכי קרוב" sorts by exact distance; Android's approximate location is only good to about 2-3 km, which would break the 1-2 km radius and the order. Users can still grant only approximate location (Android 12+, iOS 14+); the app then works with the coarser position.
- [ ] iOS: the `NSLocalNetworkUsageDescription` (English, "Expo Dev Launcher…") and `_expo._tcp` Bonjour entry come from expo-dev-client. Its plugin adds a build phase that deletes both from every non-Debug build (`node_modules/expo-dev-launcher/plugin/src/withDevLauncher.ts`, `withStripLocalNetworkKeysForRelease`). [ ] Check the Info.plist of the first production IPA (or the App Store Connect build details) to confirm they are gone.
- [ ] iOS usage strings (Hebrew, `CFBundleDevelopmentRegion: he`):
  - Camera: "SUPER XXL משתמשת במצלמה רק לסריקת ברקוד של מוצר. התמונה אינה נשמרת ואינה נשלחת, ורק מספר הברקוד נשלח לחיפוש המוצר."
  - Location (when in use): "SUPER XXL משתמשת במיקום שלך כדי להציג מחירים בסניפים הקרובים אליך. המרחק מחושב במכשיר, והמיקום אינו נשלח אלינו."
  - No microphone, Face ID, background/always location, motion. `ITSAppUsesNonExemptEncryption: false`.

## 2. Google Play

### Store listing (submitted with the review on 18 Oct 2026)
- [x] App icon 512×512 PNG (32-bit, no transparency issues)
- [x] Feature graphic 1024×500 PNG/JPG
- [x] At least 2 phone screenshots (recommended 4-8; 16:9 or 9:16, min side 320 px, max 3840 px) — scan, product with prices, nearby list, basket compare
- [x] Tablet screenshots (7" and 10")
- [x] Short description (max 80 characters, Hebrew)
- [x] Full description (max 4000 characters, Hebrew)
- [x] Contact email info@xxl.co.il; privacy policy URL
- [x] Default language Hebrew (iw-IL); category Shopping
- Note: untracked images in the mobile repo (`assets/images/icon.jpg`, `splash-icon gplay.png`, `splash-icon2.png`) — Dude's drafts, not touched.

### App content (all declarations done; submitted 18 Oct 2026)
- [x] Privacy policy URL
- [x] Ads: **No ads**
- [x] App access: some features need sign-in → provide the demo account (section 4)
- [x] Content rating questionnaire (expected: Everyone / 3+; user-generated reviews exist and are moderated — answer "users can interact / share content": reviews are public, with blacklist + report + manual review)
- [x] Target audience: **18+** (not designed for children)
- [x] Data safety (below)
- [x] Account deletion: in-app path + URL https://super.xxl.co.il/account/delete
- [x] Government app / financial features / health: No

### Data safety answers (final)
- Collects or shares required user data: **Yes**
- Encrypted in transit: **Yes**
- Users can request deletion: **Yes** (in app and URL above)
- Account creation: **username and password only** (email + password). No other sign-in methods. Account is optional.
- Shared with third parties: **None** (Supabase, Kamatera, Backblaze, Hostinger are service providers)

| Category → type | Collected | Shared | Ephemeral | Required? | Purposes |
|---|---|---|---|---|---|
| Personal info → Email address | Yes | No | No | Optional | App functionality, Account management |
| Personal info → User IDs | Yes | No | No | Optional | App functionality, Account management |
| Personal info → **Name** | **No** | | | | |
| Personal info → Address, Phone, other | No | | | | |
| Location → **Approximate location** | Yes (store IDs within the chosen radius, sent only for "nearby only" basket compare) | No | **Yes** | **Optional** | App functionality |
| Location → Precise location | No (the position never leaves the device) | | | | |
| App activity → In-app search history | Yes (search text + barcodes in server logs) | No | No | Required to use search / scan | App functionality, Security / fraud prevention |
| App activity → Other user-generated content | Yes (ratings, comments, reports, saved baskets) | No | No | Optional | App functionality |
| Photos and videos, Audio, Files, Contacts, Calendar, Messages, Health, Financial, Web browsing | No | | | | |
| App info and performance (crash logs, diagnostics) | No | | | | |
| Device or other IDs | No | | | | |

## 3. Apple App Store

### App Store Connect record (blocked until the Apple account exists — DUNS)
- [ ] Name: SUPER XXL; Subtitle (max 30 characters, Hebrew)
- [ ] Keywords (max 100 characters, comma separated)
- [ ] Description, promotional text
- [ ] Support URL; Privacy policy URL https://super.xxl.co.il/privacy
- [ ] Screenshots: 6.9" iPhone (1320×2868 or 1290×2796) required; 6.5" (1284×2778 / 1242×2688) if not covered by 6.9"; no iPad (`supportsTablet: false`)
- [ ] Age rating questionnaire (expected 4+; user-generated content is moderated → answer accordingly)
- [ ] Category: Shopping
- [ ] Export compliance: no non-exempt encryption (`ITSAppUsesNonExemptEncryption: false`)
- [ ] Sign in with Apple: not required (no third-party login; email + password only)
- [ ] Account deletion in app: Settings → מחיקת חשבון (guideline 5.1.1(v)) — mention it in the review notes
- [ ] Review notes: demo account, where deletion is, that location and camera are optional, that the app works signed out
- [ ] Review notes, guideline 1.2 (SU11A-44):
  - report and block: the ⋯ menu on each review in the product screen's reviews tab;
  - blocked list and unblock: Settings → משתמשים חסומים;
  - terms: drawer → תנאי שימוש, and the required checkbox at sign-up;
  - contact: info@xxl.co.il (terms, Help, privacy);
  - reports are reviewed within 24 hours (moderation queue + `scripts/moderation.py`).

### App Privacy answers (final)
- **Data Used to Track You: None.** No ATT prompt.
- **Data Linked to You:** Contact Info → Email Address (App Functionality); Identifiers → User ID (App Functionality); User Content → Other User Content: ratings, reviews, reports, saved baskets (App Functionality).
- **Data Not Linked to You:** Search History — search text and scanned barcodes in server logs, up to 30 days, never tied to the account (App Functionality).
- **Not collected:** Name, Location (computed on the device; the store-ID list is real-time processing only), Photos or Videos, Contacts, Health, Financial, Browsing History, Purchases, Usage Data, Diagnostics, Device ID, Sensitive Info, Other Data.

## 4. Demo reviewer account (one for Google, one for Apple, or shared)

Google Play demo account: **gplay@xxl.co.il** (password only in the Play Console review field). Never delete it, and never delete x@xxl.co.il.


- [x] Email + password account, created through the app's normal sign-up.
- [x] **Email confirmed before handing it over** — Supabase email confirmation is on, and reviewers cannot receive the mail. Sign in once on a device to prove it works.
- [ ] Normal user: tier `free`, **not** in `ADMIN_USER_EMAILS` (moderation queue), **not** in `DELETE_PROTECTED_USER_IDS` (reviewers must be able to test deletion).
- [x] Use a mailbox we control (e.g. an alias of info@xxl.co.il), not anyone's personal address.
- [ ] Seed it: one saved basket, one rating with a comment.
- [ ] If a reviewer deletes it, recreate it before the next review round.
- [ ] Put the credentials only in the store consoles' review fields — never in the repo or docs.

## 5. Pre-submission tests on real devices

Android (production AAB through internal testing track) and iPhone (TestFlight, once the account exists). Android items ticked here passed on two phones with build 7 (18 Oct 2026):
- [x] First launch: location primer → OS dialog; deny → manual city works; allow → "קרוב אלי" lists branches.
- [ ] Approximate-only location (Android 12+ "approximate", iOS "Precise: off"): app still works, no crash, radius filter still returns results.
- [ ] Camera: permission dialog shows the Hebrew text (iOS); deny → manual barcode entry works; scan EAN-13 and UPC-A.
- [ ] Search, product page, basket compare with and without "nearby only".
- [ ] Sign up → confirmation email → sign in.
- [x] Password reset by 6-digit email code, on the web and in the Android app.
- [x] Demo sign-in (gplay@xxl.co.il) and session persistence after restart.
- [x] Settings: version 1.2.1 / build 7, logout.
- [ ] Rate a product, edit it, see it under "הדירוגים שלי"; report a review.
- [ ] Privacy screen: summary shows the new camera/location line; link opens the web policy; delete-account link when signed in.
- [x] Account deletion with a throwaway account (not the reviewer account): signed out afterwards, sign-in fails, local basket and scan history remain on the phone (as the policy says).
- [ ] Signed out: drawer → privacy and terms reachable.
- [ ] Dark mode and RTL on both platforms; TalkBack / VoiceOver on the scan and delete screens.
- [ ] Android: Play Console permissions list matches section 1. iOS: production Info.plist has no `NSLocalNetworkUsageDescription`.
- [x] Terms screen: real terms and sign-up / first-rating consent are built (SU11A-44) and in build 8. The bidi / spacing fix (SU11A-46) ships in build 9. Entity name filled in SU11A-44b: XXL אנטרפרייזס (XXL Enterprises).
- [ ] Play pre-launch report for build 7: check it, and don't give the test robot the demo credentials. Deobfuscation / R8 warnings are harmless for now.
- [x] Listing approved (18 Oct 2026); Production release 8 submitted for review 18 Oct 2026; **live 23 Oct 2026**.

## 6. TO CONFIRM (do not publish until confirmed)

- [ ] Supabase project region
- [ ] Supabase auth-log retention on the current plan
- [x] Which service sends the Supabase confirmation / reset emails: **custom SMTP, Hostinger mailbox noreply@xxl.co.il** (confirmed 18 Oct 2026)
- [x] Privacy policy section 4: Hostinger named for moderation alerts AND for sign-up confirmation / password-reset emails (via Supabase, from noreply@xxl.co.il) — SU11A-44b
- [ ] Retention of moderation alerts in the info@xxl.co.il mailbox (Hostinger) — then replace the neutral wording in policy section 8
- [ ] Kamatera data-centre region
- [ ] Backblaze B2 bucket region
- [x] Legal entity name (section 0): XXL Enterprises (XXL אנטרפרייזס), the Play-verified organisation; used in the terms, privacy, accessibility and deletion pages (SU11A-44b)
- [ ] SU11A-37 popularity counters: must stay aggregate (no IP, user ID or per-event timestamp); otherwise the search-history answers and the policy change
