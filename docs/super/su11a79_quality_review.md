# SU11A-79 — Pre-marketing quality review (read-only)

Date: 12 Nov 2026. Reviewer: CC, acting as an outside senior engineer. Scope: `C:\scrp` (API, web super / portal / admin, nginx and systemd records in `deploy/`) and `C:\scrp\xxl-super-mobile` (Expo app 1.2.4).

**Method.** Static reading of the code and config. `npm audit` was run in `web\` and `xxl-super-mobile\`, with and without `--omit=dev`. `pip-audit -r requirements.txt` was run in a throwaway venv under `%TEMP%`. The git history of scrp was scanned for secret patterns (results show kind, file and commit only; every hit was a placeholder). About 30 plain GETs went to the public sites and the API at under 1 request per second, around 16:00–16:10 Israel time, outside the quiet windows. Nothing was changed, deployed or written except this file. No server login, no EAS, no Supabase dashboard.

**Session ID.** SU11A-79 was listed as the next free ID (`CLAUDE.md`, `docs/super/handoff_super.md:3363`) and is not used anywhere else.

**Important caveat.** The repo's nginx and systemd files are *records*. The live server can differ from them. Where it matters, the finding says so, and "Checks that need the server" gives a read-only command to confirm.

## Summary

**Status (12 Nov 2026):** C1, H1, H6, M1 (route part), M2, L4 and L5 are fixed in SU11A-80 and H5 in SU11A-81, both **deployed and live-checked 12 Nov 2026**. H2, H3, H4 and L13 are fixed in SU11A-82, not deployed (runbook in the SU11A-82 entry of `docs/super/handoff_super.md`). Everything else is open.

| ID | Sev | Area | Finding | file:line | Proposed fix | Effort |
|---|---|---|---|---|---|---|
| C1 | **Critical** | Perf / DoS | Every home-page visit calls public `/stats`. It runs an uncached `COUNT(*)` over all of `prices`, plus a `stores IN (SELECT store_fk FROM prices)` scan — **fixed in SU11A-80, deployed 12 Nov 2026** | `web/src/components/StatsBar.tsx:6`, `web/src/pages/HomePage.tsx:216`, `api/routers/health.py:16-19`, `db/query.py:936-941` | Serve `/stats` from a small table or the search build stamp, cached per build (as `/chains` was in SU11A-59), or use `pg_class.reltuples`. Add `/stats` to the heavy group meanwhile | S |
| H1 | High | UX / errors | The public error screen shows customers a developer hint: "ודאו ש-uvicorn api.main:app --reload פועל" — **fixed in SU11A-80, deployed 12 Nov 2026** | `web/src/components/ErrorState.tsx:19-23`, `web/src/i18n/locales/he.json:87` (en.json same key) | Replace it with a customer text, e.g. "נסו שוב בעוד רגע" | S |
| H2 | High | Monitoring | Nothing alerts anyone: site / API down, failed scrp-cron or import, a chain with no new prices, a failed backup, disk, TLS expiry, DB size. No systemd unit has `OnFailure=`, and the admin status page is pull-only — **fixed in SU11A-82, not deployed** | `deploy/systemd/*.service` (no `OnFailure`), `api/routers/admin.py:268` | External uptime check on `/health` and the web home (free tier is enough). `OnFailure=` → a small mail unit using `api/mailer.py` for scrp-cron, backup, search-items and stats. A daily "freshness / disk / DB size" mail. TLS expiry is covered by the uptime tool | M |
| H3 | High | Backups | No documented test restore. Encryption of the off-site dump is still unverified (SU11A-48 F-08, open since 22 Oct). A backup failure alerts no one — **fixed in SU11A-82, not deployed** | `docs/security/su11a48_security_review.md:66, 255`; `/usr/local/bin/scrp-backup.sh` (not in repo) | Verify the rclone remote type (S-1). Add an rclone `crypt` remote if it is plain `b2`. Do one restore into a scratch DB and write it down. Alert on failure (H2) | M |
| H4 | High | Rate limits / CGNAT | No IPv6 (no AAAA records), so every mobile user arrives over carrier CGNAT IPv4. The heavy zone is 2 r/s, burst 10 per IP. One web comparison costs 1 `/compare` + 1–3 `/promos/bulk`. About 5 people comparing at once behind one carrier IP get 429 "השרת עמוס" — **fixed in SU11A-82, not deployed** | `deploy/nginx/xxl-ratelimit-http.conf:16,21,23,25`, `deploy/nginx/xxl-ratelimit-api.conf:2,33-75` | Raise the values (see H4 section: api 30 r/s / 120, heavy 8 r/s / 40, bulk in its own zone, suggest 40 / 120, img 60 / 300). Add AAAA + `listen [::]:443`. Watch the http_429 counter daily | S |
| H5 | High | SEO / link previews | The static HTML for super.xxl.co.il carries the **portal** title, description, OG / Twitter image and `canonical=https://xxl.co.il/`. An inline script corrects them only for JS-running clients. WhatsApp / Facebook / X crawlers do not run JS, so every shared super link previews as the portal — **fixed in SU11A-81, deployed 12 Nov 2026** | `web/index.html:14-35` (fix-up script `:40-66`) | Serve a per-host HTML: build a second `super.html` with the super tags, and use `try_files $uri /super.html` in the super server block. Category pages need per-URL tags (pre-render, already planned) | M |
| H6 | High | UX / errors | The web has no React error boundary. Any render exception unmounts the whole tree and leaves a **blank white page** — **fixed in SU11A-80, deployed 12 Nov 2026** | `web/src/main.tsx:22-32`, `web/src/App.tsx:52-77` | Wrap `<App/>` in an error boundary with a Hebrew "משהו השתבש — רענון" screen and a reload button | S |
| M1 | Medium | UX / SEO | No catch-all route. An unknown path shows the header and footer with an empty body, answered 200 (soft 404). `/sitemap.xml` also returns the SPA HTML with 200 — **route part fixed in SU11A-80, deployed 12 Nov 2026** (real 404 status needs nginx) | `web/src/App.tsx:59-73` | Add `<Route path="*">` with a Hebrew 404 page, `noindex`. Optionally nginx `location = /sitemap.xml` → 301 to `sitemap-super.xml` | S |
| M2 | Medium | UX / slow API | The web axios instance has no `timeout`. On a stuck API the spinner runs until nginx's 120 s `proxy_read_timeout` — **fixed in SU11A-80, deployed 12 Nov 2026** | `web/src/api/client.ts:16-29`, `deploy/nginx/xxl-api-proxy.conf` (`proxy_read_timeout 120s`) | `timeout: 20000` on `http` (admin already uses 20 s), then show ErrorState | S |
| M3 | Medium | A11y | The basket drawer is not a dialog: no `role="dialog"` / `aria-modal`, no Esc, focus is neither moved in nor trapped | `web/src/components/BasketDrawer.tsx:84-90` | Same pattern as `ProductDetailModal.tsx` (dialog attrs, Esc, focus in, return focus) | S |
| M4 | Medium | A11y | The portal search input has no label / `aria-label` (placeholder only) and `outline-none` with no focus style | `web/src/pages/PortalPage.tsx:83-91` | `aria-label`, plus `focus-within:ring-2` on the wrapper | S |
| M5 | Medium | A11y (IS 5568) | No skip link to the main content | `web/src/App.tsx:57` (before `<Header/>`) | "דלג לתוכן הראשי" link → `#main`, visible on focus | S |
| M6 | Medium | Abuse / moderation | Reports are unlimited per user and per rating, and each one sends a mail. The mailer cap (20 / h, 60 / day per worker) means one account can **silence genuine moderation alerts** for a day. No per-user cap on new ratings, and `item_code` is not validated | `api/routers/ratings.py:243-276`, `:164-167`; `api/mailer.py:51-52`; `api/routers/blocks.py:8` | One report per (reporter, rating). Per-user daily caps (e.g. 20 ratings, 10 reports). Validate `item_code` as 1–14 digits. Mail a digest instead of one mail per report | S |
| M7 | Medium | Supabase | `portal_email_signups`: the anon key may INSERT with `check (true)`, with no DB length limits on email / user_agent / referrer and no rate limit. Anyone can script unlimited, large rows straight to PostgREST. The UI also says "success" when the insert failed | `db/migrations/9f_followup_portal_email_signups.sql` (policy / grants), `web/src/pages/ComingSoonPage.tsx:29-41` | Add CHECKs (`length(email) <= 254`, UA / referrer <= 500), a unique (email, vertical), and a Supabase rate limit or an Edge Function. Show an error on failure | S |
| M8 | Medium | Deps (API) | pip-audit: **starlette 1.0.0** (Host / path URL reconstruction, form limits → fixed 1.3.1); **Pillow 12.3.0** (≈40 memory-safety CVEs → 13.0.0); **python-jose 3.5.0** (HMAC key confusion, no fixed release, unmaintained); ecdsa / anyio (not reachable) | `requirements.txt:3,10,11,22` | Upgrade starlette (with a matching fastapi), Pillow 13, anyio 4.14.2. Plan python-jose → PyJWT (ES256 only). Reachability is in the M8 section | M |
| M9 | Medium | Security headers | CSP is `Report-Only` and has **no `report-uri`**, so it neither blocks nor collects reports. The planned "enforce after a clean week" cannot be judged | `deploy/nginx/xxl-csp-web.conf:11`, `deploy/nginx/admin.xxl.co.il.conf:49` | Enforce on admin.xxl.co.il first (small, own surface). For super / portal, either add a report endpoint or test in a browser and switch to enforcing | S |
| M10 | Medium | App errors | The app exports no Expo Router `ErrorBoundary`, so an uncaught render error closes the app | `xxl-super-mobile/src/app/_layout.tsx` (no `export function ErrorBoundary`) | Export an `ErrorBoundary` with a Hebrew retry screen (next app version) | S |
| M11 | Medium | Release state | The handoff's open-items list is stale. It says SU11A-77 is "built, not deployed", but `/announcements/active` answers 204 live. Nine other items still read "built, not deployed" (SU11A-47 / 49 / 50 / 52 / 54 / 57 / 64 / 66B / 68). Before marketing nobody can say from the docs what is live | `docs/super/handoff_super.md:3298-3330` (e.g. `:3326`) | One read-only server pass (S-9) and rewrite the list as live / not live | S |
| M12 | Medium | SEO / sharing | Products have no URL: product details are a modal only. No product page can be shared, previewed or indexed | `web/src/App.tsx:59-73` (no product route), `web/src/components/ProductDetailModal.tsx` | `/p/:barcode` route that opens the same view, with per-product tags (pre-rendered later) | L |
| M13 | Medium | Capacity | Unknown under campaign load: 2 gunicorn workers, pool 20 + 10 each, 3.8 GiB RAM, cold `/promos/today` ≈ 11 s (handoff). No load test has ever been run | `db/db.py:36`, `api/mailer.py:57` (2 workers), `docs/super/handoff_super.md` (SU11A-60 note) | Fix C1 first. Precompute `/promos/today`. Then a short, scheduled load test against a staging copy (not production) | M |
| L1 | Low | Security | `/docs`, `/redoc`, `/openapi.json` are public and list every admin route (SU11A-48 F-19, still open) | `api/main.py:30-38` | `docs_url=None, redoc_url=None, openapi_url=None` in production | S |
| L2 | Low | Headers | HSTS has no `includeSubDomains` / `preload` | `deploy/nginx/xxl-security-headers.conf:17` | Add `includeSubDomains` once every subdomain is https-only | S |
| L3 | Low | A11y contrast | `text-gray-400` (#9ca3af, ≈2.5:1 on white) on real text: review dates, item codes, "loading" | `web/src/components/ReviewsPanel.tsx:149`, `web/src/pages/MyRatingsPage.tsx:113`, `web/src/components/CategoryLine.tsx:46` | `text-gray-500` (≈4.8:1) | S |
| L4 | Low | UX | `getCities()` has no `.catch`: on an API failure the city list is silently empty (unhandled rejection). Each load also sends an unused `fetch('/health')` — **fixed in SU11A-80, deployed 12 Nov 2026** | `web/src/App.tsx:44-47` | `.catch(() => {})` + a retry. Drop the health ping (one fewer call per IP) | S |
| L5 | Low | Errors | A non-admin unhandled 500 is plain text with no CORS headers. The browser then reports a network error, and the web says "cannot reach the server" — **fixed in SU11A-80, deployed 12 Nov 2026** | `api/main.py:91-95` | JSON 500 `{"code":"server_error"}` for every path, as for /admin | S |
| L6 | Low | Deps (mobile) | npm audit: 1 critical (`shell-quote`), 12 high. All are build / dev tooling (expo CLI, metro, xmldom, node-forge, compression…), the same with `--omit=dev` because Expo lists them as dependencies. Only `query-string` / `decode-uri-component` (via expo-router URL parsing) ship in the app: local DoS on a crafted deep link at worst | `xxl-super-mobile/package-lock.json` | `npm audit fix` (non-major) at the next build; expo-router major comes with the next SDK upgrade | S |
| L7 | Low | Admin auth | The admin gate trusts the token's `email` claim (no `email_verified` check). That is safe only while Supabase "Confirm email" and "Secure email change" are on (SU11A-48 F-10) | `api/auth.py:349-353` | Also require the admin's `sub` in an allow-list (ids instead of emails) | S |
| L8 | Low | Account deletion | "Fresh sign-in" = access token `iat` ≤ 300 s, but a silently refreshed token also has a new `iat`, so it is weaker than re-authentication | `api/routers/account.py:36, 66-71` | Use the `amr` claim (`password` with a recent timestamp) | S |
| L9 | Low | Privacy | `portal_email_signups` retention is "indefinite" | `docs/store_privacy_inventory.md:116` | Set a retention period (e.g. 24 months) and state it in the policy | S |
| L10 | Low | Secrets hygiene | The scrp `.gitignore` does not ignore `*.pem`, `*.p8`, `*.p12`, `*.jks`, `*.keystore`, `google-services.json` (mobile does) (F-16) | `.gitignore:140` area | Add the patterns | S |
| L11 | Low | Ops | `scrp-geocode.service` / `.timer` are still in the repo although Nominatim is retired | `deploy/systemd/scrp-geocode.*` | Confirm disabled on the server (S-2), then delete the files or mark them retired | S |
| L12 | Low | A11y | List-view thumbnails use `alt=""`. That is acceptable as decorative (the name is next to them), but the CLAUDE.md baseline asks for the product name | `web/src/components/results/ResultsListView.tsx:48-50` | Keep `alt=""` (preferred: no double read-out), and record this as a deliberate exception | S |
| L13 | Low | Abuse | `/promos/bulk` follows every compare. While it shares the heavy bucket, a normal web comparison spends 2–4 of the 10 burst tokens — **fixed in SU11A-82, not deployed** | `deploy/nginx/xxl-ratelimit-api.conf:48` | Covered by H4 (own zone) | S |

**Counts:** Critical 1, High 6, Medium 13, Low 13.

**Verified OK (no finding):**
- Every `/admin/*` route depends on `require_admin_mfa`: the allow-list fails closed and `aal2` is required (`api/routers/admin*.py` router-level `dependencies=`, `api/routers/ratings.py:421-458`, `api/auth.py:333-360`).
- JWTs: ES256 only, plus `kid`, audience and expiry checks (`api/auth.py:113-142`).
- Every interpolated SQL fragment sampled is a constant or a generated `:param` placeholder (≈90 f-string sites listed and spot-read).
- No service-role key in the web or app config or bundles: both client keys decode to `role: anon` (`web/.env.production` `VITE_SUPABASE_ANON_KEY`; `xxl-super-mobile/app.json` `expo.extra.supabaseAnonKey`). The service-role key lives only in the server `.env` (read by `api/supabase_admin.py`).
- Git history: 5 secret-pattern hits, all placeholders (`CLAUDE.md` f898bb9, `db/migrate_sqlite_to_postgres.py` d133085, `docs/runbooks/rotate_scrp_app_password.md` c54ee6c, `tests/test_account_delete.py` ad5011c ×2).
- GA4 loads only after consent (`web/src/utils/analytics.ts:79-103`).
- No coordinates in any query string.
- The `xxl_internal` cookie is `Secure; SameSite=Lax`.
- No `dangerouslySetInnerHTML`, no open redirect (portal destinations are fixed), no file uploads. The only outbound fetch is to the JWKS (no SSRF).
- Live headers on all four hosts: HSTS, nosniff, Referrer-Policy, `X-Frame-Options DENY` + `frame-ancestors 'none'`, Permissions-Policy. http → https 301.
- CORS reflects only the xxl origins.
- The API and admin are `noindex`.
- The accessibility statement `/accessibility` exists and is linked in the footer (`web/src/components/Footer.tsx:33`).
- `<html lang="he" dir="rtl">`.
- The compare table has `<caption>` and `th scope` (`web/src/components/results/CompareTable.tsx:99-147`).
- The product modal is a proper dialog.
- The search input is labelled (`web/src/components/SearchBar.tsx:154`).
- The app: every fetch has a timeout and maps failures to Hebrew texts. The raw `detail` goes to `console.warn` only.

---

## Findings

### C1 — `/stats` scans `prices` on every home-page visit
- `StatsBar` is rendered unconditionally on the home page (`HomePage.tsx:214-217`) and calls `useStats()` → `GET /stats` (`client.ts:106`). React Query caches it per tab for 5 minutes only (`hooks.ts:14`), so every new visitor sends one.
- `fetch_stats` runs `SELECT COUNT(DISTINCT id) FROM stores WHERE id IN (SELECT store_fk FROM prices)` and `SELECT COUNT(*) FROM prices` (`db/query.py:937-941`) on every call. There is no response cache and no build-stamp cache.
- nginx gives `/stats` the general 10 r/s per IP, burst 40, so one client can keep up to 2 workers' thread pools and Postgres busy. The 15 s `statement_timeout` limits each call, not the rate.
- This breaks the standing rule "A public endpoint must not scan `prices` / `promos` per request" (CLAUDE.md, SU11A-59). `/chains` was fixed for exactly this.
- Severity: a campaign spike on the home page turns into back-to-back full scans of the largest table on a 3.8 GiB box. If S-4 shows the count finishes in well under 100 ms, downgrade it to High. The fix is small either way.

### H1 — Developer instruction on the customer error screen
`ErrorState` shows `errors.api_down_hint` in a `<code>` box whenever the request was not a 429 / 503 (`ErrorState.tsx:19-23`). The Hebrew text is "ודאו ש-uvicorn api.main:app --reload פועל" (`he.json:87`). The same text appears on any network error, timeout or 500 for every visitor. Because of L5, a server 500 also lands here.

### H2 — No alerting
- The repo's units have no `OnFailure=` (grep of `deploy/systemd/` is empty), and no script under `scraper/` or `scripts/` sends mail.
- `api/mailer.py` exists but only moderation uses it. The admin status page (`/admin/status`) shows freshness and coverage only when someone opens it.
- Nothing watches: the site or API being down, a failed scrp-cron (10:00), a partly failed load (one chain without prices for 24 h), a failed `scrp-backup` (04:00) or `scrp-search-items` (14:30), the disk (30 GB volume, GS1 images, dumps), DB size, the journald size, or certificate expiry (certs valid to 27 Dec 2026 per SU11A-48; the renewal timer is unmonitored).
- Minimum before marketing:
  1. An external uptime monitor on `https://super.xxl.co.il/` and `https://api-super.xxl.co.il/health`, alerting by mail / phone, with TLS expiry on.
  2. `OnFailure=xxl-alert@%n.service` on the five timers' services.
  3. A daily summary mail: freshness per chain, `df`, DB size.

### H3 — Backups never test-restored, encryption unverified
- Daily `pg_dump` at 04:00 → B2 `xxl-scrp-backups/daily/`, 180-day lifecycle (handoff `:39, 75-78`).
- SU11A-48 F-08 (Medium, 22 Oct) is still open: if the rclone remote is plain `b2`, the full user DB (emails, ratings, baskets) sits unencrypted at Backblaze.
- The repo has a restore *command* (handoff `:78`) but no record of a restore ever being run.
- `scrp-backup.sh` and its service are not in the repo, so there is nothing to review.
- Raised to High because the backup is the only recovery path for user data on a single VM.

### H4 — Rate limits vs Israeli CGNAT
- **Facts.** Zones are keyed by `$binary_remote_addr`:
  - `xxl_api` 10 r/s, burst 40;
  - `xxl_heavy` 2 r/s, burst 10, and a heavy request must pass both heavy and api;
  - `xxl_suggest` 20 r/s, burst 60;
  - `xxl_img` 30 r/s, burst 200.
- **No IPv6.** `nslookup -type=AAAA` for super / api-super returns no address, so every phone on Partner / Cellcom / Pelephone / HOT Mobile comes over the carrier's CGNAT IPv4 pool. Offices, schools, army bases and iCloud Private Relay also put many users behind one address.
- **Calls per screen** (from the clients):

| Screen | General zone | Heavy | Other |
|---|---|---|---|
| Web home load | `/cities`, `/health` (unused), `/stats` (C1), `/freshness`, browse tree: ≈ 4–6 | 0 | — |
| Web search, no city | `/search`: 1 | `/promos/bulk` by store chunks: 0–3 | suggest ≈ 3–8 per query; images 20–50 |
| Web compare, city | — | `/compare` 1 + `/promos/bulk` 1–3 = 2–4 | images 20–50 |
| App search | `/search`: 1 per page | 0 | suggest |
| App scan | `/product`, `/details`, `/ratings`: 3 | 0 | image 1 |
| App basket compare | — | `/basket/compare`: 1 | — |

- **50 users on one IP, campaign spike.**
  - Say 10 of them compare within the same 10 s: 10 × 3 = 30 heavy requests in 10 s = 3 r/s against 2 r/s. The 10-token burst is gone in about 3 s and the rest get 429.
  - 50 people opening the home page over 10 s cause 250 general calls in 10 s = 25 r/s against 10 r/s: the burst of 40 lasts about 3 s.
  - So **no, 10 r/s with burst 40 is not safe for ~50 active users behind one IP**, and the heavy zone fails first.
  - The 429 path itself is good: JSON, `Retry-After`, the web shows "busy", no auto-retry.
- **Proposed values** (per IP):

| Zone | Rate | Burst | Note |
|---|---|---|---|
| `xxl_api` | 30 r/s | 120 | |
| `xxl_heavy` | 8 r/s | 40 | `/compare`, `/basket/compare`, `/promos/grouped|list|promoted|today`, `/categories/*/items`, `/admin/promos/search` |
| new `xxl_bulk` (`/promos/bulk` only) | 10 r/s | 40 | It is a follow-up of a compare, not an independent heavy call |
| `xxl_suggest` | 40 r/s | 120 | |
| `xxl_img` | 60 r/s | 300 | Or serve images directly from nginx with `expires 7d` |

  Plus:
  - `limit_conn` 60 per IP as a cheap cap on parallel slow requests;
  - add AAAA records and `listen [::]:443` (IPv6 users then get their own key);
  - a daily look at the `http_429` counter (already in `/admin/status`).
- The statement timeout and the C1 fix are what actually protect the DB; the per-IP limits should be loose enough not to hit real people.

### H5 — Link previews show the portal for super.xxl.co.il
- The live HTML of `https://super.xxl.co.il/` (fetched) carries:
  - `<title>XXL — הפורטל שהופך כסף רגיל לכסף חכם</title>`;
  - `canonical https://xxl.co.il/`, `og:url https://xxl.co.il`;
  - `og:image https://xxl.co.il/og-portal.png` (the same for Twitter).
