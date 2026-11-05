# SU11A-63 — Static security / reliability audit (read-only)

Date: 4 Nov 2026. Session ID: the prompt asked for SU11A-61, but that ID is already used. `docs/SU11A-62_handover.md` refers to "the SU11A-61 plan" and reserves SU11A-62 for the promo task. This audit is therefore SU11A-63; the next free ID is SU11A-64. Note that `docs/SU11A-62_handover.md:77` still says "Next free ID afterwards: SU11A-63"; change it to SU11A-64 before that prompt is run.

**No tests were run.** Nothing was installed, executed or fetched. There was no network, server or production access. No `.env` or secret was read. Every statement below comes from reading the repo at `d438b10` (scrp) and `65882ea` (xxl-super-mobile). "Live" statements are taken from repo docs and are labelled as assumptions.

## 1. Scope and exclusions

| In scope | Excluded |
|---|---|
| `api/` (main, auth, routers, moderation, admin_audit, response_cache, supabase_admin) | `xxl-flights/` (so F-17 is not re-checked) |
| `db/` (query.py promo / basket / cache paths, db.py, promo_curation.py, migrations of user, UGC, admin and curation tables) | `node_modules/` |
| `scripts/` that take external input: `sweep_account_deletes.py`, `import_google_coordinates.py`, `import_manual_pins.py`, `geo_guard.py` | Scrapers and the loader (no external user input; read-and-report rule) |
| `deploy/nginx/*.conf`, `deploy/systemd/scrp-account-sweep.*`, `scripts/deploy_frontend.ps1` | Server state (units, pg settings, rclone, sshd): cannot be verified statically |
| `web/src` (auth, delete page, saved baskets, admin client) | Supabase dashboard settings (Confirm email, RLS on `portal_email_signups`) |
| `xxl-super-mobile/src` (supabase.ts, auth-context, delete-account, basket-context, api/client.ts) | Dependency audits (no `pip-audit` / `npm audit` run) |

## 2. Map

**Stack:**
- FastAPI 0.136 on Starlette 1.0.0 (`requirements.txt`): gunicorn with UvicornWorkers behind nginx, proxying to `127.0.0.1:8000` (`deploy/nginx/xxl-api-proxy.conf:5`).
- Postgres, with one app role `scrp_app`.
- Supabase Auth, ES256 JWTs.
- React/Vite SPA (super, portal and the admin console).
- Expo app.

**Middleware (`api/main.py`), in request order:**
1. `AdminAwareCORSMiddleware` (`:109-132`). The origins are the env list plus `https://admin.xxl.co.il` (`:40-51`). PATCH is allowed in a preflight only for the admin origin (`:115-123`). There are no credentials.
2. `RequestMetricsMiddleware` (`:54-102`). `/admin/*` answers get `no-store`, and a JSON 500 instead of the plain-text one.

**Error handlers:** `ApiCodeError` answers `{"code"}` (`:155-158`). A `statement_timeout` cancel answers 503 `query_timeout` (`:161-174`).

**DB:** a 15 s `statement_timeout` on API connections only. It is a libpq startup option (`api/main.py:24-25`, `db/db.py:21-41`).

**Auth dependencies (`api/auth.py`):**

| Dependency | Lines | Used by | What it does |
|---|---|---|---|
| `get_current_user` | `:196-213` | all signed-in endpoints | 401 on no / bad token; 401 `account_deleted`; upserts the `users` row on every call (`:154-169`) |
| `get_current_user_login_code` | `:216-230` | category suggestions | same, but 401 answers `login_required` |
| `get_current_user_optional` | `:233-247` | — | |
| `get_user_id_soft` | `:250-269` | GET ratings | never raises |
| `get_user_for_account_delete` | `:272-284` | DELETE /account | no deleted-check, no upsert, returns `iat` |
| `require_admin_mfa` | `:300-327` | admin routes | valid token, then email in `ADMIN_USER_EMAILS` (fails closed), not deleted, `aal == "aal2"` |

- Verification (`:99-141`): `alg` pinned to ES256; `kid` looked up in the JWKS cache (refetch at most once per 60 s, 5 s backoff after a failure, `:48-96`); audience `authenticated`; `iss` not checked; `exp` not required.
- `require_admin_mfa` is applied as a router dependency in `admin.py:44`, `admin_categories.py:41` and `admin_promos.py:38`, and per route for the three `/admin/ratings/*` routes in `ratings.py:421-466`.
- Grep result: no other `/admin` route exists.

**nginx (repo copies; whether they are installed is an assumption, per CLAUDE.md "installed by hand"):**
- General zone `xxl_api` 10 r/s, burst 40.
- `xxl_heavy` 2 r/s, only on `/compare`, `/basket/compare` and `/promos/grouped` (`deploy/nginx/xxl-ratelimit-api.conf:20-34`).
- `/suggest` 20 r/s; images 30 r/s.
- 429 answers `{"code":"rate_limited"}` with CORS.
- `X-Real-IP` is overwritten from `$remote_addr` (`xxl-api-proxy.conf:8`), so `admin_audit.client_ip` cannot be spoofed through nginx.

