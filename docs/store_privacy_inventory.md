# Store privacy inventory — SUPER XXL app + backend (SU11A-38)

Session SU11A-38, 2026-10-15. READ-ONLY investigation; no code, config, DB or production changed.
(SU11A-37 is reserved for popularity counters, so this session uses SU11A-38.)

Code read at: scrp `02da17c` (local; the server is at `dfd93ed`, no API change in between that touches data), xxl-super-mobile `b20ae38`.
Server facts were read over SSH with read-only commands (`systemctl cat`, `list-timers`, `grep` of nginx config, `journalctl` counts with IPs masked). Nothing printed from `.env`.

Paths: `m/` = `C:\scrp\xxl-super-mobile\`, everything else is relative to `C:\scrp\`.

---

## Key findings (short)

1. **Sign-in = email + password only**, via Supabase (`m/src/lib/auth-context.tsx:126-146`, web `web/src/components/AuthContext.tsx:55`). No Google, Apple, magic link or OTP code anywhere (`m/src/lib/auth-context.tsx:11-12`, `m/src/lib/supabase.ts:100-102`). Supabase stores email + password hash; our DB stores user id + email only (`api/auth.py:122-126`). `users.display_name` exists but nothing writes it.
2. **No third-party SDKs that send data from the phone**: no analytics, crash reporting, ads/advertising ID, push notifications, maps SDK, expo-updates or Expo Insights (`m/package.json:5-43`; `node_modules` has none of them). The app talks to only two hosts: `api-super.xxl.co.il` (ours) and the Supabase project (auth).
3. **Device location never leaves the phone.** The phone downloads all store coordinates (`GET /stores/coordinates`, no parameters, `m/src/lib/store-coords.ts:39`) and computes distance itself (`m/src/lib/geo.ts:33-73`, `m/src/lib/nearby-context.tsx:105-134`). Coordinates are not even saved on the phone (only the mode "gps/manual", the city name and the radius). The one location-derived thing sent: with "nearby only" basket compare, a list of in-range **store IDs** goes in the POST body (`m/src/api/client.ts:253-279`), which is not logged or stored (`api/routers/basket.py:28-42`).
4. **Camera:** barcode decoded on the device by expo-camera; only the digits go to the server as `GET /product/{barcode}` (`m/src/app/(tabs)/index.tsx:219-229`, `m/src/api/client.ts:61-76`). No `takePictureAsync`, no image upload anywhere.
5. **Per-user server data:** `users` (id, email, tier), `saved_baskets`, `favorites` (web only; mobile screen is a placeholder), `ratings` (+ public comment), `rating_reports` (+ reason), `flights.*` (shared account), `deleted_accounts` (id only, 7 days). All removed on account deletion except reports the user filed (kept, reporter id set NULL) — `api/routers/account.py:3-15, 42-46`.
6. **Logs:** journald (gunicorn/uvicorn access log) has **real client IP + full request path incl. search text and barcodes**, 30 days (drop-in installed, confirmed on server). nginx `combined` log: IP, time, request line, status, referrer, **user agent**, 14 days. No user ID or token in access logs (mobile search/product calls carry no auth header). App log lines carry user IDs for account deletion and auto-hidden ratings (`api/routers/account.py:109-111`, `api/routers/ratings.py:179`).
7. **Moderation mail** to `info@xxl.co.il` via Hostinger SMTP contains the **author's / reporter's email address**, the comment (≤500 chars) or report reason (`api/routers/ratings.py:420-491`). Mailbox retention is unknown.
8. **No WebView.** `react-native-webview` is not installed. External pages open in the system browser / Custom Tab: accessibility page (`m/src/app/(tabs)/settings.tsx:37, 292`), full privacy page (`m/src/app/privacy.tsx:21, 48`), mailto (`m/src/app/help.tsx:47`). Note: super.xxl.co.il loads Google Analytics after cookie consent, so opening those pages is subject to the web cookie banner.
9. **Web privacy policy gaps:** no mention of the app as such, camera, location, ratings/reviews in section 2, search/barcode text in logs, moderation mail with email address, on-device-only data, absence of analytics in the app, and hosting/backup/mail providers (Kamatera, Backblaze, Hostinger). Section D gives Hebrew text.
10. **Config notes (not data collection, but reviewers may ask):** Android merged permissions include Expo template defaults `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE`, `SYSTEM_ALERT_WINDOW`, `VIBRATE` and `ACCESS_FINE_LOCATION`; iOS gets an English `NSLocalNetworkUsageDescription` from `expo-dev-client`. See E.

---

## 1. Sign-in and auth provider

| Item | Finding | Where |
|---|---|---|
| Methods | Email + password sign-up, sign-in, password-reset email. Nothing else. | `m/src/lib/auth-context.tsx:126-146, 188-192`; `m/src/app/forgot-password.tsx:25`; web `web/src/components/AuthContext.tsx:55, 70` (only `signInWithPassword` in web/src) |
| Not present | Google OAuth, Sign in with Apple, magic link, OTP | `m/src/lib/auth-context.tsx:11-12`, `m/src/lib/supabase.ts:100-102`; no `signInWithOAuth`/`signInWithOtp` in either repo |
| Provider | Supabase Auth (`@supabase/supabase-js` ^2.116), project URL in `m/app.json` `extra.supabaseUrl` (public anon key, by design) | `m/package.json:8`, `m/src/lib/supabase.ts:93-104` |
| Email confirmation | Sign-up returns no session when confirmation is on; app shows "check your inbox" | `m/src/lib/auth-context.tsx:133-136`, `m/src/app/sign-up.tsx:31` |
| Session on phone | Supabase session (JWT + refresh token) in expo-secure-store (Keychain / Keystore), chunked | `m/src/lib/supabase.ts:37-97` |
| Fields Supabase stores | email, password hash, user UUID, sign-in timestamps, Supabase's own auth audit/request logs (IP, user agent) — Supabase-side, not in our code | Supabase default behaviour; retention: see E |
| Fields our DB stores | `users.id` (Supabase UUID), `users.email`, `users.tier`, `created_at`/`updated_at`. `display_name` column exists but is never written | `db/migrations/add_users_saved_baskets.sql:5-11`, `db/migrations/add_user_tier.sql:8`, `api/auth.py:122-126, 164-170` |
| When the users row is created | On any authenticated API call (upsert from the JWT `sub` + `email`) | `api/auth.py:153-188` |
| Name / avatar / phone | Not collected | — |

## 2. Mobile permissions and SDKs

**Permissions (merged config from `npx expo config --type introspect`, read-only):**

| Platform | Permission / key | Source | Used? |
|---|---|---|---|
| Android | `CAMERA` | expo-camera plugin, `m/app.json:42-50` | Yes, barcode scan |
| Android | `ACCESS_COARSE_LOCATION`, `ACCESS_FINE_LOCATION` | expo-location plugin, `m/app.json:70-80` | Yes, foreground only. Requests use `Accuracy.Balanced` (`m/src/lib/location-context.tsx:72, 300`); the hidden diagnostics screen uses `Accuracy.High` (`m/src/app/location-diagnostics.tsx:125`). Android 12+ lets the user grant approximate only. |
| Android | `INTERNET` | default | Yes |
| Android | `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE`, `SYSTEM_ALERT_WINDOW`, `VIBRATE` | Expo template defaults (no `android.permissions` / `blockedPermissions` in app.json) | Not used by app code |
| Android | `RECORD_AUDIO` | blocked: `recordAudioAndroid: false` (`m/app.json:46`) | No |
| Android | Background location | disabled (`m/app.json:76-78`) | No |
| iOS | `NSCameraUsageDescription` "XXL משתמש במצלמה רק לסריקת ברקודים של מוצרים." | `m/app.json:45` | Yes |
| iOS | `NSLocationWhenInUseUsageDescription` "XXL משתמש במיקום שלך כדי להציג מחירים בסניפים הקרובים אליך." | `m/app.json:75` | Yes |
| iOS | Always/background location, motion, microphone, Face ID | all `false` (`m/app.json:47, 54, 73-77`) | No |
| iOS | `NSLocalNetworkUsageDescription` (English, "Expo Dev Launcher …") | expo-dev-client plugin | Dev builds only; see E |
| iOS | `ITSAppUsesNonExemptEncryption: false` | `m/app.json:14` | — |

**Dependencies that could send data off the device (`m/package.json:5-43`):**

| Category | Present? | Notes |
|---|---|---|
| Auth | **Yes** — `@supabase/supabase-js` | email, password, tokens to Supabase |
| Our API | **Yes** — plain `fetch` to `https://api-super.xxl.co.il` | `m/src/api/client.ts:25` |
| Analytics (Firebase, GA, Amplitude, Segment, Mixpanel, PostHog, expo-insights/observe) | **No** | none in package.json or node_modules |
| Crash reporting (Sentry, Bugsnag, Crashlytics) | **No** | |
| Ads / advertising ID / tracking transparency | **No** | |
| Push notifications (`expo-notifications`, FCM/APNs tokens) | **No** | |
| OTA updates (`expo-updates`) | **No** | only `expo-updates-interface` (a type package pulled by expo-dev-client), not `expo-updates` |
| Maps SDK | **No** | distance is plain haversine on device |
| WebView | **No** | `react-native-webview` not installed |
| `expo-web-browser` | Yes | opens our own accessibility page in a Custom Tab / SFSafariViewController |
| `expo-image` | Yes | loads product images from our API (`m/src/api/client.ts:138-140`) |
| `expo-application`, `expo-constants`, `expo-localization` | Yes | read version / locale on the device for display only (`m/src/app/(tabs)/settings.tsx:149-155`); not sent |
| `expo-device` | listed, **not imported** anywhere in `m/src` | |
| `expo-dev-client` | Yes | development tooling; production profile in `m/eas.json:16-18` is not `developmentClient` |
| EAS Build / Submit | build-time only | EAS project id in `m/app.json:88-90`; Expo receives source code and build credentials, no end-user data at runtime |