- The super values (title "XXL — השוואת מחירים בסופרמרקט…", `og-super.png`, which exists, 1200×630) are set by an inline script (`index.html:40-66`). WhatsApp, Facebook, X and LinkedIn read the raw HTML and never run it.
- Every link to `/`, `/promos` or `/categories/...` shared on super therefore previews as the portal, with the portal image. The same applies to category pages (their own tags are client-set; pre-render is deferred in the handoff).
- Google renders JS, but the conflicting static canonical (→ xxl.co.il) on every super URL is a needless risk.
- `og:locale he_IL` is present. No hreflang is needed (one language).

### H6 — Blank page on any render error (web)
`main.tsx:22-32` renders the providers and `<App/>` with no error boundary. In React 19 an uncaught render error unmounts the root, so the user sees a white page with no message. The deploy keeps old hashed chunks (`scripts/deploy_frontend.ps1:44` copies and does not wipe), so a stale tab's lazy routes still load. The risk is a runtime error, e.g. an unexpected null in API data.

### M1 — Soft 404
`AppShell`'s `<Routes>` (`App.tsx:59-73`) has no `path="*"`. An unknown URL gets 200 from nginx (fetched: `/this-page-does-not-exist-xyz` → 200, the same 4487-byte HTML) and renders an empty middle. `/sitemap.xml` → 200 HTML (robots.txt correctly points to `sitemap-super.xml`, 209 URLs, and `sitemap-portal.xml`, 5).