**Trust boundaries and sources of truth:**

| State | Source of truth | Mirrors / notes |
|---|---|---|
| Identity, password, email confirmation, TOTP factor | Supabase Auth | API trusts the JWT claims `sub`, `email`, `aal`, `iat` |
| `users` row (email, tier, banned_at, terms) | our Postgres | created or refreshed from the token on every signed-in call |
| Terms consent | `users.terms_version` | first copied from the user-editable `user_metadata` (`api/terms.py`); used only as the user's own consent |
| Saved baskets | Postgres `saved_baskets` | mobile working basket: AsyncStorage `basket_items` is the source of truth; the server row `__xxl_mobile_basket__` is a mirror |
| Web basket | localStorage | — |
| Session tokens | phone: SecureStore, chunked (`xxl-super-mobile/src/lib/supabase.ts`) | web: supabase-js default localStorage (`web/src/lib/supabase.ts:10`) |
| Ratings, reports, blocks, suggestions, curation, admin audit | Postgres | `admin_audit` is SELECT / INSERT only for `scrp_app` (`su11a54_admin.sql:45`), i.e. append-only from the app |

## 3. Flow traces

### a. Sign-up, sign-in and password reset
- **Mobile:**
  - `auth-context.tsx:164-190` calls `supabase.auth.signUp` and `signInWithPassword` directly against Supabase. The session goes to the chunked SecureStore adapter.
  - Reset (`forgot-password.tsx:5-6`, `auth-context.tsx:233-250`): `resetPasswordForEmail`, then `verifyOtp({type:'recovery'})` with the 6-digit code, then `updateUser({password})`. The code is single-use, and the screen does not re-verify after a failed `updateUser` (`forgot-password.tsx:36-37`).
- **Web:** `AuthContext.tsx:67-98` makes the same calls, and the session is kept in localStorage.
- **API:** not involved until the first signed-in call, where `get_current_user` creates the `users` row (`auth.py:154-169`).
- Code throttling and brute-force limits are Supabase's (assumption: dashboard defaults).

### b. Account deletion
1. **Client:** the mobile screen (`delete-account.tsx:58-92`) and the web page (`DeleteAccountPage.tsx:66-92`) re-authenticate with the password to get a fresh token. They call `DELETE /account` at most twice (a second time only on `reauth_required`).
2. **Freshness and protection:** the API (`account.py:84-112`) requires `iat` no older than 300 s (`:36,66-70`), else 401 `reauth_required`. It refuses `DELETE_PROTECTED_USER_IDS` with 403 `account_protected` (`:61-63,94-95`).
3. **One transaction:** a `deleted_accounts` row (`ON CONFLICT DO NOTHING`), delete the flights rows, delete `users`. CASCADE removes saved baskets, favorites, ratings, blocks and suggestions; reports the user filed get `reporter_user_id SET NULL`. Then commit (`:97-105`).
4. **Supabase admin DELETE** (`supabase_admin.py:145-180`, 10 s timeout; 404 counts as success): 204 when it succeeds, 202 `deletion_pending` otherwise (`:107-112`).
5. **The sweep** (`scripts/sweep_account_deletes.py`, timer 05:30) retries pending rows and purges completed rows after 7 days.
6. **After deletion:** a still-valid old token gets 401 `account_deleted` (`auth.py:210-211`), and its `users` row is never recreated.
7. **Clients:** treat 204 / 202 / `account_deleted` as done and sign out locally (`auth-context.tsx:214-230`).

### c. Ratings
- **Submit** (`ratings.py:164-238`):
  - Order of checks: ban, then terms (only when `RATINGS_REQUIRE_TERMS` is on), then the blacklist.
  - The write is an upsert on `UNIQUE (user_id, item_code)`. An edit keeps the status unless the new text trips the blacklist.
  - A blacklist hit hides the rating and files a `source='blacklist'` report; the mail goes out in the background.
- **Report** (`:243-277`): a ban check, then an insert with no dedupe (F-09).
- **Block** (`blocks.py`): the author is resolved server-side; self-block answers 400; `ON CONFLICT (blocker_id, blocked_id) DO NOTHING`; only a new block files a report.
- **Unblock:** `DELETE ... WHERE id AND blocker_id = caller`.
- **Public read** (`ratings.py:307-345`): active rows only; with a token, blocked authors are filtered out and `is_mine` is set; `Cache-Control: private, no-store` whenever an Authorization header is present.
- **Moderation** (`api/moderation.py`, shared by the admin routes and the CLI):
  - hide / keep / restore and ban / unban stamp `reviewed_at`.
  - Every admin action writes `admin_audit` before the same commit.
  - A ban hides all of the author's active ratings; posting checks `banned_at`.

