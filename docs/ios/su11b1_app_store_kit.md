# SUPER XXL — App Store submission kit (SU11B-1)

Prepared 1 Nov 2026. Source facts: `docs/store_privacy_inventory.md` (SU11A-38), `docs/store_submission_checklist.md`, the mobile code at the SU11B-1 commit. Step-by-step use: `docs/ios/su11b1_runbook.md`.

**No credentials in this file or anywhere in the repo.** Passwords are typed only into App Store Connect / the EAS prompt.

| Item | Value |
|---|---|
| App Store Connect app | SUPER XXL, Apple ID (ascAppId) **6829450422** |
| Bundle ID | `il.co.xxl.supermarket` |
| SKU | `superxxl-ios-001` |
| Team | Individual, Team ID **V46QVK4YSA**; seller shown on the store: **Elad Tzur** (must read so before Submit for Review; it currently reads "Lead Tour") |
| Version | **1.2.2** (SU11B-2; same as Android build 9); build number from EAS (remote, auto-increment). **Submit build 1.2.2 (2)** (SU11B-3 commit); build 1.2.2 (1) was rejected in processing (ITMS-90683, missing NSMotionUsageDescription) |
| Devices | iPhone only (`supportsTablet: false`) |
| Primary language | Hebrew |
| Categories | Primary: Shopping; secondary: Food & Drink |
| Price / availability | Free; Israel only |
| DSA (EU) | Non-trader; not distributed in the EU |

---

## 1. Listing (Hebrew)

Counts are Unicode characters, as App Store Connect counts them (checked with Python `len()`).

**Name** (≤30) — 9 characters
```
SUPER XXL
```

**Subtitle** (≤30) — 23 characters (already entered in ASC)
```
השוואת מחירי סופרמרקטים
```

**Promotional text** (≤170) — 125 characters. Can be changed later without a new review.
```
סורקים ברקוד או מחפשים מוצר, ורואים מיד איפה הוא הכי זול: מחירים עדכניים מ-14 רשתות שיווק בישראל, כולל הסניפים הקרובים אליכם.
```

**Keywords** (≤100, comma-separated, no spaces after commas, no chain brand names; the words of the name and subtitle are already indexed) — 91 characters
```
מחירים,סופר,השוואה,ברקוד,סריקה,מבצעים,קניות,סל,חיסכון,זול,מצרכים,מכולת,מוצרים,מחיר,סופרמרקט
```

**Description** (≤4000) — 1174 characters
```
SUPER XXL משווה מחירי מוצרי סופרמרקט בין 14 רשתות שיווק בישראל, כדי שתדעו איפה הכי משתלם לקנות.

מה אפשר לעשות באפליקציה:
• סריקת ברקוד: מכוונים את המצלמה לברקוד של מוצר ורואים את המחיר שלו בכל הרשתות. אפשר גם להקליד את מספר הברקוד.
• חיפוש מוצרים: מחפשים לפי שם, מותג או ברקוד, עם הצעות תוך כדי הקלדה.
• קרוב אליי: אם תאשרו גישה למיקום, תראו את המחירים בסניפים שברדיוס שבחרתם, מהקרוב לרחוק או מהזול ליקר. המרחק מחושב במכשיר, והמיקום שלכם לא נשלח אלינו. אפשר גם לבחור עיר ידנית.
• סל קניות: מוסיפים מוצרים לסל ומשווים את המחיר של הסל כולו בין הרשתות, גם רק בסניפים הקרובים.
• מידע על המוצר: רכיבים, ערכים תזונתיים, סימוני אזהרה וסימון ירוק, כשהיצרן מסר אותם.
• דירוגים וביקורות: משתמשים רשומים יכולים לדרג מוצרים ולכתוב ביקורת. אפשר לדווח על ביקורת ולחסום את מי שכתב אותה.

מאיפה המחירים?
המחירים מגיעים מהקבצים שרשתות השיווק מפרסמות לפי חוק קידום התחרות בענף המזון, ומתעדכנים מדי יום. המחיר בקופה הוא הקובע; ייתכנו הבדלים בין המחיר באפליקציה למחיר בסניף.

פרטיות:
אין באפליקציה פרסומות, כלי ניתוח או מעקב. המצלמה משמשת רק לזיהוי הברקוד, ורק מספר הברקוד נשלח לחיפוש. ההרשמה אינה חובה, ואפשר למחוק את החשבון מתוך האפליקציה: הגדרות ← מחיקת חשבון.

שאלות והערות: info@xxl.co.il
```
Notes: "14 רשתות" matches `scraper/registry.py` today; change the number in both places if a chain is added or dropped. "מבצעים" in the keywords is accurate (promo prices appear on quotes) — the app has no promos screen.