### M2 — No request timeout on the web
`axios.create` sets no `timeout` (`client.ts:16-29`). nginx waits up to 120 s (`xxl-api-proxy.conf`). On a slow DB the user sees a spinner for up to two minutes, then the dev-hint error (H1).

### M3 / M4 / M5 — Accessibility
- **M3:** `BasketDrawer.tsx:84-90` is a plain `div`. It has 0 `role="dialog"`, 0 Escape handlers and 0 `focus()` calls (the product modal has all three). The basket is a core journey, so this fails WCAG 2.1.2 / 2.4.3 / 4.1.2 for keyboard and screen-reader users.
- **M4:** the portal input (`PortalPage.tsx:83-91`) has only a rotating placeholder and `outline-none`. The wrapper shows no focus ring, which fails 1.3.1 / 3.3.2 / 2.4.7. It is the first control on xxl.co.il.
- **M5:** there is no skip link anywhere in `web/src` (grep for skip / דלג / `#main`). Pages do have `<main>` landmarks, but IS 5568 reviewers expect a skip link.
- Colour check of the main classes: `text-gray-500` ≈ 4.8:1, `text-emerald-700` ≈ 5.5:1, white on `bg-emerald-700` ≈ 5.5:1 all pass AA. The exceptions are in L3.

### M6 — Report / rating abuse
- `POST /ratings/{id}/report` inserts a row every time ("No uniqueness check on purpose", `ratings.py:259-266`) and queues a mail per report (`:270-275`). Blocks also file a report and mail (`blocks.py:8`).
- The mailer suppresses mail beyond 20 / hour and 60 / day per worker (`mailer.py:51-52`). An abuser with one confirmed account can therefore fill the cap with junk, and the real blacklist and report mails for the rest of the day are only logged. That is a quiet failure of the Apple 1.2 moderation duty.
- `item_code` on `POST /items/{item_code}/rating` is an unvalidated string (`ratings.py:164-167`), so ratings can be attached to non-products.