### d. Basket
- **Mobile local basket** (`basket-context.tsx`): AsyncStorage, written only after the first read (`:139-142`). The limit is 25 signed out and 150 signed in, applied to new items only.
- **Mobile sync:**
  - On sign-in: `GET /baskets`, find the row named `__xxl_mobile_basket__`, `GET` it, merge it with the local basket (local wins, max of the quantities), then `POST` (create) or `PUT` the merged list (`:162-240`).
  - Each later change is pushed with a fire-and-forget `PUT` (`:147-154`).
- **API `/baskets`** (`saved_baskets.py`):
  - The user id comes from the token.
  - `_owned_or_404` runs before GET, PUT and DELETE by id (`:39-46`).
  - There are no size or length limits (F-11), and no unique `(user_id, name)`.
- **`POST /basket/compare`** (`basket.py:200-313`, anonymous):
  - At most 25 items (402 above that); `store_fks` at most 300; `chain_ids` / `cities` unbounded.
  - `fetch_prices` reads the 25 barcodes across all stores and filters in Python.
  - It is in the heavy rate zone.

### e. Category suggestions and the admin categories tab
- **User side** (`api/routers/categories.py:74-123`), checks in order:
  1. `login_required`, then ban, then current terms (always required here);
  2. the 24 h count (≤ 20, count-then-insert);
  3. one open suggestion per user and item, enforced by a partial unique index (`su11a57:60-61`); the race maps to 409;
  4. the item must exist, the category must be active and must differ from the current one;
  5. a comment ≤ 200 characters (pydantic plus a DB CHECK), passed through the blacklist.
- **Admin side** (`admin_categories.py`, router-level `require_admin_mfa`):
  - Set, confirm and bulk (≤ 100 codes, de-duplicated) write manual rows, with one audit row each, in one transaction.
  - Revert reads the audit row and answers 409 `changed_since` when the label moved (`:222-250`).
  - Accept and reject are one UPDATE each, in the same transaction as the label and the audit row (`:363-421`).

### f. Admin console
- **Web:** the admin client (`web/src/admin/api.ts`) sends the Supabase token from the admin origin's own storage.
- **API:** every route goes through `require_admin_mfa`.
- **Pins and hides** (`admin_promos.py:293-404`):
  - Each change runs a guard (promo exists, not already curated, not the other kind), then insert or update, renumber, and an audit row in one transaction.
  - PATCH and DELETE lock the row (`_row(..., lock=True)`).
  - The DB has a partial unique index `(kind, chain_id, promo_id) WHERE active` and CHECKs on rank, kind and dates (`su11a58:57-79`).
- **Other screens:**
  - Moderation queue: `moderation.queue`, unpaged.
  - Status: cached 30 s.
  - Audit log: `admin_audit.entries` with an id cursor, limit ≤ 200; the actor is shown as 10 hex digits of `sha256(salt + user id)`, and `ip_hash` is never returned.

### g. Public read endpoints under load

| Endpoint | Input bounds | Cost control | Cache |
|---|---|---|---|
| `/search` | `q` ≤ 200, limit ≤ 100, `offset` unbounded, `city` / `chain` lists unbounded | v2 or old path with the 1,000-candidate cap (`search.py:38-41`), 15 s timeout | v2 unfiltered: per-worker LRU keyed by normalized `q` (`response_cache.py`, ≤ 1,000 entries / 16 MB, cleared on build stamp) |
| `/suggest` | `q` ≤ 200, limit ≤ 10 | own rate zone | same cache |
| `/compare` | as `/search` | heavy zone | — |
| `/product/{barcode}` | `^\d{8,14}$` | — | — |
| `/promos/grouped` | limit ≤ 5,000; `q` unbounded and unescaped | 100-row cap without chain / category / q / branch; heavy zone | — |
| `/promos/list` | limit ≤ 100, offset ≤ 10,000; `q` unbounded and unescaped | same cap; general zone only | — |
| `/promos/promoted` | — | empty without pins; pre-filtered by `promo_id` | — |
| `/promos/today` | `city` / `chain_id` free strings | — | per-worker cache keyed by the raw values, 256 keys, TTL 300 s |
| `/promos/bulk` | `stores` list unbounded | none | — |
| `/chains` | — | small-table query | per-build cache |
| `/stats` | — | — | — |

User coordinates: the basket branch list is in the POST body (`basket.py:156-168`). No endpoint takes `lat` / `lon` in the query string (grep). PASS.

