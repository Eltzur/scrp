# SU11B-1 runbook — first iOS build, TestFlight, App Store listing, submission; Android build 9

Dude runs every step. CC prepared the config (mobile repo: SU11B-1 `85eb6a6`, SU11B-2 `c56e27f`, **SU11B-3 `65882ea`**) and the kit `docs/ios/su11b1_app_store_kit.md`. **Version 1.2.2** (SU11B-2); **iOS build 1.2.2 (2)**, Android versionCode 9 — both from the SU11B-3 commit `65882ea`.

**Release state (SU11B-7, 7 Nov 2026):**
- **iOS 1.2.2 (2)** (EAS `4eaab3fc`, mobile `65882ea`): **LIVE on the Israel App Store** (https://apps.apple.com/il/app/super-xxl/id6829450422). Dude released it with the seller still reading "Lead Tour" (Apple Support case 103015749110 open; the listing updates itself when Apple fixes it). The listing shows the languages "EN + 1 More"; 1.2.3 declares Hebrew only (SU11B-7). Submitted 4 Nov 20:58 (submission `871055cd-5aab-48e7-8f41-b3a4af70e0d0`).
- **iOS 1.2.2 (1)** (EAS `80074645`, `c56e27f`): failed processing with ITMS-90683 (below; fixed in SU11B-3).
- **Android 9 (1.2.2)** (EAS `0992b1c3`, `65882ea`): **published to Play Production 4 Nov** (submission 3), full rollout, Israel, managed publishing off. Closed testing – Alpha: draft 8 (1.2.1) discarded, track inactive. Play release notes use the language tag **`iw-IL`** (`he-IL` is rejected).
- **Play trader status:** account declared **TRADER** (XXL Enterprises, D-U-N-S, address, phone and email shown publicly under "App support"); app-level declaration published 5 Nov (submission 4), ToS URL https://xxl.co.il/disclaimer. **Apple DSA stays "non-trader / not distributing in the EU"** (iOS is Israel only); align Apple to trader before any EU distribution.
- **Lesson:** a Play App content / policy change submitted while a release is in review restarts that review. Submit such changes only when nothing is in review.
- **Seller-name RELEASE gate (G1): CLOSED.** Dude released 1.2.2 with the name still "Lead Tour". Apple Support case **103015749110** (opened 1 Nov, nudged 3 Nov) is still open; no action is needed when Apple fixes the name.
- **Release option (Dude, 7 Nov 2026): from 1.2.3 on, every App Store version uses "Automatically release this version".** Approval publishes at once, so the TestFlight retest (K step 4) is the last gate: submit for review only after it has passed in full.
- **Next: 1.2.3** from the SU11B-7 mobile commit `f1c6ce6`: section K.

**Build 1.2.2 (1) rejected (SU11B-3 record):** EAS build `80074645` (commit `c56e27f`) was uploaded and Apple rejected it in processing with **ITMS-90683** "Missing purpose string in Info.plist — NSMotionUsageDescription" (expo-location references `CMMotionActivityManager`; SU11B-1 had set `motionUsagePermission` false). SU11B-3 adds NSMotionUsageDescription plus NSMicrophoneUsageDescription, NSFaceIDUsageDescription and NSPhotoLibraryUsageDescription (each an honest Hebrew "the app never uses / never requests it" text). Build 1 stays in App Store Connect as invalid and is never used; B runs again and produces build 2.

**Decisions recorded (Dude, SU11B-2):** placeholder drawer rows hidden on all platforms; version 1.2.2; age rating: alcohol/tobacco "Infrequent" → **13+**; review account created at step D. **GS1 (SU11B-3): CLOSED** — Dude confirmed on 2 Nov 2026 that the GS1 service terms cover public price comparison; Content Rights: third-party content Yes, necessary rights Yes.
Rules: passwords and 2FA codes are typed only into the EAS prompt or the Apple / Google page, never into chat or files. Throwaway users only for deletion tests; never delete `x@xxl.co.il` or `gplay@xxl.co.il`. Each `eas build` run burns a build number / versionCode: run each build once.

Order: A (checks) → B (iOS build) → **J step 1 (Android build, right after B, same commit)** → C (submit to App Store Connect) → D (TestFlight test) → E (listing) → F (screenshots) → G (history: both gates closed) → H (submit for review: **done for 1.2.2, 4 Nov**) → I (after approval: 1.2.2 released by Dude; automatic from 1.2.3; website badge done) → K (1.2.3 update). The Android upload to Play (J step 2 on) can follow D's checks.

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

## G. Gates before release — history, both CLOSED

### G1 — the seller / team name: CLOSED (7 Nov 2026)

The seller name was mistyped as "Lead Tour" (should be "Elad Tzur"). On 4 Nov Dude moved this gate from Submit to RELEASE, and 1.2.2 was submitted with "Manually release this version". Dude then released 1.2.2 with "Lead Tour" still showing. Apple Support case 103015749110 (opened 1 Nov, nudged 3 Nov) stays open; the store listing updates itself when Apple fixes the name, and **no action is needed then**. The name no longer blocks any version.

### G2 — GS1 public-display rights: CLOSED (2 Nov 2026)

Dude confirmed on 2 Nov 2026 that the GS1 service terms cover public price comparison. Content Rights (kit §4): third-party content **Yes**, necessary rights **Yes**. No action left here.

---

## H. Submit for review — DONE for 1.2.2 (4 Nov 20:58, submission 871055cd-5aab-48e7-8f41-b3a4af70e0d0)

For later versions (section K):

[Browser]
Version page → **Add for Review** → **Submit to App Review**. Expected: status "Waiting for Review", then "In Review" (typically 24–48 h). If rejected: copy the Resolution Center text (no credentials) to the chat; do not reply to Apple before the chat has reviewed it.

---

## I. After approval

- **1.2.2 (2):** released by Dude (manual release; G1 closed). The public page is https://apps.apple.com/il/app/super-xxl/id6829450422.
- **From 1.2.3 on, releases are automatic** ("Automatically release this version", Dude, 7 Nov 2026): Apple's approval publishes the version, and nothing is pressed here. The checks before submitting are in K step 4.
- **Website badge:** done in SU11A-70 (Apple's official badge, linked to the store page, deployed). Nothing left to do.
- After each release, check the public page (it can take a few hours to show the new version).

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
3. Production → Create new release → add from library / upload the AAB → release notes in `<iw-IL>` (Hebrew; `he-IL` is rejected), e.g. "גרסה 1.2.2: הצעות חיפוש תוך כדי הקלדה, הצעת קטגוריה למוצר ותיקוני תצוגה") → Next → countries unchanged (Israel) → Start rollout to Production (100%).
4. App bundle explorer → Permissions: INTERNET, CAMERA, ACCESS_COARSE_LOCATION, ACCESS_FINE_LOCATION, VIBRATE, ACCESS_NETWORK_STATE (+ the signature-level DYNAMIC_RECEIVER permission). STOP if READ/WRITE_EXTERNAL_STORAGE or SYSTEM_ALERT_WINDOW appear.

---

## K. 1.2.3 update (SU11B-5 `130b610`, SU11B-6 `a3988d1`, SU11B-7 `f1c6ce6`)

**Build both stores from the SU11B-7 mobile commit `f1c6ce6`** (not `a3988d1`: that commit lacks the Hebrew-only localization and the text-field borders). iOS first, Android right after, no pull in between. One version in review at a time. Each run burns a build number: run each once. Expected numbers: iOS **1.2.3 (3)**, Android versionCode **10**. **Release: automatic** (Dude, 7 Nov 2026), so step 4 is the last gate before the public release.

What changed in 1.2.3:
- add-to-basket on the product page (shared header, every tab) and on every search row (compact icon button), and a filled, more visible basket button;
- account-deletion timeout recovery (SU11A-63 L1, SU11B-6) and reserved-basket recovery (L2);
- Android `USE_BIOMETRIC` / `USE_FINGERPRINT` removed from the manifest;
- **SU11B-7:** iOS declares **Hebrew only** (`CFBundleLocalizations` [he]); every text field has a visible border (≥ 3:1) and a 2 px emerald border while focused.

### K1. Pre-flight

Run A first, expecting the top commit `f1c6ce6` (fix(ios): SU11B-7 …), tsc and A3's four purpose strings. Then the localization check:

[PC — PowerShell]
```powershell
cd C:\scrp\xxl-super-mobile
$env:NODE_ENV='production'; $env:EAS_BUILD_PROFILE='production'
npx expo config --type introspect --json | Select-String -Pattern 'CFBundleLocalizations[^\]]*\]|CFBundleDevelopmentRegion":"[a-z]*"' -AllMatches | ForEach-Object { $_.Matches.Value } | Sort-Object -Unique
```
Expected, exactly two lines:
```
CFBundleDevelopmentRegion":"he"
CFBundleLocalizations":["he"]
```
STOP if `"en"` appears or a line is missing.

### K2. Builds (iOS, then Android at once)

[PC — PowerShell]
```powershell
cd C:\scrp\xxl-super-mobile
git log --oneline -1
npx eas-cli@latest build -p ios --profile production
```
Expected: `git log` shows `f1c6ce6`; the build log shows `Version 1.2.3` and build number **3**; the build finishes with an `.ipa`. STOP on any other version or build number.

[PC — PowerShell]
```powershell
cd C:\scrp\xxl-super-mobile
git log --oneline -1
npx eas-cli@latest build -p android --profile production
```
Expected: the same commit; `versionName 1.2.3`, **versionCode 10**; an `.aab`. STOP on any other number.

### K3. iOS upload

[PC — PowerShell]
```powershell
cd C:\scrp\xxl-super-mobile
npx eas-cli@latest submit -p ios --profile production --latest
```
Expected: as in C, the upload succeeds and App Store Connect → TestFlight lists 1.2.3 (3) "Processing", then ready. STOP on any ITMS mail from Apple.

### K3a. IPA check on Windows (no Mac)

[Browser]
EAS build page of the iOS 1.2.3 (3) build → **Download** the `.ipa`. Save it as `%USERPROFILE%\Downloads\superxxl-1.2.3-3.ipa`.

Expected: one `.ipa` file. STOP if the download is anything else.

[PC — PowerShell]
```powershell
cd $env:USERPROFILE\Downloads
Copy-Item .\superxxl-1.2.3-3.ipa .\superxxl-1.2.3-3.zip -Force
Expand-Archive .\superxxl-1.2.3-3.zip -DestinationPath .\superxxl-1.2.3-3 -Force
$app = (Get-ChildItem .\superxxl-1.2.3-3\Payload -Directory -Filter *.app).FullName
"lproj in the main bundle:"; Get-ChildItem $app -Directory -Filter *.lproj | ForEach-Object Name
python -c "import plistlib,sys; p=plistlib.load(open(sys.argv[1],'rb')); [print(k, '=', p.get(k)) for k in ('CFBundleShortVersionString','CFBundleVersion','CFBundleDevelopmentRegion','CFBundleLocalizations')]; print('local network keys:', [k for k in ('NSLocalNetworkUsageDescription','NSBonjourServices') if k in p])" "$app\Info.plist"
```
The Info.plist inside an IPA is a **binary** plist; Python's `plistlib` reads it. If `python` is not found, type `py` instead.

Expected:
```
lproj in the main bundle:
he.lproj                      (or nothing; Base.lproj is also allowed)
CFBundleShortVersionString = 1.2.3
CFBundleVersion = 3
CFBundleDevelopmentRegion = he
CFBundleLocalizations = ['he']
local network keys: []
```
- The `.lproj` list is the top level of the `.app` only. The many `*.lproj` folders inside `*.bundle` folders (for example React Native's `RCTI18nStrings.bundle`) belong to libraries and are expected; they are not listed.
- `local network keys: []` is the D14 check (expo-dev-launcher strips them from Release builds).

**STOP if:**
- `en.lproj` or any other language's `.lproj` is listed;
- `CFBundleLocalizations` contains `en`;
- a local network key is listed;
- the version or build number differs.

Do not submit for review; paste the output to the chat. Afterwards delete the `.zip` and the folder; the `.ipa` may stay.

### K4. TestFlight / device retest — the last gate before the public release

[iPhone] the iPhone 12, TestFlight build 1.2.3 (3). On an Android phone, the Play internal-testing build of versionCode 10: items 1–11 and 13 (the borders are on Android too).

1. Scan result: add to basket, button turns to "בסל" (outlined + check), tap again removes.
2. Product page: the button sits under the category line on **each** tab (מחירים / מידע / ביקורות); state matches the basket.
3. Search rows: tapping the icon button toggles the basket and does **not** open the product; tapping the name area opens the product (prices tab).
4. Basket count and limit: signed out, add a 26th item from each of the three places → the 25-item message (with "להרשמה") appears each time; signed in, 150 limit message. Bumping an item already in the basket is allowed.
5. Compare from the basket still works.
6. **Account deletion, throwaway user only:** normal deletion; then a second throwaway user: tap "מחיקה לצמיתות" and switch **airplane mode on right after the tap** → an error (no connection) → airplane off → enter the password again and delete → the confirmation "החשבון נמחק" with the note "החיבור נקטע במהלך המחיקה…", signed out. (If the first request never left the phone, the second attempt simply deletes normally; both are correct.) Never with x@xxl.co.il, gplay@xxl.co.il or appreview@xxl.co.il.
   **SU11B-6 recovery checks** (a third throwaway user; first make a deletion time out as above, so the app holds an unanswered attempt):
   - after a deletion timeout, wrong password while offline (airplane mode on) → the offline message, still signed in;
   - wrong password online while the account still exists → "wrong password", still signed in;
   - the account still exists in Supabase after both.
7. **Basket sync:** signed in on the phone with items; on super.xxl.co.il → my baskets → delete `__xxl_mobile_basket__`; back on the phone add an item → the website shows the basket again with all phone items.
8. VoiceOver / TalkBack: the button reads "הוסף לסל: <product>" / "הסר מהסל: <product>" and "selected" when in the basket; the search row reads its name separately from its button.
9. Dark mode on scan, product, search: the filled button and the outlined "בסל" state are clearly visible.
10. RTL on the basket button: the icon is on the right of the text; on search rows the button is at the left end of the row, after the chevron.
11. **Text-field borders (SU11B-7), in light AND dark mode:** each of these fields shows a clearly visible grey border against the page:
    - the search box on the Search tab;
    - "הזנת ברקוד ידנית" (Scan tab);
    - the city picker's search (Settings → עיר);
    - the category sheet's search and comment ("הצעת עדכון קטגוריה");
    - the rating comment;
    - the sign-in / sign-up / password-reset fields.

    Tapping into a field turns its border **emerald and thicker**; leaving it turns it back. The text and caret do not jump noticeably. The Settings version row still reads "1.2.3 (3)" exactly as before.
12. **English iPhone:** Settings → General → Language & Region → iPhone Language → **English** (the phone redraws its UI). Open SUPER XXL:
    - every app text stays **Hebrew**, and the layout stays **right-to-left**;
    - note which system texts appear in Hebrew. Expected Hebrew: the buttons of the location / camera dialogs (not "Allow While Using App" / "Don't Allow"), the text-field menu (העתק / הדבק, not Copy / Paste), the share sheet;
    - Settings → SUPER XXL shows **no** "Language" choice.

    Switch the phone back to Hebrew afterwards.
13. **RTL unchanged:** Hebrew fields stay right-aligned, while the barcode and the email / password fields stay left-to-right. The search icon is on the right of the search box, the drawer opens from the right, and the tab order is as in 1.2.2.

**STOP if** any item fails: a crash, a field without a visible border or focus state, English app text or English system buttons inside the app (12), or a left-to-right layout. **Do not go on to K5**: with automatic release, an approved version goes public at once.

### K5. App Store Connect: version 1.2.3, automatic release, submit

[Browser]
App Store Connect → SUPER XXL → version page "+" → new version **1.2.3** → "What's New" (Hebrew), paste:
```
גרסה 1.2.3: הוספה לסל ישירות מעמוד המוצר ומתוצאות החיפוש, כפתור סל בולט יותר, ושיפורי אמינות במחיקת חשבון ובסנכרון הסל.
```
Then:
1. Build → select **1.2.3 (3)**.
2. **Screenshots retaken on 1.2.3**, showing the new button (product page and search rows). Use the same five screens as kit §7, in the slot "iPhone with Dynamic Island (medium display)". Raw files go to `C:\xxl-archive\ios_screens\1.2.3\raw` (not the repo).
3. App Privacy and age rating **unchanged**. 1.2.3 collects no new data and shows no ממומן content (checked in SU11B-7 against the diff since `65882ea`), so Advertising stays No.
4. "App Store Version Release" → **"Automatically release this version"** (Dude, 7 Nov 2026).
5. **Submit only after K4 has passed in full**: approval publishes the version at once. Then Add for Review → Submit to App Review.

Expected: status "Waiting for Review", then "In Review", then "Ready for Distribution" (published automatically).

**STOP if:**
- the build picker does not offer 1.2.3 (3);
- the release option is not "Automatically release this version";
- any K4 item is still open.

If rejected, follow H (Resolution Center text to the chat).

**After the release** (can take a few hours):

[Browser]
https://apps.apple.com/il/app/super-xxl/id6829450422

Expected: version 1.2.3, and under "Languages" **Hebrew** only (no longer "EN + 1 More").

STOP and tell the chat if it still shows English the next day, with a screenshot of the Languages line. Do not change anything in App Store Connect.

### K6. Play: 1.2.3 (versionCode 10)

[Browser]
Play Console → SUPER XXL → Production → Create new release → upload the 1.2.3 AAB → release notes, paste (the language tag is `iw-IL`; `he-IL` is rejected):
```
<iw-IL>
גרסה 1.2.3: הוספה לסל ישירות מעמוד המוצר ומתוצאות החיפוש, כפתור סל בולט יותר, ושיפורי אמינות במחיקת חשבון ובסנכרון הסל.
</iw-IL>
```
Then App bundle explorer → Permissions.

Expected: as in J step 4, and **no `USE_BIOMETRIC` / `USE_FINGERPRINT`**. Then Start rollout to Production.

**STOP if** either biometric permission is listed, or READ / WRITE_EXTERNAL_STORAGE or SYSTEM_ALERT_WINDOW appears. Do not submit App content changes while this is in review.