### M7 — Supabase `portal_email_signups`
- The policy is `for insert to anon, authenticated with check (true)`, with grants to anon and authenticated (9f migration). The columns are plain `text` with no length CHECK. The 500-character truncation is client-side only (`ComingSoonPage.tsx:33-35`).
- With the public anon key, anyone can POST arbitrary-size rows straight to PostgREST in a loop.
- On error the page still shows success (`:38-42`).
- I could not see the Supabase dashboard, so whether other `public` tables exist with weaker RLS is a server / dashboard check (S-10).

### M8 — Python dependencies (pip-audit, 59 packages, 55 advisories in 5 packages)

| Package | Advisories | Fixed in | Reachable? |
|---|---|---|---|
| starlette 1.0.0 | CVE-2026-48710 / -54282 (Host / path not validated when rebuilding `request.url`), CVE-2026-54283 (`form()` limits), CVE-2026-48817 / -48818 (HTTPEndpoint, StaticFiles on Windows) | 1.3.1 | Partly. nginx fixes `Host` to the matched server name, the app does not use `request.url` for redirects, no forms, no StaticFiles. Upgrade anyway: it is the web framework |
| Pillow 12.3.0 | ≈40 (heap overflows, use-after-free, decompression DoS in TIFF / GIF / PDF / BMP / JPEG / JPEG2000) | 13.0.0 | Only in `scraper/gs1_fetch_images` (GS1 originals, a semi-trusted third party). No user uploads |
| python-jose 3.5.0 | CVE-2026-85394 (HMAC key confusion) | none | Not reachable while `alg` is pinned to ES256 (`auth.py:113, 135`). The library is unmaintained, so plan PyJWT |
| ecdsa 0.19.2 | CVE-2024-23342 (Minerva, signing) | none | Not reachable (verify only) |
| anyio 4.13.0 | CVE-2026-63374 / -64847 (IDN TLS, process-pool stderr) | 4.14.2 | Not reachable |