### h. Store coordinate imports
- **Google importer** (`import_google_coordinates.py`): Israel bounding box on every pair (`:43,55-62,166-169`); NaN fails the comparison and is rejected; dry run by default; `--apply` needs `--expect N` and makes a backup table (`:10-22`).
- **Manual pins** (`import_manual_pins.py:40,97-103`): numbers must be finite and inside the bounding box; `method` is allow-listed; the latest timestamp wins per `store_fk`.
- **Pin tool** (`tools/pin_tool/`): static HTML / JS, with no server endpoint.
- Both are operator-run, and their input files are operator-supplied.

## 4. Matrix

PASS = static evidence supports it; GAP = see §5; N/A = not applicable; UNKNOWN = the evidence is missing.

| Flow | Validation | Authn / authz / IDOR | Duplicates / concurrency | Timeouts / partial failure | UI confirmed vs pending | Policies actually applied |
|---|---|---|---|---|---|---|
| a. Auth / reset | PASS: Supabase validates; email trimmed (`auth-context.tsx:233`) | PASS: ES256 pinned, aud checked; **F-10 open** (no `iss`, `exp` not required) | PASS: OTP single-use, no re-verify (`forgot-password.tsx:36-37`) | UNKNOWN: Supabase-side throttling; dashboard not visible | PASS: errors mapped to Hebrew messages (`lib/authErrors.ts`) | GAP-M2: stale `users.email` UNIQUE breaks a re-created account |
| b. Account deletion | PASS: UUID check, `iat` ≤ 300 s, protected list | PASS: id from the token only | PASS: idempotent insert, deletes find nothing on retry, 404 from Supabase = success | PASS server-side (202 + sweep); **GAP-L1 client side** (timeout after a server success) | GAP-L1 | PASS: CASCADE / SET NULL verified in migrations |
| c. Ratings | PASS: rating 1–3, comment ≤ 2,000, reason ≤ 1,000; F-11 `item_code` unbounded | PASS: upsert keyed on the caller; author never returned; unblock scoped to the blocker | PASS: unique `(user_id, item_code)` and `(blocker, blocked)`; **F-09 open** (reports) | PASS: mail in the background, never inline | PASS: server-side status; hidden rows never public | PASS: ban checked before every write; terms per flag |
| d. Basket | **F-11 open**: names, items, qty, `chain_ids`, `cities` unbounded; compare 25 items / 300 `store_fks` | PASS: `_owned_or_404` on every id route; id from the token | **GAP-L2**: reserved basket not unique, duplicable, deletable from web | PASS: push failures stay local and the next change retries; GAP-L2 dead-id case | PASS: local-first by design | PASS: compare in the heavy zone |
| e. Category suggestions | PASS: pydantic + CHECK ≤ 200, category active, item exists | PASS: admin router-level gate | PASS: partial unique index → 409; GAP-L4 daily-cap race (≤ a few over 20) | PASS: one transaction per admin decision | PASS: codes mapped (`category-suggest.tsx:69-74`) | PASS: blacklist applied; ban and terms checked |
| f. Admin console | PASS: rank 1–50, note ≤ 200, dates CHECK, `q` ≤ 80 | PASS: allowlist + aal2 on every `/admin` route (grep); 404 vs 403 behaviour documented | PASS: row lock on PATCH / DELETE; **GAP-L3** concurrent create → 500 / both kinds | PASS: audit row in the same commit (`moderation.py`, `admin_promos._audit`) | PASS: the console re-reads after writes (assumption from the API shape) | PASS: CORS PATCH admin-only; `admin_audit` append-only grant |
| g. Public reads | **GAP-H1** `/promos/bulk` unbounded; **GAP-H2** promos `q` wildcards lift the cap; `/search` `offset` unbounded (bounded by the candidate cap: PASS) | N/A (no user data); GET ratings sets `no-store` with auth | **GAP-M1** `/promos/today` cache churn / no single-flight | PASS: 15 s timeout → 503 | N/A | **F-02 changed**: the new promo endpoints are not in the heavy zone; installation UNKNOWN |
| h. Coordinate imports | PASS: bounding box, finite, method allow-list | N/A (operator-run, no network input) | PASS: latest timestamp wins; `--expect` count gate | PASS: one transaction + backup table | N/A | PASS: `coord_source` CHECK (CLAUDE.md, migration su11a23) |

## 5. Gaps (new, deduplicated, ranked)

### GAP-H1 — High: `POST /promos/bulk` takes an unbounded store list and returns every promo row of those stores
- **Status: fixed in SU11A-64, not deployed** (`docs/security/su11a64_runbook.md`). At most 300 stores and 1,000 barcodes per call (422), at most 50,000 rows per answer (422 `too_many_rows`); optional `item_codes`, which the web now sends, splitting longer store lists; `/promos/bulk` in the nginx heavy group. Tests: `tests/test_audit_fixes_su11a64_pg.py`.
- **Flows:** g.
- **Evidence:**
  - `api/routers/promos.py:23-42`: `stores: list[_StoreRef]`, with no `max_length`.
  - `db/query.py:1384-1430`: one `IN (...)` over all the pairs, joined to `prices`, with no `LIMIT`. The rows are held in Python and validated against `response_model=dict[str, list[PromoItem]]`.
  - `deploy/nginx/xxl-ratelimit-api.conf:20-34`: `/promos/bulk` is not in `xxl_heavy`, so it gets the general 10 r/s.
  - SU11A-48 did not list it (F-01 / F-02 / F-11 name other endpoints).
