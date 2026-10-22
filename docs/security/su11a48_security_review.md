# SU11A-48 — Security review (read-only)

Date: 22 Oct 2026. Scope: `C:\scrp` (API, scrapers, web, scripts, deploy, docs), `C:\scrp\xxl-super-mobile`, and `C:\scrp\xxl-flights` (shared-server items only), plus the production server `185.229.226.190` (read-only ssh, no sudo) and the public hosts.

No code, config, server or data was changed. Secrets are referred to by variable NAME and a masked value only (first 4 characters + `****`).

## Executive summary

1. **Highest risk is availability, not data theft.** One anonymous request can make the API fetch prices for ~30K barcodes:
   - Affected: `/compare`, and `/search` with `city` / `chain` / `group_by=store`. The web's default view uses this path.
   - Nothing stops it: there is no rate limiting on any host, and `statement_timeout` is 0 for the app role.
   - Result: the 3.8 GiB server, which holds the DB, the API and flights, can be stalled or pushed to OOM. Fixes are small (F-01, F-02).
2. **Authentication and authorization are sound.**
   - Every id-taking endpoint checks ownership.
   - JWTs are pinned to ES256 with an audience check.
   - The admin gate fails closed.
   - All SQL is parameterised; dynamic fragments are whitelisted.
3. **No real secret was ever committed** in the three repos' full history (gitleaks). The tracked keys are Supabase anon keys (role `anon`), which are public by design.
4. **The platform is mostly hardened:**
   - SSH is key-only in the main config, and fail2ban and unattended-upgrades are active.
   - Postgres listens on localhost only (the 22 Oct fix is confirmed).
   - TLS 1.2/1.3 only, and `.env` files are mode 600.
5. **The gaps are hygiene:**
   - no security headers or CSP, and nginx shows its version;
   - a world-writable web-asset directory;
   - outdated server Python packages (starlette, pillow, cryptography);
   - one DB role shared by both verticals, and the API runs as the sudo-group login user;
   - backups uploaded unencrypted (to verify).

   On compliance, the Data Security Regulations documents are missing: security procedure, incident procedure, periodic review.

## Status (updated in SU11A-49, 22 Oct 2026)

| Finding | Status | Where |
|---|---|---|
| F-01 | **Fixed, pending deploy.** API-only 15 s `statement_timeout` (libpq startup option, set in `api/main.py`; scripts and timers unaffected), timeout answers `503 {"code":"query_timeout"}`, old path prices at most 1,000 candidates (`api/routers/search.py` `cap_candidates`) | scrp `fix(security): SU11A-49 ...` |
| F-02 | **Fixed, pending deploy.** nginx rate-limit zones + 429 JSON (`deploy/nginx/`) | runbook `docs/security/su11a49_runbook.md` |
| F-03 | **Fixed, pending deploy.** Security headers on all hosts, CSP Report-Only on xxl / super / fly, `server_tokens off`; http-level `ssl_protocols` edited in the runbook. CSP enforcement: later session | same runbook |
| F-04 | **Fixed, pending deploy.** `scripts/deploy_frontend.ps1` sets dirs 755 / files 644 after upload; one-time chmod in the runbook | same runbook |
| F-05 | **Fixed, pending deploy.** JWKS refetch at most once per 60 s; failed fetch backs off 5 s | `api/auth.py` |
| F-06 to F-23 | Open (unchanged) | — |
| Compliance gaps | **Drafts written (SU11A-49), for Dude / advisor review:** `docs/compliance/database_definition_he.md`, `security_procedure_he.md`, `incident_procedure_he.md`, `periodic_review_he.md` | — |

## Findings

Severity is CVSS-style: attack vector, privileges needed, and impact on confidentiality / integrity / availability (C/I/A). Effort: S under half a day, M one to two days, L more.

### Quick wins (High, effort S)

| ID | Sev | Area | Where | Description | Exploit scenario | Fix | Effort |
|---|---|---|---|---|---|---|---|
| F-01 | **High** (network, no auth, low complexity, A:H) | API / DB | `api/routers/search.py:37` (`_build_result` → `fetch_prices` on ALL candidates); `db/query.py:169` (no cap); `db/db.py:23` (no timeout); DB role `scrp_app` `statement_timeout = 0` | The old search path (`/compare`, and `/search` with city / chain / group_by=store / engine=v1) loads prices for EVERY matching barcode before paginating. A 2-letter query matches ~30K barcodes: `ים` 29,642, `לי` 31,233, `10` 8,327 of 171,122 items. They are joined against `prices` (7.84M rows) and then held in Python. No DB statement timeout. The gunicorn `--timeout 120` does not stop a sync handler running in the UvicornWorker threadpool. | `curl 'https://api-super.xxl.co.il/compare?q=%D7%99%D7%9D'` in a loop of a few parallel requests. Postgres and both API workers saturate; memory climbs on a 3.8 GiB box shared with the DB, the loader and flights. | (1) API-only DB timeout: in `api/dependencies.get_db` run `SET statement_timeout = '15s'` (or engine `connect_args={"options": "-c statement_timeout=15000"}` behind an env var only the API unit sets). Not role-wide: the loader and build run as the same role. (2) Cap candidates before `fetch_prices`, e.g. the top 1,000 by relevance tier (`ORDER BY tier, item_code LIMIT`). (3) When the match count is over the cap, price only the capped set and keep `total_matches` as the true count, so the page still works. | S |
| F-02 | **High** (network, no auth, A:H; cost) | nginx (shared) | `/etc/nginx/sites-available/*` (no `limit_req` / `limit_conn` anywhere); flights `backend/api/routers/search.py:152` | No rate limiting on any host or in the apps. Expensive anonymous endpoints: `/compare`, `/search` (old path), `/basket/compare` (25 barcodes, all stores), `/promos/grouped` (`limit` up to 5000), `/suggest`. Flights: anonymous (guest) `/api/search`, `/api/explore` and `/api/flexible-dates` each make paid SerpApi calls. | A single client scripts F-01, or burns the monthly SerpApi quota in minutes, so flights search fails for everyone until the quota resets. | `http {}`: `limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s; limit_req_zone $binary_remote_addr zone=heavy:10m rate=2r/s; limit_req_zone $binary_remote_addr zone=serp:10m rate=10r/m; limit_req_status 429;`. Then: api-super `location /` `limit_req zone=api burst=40 nodelay;`; a `location ~ ^/(compare\|search\|basket/compare\|promos/grouped)` with `limit_req zone=heavy burst=10 nodelay;` (same proxy settings); fly `location /api/` `limit_req zone=serp burst=5;` (or app-side per-IP and per-user counters on the SerpApi routes). Mobile NAT / CGNAT: keep bursts generous and watch for 429s. | S |