## 3. Location

- Requested only in the foreground, once at first launch (primer first) or on an explicit tap (`m/src/lib/location-context.tsx:13-18, 286`).
- Position sources: `getLastKnownPositionAsync` then `getCurrentPositionAsync({accuracy: Balanced})` (`m/src/lib/location-context.tsx:70-72, 216-259, 299-302`).
- Kept **in memory only**; AsyncStorage holds `xxl_location_mode` ("gps"/"manual") and `xxl_last_city` (`m/src/lib/location-context.tsx:100-101, 293-330`), radius `xxl_nearby_radius_km` (`m/src/lib/nearby-context.tsx:38`).
- Store coordinates are fetched with **no input** (`m/src/lib/store-coords.ts:35-50`; server `api/routers/stores.py:61-84`), and only after a position exists (`m/src/lib/nearby-context.tsx:86-97`). Distance computed on the phone (`m/src/lib/geo.ts`, `m/src/lib/nearby-context.tsx:105-134`).
- **Never sent:** no lat/lon in any query string, header or body in `m/src/api/client.ts` (all 15 calls read). `/search` and `/product` take no location (`m/src/api/client.ts:175-182`; SU11A-34 note). `compareBasket` sends `chain_ids: null, cities: null` (`m/src/api/client.ts:273-276`).
- **Sent, derived:** `store_fks` (up to 300 store IDs within the chosen radius) in the POST body of `/basket/compare` when the "nearby only" toggle is on (`m/src/api/client.ts:250-279`). Server: body not logged, used for the calculation only, not stored (`api/routers/basket.py:28-42, 101-102`). This reveals a rough area for the duration of the request.
- Manual city choice stays on the phone (`xxl_last_city`); `/cities` is a public list download (`m/src/api/client.ts:119-135`).
- Diagnostics screen shows coordinates on screen only (`m/src/app/location-diagnostics.tsx:82-156, 193-237`).
- Device logs: the 3 `console.warn` calls print search/basket error detail with the URL (search text) to the device log only (`m/src/app/(tabs)/search.tsx:152, 188`, `m/src/app/basket-compare.tsx:65`); nothing is collected from device logs.