- **Scenario:**
  1. An anonymous client reads `/stores` (public) and posts every `(chain_id, store_id)` pair, about 900, which fits in nginx's 1 MB body.
  2. The query returns every active promo row with its shelf price. `db/query.py:2144` estimates about 0.5–1M rows.
  3. Each request either runs into the 15 s timeout (503) or builds a response of several hundred MB on a 3.8 GiB box shared with Postgres. At 10 r/s per IP, a few requests exhaust worker memory.
  4. Assumption: the exact row count and run time are not measured here.
- **Minimal fix:**
  - `promos.py:28-29`: `stores: list[_StoreRef] = Field(..., max_length=N)`.
  - Add `location = /promos/bulk` with the heavy zone in `xxl-ratelimit-api.conf` (5 lines).
  - Before choosing N, measure the web's normal pair count. `web/src/components/ResultsList.tsx:64-76` sends the unique stores of a results page, which can be large. If it regularly exceeds a safe cap, also send the page's `item_codes` and add `AND p.item_code IN :codes` to the SQL (about 10 lines).
- **Test:**
  - pytest with TestClient: POST N+1 stores → 422.
  - PG test: N stores with a seeded promo set → the expected keys only.
  - Web unit test: the request body never exceeds N.

### GAP-H2 — High: promo search text with `%` / `_` / spaces lifts the SU11A-60 unfiltered cap
- **Status: fixed in SU11A-62, not deployed** (`docs/admin/su11a62_runbook.md`).
  - `db/query.py clean_promo_q`: whitespace collapsed; under 2 characters besides `%` / `_` / `\` / spaces is no search.
  - Every promo LIKE, public and admin, is `_like_escape` + `ESCAPE '\'` (`promo_match_sql`).
  - `q` is `max_length=100` on the public endpoints.
  - An unfiltered `/promos/list` / `/promos/grouped` (including `q=%`) returns `[]` with no DB query (`api/routers/promos._unfiltered`).
  - Tests: `tests/test_promo_search_su11a62_pg.py`.
  - Still open, in SU11A-64: `/promos/list` and `/promos/promoted` in the nginx heavy zone.
- **Flows:** g.
- **Evidence:**
  - `api/routers/promos.py:129-132`: `_capped` returns the full limit whenever `args["q"]` is truthy.
  - `q` has no `max_length` and no strip: `promos.py:71` and `:140`.
  - `db/query.py:1824-1830`: `params["q_like"] = f"%{q}%"`, unescaped (F-11 noted only the escaping, not the cap bypass, which arrived with SU11A-60).
  - `/promos/list` is in the general zone only.
  - `docs/SU11A-62_handover.md:51` records that unfiltered `/promos/list` / `/promos/grouped` take 15 s and return 503 on production.
- **Scenario:**
  - `GET /promos/list?q=%25&offset=9900&limit=100` or `GET /promos/grouped?q=%25&limit=5000`.
  - Each call is the full unfiltered scan the cap exists to prevent, so it ends in the 15 s timeout (503).
  - At 10 r/s per IP (`/promos/list`) the DB is kept busy, with dozens of concurrent 15 s statements across the two workers' pools of 30.
  - `q=%20` (a space) has the same effect.
- **Minimal fix:**
  - In `_filters` (`promos.py:117-126`): `q = (q or "").strip() or None`, and lift the cap only when `len(q) >= 2`.
  - In `query.py:1829`: `f"%{_like_escape(q)}%"` with `ESCAPE '\'` (the helper already exists at `:119`).
  - `Query(None, max_length=100)` in both places.
  - Add `/promos/list` to the heavy zone.
  - About 8 lines.
- **Test:**
  - PG test (fixture of `test_promos_page_su11a60_pg.py`, `UNFILTERED_CAP` patched to 5): `q=%` → at most 5 rows and no wildcard match; `q=" "` → capped; `q="50%"` matches the literal text only.

### GAP-M1 — Medium: the `/promos/today` cache key is caller-controlled, LRU of 256, with no single-flight
- **Status: fixed in SU11A-64, not deployed** (`docs/security/su11a64_runbook.md`). `city` must be a known `city_canonical` and `chain_id` a known chain (422 `unknown_city` / `unknown_chain`; the check fails open if the tables cannot be read); one rebuild per key and worker; LRU 256 kept; `/promos/today` in the nginx heavy group.
- **Flows:** g.
- **Evidence:**
  - `db/query.py:2153-2189`: the key is `(limit, city, chain_id, curation)`, built from raw query strings (`promos.py:50-57`, with no validation).
  - When the cache is full, the oldest key is dropped (`:2188-2189`).
  - A miss runs `fetch_today_promos_live` with no lock around the rebuild. The comment at `:2143-2145` gives about 11 s for the unfiltered query.