### All findings by severity

| ID | Sev | Area | Where | Description | Exploit scenario | Fix | Effort |
|---|---|---|---|---|---|---|---|
| F-01 | High | API / DB | see above | Unbounded anonymous price fetch, no statement timeout | see above | see above | S |
| F-02 | High | nginx | see above | No rate limiting; paid SerpApi behind anonymous flights routes | see above | see above | S |
| F-03 | Medium (network, UI needed, I:L/C:L) | nginx / web | all four server blocks; `/etc/nginx/nginx.conf:21` (`# server_tokens off;`) | No HSTS, X-Content-Type-Options, frame-ancestors / X-Frame-Options, Referrer-Policy, Permissions-Policy or CSP on xxl.co.il, super, fly or api-super (verified with `curl -sI`). `Server: nginx/1.24.0 (Ubuntu)` is disclosed. | The account pages (`/account/delete`, sign-in) can be framed for clickjacking. With no HSTS, a first visit over http on hostile Wi-Fi can be stripped. With no CSP, any future XSS has no second line of defence. | `server_tokens off;` in `http {}`. Per 443 server: `add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always; add_header X-Content-Type-Options nosniff always; add_header Referrer-Policy strict-origin-when-cross-origin always; add_header Permissions-Policy "camera=(), microphone=(), geolocation=(self)" always; add_header X-Frame-Options DENY always;`. **nginx rule:** a `location` with its own `add_header` (super's static-asset block has `Cache-Control`) drops all server-level headers, so put the set in a snippet and `include` it in both. CSP: see "CSP proposal" below, Report-Only first. | S (headers), M (CSP) |
| F-04 | Medium (local, low privileges, I:H on served JS) | server | `/var/www/super.xxl.co.il/assets` mode `drwx---rwx` (707), files 664 | The directory holding the JS bundle that super.xxl.co.il AND xxl.co.il serve is world-writable. Probable cause: scp from Windows preserving odd modes. | Any other local account (`www-data` after an nginx or PHP-style bug, `postgres` after a DB escape) replaces `index-*.js`. Every visitor then runs attacker JS that can read the Supabase session from localStorage. | `chmod 755 /var/www/super.xxl.co.il/assets && chmod 644 /var/www/super.xxl.co.il/assets/* /var/www/super.xxl.co.il/*` (dude owns them, no sudo). Make `scripts/deploy_frontend.ps1` finish with `ssh ... "chmod -R u=rwX,go=rX /var/www/super.xxl.co.il"`. Also delete the stray `og-super.png.png` (5.6 MB). | S |
| F-05 | Medium (network, no auth, A:L–M) | API auth | `api/auth.py:50-66` | A JWT whose `kid` is not cached triggers a full JWKS refetch (10 s timeout) under a global lock. There is no cooldown or negative cache. | An anonymous client sends `Authorization: Bearer <forged header with random kid>` to any endpoint (or `/items/{code}/ratings`, soft auth) at high rate. Every request makes an outbound call to Supabase, serialised behind one lock, tying up threadpool workers. Supabase may then throttle the server's IP, and legitimate key-rotation refreshes fail. | Refresh at most once per 60 s (store `last_refresh`); on a miss inside the window, answer 401 without fetching. Optionally pre-load the JWKS at startup. | S |
| F-06 | Medium (network; library advisories) | deps (server) | server venvs: `~/scrp/venv` (Python 3.12.3), `~/xxl-flights/venv` | pip-audit on the installed packages (`pip freeze` from the server).<br>**scrp:** starlette 1.0.0 (5 advisories, incl. Host-header URL reconstruction CVE-2026-48710 and path validation CVE-2026-54282; fix ≥1.3.1); pillow 12.3.0 (24; the GS1 fetcher decodes remote images; fix 13.0.0); cryptography 48.0.0 (4, incl. bundled OpenSSL GHSA-537c-gmf6-5ccf); python-jose 3.5.0 (HMAC/asymmetric-key confusion CVE-2026-85394, no fix; NOT exploitable here because `algorithms=["ES256"]` is pinned, `api/auth.py:104`); pyjwt 2.12.1 (15; pulled in by `supabase`, not used for our verification); urllib3, anyio, h2, hpack, pyasn1, python-multipart (no form endpoints), certifi, fsspec, multidict.<br>**flights:** starlette 0.38.6 (7, incl. multipart DoS CVE-2024-47874 / CVE-2025-54121), python-jose 3.5.0, python-dotenv 1.0.0, anyio, cryptography 49.0.0, certifi. | Starlette Host / path issues can be used for cache poisoning or redirect tricks; Pillow parser bugs are reachable through a malicious image from the GS1 media endpoint. | Bump `fastapi` + `starlette` together (scrp to a FastAPI release on starlette ≥1.3.1; flights off 0.38.x), `Pillow>=13.0.0`, `cryptography>=50`, `urllib3>=2.8`, `anyio>=4.14.2`. Pin `python-jose` and plan a move to `joserfc` or PyJWT ≥2.15 for verification. Run the test suite and the API smoke checks after. | M |
| F-07 | Medium (post-compromise blast radius, C:H/I:H) | DB / host | Postgres roles: only `postgres` and `scrp_app`; `scrp_app` has 24 privileges on schema `flights`; `scrp-api` and `flights-api` units run as `User=dude` (group `sudo`) | Both internet-facing APIs, the loader, the build and the sweep share one DB role. Both APIs run as the interactive login user, which is in the sudo group and owns `~/scrp/.env`. That file holds `SUPABASE_SERVICE_ROLE_KEY`, the DB URL, SMTP and Google keys. | An RCE in the smaller flights API (or super) gives read/write on every user table in both verticals. It also gives the Supabase service-role key (full admin over the shared auth project) and dude's files, including `~/.ssh` and `~/google_compare`. | (1) A separate DB role for flights with grants on `flights.*` (+ the shared `users` columns it needs). (2) A read-mostly role for the super API (SELECT on catalog tables; writes only on user tables) distinct from the loader role. (3) Run the APIs as dedicated system users (`scrp-api`, `flights-api`) with their own `EnvironmentFile` (mode 600) and `ProtectHome=read-only`, `NoNewPrivileges=yes`, `PrivateTmp=yes` in the units. Keep the service-role key only in the API's env (and the sweep's). | M–L |
| F-08 | Medium (third-party storage, C:H if the B2 account is compromised) | backups | `/usr/local/bin/scrp-backup.sh` (`rclone copy "$DUMP" b2:xxl-scrp-backups/daily/`) | Full `pg_dump` (user emails, ratings, saved baskets, flights rows) is uploaded through remote `b2`. The handoff says it is the native B2 backend. Unless that remote is a `crypt` wrapper, the dumps sit unencrypted at Backblaze. The GS1 image backup uses the same remote, which is fine for public images. | A leaked B2 application key (it lives in root's rclone config on the same box) or a B2 account takeover gives the whole user database. | Dude: check the remote type (sudo list below). If it is `b2`, add an rclone `crypt` remote over `b2:xxl-scrp-backups/daily-enc/` (keep the password offline as well), switch the script to it, and let the old `daily/` objects age out via the existing 180-day lifecycle. Document a test restore. | M |
| F-09 | Low (auth'd, A:L) | API | `api/routers/ratings.py:248` (report), `api/routers/blocks.py` (block), `api/mailer.py:51` | One account can file unlimited reports on any rating (no per-user / per-rating dedupe, by design for "different users"). Each report queues a moderation mail. The mail caps (20/h, 60/day per worker) are shared with blacklist auto-hide alerts. | A user files 100 reports. `rating_reports` grows, the moderation queue fills, and the next real blacklist alert is suppressed ("throttled") for the rest of the hour or day. | Unique `(rating_id, reporter_user_id)` for `source='user'` (or a 24 h window), and a per-user cap (e.g. 20 reports/day). Optionally send report mails as a digest. | S |
| F-10 | Low (auth hardening) | API auth | `api/routers/ratings.py:415-433`; `api/auth.py:104` | The admin gate trusts the token's `email` claim. That is safe only while Supabase "Confirm email" and "Secure email change" stay on; the flights handoff says confirmation is required. The issuer (`iss`) is not checked, and `exp` is not required (python-jose only checks it when present; Supabase always sets it). | If email confirmation were ever turned off, anyone could sign up as an allow-listed address that has no account yet and get moderation powers. | Allow-list user ids (`ADMIN_USER_IDS`) instead of, or in addition to, emails. Add `issuer=f"{SUPABASE_URL}/auth/v1"` and `options={"require_exp": True, "require_sub": True}` to `jwt.decode`. | S |
| F-11 | Low (auth'd / anon, A:L) | API input limits | `api/routers/saved_baskets.py:19-26`; `api/routers/favorites.py:16`; `api/routers/ratings.py` path `item_code`; `api/routers/basket.py:23,28-29`; `api/routers/search.py:144-145`; `api/routers/promos.py:62`, `db/query.py:1649` | No max length or count on: basket `name`, `items` (list size), item `name`, `barcode`, `qty`; favorites / ratings `item_code` (any string, not checked against `items`); basket `quantity`, `chain_ids`, `cities`; `/search` `city` / `chain` lists; `/promos/grouped` `q` (no max_length, and `%`/`_` not escaped in the ILIKE). The only global limit is nginx's default 1 MB body. | A signed-in user stores thousands of 1 MB baskets, or ratings on junk "item codes"; an anonymous client sends 500 `city=` params. Storage growth and slow queries, nothing more. | Pydantic `Field(max_length=…)` / `conlist(max_length=…)`: basket name 100, items 200, qty 1–999, barcode `^\d{4,14}$` (or the item_code pattern the catalog uses), city/chain lists ≤20, promos `q` max 100 with `_like_escape`. Per-user caps: 50 baskets, 500 favorites. | S |
| F-12 | Low (privacy / mixed content) | web | `web/src/pages/HomePage.tsx:88`, `web/src/utils/city.ts:55` | City auto-detect calls `http://ip-api.com/json/...` from an https page. Browsers block it as mixed content, so in production it always falls back. If it ever loaded (e.g. via https), it would send every visitor's IP to an undisclosed third party with no consent. ip-api's free tier also forbids commercial use. | — (currently blocked by the browser) | Remove the call, or replace it with a server-side lookup (nginx GeoIP / the API) that the privacy policy covers. | S |
| F-13 | Low | web deps | `web/package.json` | Runtime advisories: `axios` 1.15.1 (prototype-pollution gadgets; the follow-redirects / form-data advisories are Node-adapter only) and `react-router-dom` 7.14.2 (advisories concern framework / SSR mode; this is a SPA). `tailwindcss`, `postcss` and `autoprefixer` are listed under `dependencies`, so `npm audit --omit=dev` reports build tooling as runtime. | Low: the bundle only talks to our API and Supabase. | `npm i axios@latest react-router-dom@latest`; move tailwind / postcss / autoprefixer to `devDependencies`; `npm audit fix` for vite (dev server only). | S |
| F-14 | Low | mobile deps | `xxl-super-mobile/package-lock.json` | 34 advisories (1 critical `shell-quote`, 27 high, 6 moderate), all in build tooling (expo CLI, metro, node-forge in code signing, xcode, image-size), except `expo-router` → `query-string` 7.1.3 → `decode-uri-component` 0.2.2 (DoS on a malformed deep link; affects the app only). | A crafted `xxlsupermobile://` link could freeze the app. | Follow the next Expo SDK patch release (`npx expo install --fix`) at build 10; do not run `npm audit fix --force` (it downgrades Expo). | M |
| F-15 | Low (needs confirmation) | SSH | `/etc/ssh/sshd_config` (readable lines); `/etc/ssh/sshd_config.d/50-cloud-init.conf` (not readable without sudo) | Readable config: `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitRootLogin prohibit-password`, `X11Forwarding yes`. The cloud-init drop-in is read FIRST and can override `PasswordAuthentication` (cloud-init can set it to `yes`); the effective value needs `sshd -T`. fail2ban `sshd` jail is active. | If the drop-in enables passwords, SSH is open to password guessing (fail2ban slows it). | `sudo sshd -T` (list below). Set `PermitRootLogin no`, `X11Forwarding no`, `MaxAuthTries 3`; make the drop-in say `PasswordAuthentication no`. | S |
| F-16 | Low | repos | `.gitignore` of all three repos | scrp and flights do not ignore `*.pem`, `*.jks`, `*.keystore`, `*.p12`, `*.p8`, `google-services.json`, `GoogleService-Info.plist`, `credentials*.json`, `service-account*.json`. Mobile does not ignore `.env` (only `.env*.local`), `*.keystore`, `google-services.json`. None of these was ever committed (full-history file-name check). | A future Play service-account JSON or upload keystore gets committed by `git add -A`. | Add those patterns. | S |
| F-17 | Low | flights API | `xxl-flights/backend/main.py:9-10` | CORS `allow_credentials=True` with `http://localhost:5173` in the production allow-list, plus `allow_methods/headers=["*"]`. Auth is a bearer header, not cookies, so credentials mode buys nothing. | A page served from a developer's localhost:5173 can make credentialed calls. Negligible today. | Drop `allow_credentials`, and take the localhost origin from an env var that only dev sets. (super's API is already env-driven: production answers only xxl.co.il, www and super; fly and localhost get no ACAO.) | S |
| F-18 | Low (privacy) | API logging | `api/routers/search.py:258, 295` (`exc_info=True`) | A v2 or suggest failure logs a traceback that can include SQL parameters, i.e. the search text, in journald (30 days). This is already noted in the privacy inventory. Search text is in the access-log URL anyway. | — | Log the exception class and a fixed message only, or redact `params` in a logging filter. | S |
| F-19 | Info | API | `https://api-super.xxl.co.il/docs`, `/redoc`, `/openapi.json` (200); `/admin/ratings/pending` → 401 anonymous, 404 for signed-in non-admins | API docs are public and the admin route is visible in the OpenAPI schema. The 404 hiding only works for signed-in callers. | Recon only. | Optionally `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` in production (env flag), or `include_in_schema=False` on the admin routes. | S |
| F-20 | Info | TLS | `/etc/nginx/nginx.conf:33` | The global `ssl_protocols TLSv1 TLSv1.1 TLSv1.2 TLSv1.3` is overridden in every server by certbot's `options-ssl-nginx.conf` (TLS 1.2/1.3). Verified: TLS 1.1 handshake refused; certificates valid to 27 Dec 2026; certbot timer active. | — | Set the global line to `TLSv1.2 TLSv1.3` for tidiness. | S |
| F-21 | Info | OS | server | Ubuntu 24.04.4, kernel 6.8.0-147; 64 packages upgradable (0 from the security pocket); `unattended-upgrades` active with daily periodic settings. | — | Routine `apt upgrade` + reboot in a quiet window. | S |
| F-22 | Info | mobile | `xxl-super-mobile/app.json`, `src/lib/supabase.ts` | Good: session in SecureStore (chunked); `detectSessionInUrl: false`; no cleartext config (Expo release defaults: cleartext off, iOS ATS on); production profile `developmentClient: false`; only the anon key in `extra` (masked `eyJh****`, role `anon`); no token logging. Note: Expo leaves `android:allowBackup` at its default `true`. SecureStore values are Keystore-bound and are not restorable, so the effect is small. | — | Optional: `"android": {"allowBackup": false}` at the next build. | S |
| F-23 | Info | server ops | `/usr/local/bin/xxl-deploy-webroot.sh` | The root-run `cp -r /home/dude/fly_deploy/*` copies dude-controlled content, including symlinks, into the www-data web root. www-data cannot read dude's home, so the impact is limited. | — | `cp -r --no-dereference` is already the default; add `find /var/www/fly.xxl.co.il -type l -delete` after the copy. | S |
| F-24 | Resolved | DB | Postgres | The 22 Oct 2026 hardening is in place: `listen_addresses='localhost'` (verified `ss -ltn`: `127.0.0.1:5432` only), the `pg_hba` 0.0.0.0/0 line disabled (backup `pg_hba.conf.bak-2026-10-22`). DB `ssl on`, `password_encryption scram-sha-256`; app role `scrp_app` is not superuser / createrole / createdb / bypassrls. | — | — | — |

## Authorization / IDOR review

| Endpoint | Auth | Ownership check | Verdict |
|---|---|---|---|
| `POST/GET /baskets` | required | INSERT with caller id; list `WHERE user_id = caller` | OK |
| `GET/PUT/DELETE /baskets/{id}` | required | `_owned_or_404` (other user's id → 404) before every read / update / delete | OK |
| `POST/DELETE /favorites/{barcode}`, `GET /favorites` | required | every statement `WHERE user_id = caller` | OK (F-11 limits) |
| `POST /items/{code}/rating` | required + ban check (+ terms flag) | upsert keyed `(user_id, item_code)` | OK |
| `GET /items/{code}/ratings` | soft (never 401/503) | public rows; author id never returned; `is_mine` computed server-side; `private, no-store` when Authorization is present | OK (F-05 applies) |
| `GET /me/ratings` | required | `WHERE r.user_id = caller` | OK |
| `POST /ratings/{id}/report` | required + ban check | any rating, by design (flags only) | OK (F-09 abuse) |
| `POST /ratings/{id}/block-author` | required | author resolved server-side, never returned; self-block → 400 | OK |
| `GET /me/blocks`, `DELETE /me/blocks/{id}` | required | `WHERE blocker_id = caller` (DELETE included) | OK |
| `GET/POST /me/terms` | required | `users.id = caller`; only the current version accepted | OK |
| `DELETE /account` | token verified, no deleted-check; `iat` ≤ 300 s; protected-id list | deletes only the caller's rows (users cascade + flights rows) | OK |
| `GET /admin/ratings/pending`, `POST /admin/ratings/{id}/moderate`, `/ban-author` | `require_admin`: email allow-list, **fails closed** (unset → nobody), 404 to non-admins | — | OK (F-10 hardening) |
| `/search`, `/compare`, `/suggest`, `/product/*`, `/basket/compare`, `/promos/*`, `/stores*`, `/cities`, `/chains`, `/coverage`, `/freshness`, `/stats`, `/health` | none | no user data; `/product/{barcode}/image` path built only after `^\d{8,14}$` (no traversal) | OK (F-01/F-02 cost) |
| flights `GET /api/me` | optional | returns the caller's own tier | OK |
| flights `/api/search`, `/api/explore`, `/api/flexible-dates`, `/api/price-calendar`, `/api/airports` | optional (tier) | no user-owned objects; `flights.alerts` / `saved_searches` have no endpoints yet | OK (F-02 cost) |

**Injection:** every `text(f"...")` in `api/` and `db/` was traced.
- What is interpolated is only module constants, generated parameter names (`:w0n`, `:c3`), or values from whitelists:
  - `moderation.py:89` status from a fixed dict;
  - `saved_baskets.py:113` fixed clause strings;
  - `query.py:1760` `ORDER BY` from `_PROMO_SORTS`, with `sort` also regex-validated at `promos.py:64`;
  - `stores.py:77` `live_store_clause` output.
- Every value is a bound parameter.
- LIKE: escaped with `ESCAPE '\'` in search v1 / v2 and suggest. The exception is `/promos/grouped` `q` (F-11): wildcards only, no injection.
- Regex: user words go through `re.escape` before Postgres `~`.
- Python `re` on user text: only literal, escaped blacklist terms. No ReDoS-prone pattern found.

**Error handling:** unhandled errors return FastAPI's plain `Internal Server Error` (no stack trace or SQL). `ApiCodeError` answers `{"code": …}`. 422 bodies echo only the caller's own input.

**Mailer:** recipient fixed from env. Subjects hold only ids. Headers are built by `EmailMessage`, which rejects CR/LF in header values, so there is no header injection. User content (comment ≤500 chars, report reason) goes in the plain-text body only.

**CORS:**
- super API: production allow-list is `https://xxl.co.il`, `https://www.xxl.co.il`, `https://super.xxl.co.il` (verified by Origin probes), with no `allow-credentials`.
- flights: see F-17.

**Logging vs privacy inventory:** consistent with `docs/store_privacy_inventory.md` §6. The only new note is F-18.

**Supabase from the clients (anon key):**

| Client | Table / API | Operation | RLS it REQUIRES (Dude to verify in the dashboard) |
|---|---|---|---|
| web `src/pages/ComingSoonPage.tsx:30` | `public.portal_email_signups` | INSERT `{email, vertical, user_agent, referrer}` | RLS **enabled**. Policy: `FOR INSERT TO anon, authenticated WITH CHECK (true)` (optionally `length(email) <= 254`). **No SELECT, UPDATE or DELETE policy for anon or authenticated** (the client does not read back: no `.select()`). Also a CHECK on column lengths, and consider a unique `(email, vertical)` so repeat inserts fail. Spam: no rate limit beyond Supabase's own. |
| web / mobile / flights | Supabase Auth (`signUp`, `signInWithPassword`, `updateUser`, reset) | auth API | Dashboard: "Confirm email" ON, "Secure email change" ON (F-10 relies on both), minimum password length / leaked-password check per plan. |
| — | every other `public` table | none | Security Advisor should show no table exposed to `anon` with RLS off. |

- `user_metadata` (terms consent) is user-editable through `updateUser`. It is used only as the user's own consent record, never for authorization. OK.
- Service-role key: only in `api/supabase_admin.py` (server, env `SUPABASE_SERVICE_ROLE_KEY`), never logged. It does not appear in any client bundle or repo history (gitleaks + grep).

## Web and mobile

**Web:**
- XSS sinks: none. No `dangerouslySetInnerHTML`, `innerHTML`, `eval`, `document.write`, `href`/`window.open` from data.
- Review comments render as React text (`ReviewsPanel.tsx:177`, `MyRatingsPage.tsx:108`).
- Token storage: supabase-js default, localStorage. That is acceptable for a SPA, but it makes F-04 and a CSP (F-03) matter.
- Third-party scripts: Google Fonts CSS, GA4 `gtag.js` (consent-gated), ip-api (F-12).
- `index.html` has one inline script (SEO host fix).

**Mobile:** see F-22.
- Deep links: scheme `xxlsupermobile` (expo-router). Reachable screens take only `barcode` / `tab` / `email` params, which are used as display or API path values. There is no destructive action on open.
- Android components: generated at build (CNG, `/android` gitignored). Only the main activity with the launcher and scheme intent filters is exported.
- Blocked permissions are listed in `app.json`.

### CSP proposal (start as `Content-Security-Policy-Report-Only` on super / xxl.co.il)

```
default-src 'self';
script-src 'self' 'sha256-LO2icOS4USz6HYBRrTSoEr8dKWyC8lMuaisAr14JTZA=' https://www.googletagmanager.com;
connect-src 'self' https://api-super.xxl.co.il https://dwohlwmiejgjlsbuegeu.supabase.co wss://dwohlwmiejgjlsbuegeu.supabase.co https://*.google-analytics.com https://*.analytics.google.com https://www.googletagmanager.com;
img-src 'self' data: https://api-super.xxl.co.il https://*.google-analytics.com https://www.googletagmanager.com;
style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
font-src 'self' https://fonts.gstatic.com;
frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'
```

- **Inline-script hash:** taken from the current `web/dist/index.html`. Recompute whenever that inline script changes: `openssl dgst -sha256 -binary | base64` over the exact script body.
- **GA4:** loads only after consent; the policy allows its hosts either way, which is harmless before consent.
- **`style-src 'unsafe-inline'`:** kept for injected toast styles.
- **Rollout:** switch from Report-Only after a week without violations.
- **Other hosts:** api-super needs only the F-03 headers; fly needs its own policy (its own bundle and the GA4 hosts).

## Server / platform (read-only ssh, no sudo)

| Check | Result |
|---|---|
| OS / kernel | Ubuntu 24.04.4 LTS, `6.8.0-147-generic`; up 2 days |
| Upgrades | 64 upgradable, 0 from `-security`; `20auto-upgrades` periodic update + unattended-upgrade = 1; `unattended-upgrades` active |
| fail2ban | active; jail `sshd` (nftables, systemd backend) |
| sshd (readable) | `PermitRootLogin prohibit-password`, `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `X11Forwarding yes`; drop-in `50-cloud-init.conf` unreadable (F-15) |
| Listening | public: 22, 80, 443 (v4 + v6). Local only: 5432 (Postgres), 8000 (scrp-api), 8001 (flights-api), 53 (resolved). Matches UFW 22/80/443 from the handoff (UFW status itself needs sudo) |
| Secrets files | `~/scrp/.env` 600 dude; `~/xxl-flights/backend/.env` 600 dude (`~/xxl-flights/.env` does not exist); `~/google_compare` 700; `~/pin_tool_data` 700; home 750 |
| Timers | scrp-backup 04:00, account-sweep 05:30, scrp-cron 10:00, search-items 14:30, gs1-fetch Sun 14:00, gs1-images-backup Sun 17:00, certbot, apt; `scrp-geocode.timer` no longer listed (disabled as planned); dude has no crontab |
| Web roots | `/var/www/super.xxl.co.il` dude:dude 755 with `assets/` **707** (F-04); `/var/www/fly.xxl.co.il` www-data 755; `/var/www/html` root |
| Backups | `/var/backups/scrp` 750 postgres; the script uploads to remote `b2:` (F-08) |
| Units | `scrp-api`: gunicorn, 2 UvicornWorkers, `--timeout 120`, `User=dude`, `EnvironmentFile`; `flights-api`: uvicorn, `User=dude` (F-07) |
| DB settings (read-only query as the app role) | `statement_timeout 0`, `idle_in_transaction_session_timeout 0` (F-01), `ssl on`, scram-sha-256, `max_connections 100`, `log_statement none`; roles: `postgres`, `scrp_app` only |

**Public (from this PC):**

| Host | HSTS | nosniff | Frame protection | Referrer-Policy | Permissions-Policy | CSP | Server header |
|---|---|---|---|---|---|---|---|
| xxl.co.il | — | — | — | — | — | — | `nginx/1.24.0 (Ubuntu)` |
| super.xxl.co.il | — | — | — | — | — | — | same |
| fly.xxl.co.il | — | — | — | — | — | — | same |
| api-super.xxl.co.il/health | — | — | — | — | — | — | same |

- **`/.git/HEAD`, `/.git/config`, `/.env`, `/backend/.env`:**
  - api-super: **404**.
  - xxl, super, fly: **200**, but the body is the SPA `index.html` (`try_files` fallback), not the file. No exposure. A 404 for dot-paths would remove the scanner noise: `location ~ /\. { return 404; }`.
- **http → https:** 301 on all hosts.
- **TLS:** 1.2 and 1.3 only.

## Scan outputs

All tools ran from a throwaway location (`%TEMP%\…\scratchpad\sec48`): a venv for the Python tools and a downloaded release binary for gitleaks. Nothing was added to the repos.

| Tool (version) | Target | Result | Real findings |
|---|---|---|---|
| gitleaks 8.28.0 (`git` mode, full history, `--redact`) | scrp (506 commits) | 1 | 0. `tests/test_account_delete.py:27-28` `SECRET` = `sb_s****`, `LEGACY` = `eyJh****`: fake test fixtures (contain "test"). |
| | xxl-super-mobile (55) | 1 | 0. `app.json:73` `supabaseAnonKey` `eyJh****` (role `anon`, public by design). |
| | xxl-flights (38) | 2 | 0 secret. `frontend/.env.production:2`, `frontend/.env.development:2` `VITE_SUPABASE_ANON_KEY` `eyJh****` (role `anon`). Note: these `.env.*` files are tracked; keep only public values in them. |
| history file-name scan | 3 repos | — | No `.pem`, `.key`, `.jks`, `.keystore`, `.p12`, `.p8`, `google-services*`, `GoogleService-Info*`, credentials / service-account JSON or rclone config ever committed. `.env` is ignored in scrp and flights (F-16 for the rest). |
| pip-audit 2.10.1 (`--no-deps` on the server's `pip freeze`) | scrp venv (85 packages) | 66 unique advisories in 15 packages | F-06 |
| | flights venv (34 packages) | 15 unique in 7 packages | F-06 |
| npm audit (npm 11.18.0) | web `--omit=dev` / full | 16 (15 high, 1 moderate) / 21 | Runtime: axios, react-router-dom (F-13). The rest are build tools listed under `dependencies`, or vite / eslint (dev). |
| | mobile `--omit=dev` / full | 34 (1 critical, 27 high, 6 moderate) / same | Build tooling, except expo-router → query-string → decode-uri-component (F-14). |
| | flights frontend `--omit=dev` / full | 0 / 13 (10 high, 3 moderate) | 0 runtime (all tailwind / postcss / vite tooling). |
| bandit 1.9.4 | scrp `api db scraper scripts` | 148 (2 high, 18 medium, 128 low severity) | 0. B608 ×57: all traced, parameterised or whitelisted (see Injection). B314 ×8: stdlib `ElementTree` on chain-portal XML (no external-entity expansion in stdlib; data from mandated government feeds). B324 ×2: md5 used as a content hash, not security. B310 ×2: fixed Nominatim URL (retired). B108 ×3: `/tmp` default `--out` for ops scripts. B105 ×2: empty form field / regex. B101 / B110 / B112 / B404 / B603 / B607: test asserts and fixed-argument subprocess calls. |
| | flights backend (16 files, 1,304 LOC) | 0 | 0 |
| semgrep 1.182.1 (`p/python p/react p/typescript p/owasp-top-ten`, metrics off) | scrp (270 files) | 66 | 1, already F-12. `react-insecure-request` ×2 (`HomePage.tsx:88`, `city.ts:55`). `avoid-sqlalchemy-text` ×60 (same set as B608; FP). md5 ×2 (FP). `use-defused-xml-parse` ×1 (`scripts/ingest_store_xml.py:109`, local ops script on portal XML; FP). `insecure-file-permissions` ×1 (`export_pin_queue.py:265` sets 0o700, restrictive; FP). 2 YAML parse errors (not code). |
| | mobile (98 files) | 0 | 0 |
| | flights (65 files) | 0 | 0 |

## Commands for Dude (sudo; read-only)

```
sudo nginx -T | grep -nE "ssl_protocols|ssl_ciphers|server_tokens|add_header|client_max_body_size|limit_req|limit_conn"
sudo sshd -T | grep -E "passwordauthentication|permitrootlogin|maxauthtries|kbdinteractive|x11forwarding|pubkeyauthentication"
sudo cat /etc/ssh/sshd_config.d/50-cloud-init.conf
sudo ufw status verbose
sudo -u postgres psql -c "\du"
sudo -u postgres psql xxl_super -c "SELECT rolname, rolconfig FROM pg_roles WHERE rolname='scrp_app'"
sudo -u postgres psql -c "SHOW hba_file" -c "SELECT type, database, user_name, address, auth_method FROM pg_hba_file_rules WHERE NOT (address IS NULL OR address IN ('127.0.0.1','::1'))"
sudo ls -l /etc/sudoers.d/ && sudo cat /etc/sudoers.d/xxl-ops
sudo grep -E '^\[|^type' /root/.config/rclone/rclone.conf     # remote NAMES and TYPES only; expect a "crypt" remote for backups (F-08)
sudo fail2ban-client status sshd
sudo ls -l /var/backups/scrp | tail -3
sudo journalctl -u ssh --since "-7 days" | grep -c "Failed password"
```

**Quick fix that needs no sudo** (F-04; dude owns the files):

```
chmod 755 /var/www/super.xxl.co.il/assets && find /var/www/super.xxl.co.il -type f -exec chmod 644 {} +
```

## Compliance gap note (not legal advice)

**Israeli Privacy Protection (Data Security) Regulations 2017, basic-level items, against what exists today:**

| Requirement (basic level) | Status | Evidence / gap |
|---|---|---|
| Database definition document (purposes, data types, transfers, processors) | **Partial → draft** (`docs/compliance/database_definition_he.md`, SU11A-49) | `docs/store_privacy_inventory.md` (data inventory, processors, retention), `docs/compliance_amendment13.md` (thresholds). There is no single signed "database definition" document naming the database manager, its purposes, and the date of the last update. |
| Security procedure (נוהל אבטחת מידע) | **Missing → draft** (`docs/compliance/security_procedure_he.md`, SU11A-49) | Rules are scattered (CLAUDE.md rules 13–15, runbooks). There is no written procedure covering access, passwords, backups, incidents and vendor use. |
| Systems / infrastructure mapping | **Partial** | `docs/xxl-stack.md`, the handoff "Hosting topology", this report's server section. No network diagram or asset list with owners. |
| Access control and authorized-persons list | **Partial** | SSH keys only (pending F-15 confirmation), sudo password, a single operator, a fail-closed admin allow-list (`ADMIN_USER_EMAILS`). There is no written list of who has access to what (server, DB, Supabase, B2, Hostinger, Google Cloud, Play / EAS), and no review date. |
| Identification and authentication | **Partial** | Supabase auth for users (email confirmation on). MFA on the operator's cloud consoles is not documented. |
| Logging / audit trail | **Partial** | journald 30 days and nginx 14 days (`deploy/systemd/journald-scrp.conf`, privacy inventory §6). Moderation actions are logged. There is no access log for DB admin actions (`log_statement none`, `log_connections` off). |
| Backups | **Exists (gaps)** | Daily `pg_dump` to B2, lifecycle 180 days (SU11A-33). Gaps: encryption (F-08), no documented restore test. |
| Security incident handling | **Missing → draft** (`docs/compliance/incident_procedure_he.md`, SU11A-49) | No incident / breach procedure. `compliance_amendment13.md` lists it as "YES, applies now". |
| Outsourcing / processors | **Partial** | Processors are listed in the privacy inventory §7 (Supabase, Kamatera, Backblaze, Hostinger, Google). There is no record of the DPA / terms each one was accepted under. |
| Periodic review | **Missing → draft** (`docs/compliance/periodic_review_he.md`, SU11A-49) | No scheduled review. This report (SU11A-48) can serve as the first one; set a date for the next. |

**PCI DSS:** nothing is in scope today; there are no payments. The locked decision in `docs/compliance_amendment13.md` (hosted / tokenised gateway, no card data on XXL infrastructure) points to the **SAQ-A** path:
- the web uses a fully hosted checkout or a redirect;
- mobile uses the store's billing (Play / App Store) for digital goods.

Keeping SAQ-A then mainly means two things: the payment page's scripts are not served from our server, and CSP / script integrity are on the pages that link to checkout (F-03).

## Not covered / limits

- **Not done:** no active exploitation, no load testing of F-01 / F-02 against production, no authenticated dynamic testing, no Supabase dashboard review (no access).
- **Sudo-only items:** UFW, effective sshd config, pg_hba, sudoers and the rclone remote type are listed for Dude above.
- **Blocked check:** an SSH probe of the offered auth methods from this PC was not run (blocked by the local permission policy). `sshd -T` covers it.
- **Dependency results:** as of 22 Oct 2026, from the installed server packages (Python) and the lockfiles (JS).