**URLs**

| Field | URL | Note |
|---|---|---|
| Support URL | https://super.xxl.co.il | Footer "צור קשר" (mailto:info@xxl.co.il) on every page |
| Marketing URL (optional) | https://super.xxl.co.il | |
| Privacy Policy URL | https://super.xxl.co.il/privacy | |
| Terms (not an ASC field; for the review notes / EULA) | https://xxl.co.il/disclaimer | Same link as the in-app terms footer. Keep Apple's standard EULA (no custom licence agreement). |
| Account deletion (web) | https://super.xxl.co.il/account/delete | |

**Copyright**
```
2026 XXL Enterprises
```
(App Store Connect adds the © itself.)

**What's New** (first version: not shown; keep for 1.2.3+).

---

## 2. App Privacy questionnaire

Derived from `docs/store_privacy_inventory.md` §C and §A; matches the privacy manifest now in `app.json` (`ios.privacyManifests`).

**Do you or your third-party partners collect data from this app?** Yes.

| Data type (Apple) | Collected | Linked to the user | Used for tracking | Purposes | Reasoning |
|---|---|---|---|---|---|
| Contact Info → **Email Address** | Yes | **Yes** | No | App Functionality | Only when the user registers (Supabase auth; `users.email`). Optional account. |
| Identifiers → **User ID** | Yes | **Yes** | No | App Functionality | Supabase UUID that links ratings, baskets, blocks and terms consent to the account. |
| User Content → **Other User Content** | Yes | **Yes** | No | App Functionality | Ratings, review comments, reports, saved/synced basket, category suggestions, block list. Public reviews are shown without any identifier, but they are stored against the account, so "linked". |
| **Search History** | Yes | **No** | No | App Functionality | Search text and barcodes travel in request paths and stay in server access logs (journald 30 days, nginx 14 days) with the IP, never with the account (search/product calls send no token). |
| Location (Precise / Coarse) | **No** | — | — | — | The position stays on the phone; distances are computed on the device. The only derived data sent is a list of in-radius store IDs in the "nearby only" basket-compare body, processed in real time and not stored or logged — Apple's definition excludes real-time processing. |
| Photos or Videos | No | | | | Camera frames are decoded on the device; only the barcode digits are sent. |
| Contacts, Health & Fitness, Financial Info, Sensitive Info, Browsing History, Purchases, Messages | No | | | | |
| Usage Data, Diagnostics (crash / performance) | No | | | | No analytics, crash or performance SDK in the app. |
| Identifiers → Device ID | No | | | | No advertising ID, no device identifiers sent. |
| Other Data | No | | | | |

**Tracking:** No data is used to track. No ATT prompt. `NSPrivacyTracking` = false, no tracking domains.

Answer flow in App Store Connect (App Privacy → Get Started): "Yes, we collect data" → tick Email Address, User ID, Other User Content, Search History → for each: purposes = App Functionality only; linked = Yes for the first three, No for Search History; tracking = No for all.

---

## 3. Age rating (Apple's 2026 questionnaire)

App Store Connect → App Information → Age Rating → Edit. Answers:

| Section / question | Answer | Why |
|---|---|---|
| Parental controls (in-app) | No | |
| Age assurance (in-app) | No | |
| Unrestricted web access | No | No in-app browser; legal pages open in Safari / SFSafariViewController on our own domain only. |
| User-generated content | **Yes** | Product ratings and review comments, public and anonymous. Moderated: automatic blacklist hides a comment and alerts us; every review has report + block; blocked-users list in Settings; reports reviewed within 24 hours; terms acceptance required before posting. |
| Messaging and chat | No | Reviews are not messages between users. |
| Advertising | No | No ads. |
| Gambling / simulated gambling / contests | None | |
| Loot boxes | No | |
| Cartoon / realistic violence, prolonged violence, horror / fear themes | None | |
| Profanity or crude humour | None | Blacklist filters it from reviews. |
| Mature or suggestive themes, sexual content or nudity, graphic sexual content | None | |
| **Alcohol, tobacco or drug use or references** | **Infrequent / Mild** (recommended) | The catalogue lists beer, wine, spirits and cigarettes with their prices, like any supermarket price list. Answering "None" invites a metadata rejection if a reviewer searches for them. |
| Medical or treatment information, health / wellness topics | None | Nutrition facts and Health Ministry labels are product-label data, not medical advice. |
| Weapons | None | |
| Made for Kids | No | |

**Decision (Dude, SU11B-2): alcohol/tobacco "Infrequent" → 13+.** Google Play rated the same app PEGI 3 / Everyone; the difference is Apple's alcohol/tobacco question. App Store Connect computes the final rating from the answers — confirm it shows 13+ before saving.

---

## 4. Content Rights

**Status: CLOSED (SU11B-3).** Dude confirmed on 2 Nov 2026 that the GS1 service terms cover public price comparison (display of GS1 product data and images in the website and apps). **Answers: third-party content → Yes; necessary rights → Yes.**

App Store Connect → App Information → Content Rights: **"Does your app contain, show, or access third-party content?" → Yes.** Then: "Do you have all necessary rights to that third-party content…?"