- **Scenario:**
  1. A client requests `/promos/today?city=x1` … `x300`, which is cheap if an unknown city filters early. That is an assumption, not measured.
  2. This evicts the default `(200, None, None)` key on that worker.
  3. Every real visitor then pays the ~11 s query, and concurrent visitors each run it in parallel (no single-flight). Near the 15 s timeout this turns into 503s.
  4. TTL expiry alone also causes a thundering herd of rebuilds on busy minutes.
- **Minimal fix:**
  - Normalise and validate the key: `city` must be in the city list (or None) and `chain_id` must be a known chain. Otherwise answer `[]` without touching the cache.
  - Pin the default key so it is never evicted.
  - Hold a per-key lock during the rebuild, so later callers wait or are served the stale entry.
  - About 20 lines in `db/query.py` and 3 in `promos.py`.
- **Test:**
  - Unit test with `fetch_today_promos_live` monkeypatched to count calls:
    - 300 distinct unknown cities → 0 live calls, and the default key still cached;
    - 10 threads on an expired key → 1 live call.

### GAP-M2 — Medium: a stale `users.email` row locks a re-created account out of every signed-in endpoint
- **Status: fixed in SU11A-64, not deployed** (`docs/security/su11a64_runbook.md`). `users.email` is `NOT NULL UNIQUE`, so on the clash the old row's email becomes `orphaned+<old id>@invalid.local` and the new row is inserted, in one transaction; nothing moves to the new account; warning with ids only (`api/auth.py _upsert_user`).
- **Flows:** a, and every signed-in endpoint.
- **Evidence:**
  - `db/migrations/add_users_saved_baskets.sql:7`: `email TEXT NOT NULL UNIQUE`.
  - `api/auth.py:159-169`: `INSERT ... ON CONFLICT(id) DO UPDATE` handles an id conflict only. An email held by a different id raises `IntegrityError`, which is not caught and becomes a 500 on every call.
  - Only `DELETE /account` removes `users` rows (`account.py:45`).
  - CLAUDE.md §15 documents creating throwaway users in the Supabase dashboard (and deleting them there removes no `users` row).
  - The App Review account is to be re-created after a reviewer deletes it. The in-app path is fine; a dashboard deletion is not.
- **Scenario:**
  1. A test user `t@xxl.co.il` uses the app, so a `users` row exists.
  2. The user is deleted in the Supabase dashboard, then re-created with the same email (new `sub`).
  3. Every request of the new account through `get_current_user` (baskets, ratings, terms, favorites, suggestions) answers 500.
  4. The same happens after a Supabase email change to an address a stale row still holds.