## 4. Camera / barcode

- `CameraView` with `onBarcodeScanned` only (`m/src/app/(tabs)/index.tsx:22, 219-229`); no `takePictureAsync`, `recordAsync` or image picker in the codebase (grep).
- The decoded digits are normalised and looked up via `GET /product/{barcode}` (`m/src/api/client.ts:44-76`), plus `GET /product/{barcode}/details`, `/product/{barcode}/image`, `/items/{code}/ratings` on the result screen. Barcode values therefore appear in server access logs (with IP).
- Scan history: last 50 products (barcode, name, time, cheapest price, chain) in AsyncStorage `xxl_scan_history`, on the device only (`m/src/lib/scan-history.ts:9-40`).
- **No image ever leaves the device.**

## 5. Per-user data on the server

All in Postgres on the Kamatera VM except where noted. Deletion = `DELETE /account` (`api/routers/account.py:84-112`): one transaction deletes `flights.alerts`, `flights.saved_searches` and the `users` row; FKs cascade the rest; then the Supabase auth user is deleted via the admin API (`api/supabase_admin.py:33-67`); failures are retried daily by `scrp-account-sweep.timer` (installed and active, 05:30, confirmed on server).

| Table / store | Columns (personal) | Purpose | Retention | On account deletion |
|---|---|---|---|---|
| Supabase `auth.users` (Supabase) | email, password hash, UUID, timestamps | sign-in | until deletion | Deleted via admin API (`api/routers/account.py:73-81`) |
| `users` | id, email, tier, timestamps (`display_name` unused) | link app data to account, tier | until deletion | Deleted (`api/routers/account.py:45`) |
| `saved_baskets` | user_id, name, items JSON (barcode, name, qty) | saved baskets; mobile syncs the working basket into one reserved row when signed in (`m/src/lib/basket-context.tsx:1-25, 151-223`) | until user deletes / account deletion | CASCADE (`db/migrations/add_users_saved_baskets.sql:15`) |
| `favorites` | user_id, barcode | favourites (web; mobile screen is a placeholder, `m/src/app/favorites.tsx:1-2`) | until removed / deletion | CASCADE (`db/migrations/add_favorites.sql:6`) |
| `ratings` | user_id, item_code, rating 1-3, comment (≤2000), status | public reviews; comment shown publicly **without** any user identifier (`api/routers/ratings.py:259-265`) | until user edits / deletion | CASCADE (`db/migrations/su10r1_ratings.sql:32`) |
| `rating_reports` (filed by the user) | reporter_user_id, reason (≤1000) | moderation | indefinite | Row kept, `reporter_user_id` SET NULL (`db/migrations/su10r1_ratings.sql:68`) |
| `rating_reports` (about the user's ratings) | rating_id, reason | moderation | indefinite | CASCADE via `ratings` (`db/migrations/su10r1_ratings.sql:67`) |
| `flights.alerts`, `flights.saved_searches` | user_id + flight search params | XXL Flights (shared account) | until deletion | Deleted explicitly (`api/routers/account.py:43-44`) |
| `deleted_accounts` | user_id (UUID), timestamps, attempts, short error code; no email | block reuse of a deleted account's token, drive retries | purged 7 days after completion (`scripts/sweep_account_deletes.py:23, 34`) | It *is* the deletion record |
| `portal_email_signups` (Supabase) | email, vertical, user agent, referrer | web "coming soon" sign-ups — **web only, not the app** | indefinite | Not linked to the account (policy section 8 says so) |
| Search / scan history | — | **not stored per user** on the server; no search-log table (grep of `api/`, `db/`) | — | — |
| Push tokens, consent flags, preferences | — | **none** on the server. Theme and "recommendations" toggle are device-only (`m/src/lib/prefs-context.tsx:30-31`) | — | — |
| Backups | full DB dump incl. all of the above | disaster recovery | local 7 daily / 4 weekly / up to 180 days monthly; B2 `daily/` lifecycle hide 180 d + delete 1 d (SU11A-33) | Ages out with the backup cycle (policy says so) |

**Device-only data (never sent, not deleted by account deletion; `m/src/lib/auth-context.tsx:43-48`):** basket (`basket_items`), scan history (`xxl_scan_history`), location mode / city / radius, location prompt flags, theme, recommendations toggle, cached store coordinates (`xxl_store_coords_v1`, 24 h), Supabase session (SecureStore, removed on sign-out).

## 6. Server and proxy logs

| Log | Contents | Retention | Source |
|---|---|---|---|
| journald, `scrp-api` (gunicorn + UvicornWorker access log) | `<client IP> - "METHOD /path?query HTTP/1.1" status`. Real client IP (uvicorn honours `X-Forwarded-For` from nginx on 127.0.0.1; 2,998 of 3,000 sampled lines are non-loopback). Path includes **search text** (`/search?q=…`) and **barcodes**. No user agent, no Authorization header, no body. | 30 days (`/etc/systemd/journald.conf.d/scrp.conf`: MaxRetentionSec=30day, MaxFileSec=1day — installed); current size 108 MB | `systemctl cat scrp-api`: `--access-logfile - --error-logfile -`, `StandardOutput=journal` |
| journald, app log lines | user_id on account deletion / Supabase admin delete (`api/routers/account.py:109-111`, `api/supabase_admin.py:56-67`); user_id + item on auto-hidden ratings (`api/routers/ratings.py:179`); rating id + item on moderation (`api/routers/ratings.py:459, 482`); mail recipient (info@) + subject (`api/mailer.py:166`). **No emails, tokens or passwords** (SU11A-32). One caveat: `search.py:206` logs a traceback on a v2 failure, which can include SQL parameters (the search text). | 30 days | as cited |
| nginx `/var/log/nginx/api-super.access.log`, `access.log` | default `combined`: IP, time, request line (path + query string), status, bytes, referrer, **user agent** (no custom `log_format` in nginx.conf or sites) | 14 days (`/etc/logrotate.d/nginx`: daily, rotate 14) | server config |
| Supabase logs | auth requests (IP, UA, email on events) | Supabase plan-dependent — unknown | — |

## 7. Third parties that receive user data

| Party | Data | Role | Notes |
|---|---|---|---|
| Supabase | email, password, auth tokens, auth request logs (IP/UA); web portal sign-ups | Processor (service provider) | in policy; region not in code |
| Kamatera | hosts the VM: Postgres (all of section 5), logs | Processor (infrastructure) | **not named in policy** |
| Backblaze B2 (`xxl-scrp-backups`) | DB backup copies incl. user data | Processor | **not named in policy**; mentioned only as "off-site backup copy" |
| Hostinger (SMTP `notify@xxl.co.il` → mailbox `info@xxl.co.il`) | moderation alerts: author / reporter **email**, rating id, item, comment ≤500 chars or report reason (`api/routers/ratings.py:420-491`, `api/mailer.py:82-166`) | Processor | **not named in policy**; mailbox retention unknown |
| Supabase Auth via custom SMTP: Hostinger mailbox `noreply@xxl.co.il` (confirmed 18 Oct 2026) | confirmation / reset emails to the user (reset email carries a 6-digit code) | Processor | Hostinger is named in the policy for moderation alerts only; add the auth emails (see E1) |
| Expo / EAS | build-time source + signing credentials; **no end-user data at runtime** (no updates, push or insights) | — | not user data; no disclosure needed |
| Google Play / Apple | store distribution, their own analytics on installs | Independent (platform) | not caused by our code |
| Google (Places/Geocoding) | **store** addresses only, server-side; no user data | — | not user data |
| Google Analytics | **web only**, after cookie consent; **not in the app** | Processor | in policy |

## 8. WebView

None. External links: `openBrowserAsync('https://super.xxl.co.il/accessibility')` (`m/src/app/(tabs)/settings.tsx:37, 292`), `Linking.openURL('https://super.xxl.co.il/privacy')` (`m/src/app/privacy.tsx:21, 48`), `mailto:info@xxl.co.il` (`m/src/app/help.tsx:47`), the generic `ExternalLink` (`m/src/components/external-link.tsx:18`).

## 9. User-generated content

| Content | Stored | Reviewed by us | Public |
|---|---|---|---|
| Rating 1-3 + optional comment (≤2000) | `ratings` | Blacklist term → hidden + system report + mail to info@ (with author email) (`api/routers/ratings.py:147-200`); moderation queue for allowlisted admin emails (`api/routers/ratings.py:336-391`) | Yes, active ones, anonymous |
| Report on a rating + optional reason (≤1000) | `rating_reports` | Mail to info@ with reporter email (`api/routers/ratings.py:210-245`) | No |
| Saved basket name + items | `saved_baskets` | No | No |

---

## A. Data inventory table

| Data item | Collected (leaves device)? | Where in code | Linked to user? | Used for | Shared with third party? | Retention | Deleted with account? |
|---|---|---|---|---|---|---|---|
| Email address | Yes (only if the user registers) | `m/src/lib/auth-context.tsx:126-146`; `api/auth.py:122-126` | Yes | Account, sign-in, password reset, moderation contact | Processors only: Supabase; Hostinger mailbox (moderation alerts only) | Until deletion; moderation mails: unknown | Yes (Supabase + `users`); copies in mails/backups age out |
| Password | Yes (to Supabase only; hashed there) | `m/src/lib/auth-context.tsx:139-143` | Yes | Sign-in | Supabase (processor) | Until deletion | Yes |
| User ID (Supabase UUID) | Yes | `api/auth.py:153-170` | Yes | Linking data | Supabase (processor) | Until deletion; `deleted_accounts` 7 days after | Yes |
| Name / phone / address / avatar | **No** | — | — | — | — | — | — |
| Precise / approximate device location | **No** (processed on device) | `m/src/lib/location-context.tsx`, `m/src/lib/geo.ts` | — | Nearby stores, distance | No | Not stored (memory only) | n/a |
| Nearby store IDs (derived from location) | Yes, ephemeral, only with "nearby only" basket compare | `m/src/api/client.ts:250-279`; `api/routers/basket.py:28-42` | No (no auth on the call) | Basket price within radius | No | Not stored, not logged | n/a |
| Chosen city | **No** (device only) | `m/src/lib/location-context.tsx:323-330` | — | Location fallback | No | Device | No (device) |
| Camera images | **No** | `m/src/app/(tabs)/index.tsx:219-229` | — | — | — | — | — |
| Barcode values scanned / typed | Yes, in request path | `m/src/api/client.ts:61-76, 138, 371-375, 502-506` | No (IP only, in logs) | Product lookup | No | Logs: journald 30 d, nginx 14 d | n/a (not linked); expire with logs |
| Search text | Yes, in query string | `m/src/api/client.ts:175-182` | No (IP only, in logs) | Search results | No | journald 30 d, nginx 14 d | n/a; expire with logs |
| IP address | Yes (every request) | server logs (section 6) | No account link in access logs | Security, operation | Hosting (Kamatera), Supabase for auth calls | 14 / 30 days | n/a; expire with logs |
| User agent | Yes (nginx only) | nginx combined log | No | Operation | Kamatera | 14 days | n/a |
| Saved / synced basket | Yes, if signed in | `m/src/lib/basket-context.tsx:151-223`; `api/routers/saved_baskets.py:60` | Yes | Restore basket across devices | No | Until deletion | Yes (CASCADE) |
| Favorites | Yes (web only today) | `api/routers/favorites.py:33` | Yes | Favourites list | No | Until removed | Yes (CASCADE) |
| Ratings + comments | Yes, if the user rates | `m/src/api/client.ts:404-431`; `api/routers/ratings.py:138-200` | Yes (public copy anonymous) | Reviews | Public display (anonymous); moderation mail via Hostinger | Until deletion | Yes (CASCADE) |
| Reports + reason | Yes, if the user reports | `m/src/api/client.ts:434-458`; `api/routers/ratings.py:210-245` | Yes, until deletion | Moderation | Hostinger mailbox (with reporter email) | Kept indefinitely | Row kept, reporter id removed |
| Scan history | **No** (device only) | `m/src/lib/scan-history.ts` | — | History screen | No | Device, last 50 | No (device) |
| Local basket (guest) | **No** | `m/src/lib/basket-context.tsx:116-141` | — | Basket | No | Device | No (device) |
| Theme / recommendations toggle / radius | **No** | `m/src/lib/prefs-context.tsx:30-31`; `m/src/lib/nearby-context.tsx:38` | — | Preferences | No | Device | No (device) |
| Crash logs / diagnostics / performance | **No** | no SDK | — | — | — | — | — |
| Device / advertising IDs | **No** | no SDK | — | — | — | — | — |
| Push token | **No** | no expo-notifications | — | — | — | — | — |
| Account tier | Yes (server-set, default free) | `db/migrations/add_user_tier.sql:8` | Yes | Feature limits | No | Until deletion | Yes |

## B. Proposed Google Play Data safety answers

General questions:
- Does your app collect or share any of the required user data types? **Yes.**
- Is all user data encrypted in transit? **Yes** (HTTPS only: `m/src/api/client.ts:25`, Supabase https).
- Do you provide a way for users to request that their data be deleted? **Yes** — in-app (Settings → מחיקת חשבון) and URL `https://super.xxl.co.il/account/delete`.
- Account creation: **Username and password** (email + password). Sign-in is optional; the app works without an account. No other login methods.
- Data shared with third parties: **None** (Supabase, Kamatera, Backblaze, Hostinger are service providers acting on our behalf → not "sharing" under Play's definition; public anonymous reviews are user-initiated).

| Play category → data type | Collected | Shared | Ephemeral | Required / optional | Purposes |
|---|---|---|---|---|---|
| **Personal info** → Email address | Yes | No | No | Optional (only for an account) | App functionality, Account management |
| Personal info → User IDs | Yes | No | No | Optional | App functionality, Account management |
| Personal info → Name, Address, Phone, Race, Political, Sexual orientation, Other info | No | — | — | — | — |
| **Financial info** (all) | No | — | — | — | — |
| **Health and fitness** | No | — | — | — | — |
| **Messages** | No | — | — | — | — |
| **Photos and videos** | No (camera frames never leave the device) | — | — | — | — |
| **Audio** | No | — | — | — | — |
| **Files and docs** | No | — | — | — | — |
| **Calendar / Contacts** | No | — | — | — | — |
| **Location** → Approximate location | **Yes — conservative answer**, see note | No | **Yes** | Optional | App functionality |
| Location → Precise location | No | — | — | — | — |
| **App activity** → In-app search history | Yes (search text + barcodes reach our server logs) | No | No | Required to use search/scan | App functionality, Fraud prevention / security |
| App activity → Other user-generated content | Yes (ratings, comments, reports, saved baskets) | No | No | Optional | App functionality |
| App activity → App interactions, Installed apps, Other actions | No | — | — | — | — |
| **Web browsing** | No | — | — | — | — |
| **App info and performance** → Crash logs, Diagnostics, Other | No | — | — | — | — |
| **Device or other IDs** | No | — | — | — | — |

Notes for B:
- **Location:** the device position itself never leaves the phone, so strictly it is not "collected". The only location-derived transmission is the in-radius store-ID list for "nearby only" basket compare, processed in real time and not stored or logged. Two defensible answers: (a) declare nothing for Location; (b) declare *Approximate location*, collected, **processed ephemerally**, optional, App functionality. **Recommendation: (b)** — the app holds the location permission (incl. `ACCESS_FINE_LOCATION`), and declaring the ephemeral derived list removes any mismatch for the reviewer. Do NOT declare Precise location.
- **IP address:** Play has no separate IP type; it is not used to infer location. Nothing to declare beyond the above.
- If Dude prefers the narrowest form, "In-app search history" could be argued as server logs only; keep it — the policy already says logs keep "pages viewed", and search text is in the URL.

## C. Proposed Apple App Privacy answers

**Data Used to Track You: None.** (No third-party SDKs, no data combined with other companies' data, no advertising ID, no data broker.) No App Tracking Transparency prompt needed.

**Data Linked to You:**
| Apple type | Purpose |
|---|---|
| Contact Info → Email Address | App Functionality |
| Identifiers → User ID | App Functionality |
| User Content → Other User Content (ratings, review comments, reports, saved baskets) | App Functionality |

**Data Not Linked to You:**
| Apple type | Purpose |
|---|---|
| Search History (search text and scanned barcodes in server request logs, kept with IP up to 30 days, never tied to the account) | App Functionality |

**Not collected:** Location (on-device only; the store-ID list is real-time processing, which Apple's definition excludes), Photos or Videos, Contacts, Health, Financial, Browsing History, Purchases, Diagnostics (no crash or performance SDK), Usage Data, Identifiers → Device ID, Sensitive Info, Other Data.

Notes for C:
- Apple: "optional disclosure" applies to data that is not used for tracking, is infrequent, optional and clearly disclosed. Ratings/reviews do not qualify (they are a core feature) — keep them declared.
- A demo account for review must NOT be in `DELETE_PROTECTED_USER_IDS` (existing open item).

## D. Hebrew text proposals

### D1. Web privacy policy (`web/src/pages/PrivacyPolicyPage.tsx`)

**Section 1 — scope (replace the first sentence):**
> מדיניות זו מפרטת כיצד XXL בע"מ ("XXL", "אנחנו") אוספת, משתמשת ומגנה על מידע אישי של משתמשי האתר xxl.co.il ואתרי המשנה שלו (לרבות super.xxl.co.il ו-fly.xxl.co.il) ושל אפליקציית SUPER XXL לאנדרואיד ול-iOS (יחד: "השירות").

**Section 2 — change the account bullet:**
> **חשבון משתמש**: ההרשמה לחשבון אינה חובה. בעת הרשמה אנו שומרים את כתובת האימייל שלכם וסיסמה מוצפנת (מנוהל דרך ספק האימות שלנו, Supabase). לאחר התחברות אנו שומרים גם את המידע שאתם יוצרים בחשבון: מוצרים מועדפים, סלי קניות שמורים (באפליקציה, סל הקניות מסונכרן לחשבון כשאתם מחוברים), דירוגים וביקורות שפרסמתם ודיווחים שהגשתם על ביקורות.

**Section 2 — new bullets:**
> **דירוגים וביקורות**: דירוג ותגובה שאתם מפרסמים על מוצר מוצגים לכלל המשתמשים ללא שמכם וללא כתובת האימייל שלכם. ביקורת שנחסמה אוטומטית או שדווחה מועברת לבדיקה ידנית, וההתראה לתיבת הדואר שלנו כוללת את כתובת האימייל של הכותב או של המדווח ואת תוכן הביקורת או סיבת הדיווח.

> **מצלמה (אפליקציה)**: המצלמה משמשת רק לסריקת ברקוד של מוצר, ורק לאחר שאישרתם גישה. זיהוי הברקוד מתבצע במכשיר, ולשרת נשלח מספר הברקוד בלבד כדי להציג את המוצר והמחירים. איננו מצלמים, שומרים או מעלים תמונות.

> **מיקום (אפליקציה, לא חובה)**: אם אישרתם גישה למיקום בזמן השימוש באפליקציה, המיקום משמש להצגת סניפים קרובים. המרחק לסניפים מחושב במכשיר עצמו, מול רשימת הסניפים שהאפליקציה מורידה מאיתנו; המיקום שלכם אינו נשלח לשרתים שלנו ואינו נשמר אצלנו. כשאתם משווים סל רק בסניפים קרובים, נשלחת לשרת רשימת הסניפים שבטווח שבחרתם, לצורך החישוב בלבד, והיא אינה נשמרת. איננו ניגשים למיקום ברקע. אפשר לבחור עיר ידנית במקום להשתמש במיקום.

> **חיפושים וסריקות**: מילות החיפוש ומספרי הברקוד שאתם מחפשים או סורקים נשלחים לשרת כדי להחזיר תוצאות. הם אינם נשמרים בחשבונכם, אך נרשמים ביומני השרת יחד עם כתובת ה-IP (ראו סעיף 8 לתקופות השמירה).

> **מידע שנשמר במכשיר בלבד (אפליקציה)**: היסטוריית הסריקות (עד 50 מוצרים אחרונים), סל הקניות, העיר שבחרתם, רדיוס החיפוש והעדפות התצוגה נשמרים במכשיר שלכם ואינם נשלחים אלינו (למעט סנכרון הסל לחשבון כשאתם מחוברים). מידע זה אינו נמחק עם מחיקת החשבון; ניתן למחוק אותו בהסרת האפליקציה או במחיקת נתוני האפליקציה.

> **ללא פרסום ומעקב באפליקציה**: באפליקציה אין כלי ניתוח, פרסומות, מזהה פרסום, התראות פוש או דיווח קריסות של צד שלישי, ואיננו עוקבים אחריכם באפליקציות או באתרים אחרים. Google Analytics פועל באתר בלבד ובכפוף להסכמתכם (סעיף 5).

**Section 2 — technical logs bullet (replace):**
> **לוגים טכניים**: שרתי השירות שומרים באופן שגרתי כתובת IP, מועד הבקשה, הכתובת שהתבקשה (כולל מילות חיפוש ומספרי ברקוד שבה) וסוג הדפדפן או האפליקציה, למטרות אבטחה ותפעול. יומנים אלה אינם משויכים לחשבון.

**Section 4 — replace the Supabase line and add providers:**
> - **Supabase** — ניהול חשבונות משתמשים ואימות (אימייל וסיסמה מוצפנת), ושמירת הרשמות לעדכונים מדפי "בקרוב".
> - **Kamatera** — אחסון השרתים ומסד הנתונים של השירות.
> - **Backblaze** — אחסון עותק הגיבוי החיצוני של מסד הנתונים.
> - **Hostinger** — שירות הדואר שבאמצעותו נשלחות אלינו התראות בקרה על ביקורות.

**Section 8 — "what is kept" bullet on operational emails (replace):**
> הודעות אימייל תפעוליות (למשל התראה על ביקורת שהועברה לבדיקה, הכוללת את כתובת האימייל של הכותב או המדווח) נשמרות בתיבת הדואר שלנו רק כל עוד הן נחוצות לתפעול ולבקרה. *(Replace with a concrete period once the mailbox retention is set — see E.)*

**Section 9 — add the new providers:**
> חלק מספקי השירות שלנו (כגון Google, Supabase, Backblaze ו-Hostinger) עשויים לעבד מידע מחוץ לישראל. ...

(Update the date line at the top when deploying.)

### D2. One added line for the in-app summary (`m/src/i18n/he.ts`, `legal.privacySummary`, after the "what we collect" line)

> 'באפליקציה: המצלמה משמשת רק לסריקת ברקוד (נשלח רק מספר הברקוד, ללא תמונה), והמיקום (לא חובה) משמש לחישוב המרחק לסניפים במכשיר עצמו ואינו נשלח אלינו. אין באפליקציה פרסומות, כלי ניתוח או מעקב.',
> // en: "In the app: the camera is used only to scan barcodes (only the number is sent, no image), and location (optional) is used to compute distance to stores on the device itself and is not sent to us. The app has no ads, analytics or tracking."

The in-app summary must only restate the web policy, so deploy D1 first.

## E. Open questions (code cannot answer)

1. **Supabase**: project region and auth-log retention on the current plan. *Answered 18 Oct 2026:* confirmation / reset emails go through custom SMTP (Hostinger mailbox noreply@xxl.co.il, sender "SUPER XXL"), so Hostinger must also be named for these emails in policy section 4.
2. **Moderation mailbox (info@xxl.co.il, Hostinger)**: retention for alert mails that contain user emails — set a period (e.g. delete after 90 days) so section 8 can state it.
3. **Kamatera / Backblaze regions** (for section 9 "transfer abroad"): which data centre hosts the VM and the B2 bucket.
4. **Location answer for Play**: confirm option (b) in B (declare approximate location as ephemeral) or (a) (declare nothing).
5. **SU11A-37 popularity counters**: if they store search queries or per-item views, keep them aggregate with no IP, user ID or timestamp per event; otherwise B/C and D1 change (search history would become stored data).
6. **Config hygiene before submission (separate code task, not done here)**: add `android.blockedPermissions` for `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE`, `SYSTEM_ALERT_WINDOW` (unused); decide whether `ACCESS_FINE_LOCATION` is needed (the app requests Balanced accuracy; only the diagnostics screen asks for High); confirm the production iOS build does not carry the English `NSLocalNetworkUsageDescription` from `expo-dev-client` (check the built Info.plist, or exclude expo-dev-client from production).
7. **Legal entity**: the policy says `XXL בע"מ` — confirm the exact registered name matches the developer name on Google Play / Apple.

## F. Updates (18 Oct 2026, SU11A-43)

- **Auth email provider confirmed:** Supabase sends sign-up confirmation and password-reset emails through custom SMTP, using the Hostinger mailbox noreply@xxl.co.il (sender "SUPER XXL"). No new processor; Hostinger was already one, for moderation alerts. The policy text still has to say Hostinger also carries these emails (TO CONFIRM in `docs/store_submission_checklist.md`).
- **Password reset** now emails a 6-digit code instead of a link (SU11A-41). No data-category change.
- **Google Play Data safety** was submitted on 18 Oct 2026 with the answers in `docs/store_submission_checklist.md`. The review is pending.
- **Block lists and the consent record now exist (SU11A-44, not deployed):** `user_blocks` and `users.terms_version` / `users.terms_accepted_at` (plus `users.banned_at`, set only by a moderator).
  - The Data safety / App Privacy categories do not change; both fall under the existing account data and other user-generated content.
  - The web policy, the deletion page and the in-app summary mention them (SU11A-44). All of it is deleted with the account (FK CASCADE).
