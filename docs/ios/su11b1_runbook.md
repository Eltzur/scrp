# SU11B-1 runbook — first iOS build, TestFlight, App Store listing, submission; Android build 9

Dude runs every step. CC prepared the config (mobile repo: SU11B-1 `85eb6a6`, SU11B-2 `c56e27f`, **SU11B-3 `65882ea`**) and the kit `docs/ios/su11b1_app_store_kit.md`. **Version 1.2.2** (SU11B-2); **iOS build 1.2.2 (2)**, Android versionCode 9 — both from the SU11B-3 commit `65882ea`.

**Build 1.2.2 (1) rejected (SU11B-3 record):** EAS build `80074645` (commit `c56e27f`) was uploaded and Apple rejected it in processing with **ITMS-90683** "Missing purpose string in Info.plist — NSMotionUsageDescription" (expo-location references `CMMotionActivityManager`; SU11B-1 had set `motionUsagePermission` false). SU11B-3 adds NSMotionUsageDescription plus NSMicrophoneUsageDescription, NSFaceIDUsageDescription and NSPhotoLibraryUsageDescription (each an honest Hebrew "the app never uses / never requests it" text). Build 1 stays in App Store Connect as invalid and is never used; B runs again and produces build 2.

**Decisions recorded (Dude, SU11B-2):** placeholder drawer rows hidden on all platforms; version 1.2.2; age rating: alcohol/tobacco "Infrequent" → **13+**; review account created at step D. **GS1 (SU11B-3): CLOSED** — Dude confirmed on 2 Nov 2026 that the GS1 service terms cover public price comparison; Content Rights: third-party content Yes, necessary rights Yes.
Rules: passwords and 2FA codes are typed only into the EAS prompt or the Apple / Google page, never into chat or files. Throwaway users only for deletion tests; never delete `x@xxl.co.il` or `gplay@xxl.co.il`. Each `eas build` run burns a build number / versionCode: run each build once.

Order: A (checks) → B (iOS build) → **J step 1 (Android build, right after B, same commit)** → C (submit to App Store Connect) → D (TestFlight test) → E (listing) → F (screenshots) → **G (HARD STOP: name "Elad Tzur")** → H (submit for review) → I (release + website). The Android upload to Play (J step 2 on) can follow D's checks.

**B and J must be built from the same commit (the SU11B-3 commit `65882ea` or a later docs-only state of `main`): iOS build 2 first, Android build 9 right after. Do not pull or change anything between the two builds.**

---

## A. Pre-flight

[PC — PowerShell]
```powershell
cd C:\scrp\xxl-super-mobile
git pull origin main
git log --oneline -5
git status --short
npx eas-cli@latest --version
npx eas-cli@latest whoami
```
Expected: the top commit is the SU11B-3 commit `65882ea` (fix(ios): SU11B-3 …); `git status` shows only Dude's untracked drafts (`assets/images/icon.jpg`, `splash-icon gplay.png`, `splash-icon2.png`, `crpxxl-super-mobile`); eas-cli ≥ 21.7.1; `whoami` prints the Expo account that owns `xxlcoils-team`.
STOP if `whoami` says "Not logged in": run `npx eas-cli@latest login` (Expo account, not Apple) and repeat. STOP if there are modified tracked files.