- **Minimal fix (`auth.py:159-168`):**
  - Before the upsert, in the same statement or transaction, run `DELETE FROM users WHERE email = :email AND id <> :id` (the old row's data is orphaned anyway). Or catch `IntegrityError` and answer 409 `{"code":"email_conflict"}` for a manual fix.
  - The first option silently cascades the stale row's baskets and ratings, which is a product decision for Dude.
  - About 5 lines.
- **Test:**
  - PG test: insert `users(id=A, email=e)`, then call any signed-in endpoint with a token `sub=B, email=e`.
  - Expect 200 and one `users` row (B, e) with the first fix, or 409 `email_conflict` with the second. Never a 500.

### GAP-L1 — Low: a client timeout after a successful server delete shows an error and leaves the user stuck
- **Status:** mobile, SU11B-5 (`docs/handoff_mobile.md`). The web account-deletion page has the same pattern; not changed.
- **Flows:** b.
- **Evidence:**
  - Both clients abort `DELETE /account` at 15 s: mobile `src/api/client.ts:29,699-718`, web `client.ts:597-617`.
  - The server can take DB time plus up to 10 s for the Supabase call (`supabase_admin.py:131`), and it commits the DB deletion before that call (`account.py:97-107`).
  - On `timeout` / `network` the screens show the offline message (`delete-account.tsx:88-90`; `DeleteAccountPage.tsx:90-91`).
  - A retry re-authenticates first (`delete-account.tsx:67-72`). That fails with "wrong credentials" once the Supabase user is gone, so the retry never reaches the server's idempotent answer.
- **Scenario:**
  1. On a slow network, the Supabase delete takes 9 s, and the response arrives after the 15 s abort.
  2. The account is deleted, but the app says "no connection".
  3. On retry the password is "wrong", and the user stays signed in locally on a dead account. Every signed-in call answers 401 `account_deleted`.
- **Minimal fix:**
  - On `timeout` / `network`, first retry `DELETE /account` with the same fresh token: it is still under 300 s old, and `account_deleted` maps to `deleted` (mobile `client.ts:691`, web `client.ts:591`).
  - Only then fall back to the error.
  - About 6 lines per client.
- **Test:**
  - Client unit test with fetch mocked: the first call aborts, the second answers 401 `account_deleted` → the result is `deleted`, `finishAccountDeletion` is called, and no error is shown.

### GAP-L2 — Low: the reserved mobile basket is visible, deletable and duplicable
- **Status: web / API part fixed in SU11A-64, not deployed** (`docs/security/su11a64_runbook.md`): הסלים שלי does not list `__xxl_mobile_basket__`; DELETE / rename of it (and renaming another basket to it) is 409; GET still lists it. Mobile part (recreate on 404, lowest id on duplicates): SU11B-5. No unique index (duplicates stay possible; the app picks the lowest id).
- **Flows:** d.
- **Evidence:**
  - The web lists and deletes every saved basket, including the one named `__xxl_mobile_basket__` (`web/src/pages/MyBasketsPage.tsx:53-63,105-131`; no filter anywhere, by grep).
  - Mobile caches the row id for the session (`basket-context.tsx:106,150-151`), and the merge runs once per sign-in (`:174-175`). After a web delete, every push is a swallowed 404 until the next sign-in.
  - Nothing makes the name unique (`saved_baskets.py:53-69`, migration `add_users_saved_baskets.sql:13-20`). Two first sign-ins at once (two phones) each create a row, and each phone then syncs to its own row.
  - Changes made between the merge's `setItems` and the `POST` response are not pushed until the next change (`:213-228`).
- **Scenario:**
  - A user sees a basket named `__xxl_mobile_basket__` on the website, deletes it, and keeps shopping on the phone.
  - Nothing reaches the server until the app restarts. A second device then sees an old or empty basket.
- **Minimal fix:**
  - Web: filter `name === '__xxl_mobile_basket__'` out of `getSavedBaskets` (1 line), or show it labelled "סל מהאפליקציה" without a delete button.
  - Mobile: on a 404 from `updateSavedBasket`, clear `syncedIdRef` and re-run create (about 5 lines in `pushToBackend`).
  - Optional DB: a partial unique index `(user_id) WHERE name = '__xxl_mobile_basket__'`, with the 409 mapped to "list again".
- **Test:**
  - Web unit test: the list hides the reserved name.
  - Mobile unit test: a PUT that answers 404 → one POST, and the new id is used afterwards.

### GAP-L3 — Low: concurrent pin / hide creation can give a 500 or leave both a pin and a hide active
- **Status:** deferred (low; a single admin today).
- **Flows:** f.
- **Evidence:**
  - `admin_promos.py:293-333`: `_guard_new` checks first, then `_insert` runs. There is no lock and no `IntegrityError` handling.
  - The unique index is per kind (`su11a58:78-79`). Two pins at once give an `IntegrityError` (JSON 500 `server_error`, `main.py:96-102`). A pin and a hide at once both succeed, breaking "a promotion is either pinned or hidden". `_renumber` also races for ranks.
- **Scenario:**
  - Two admin tabs (or a double click without a disabled button) pin the same promo, or one pins while the other hides.
  - Reachability is low: one admin.
- **Minimal fix:**
  - `SELECT pg_advisory_xact_lock(hashtext(chain_id || '/' || promo_id))` at the start of `_guard_new`, plus one global advisory lock for pin renumbering.
  - Catch `IntegrityError` → 409 `already_curated`.
  - About 8 lines.
- **Test:**
  - PG test with two connections:
    - pin A on connection 1 (uncommitted), then pin A on connection 2 → connection 2 waits, then 409;
    - pin plus hide → exactly one active row.

### GAP-L4 — Low: the category-suggestion daily cap is count-then-insert
- **Status:** deferred (low).
- **Flows:** e.
- **Evidence:** `api/routers/categories.py:85-90` counts, and `:108-116` inserts later. Parallel requests for different items can each pass the count.
- **Scenario:** 20 parallel POSTs for 20 different items at the 19th suggestion → up to about 39 stored. The impact is queue noise only.
- **Minimal fix:** `SELECT pg_advisory_xact_lock(hashtext(:uid))` before the count (1 line).
- **Test:** a PG test with 5 threads at count 19 → exactly one 201 and four 429s.

## 6. KNOWN findings (SU11A-48) — status in the repo today

| ID | Status | Evidence |
|---|---|---|
| F-01 | **Fixed in code** (live per CLAUDE.md "Security baseline", assumption) | `api/main.py:24-25`, `db/db.py:34-41`, `api/routers/search.py:38-41` |
| F-02 | **Fixed in repo files, changed:** the promo endpoints added since (`/promos/list`, `/promos/promoted`, `/promos/today`, `/promos/bulk`) are only in the general zone; see GAP-H1 / H2 | `deploy/nginx/xxl-ratelimit-api.conf:20-34`; installed state UNKNOWN |
| F-03 | **Partly fixed:** headers in repo; CSP still `Content-Security-Policy-Report-Only` | `xxl-csp-web.conf:33`, `admin.xxl.co.il.conf:49` |
| F-04 | **Fixed** | `scripts/deploy_frontend.ps1:48-50` |
| F-05 | **Fixed** | `api/auth.py:48-96` |
| F-06 | **Open** | `requirements.txt`: `starlette==1.0.0`, `Pillow==12.3.0`, `python-jose[cryptography]>=3.3.0` |
| F-07 | UNKNOWN (server units / roles not in the repo) | — |
| F-08 | UNKNOWN (rclone config on the server) | — |
| F-09 | **Open** | `ratings.py:259-266` (no dedupe); `su10r1_ratings.sql:56` |
| F-10 | **Open, impact reduced:** still the email allowlist and no `iss` / `require_exp`, but admin routes now also need aal2 | `api/auth.py:135, 295-327` |
| F-11 | **Open, widened** (promo `q` now also lifts the cap: GAP-H2) | `saved_baskets.py:19-32`, `basket.py:147-155`, `search.py:205-206`, `promos.py:71,140`, `db/query.py:1829` |
| F-12 | **Fixed in code** (da83ca4; deployed 1 Nov per `docs/SU11A-62_handover.md:45`, assumption) | `web/src/utils/city.ts:9`; no `ip-api` call in `web/src` (grep) |
| F-13 | **Open** | `web/package.json:20-32`: `axios ^1.15.1`, `react-router-dom ^7.14.2`; tailwind / postcss / autoprefixer under `dependencies` |
| F-14 | UNKNOWN (no `npm audit` run in this session) | — |
| F-15 | UNKNOWN (server) | — |
| F-16 | **Partly fixed:** mobile now ignores `*.jks *.p8 *.p12 *.pem`; mobile still lacks `.env`, `*.keystore`, `google-services.json`; scrp still lacks the key / credential patterns | `xxl-super-mobile/.gitignore:16-35`; `.gitignore` (grep) |
| F-17 | Not checked (flights excluded) | — |
| F-18 | **Open** | `api/routers/search.py:384, 421` (`exc_info=True`) |
| F-19 | **Open** | `api/main.py:30-38` (no `docs_url=None`; admin routes in the schema) |
| F-20, F-21, F-23 | UNKNOWN (server) | — |
| F-22 | **Open** (optional item) | no `allowBackup` in `xxl-super-mobile/app.json` |

## 7. Unknowns and the check that settles each

| Unknown | Next check |
|---|---|
| Whether `deploy/nginx` rate-limit and header files match the live nginx | **[Server — bash]** `sudo nginx -T \| grep -nE "limit_req\|Content-Security"` and compare with the repo copies |
| `/promos/bulk` real cost for all stores (GAP-H1) and the web's usual pair count | Throwaway PG with a production-sized promo dump: `EXPLAIN ANALYZE` the bulk SQL for 900 pairs. Web: log `stores.length` in a local build on common searches. Never against production (CLAUDE.md §9) |
| `/promos/today` miss cost for an unknown city (GAP-M1) | `EXPLAIN ANALYZE` of `_fetch_today_promos_raw` with `city='x'` on the throwaway PG |
| Supabase: "Confirm email" / "Secure email change" on (F-10 relies on both), OTP rate limits, minimum password length | Dashboard → Authentication → Providers / Rate limits (Dude) |
| RLS on `public.portal_email_signups` (SU11A-48 table) | Supabase Security Advisor (Dude) |
| F-07 / F-08 / F-15 / F-20 / F-21 / F-23 | The sudo command list in `docs/security/su11a48_security_review.md` "Commands for Dude" |
| Dependency advisories now (F-06 / F-13 / F-14) | `pip-audit` on the server's `pip freeze`, `npm audit --omit=dev` in `web/` and the mobile repo, in a later session |
| Whether any `users` row is already orphaned (GAP-M2) | Read-only on the server: count `users` rows whose id is not in `auth.users` (Supabase SQL editor; ids only, never print emails) |

## 8. Notes
- **Re-checked and still PASS:** the IDOR table of SU11A-48 holds for every new endpoint since (suggestions, admin categories, admin promos, terms, blocks). Each takes the user id from the token or is admin-gated.
- **No injection paths found:** every new `text(f"...")` interpolates only fixed clause strings or generated parameter names (`admin_audit.entries`, `saved_baskets.update`, `moderation.moderate`, `_fetch_promos_bulk_all` placeholders).
- **GET ratings:** returns every active rating of an item without paging. That is bounded by the number of users, so it is not reported.