| Content | Basis | Status |
|---|---|---|
| Chain prices, promotions, store lists | Published by the chains as public files under the Promotion of Competition in the Food Sector Law (חוק קידום התחרות בענף המזון, 2014), whose purpose is public price comparison. | OK. |
| Store coordinates | Google (stored under Dude's decision of 2026-10-08, licensing his) + legacy OpenStreetMap rows (ODbL, credited on the Help screen). | Dude's call (CLAUDE.md "Google data"). |
| GS1 Israel product data (names, brand, ingredients, nutrition, allergens, labels) and **product images** | Fetched with our GS1 Israel API account (`docs/gs1_integration.md`). | OK — Dude confirmed 2 Nov 2026 that the GS1 service terms cover public price comparison. |
| Product names / reviews by users | Our users, under the terms they accept. | OK. |

(Before SU11B-3 this row was UNCLEAR: the repo held no GS1 licence terms. Dude's confirmation of 2 Nov 2026 closes it; the basis is the GS1 service terms, kept outside the repo.)

---

## 5. Export compliance

`app.json` → `ios.config.usesNonExemptEncryption: false`, which writes `ITSAppUsesNonExemptEncryption = NO` into Info.plist, so App Store Connect does not ask per build.

If asked: **"Does your app use encryption?" → Yes, only exempt encryption** — i.e. "None of the algorithms mentioned above": the app uses only Apple's system HTTPS/TLS (`fetch` to api-super.xxl.co.il and Supabase) and the iOS Keychain (expo-secure-store). No custom or proprietary cryptography (no crypto library in `package.json`; grep of `src/` finds none). No French declaration needed (not distributed in France).

---

## 6. App Review information

**Sign-in required:** Yes (some features). Create the review account first:

1. Supabase → Authentication → Users → **Add user** → email `appreview@xxl.co.il`, a strong password, **Auto Confirm User** ticked.
2. Type that password **only** into App Store Connect → App Review Information → Password. Never into chat, docs or the repo.
3. The account must **NOT** be in `DELETE_PROTECTED_USER_IDS` (the reviewer may test deletion). If the reviewer deletes it, re-create it the same way before the next submission.
4. Seed it on the iPhone (TestFlight build): sign in, accept the terms, add 2 items to the basket, rate one product with a short comment.
5. Never delete `x@xxl.co.il` or `gplay@xxl.co.il`.

**Contact:** Elad Tzur, info@xxl.co.il, phone (Dude types it in ASC).

**Notes (English, paste into "Notes"):**
```
SUPER XXL compares supermarket prices across 14 Israeli grocery chains. Prices come from the public price files that chains must publish under Israel's Promotion of Competition in the Food Sector Law (2014); they are collected daily by our server. Product details (ingredients, nutrition, images) come from GS1 Israel's product catalogue. The app is in Hebrew (right-to-left).

The app works without an account: scanning, search, product prices and the basket comparison need no sign-in. An account is needed only to rate products and write reviews. Demo account: see the sign-in fields above.

Testing the barcode scanner without a physical product:
- Scan tab (first tab): allow the camera, then tap the "הזנת ברקוד ידנית" (enter barcode manually) button on the camera view and type a barcode, or
- Search tab (magnifier icon): type the barcode digits and press search; the product opens directly.
Sample barcodes in our catalogue: 7290004131074 (milk 3%), 7290011194246 (cottage cheese 5%), 7290003726615 (tofu), 7290009420517 (Coca-Cola).
If the camera permission is denied, the Scan tab explains why and offers to open Settings; the Search tab still finds products by barcode.

Location is optional and asked for only with an explanation first. Without it, the user picks a city in Settings. The position never leaves the device: distances to stores are computed on the phone.

User-generated content (Guideline 1.2):
- Terms: menu (☰ at the top) > "תנאי שימוש"; a required terms checkbox at sign-up and before a first review.
- Report and block: open any product > "ביקורות ודירוגים" tab > the "⋯" button on another user's review > "דיווח על התוכן" (report) or "חסימת המשתמש" (block). The blocked author's reviews disappear at once.
- Blocked users and unblock: Settings tab > "משתמשים חסומים".
- Reviews are filtered by a blacklist; reported content is reviewed within 24 hours and abusive users are banned.
- Contact: info@xxl.co.il (Help screen, terms, privacy).

Account deletion (Guideline 5.1.1(v)): Settings tab > "מחיקת חשבון" (shown when signed in) > enter password > confirm. Web alternative: https://super.xxl.co.il/account/delete

Privacy policy: https://super.xxl.co.il/privacy (also in the app: menu > "מדיניות פרטיות").
No in-app purchases, no ads, no tracking, no analytics SDKs. Sign-in is email + password only (no third-party login).
```
Labels quoted above were checked against `src/i18n/he.ts` at SU11B-1 (`scan.manualEntry`, `productDetail.tabReviews`, `ratings.actionReport` / `actionBlock`, `settings.blockedUsers` / `deleteAccount`, `drawer.terms` / `privacy`).

---

## 7. Screenshots

**Required (Apple spec as of 2026, iPhone-only app):** one set for **6.9"** (1320×2868, 1290×2796 or 1260×2736 portrait) **or**, if no 6.9" set is provided, **6.5"** (1242×2688 or 1284×2778 portrait). Smaller sizes are scaled from these. 1–10 screenshots per set, PNG or JPEG, no alpha. No iPad set (`supportsTablet: false`). Re-check the "iPhone 6.9" Display" box on the version page: App Store Connect states there whether 6.5" is accepted in its place.

**Plan:** the iPhone 12 captures 1170×2532 (19.5:9). 1242×2688 is the same aspect ratio (scale 1.0615 on both axes, 2532 × 1.0615 = 2687.8 → 2688), so a straight resize with no crop or padding gives a valid **6.5"** set. Upload it in the 6.5" slot and leave 6.9" empty. (Reaching 1290×2796 would need a 0.15% non-uniform stretch or a 4 px crop; not worth it.)

**Screens (5), in this order, light mode, Hebrew, signed in with the review account, Wi-Fi + full battery icons:**
1. **Product** — scan result / product-detail of milk 7290004131074, "קרוב אלי" list with distances.
2. **Search** — Search tab with "קוטג'" typed and the suggestions + results visible.
3. **Compare** — basket-compare (סל) with 4–5 items, totals per chain.
4. **Basket** — Basket tab with the items and quantities.
5. **Scanner** — Scan tab with the camera aimed at a real barcode (point it at any product at home).

**Capture on the iPhone 12 (TestFlight build):** side button + volume up. AirDrop or iCloud Photos the PNGs to the PC (or plug in the cable → Windows Photos import), into a folder such as `C:\xxl-archive\ios_screens\raw\`. Screenshots are not committed to the repo.

**Resize:** `scripts/ios/resize_screenshots.ps1` (this repo). It refuses anything that is not 1170×2532 (or 2532×1170), resizes with high-quality bicubic to 1242×2688, and writes PNGs without alpha.

[PC — PowerShell]
```powershell
powershell -ExecutionPolicy Bypass -File C:\scrp\scripts\ios\resize_screenshots.ps1 -InputDir C:\xxl-archive\ios_screens\raw -OutputDir C:\xxl-archive\ios_screens\6.5
```
Expected: one `OK  <name>.png 1170x2532 -> 1242x2688` line per file and `Done: N file(s)`. STOP if any line says `SKIP` (wrong size: a screenshot from another device or an edited image).

---

## 8. Pricing and availability

- Price: **Free** (Tier 0). No in-app purchases.
- Availability: **Israel only** (Pricing and Availability → Countries or Regions → deselect all → Israel).
- Pre-orders: No. Distribution: Public on the App Store.
- EU DSA: trader status already declared **non-trader**; the EU is not selected.

---

## 9. Website badge switch (after the app is LIVE — not before)

Apple's badge and logo may appear only once the app is available. Do these together, in one web deploy from the home PC:

1. Download Apple's official **Hebrew "Download on the App Store"** badge (black, SVG) from Apple's App Store marketing resources (developer.apple.com/app-store/marketing/guidelines → Badges). Save it **unaltered** as `web/public/badges/app-store-he.svg` and add its source URL + download date to `web/public/badges/SOURCE.txt`.
2. `web/src/config/apps.ts`: add `export const IOS_APP_ID = '6829450422';` and set `export const IOS_APP_URL: string | null = 'https://apps.apple.com/il/app/id6829450422';`. With that, `AppBadges.tsx` shows the badge instead of "בקרוב גם ל-iPhone", and `AppBanner.tsx` gives iPhone visitors a store link.
3. `web/src/utils/seoMeta.ts`: next to `google-play-app` (around lines 91, 122 and 189), add an `iosApp` field = `app-id=${IOS_APP_ID}` on the super host (null on the portal), set with `setMeta('name', 'apple-itunes-app', m.iosApp)` and removed when null, exactly like `playApp`. Update the header comment (line 25) that says there is no apple-itunes-app meta yet. Result on super.xxl.co.il: `<meta name="apple-itunes-app" content="app-id=6829450422">` (Safari's Smart App Banner).
4. `web/src/admin/AdminApp.tsx` line 50: add `meta[name="apple-itunes-app"]` to the selector list it removes, like `google-play-app`.
5. Build, check `grep -r "apple-itunes-app" web/dist` is empty (the meta is set at runtime) and the badge file is in `web/dist/badges/`, commit, push, then Dude deploys: `.\scripts\deploy_frontend.ps1` (home PC, MATCH expected).
6. CLAUDE.md: replace the "Apple App Store badge … only after the iOS app is live" bullet with "live since <date>".