Note that `requirements.txt` pins `python-jose>=3.3.0` and `supabase>=2.0.0` unpinned, so server installs can drift. Check what is installed (S-7).

**Web (`web\`):** 7 moderate, all dev-only. `--omit=dev` → 0. Nothing to do before launch.

### M9 — CSP collects nothing
The policy is shipped as `Content-Security-Policy-Report-Only` on all three web hosts (live headers confirmed). `xxl-csp-web.conf:11` says "No report-uri yet". Without reports, the "CSP enforcement after a clean week" step in the handoff has no evidence to rely on.

### M10 — App crash on render error
`src/app/_layout.tsx` has no `export function ErrorBoundary` (grep for ErrorBoundary / setGlobalHandler in `src/` is empty). Expo Router would render it per route instead of crashing.

### M11 — Stale deployment list
Live `GET /announcements/active?platform=ios` → 204, so SU11A-77 is deployed. Yet `handoff_super.md:3326` says "built, not deployed". The security headers (SU11A-49) and admin.xxl.co.il (SU11A-54) are also live although the list still marks them not deployed. Before marketing, one authoritative "what is live" list is needed.

### M12 — No product URLs
The routes are `/`, `/promos`, `/categories(/:id)`, account pages and the legal pages (`App.tsx:59-73`, `:121-142`). The product view is `ProductDetailModal` with no URL state, so a product cannot be linked from WhatsApp, a campaign or Google.

### M13 — Unknown capacity
2 gunicorn workers (stated in `mailer.py:57`), SQLAlchemy pool 20 + 10 per worker (`db/db.py:36`), 3.8 GiB RAM. A cold `/promos/today` takes about 11 s (handoff, SU11A-60 follow-up), and the first call per category after the 14:30 build 1.5–2.5 s. No load test exists, and none may run against production (CLAUDE.md rule 9).

### Low findings
The evidence for L1–L13 is fully given in the table: each is one line of code or config at the cited place. L1 was confirmed live (`/docs` 200, `/openapi.json` 200).

---

## Checks that need the server

Read-only. Run them as dude over interactive SSH, outside the quiet times (not 03:30–03:45, 04:00–04:30, 10:00 until scrp-cron is inactive, 14:25–15:00). None of them prints a secret or an IP address.

[Bash - server]
```bash
# S-1 backups: remote NAMES and TYPES only (expect a "crypt" type for the DB dumps), latest dumps, last runs
sudo grep -E '^\[|^type' /root/.config/rclone/rclone.conf
ls -lh /var/backups/scrp/ | tail -4
journalctl -u scrp-backup.service --since "-3 days" --no-pager | tail -8
sudo grep -nE 'rclone|pg_dump|gpg|crypt' /usr/local/bin/scrp-backup.sh

# S-2 timers and failed units (scrp-geocode should be disabled / absent)
systemctl --failed --no-pager
systemctl list-timers --all --no-pager | grep -E 'scrp|certbot'
systemctl is-enabled scrp-geocode.timer 2>&1

# S-3 disk, journal, DB size, TLS expiry
df -h / | tail -1
journalctl --disk-usage
sudo -u postgres psql -d xxl_super -Atc "select pg_size_pretty(pg_database_size('xxl_super'))"
sudo certbot certificates 2>/dev/null | grep -E 'Certificate Name|Expiry Date'

# S-4 /stats cost (C1): row estimate (no scan), and how often /stats is called per day
sudo -u postgres psql -d xxl_super -Atc "select relname, reltuples::bigint from pg_class where relname in ('prices','promos','stores')"
journalctl -u scrp-api --since "-1 day" --no-pager | grep -c 'GET /stats '
# Optional, one scan, capped at 20 s (run only at a quiet hour of traffic):
( ulimit -v 1000000; sudo -u postgres psql -d xxl_super -c "set statement_timeout='20s'" -c "\timing on" -c "select count(*) from prices" )

# S-5 rate-limit hits and per-IP peaks (counts only, no addresses)
sudo grep -c 'limiting requests' /var/log/nginx/error.log
sudo awk '$9==429' /var/log/nginx/api-super.access.log | wc -l
sudo awk '{print $1, substr($4,2,20)}' /var/log/nginx/api-super.access.log | sort | uniq -c | sort -rn | head -5 | awk '{print $1" requests in one second from one IP"}'

# S-6 live nginx limits match the repo
sudo nginx -T 2>/dev/null | grep -E 'limit_req_zone|limit_req zone|limit_conn' | sed 's/^\s*//' | sort | uniq -c

# S-7 API process and installed versions (no env printed)
systemctl cat scrp-api | grep -E 'ExecStart|EnvironmentFile' | sed -E 's/(EnvironmentFile=).*/\1<path>/'
~/scrp/venv/bin/pip list 2>/dev/null | grep -iE '^(starlette|fastapi|pillow|python-jose|anyio|supabase|ecdsa) '
sudo -u postgres psql -Atc "show max_connections"

# S-8 logs: retention as documented (nginx 14 days, journald 30 days)
grep -E 'rotate|daily' /etc/logrotate.d/nginx
cat /etc/systemd/journald.conf.d/scrp.conf

# S-9 what is live (for M11): last pulled commit and the applied migrations' tables
git -C ~/scrp log -1 --format='%h %ad %s' --date=short
sudo -u postgres psql -d xxl_super -Atc "select table_name from information_schema.tables where table_schema='public' and table_name in ('app_announcements','item_categories','promo_curation','stats_daily','admin_audit','category_suggestions') order by 1"
```

S-10 (Supabase dashboard, by hand):
- Table Editor: list every `public` table and its RLS state and policies.
- Auth → Providers → Email: "Confirm email" ON and "Secure email change" ON (L7).
- Auth → Rate limits: the current values.
- Confirm that no service-role key is used anywhere except the server `.env`.

---

## Not checked and why

- **Browser and device behaviour** (very long Hebrew strings, RTL layout at 375 px, offline mode, location-denied flow, session expiry in a live tab, the camera scan): the task is static and read-only, with no logins. These need a manual pass on a phone and in a browser. The app code shows Hebrew messages and timeouts for these paths, but nothing was exercised.
- **Real link-preview rendering** on WhatsApp / Facebook: inferred from the raw HTML the crawlers receive (H5), not tested in the apps.
- **Load and capacity:** load tests are forbidden on production (rule 9). See M13.
- **Supabase dashboard** (RLS on tables outside the repo, auth settings, rate limits): no access; S-10.
- **Server state** (backup script, rclone remote, installed nginx, gunicorn flags, failed units, disk): no server access in this session; S-1 to S-9.
- **Authenticated API behaviour** (ratings, reports, deletion, admin with 2FA): no logins allowed; reviewed from code only.
- **SQL injection:** about 90 f-string SQL sites were listed and sampled, not every one was proven. Every sampled interpolation was a constant or a generated `:param` placeholder.
- **The flights vertical** (`xxl-flights`, fly.xxl.co.il): out of scope (super / portal / admin only), apart from the shared nginx zones.
- **pip-audit severity:** pip-audit does not grade severity. The grading above is mine, based on reachability.
- **Mobile typecheck and tests:** not run (6–8 min tsc; Dude runs it per CLAUDE.md).