Typecheck (Dude's standard bar, 6–8 minutes):

[PC — PowerShell]
```powershell
cd C:\scrp\xxl-super-mobile
node node_modules/typescript/bin/tsc --noEmit; "exit $LASTEXITCODE"
```
Expected: `exit 2` with only the 5 known `src/tw` errors. STOP on any other error.

Config check (the production Info.plist values):

[PC — PowerShell]
```powershell
cd C:\scrp\xxl-super-mobile
npx expo config --type introspect --json | Select-String -Pattern 'ITSAppUsesNonExemptEncryption|NSAllowsArbitraryLoads|NSPrivacyTracking"|NSMotionUsageDescription|NSMicrophoneUsageDescription|NSFaceIDUsageDescription|NSPhotoLibraryUsageDescription'
```
Expected: `ITSAppUsesNonExemptEncryption":false`, `NSAllowsArbitraryLoads":false`, `NSPrivacyTracking":false`, and **all four** purpose strings present, each a Hebrew text starting "SUPER XXL אינה משתמשת ב…": `NSMotionUsageDescription`, `NSMicrophoneUsageDescription`, `NSFaceIDUsageDescription`, `NSPhotoLibraryUsageDescription` (SU11B-3; required because autolinked native code references these APIs — ITMS-90683 rejected build 1 without the motion key). STOP if any of the four is missing. (The introspect output still lists `NSLocalNetworkUsageDescription` / `_expo._tcp`; expo-dev-launcher's build phase deletes them from Release builds — checked in D.)

---

## B. iOS production build (EAS cloud, no Mac)

SDK 57 → the default EAS image has Xcode 26 / iOS 26 SDK, which Apple requires since 28 Apr 2026.

[PC — PowerShell]
```powershell
cd C:\scrp\xxl-super-mobile
npx eas-cli@latest build -p ios --profile production
```
What EAS asks and what to answer:

| Prompt | Answer |
|---|---|
| "iOS app only uses standard/exempt encryption?" (only if asked) | **Yes** (already set in app.json) |
| No remote build number yet / "initialize from local?" (if asked) | **Yes** — it starts at 1 |
| "Do you want to log in to your Apple account?" | **Yes** |
| Apple ID | Dude's Apple ID email (typed into the prompt only) |
| Password | typed into the prompt only |
| 2FA code | from the iPhone |
| Select team (if more than one) | Team **V46QVK4YSA** (Individual; may still be labelled "Lead Tour" — fine for building) |
| Bundle identifier `il.co.xxl.supermarket` exists / sync capabilities | **Yes** |
| "Generate a new Apple Distribution Certificate?" | **Yes** (stored on EAS servers) |
| "Generate a new Apple Provisioning Profile?" | **Yes** |
| "Would you like to set up Push Notifications?" (if asked) | **No** — the app has no push |

Expected: upload of the project, then a build URL; the build runs 15–30 min and ends with **Build finished** and an `.ipa` link. The build log shows `Version 1.2.2`, **`Build number 2`** (build 1 was the rejected SU11B-2 upload).
STOP if: the build fails (send the build page's error section to the chat); the version is not 1.2.2 or the build number is not 2; EAS asks for a password anywhere other than its own prompt.

---

## C. Upload to App Store Connect

**Simplest for an Individual account: let `eas submit` create an App Store Connect API key for you** (it logs in with your Apple ID once and stores the key on EAS; nothing in the repo). `eas.json` already holds `ascAppId 6829450422` and `appleTeamId V46QVK4YSA`.

[PC — PowerShell]
```powershell
cd C:\scrp\xxl-super-mobile
npx eas-cli@latest submit -p ios --profile production --latest
```
| Prompt | Answer |
|---|---|
| Log in to Apple account | **Yes** → Apple ID, password, 2FA (prompt only) |
| "Generate a new App Store Connect API Key?" | **Yes** |

Expected: "Submitted your app to Apple App Store Connect!" and a link; 5–30 min later Apple mails "The following build has completed processing".
STOP if it fails creating the API key (some Individual accounts cannot): use the fallback below.

Fallback — app-specific password:
[Browser]
appleid.apple.com → Sign-In and Security → App-Specific Passwords → "+" → label `eas-submit` → copy the generated password (keep it in the clipboard only).

[PC — PowerShell]
```powershell
cd C:\scrp\xxl-super-mobile
$env:EXPO_APPLE_APP_SPECIFIC_PASSWORD = Read-Host "App-specific password"
npx eas-cli@latest submit -p ios --profile production --latest
Remove-Item Env:EXPO_APPLE_APP_SPECIFIC_PASSWORD
```
Expected: as above. STOP on "Missing compliance", "Invalid binary" or any ITMS-9xxxx mail from Apple (build 1 got ITMS-90683): forward the text (no secrets) to the chat.

---

## D. TestFlight internal test on the iPhone 12

[Browser]
App Store Connect → Apps → SUPER XXL → TestFlight → the build 1.2.2 (2) shows "Ready to Submit"/"Testing" (no "Missing Compliance", because `usesNonExemptEncryption` is false). Internal Testing → "+" group `XXL` → add yourself → the build.

[iPhone]
Install **TestFlight** from the App Store → open the invitation mail → Install SUPER XXL. Then work through this checklist (tick in the chat when done):

1. **First launch:** RTL layout; the location primer appears first, then the iOS dialog with the Hebrew text; **deny** → choose a city in Settings, prices work. Later Settings → allow → "קרוב אלי" lists branches with km. Also try "Precise: Off".
2. **Scanner:** Scan tab → camera dialog shows the Hebrew text → **Don't Allow** → explanation + "open Settings" button; the Search tab still opens a product by barcode `7290004131074`. Allow in iOS Settings → scan a real product (EAN-13) → product page. "הזנת ברקוד ידנית" with `7290011194246`.
3. **Search:** type "קוט" → suggestions; pick a product → product page; pick a term → results.
4. **Product:** the three tabs; "קרוב אלי" / "הכל" sort toggle; category line and "הצעת עדכון קטגוריה" (signed in / signed out).
5. **Basket + compare:** add 4 items, compare, "nearby only" on/off.
6. **Account:** sign-up with a throwaway email → the terms checkbox is required; confirmation mail; sign-in; sign-out; **password reset** with the 6-digit code.
7. **UGC:** with a second throwaway account, rate a product with a comment; with the first, "⋯" on that review → report (reason prompt) → block → the review disappears; Settings → משתמשים חסומים → unblock.
8. **Account deletion — throwaway user only:** Settings → מחיקת חשבון → wrong password (error) → right password → confirm → signed out; sign-in fails afterwards.
9. **Drawer (☰):** no "מועדפים", "רשימות" or "המלצות" (hidden on all platforms, SU11B-2); terms, privacy, help, share work; the drawer closes by tapping outside.
10. **Back navigation:** on every pushed screen (product, compare, terms, privacy, help, sign-in/up, forgot password, delete account, blocked users, scan history, my ratings) both the header back button and the **edge swipe** go back (in RTL the swipe starts at the right edge). Modals: city picker (סגירה), manual barcode (ביטול), category sheet (✕ or swipe down), consent (ביטול), permission primer (לא עכשיו).
11. **Dark mode** (iOS Control Center) on scan, search, product, terms; **VoiceOver** spot check: tab bar, the ⋯ button reads "פעולות על הביקורת", the consent checkbox reads as a checkbox.
12. **Terms screen:** lines starting with Latin ("XXL…", "SerpApi…") stay right-aligned (SU11A-46).
13. Settings shows version 1.2.2 (build 2). No microphone, Face ID, photo-library or motion ("Motion & Fitness") dialog appears at any point in the checklist — the strings exist only because of built-in components.
14. **Local-network check:** the app must never ask "find devices on your local network". Also, if App Store Connect offers an Info.plist view for the build (TestFlight → build → Build Metadata), it has no `NSLocalNetworkUsageDescription` / `NSBonjourServices`. If there is no such view, the on-device check (no "local network" dialog during the whole checklist) is sufficient.
15. **Images (ATS: `NSAllowsArbitraryLoads` is false):** product images load on the product page (milk `7290004131074`, cottage `7290011194246`) and in the search results list. **Any blank image where the Android app shows one → STOP** and report the product barcode.

STOP on any crash, a missing Hebrew permission text, a screen without a way back, a blank product image (15), or item 14 failing; report it to the chat before going on.

**Create the review account now** (kit §6): Supabase → Authentication → Users → Add user → `appreview@xxl.co.il`, Auto Confirm; not in `DELETE_PROTECTED_USER_IDS`; seed it on the iPhone.

---

## E. Fill App Store Connect from the kit

[Browser]
App Store Connect → SUPER XXL:
1. **App Information:** name, subtitle, categories Shopping / Food & Drink, Content Rights (kit §4: third-party content **Yes**, necessary rights **Yes** — GS1 confirmed by Dude 2 Nov 2026), Age Rating (kit §3: alcohol/tobacco "Infrequent" → expect **13+**, Dude's decision).
2. **App Privacy:** kit §2; privacy policy URL.
3. **Pricing and Availability:** Free; Israel only (kit §8).
4. **Version page:** it must read **1.2.2** — if App Store Connect created it as 1.0, edit the version number to 1.2.2 **before** selecting the build (a build only attaches to a version with the same number). Then: promotional text, description, keywords, support / marketing URLs, copyright (kit §1); **App Review Information:** contact first name, last name, email (info@xxl.co.il) **and a phone number with country code (+972 …)**, sign-in required = Yes with `appreview@xxl.co.il` and its password (typed only here), notes (kit §6); build → select **1.2.2 (2)** (never the rejected build 1). Release: "Manually release this version".
Expected: every section saved without red marks except screenshots (next step).

---

## F. Screenshots

[iPhone]
Capture the five screens in kit §7 (side button + volume up), light mode, signed in with the review account.

[PC — PowerShell]
```powershell
powershell -ExecutionPolicy Bypass -File C:\scrp\scripts\ios\resize_screenshots.ps1 -InputDir C:\xxl-archive\ios_screens\raw -OutputDir C:\xxl-archive\ios_screens\6.5
```
Expected: `OK … 1170x2532 -> 1242x2688` for each and `Done: 5 file(s)`. STOP on any `SKIP`.

[Browser]
Version page → Previews and Screenshots → iPhone → **6.5" Display** → drag the five files in order. Leave 6.9" empty if the page accepts 6.5" alone. STOP if App Store Connect insists on a 6.9" set: tell the chat (the fallback is a 1290×2796 export with a 4 px crop).

---

## G. HARD STOP before any submission

**Do not press "Add for Review" / "Submit for Review" until G1 passes.** G1 is the only remaining hard stop (G2 closed in SU11B-3).

### G1 — the seller / team name reads "Elad Tzur" (not "Lead Tour")

Check both:

[Browser]
1. developer.apple.com/account → **Membership details** → "Entity name" / "Team name".
2. App Store Connect → top-right account menu (team switcher) shows the team name; and the App Store Connect app page → App Information → the seller line in the product-page preview, if shown.

If either still says "Lead Tour": stop here; building, TestFlight and the listing stay ready. Follow up with Apple Developer Support on the open case.

### G2 — GS1 public-display rights: CLOSED (2 Nov 2026)

Dude confirmed on 2 Nov 2026 that the GS1 service terms cover public price comparison. Content Rights (kit §4): third-party content **Yes**, necessary rights **Yes**. No action left here.

---

## H. Submit for review (only after G1 passes)

[Browser]
Version page → **Add for Review** → **Submit to App Review**. Expected: status "Waiting for Review", then "In Review" (typically 24–48 h). If rejected: copy the Resolution Center text (no credentials) to the chat; do not reply to Apple before the chat has reviewed it.

---

## I. After approval

1. [Browser] Status "Pending Developer Release" → **Release This Version**. Check the public page `https://apps.apple.com/il/app/id6829450422` loads (can take a few hours).
2. Website badge switch: kit §9 — a CC prompt prepares it (web code + Apple's badge file), then Dude deploys **from the home PC**:

[PC — PowerShell]
```powershell
cd C:\scrp
git pull origin main
.\scripts\deploy_frontend.ps1
```
Expected: the deploy guard prints MATCH; super.xxl.co.il shows Apple's badge next to the Play badge; Safari on the iPhone shows the Smart App Banner. STOP on MISMATCH.

3. Docs: CLAUDE.md "Apple App Store badge … only after live" → "live since <date>"; handoff entries.

---

## J. Android build 9 (same commit as the iOS build)

Step 1 runs **right after B**, from the same commit, before any `git pull`. Run it **once** — every run burns a versionCode.

[PC — PowerShell]
```powershell
cd C:\scrp\xxl-super-mobile
git log --oneline -1
npx eas-cli@latest build -p android --profile production
```
Expected: `git log` shows the same commit as the iOS build 2 in B (SU11B-3 `65882ea` or a later docs-only state); the build log shows `versionName 1.2.2`, **`versionCode 9`**; the result is an `.aab` (app-bundle). STOP if the versionCode is not 9 (tell the chat before uploading).

[Browser]
1. Download the `.aab` from the EAS build page.
2. Play Console → SUPER XXL → (optional first) Testing → Internal testing → Create release → upload → roll out to testers; check on a phone (terms bidi, search suggestions, category suggestion button). Promote to Production, or:
3. Production → Create new release → add from library / upload the AAB → release notes (Hebrew, e.g. "גרסה 1.2.2: הצעות חיפוש תוך כדי הקלדה, הצעת קטגוריה למוצר ותיקוני תצוגה") → Next → countries unchanged (Israel) → Start rollout to Production (100%).
4. App bundle explorer → Permissions: INTERNET, CAMERA, ACCESS_COARSE_LOCATION, ACCESS_FINE_LOCATION, VIBRATE, ACCESS_NETWORK_STATE (+ the signature-level DYNAMIC_RECEIVER permission). STOP if READ/WRITE_EXTERNAL_STORAGE or SYSTEM_ALERT_WINDOW appear.

