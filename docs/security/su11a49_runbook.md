# SU11A-49 — security fixes: server runbook

Written 22 Oct 2026 for Dude. Covers F-01 to F-05 of `docs/security/su11a48_security_review.md`.

**How to run it**
- Run the steps in order, on the server (`ssh dude@185.229.226.190`, interactive) unless the step says "PC".
- Each step says what to expect and when to STOP. If you stop, paste the output to the chat; do not improvise a fix.
- Nothing here prints `.env` or a secret.

**Quiet times**
- Avoid: 04:00–04:30 (backup), 10:00 until `scrp-cron` is `inactive` (load), 14:30 (search build).
- Good: a weekday afternoon after about 15:30, or an evening.

**What it deploys**

| Finding | What changes | Where |
|---|---|---|
| F-01 | The API sets a 15 s `statement_timeout` on its own DB connections. A timeout answers `503 {"code":"query_timeout"}`. `/compare` and the filtered `/search` price at most 1,000 candidates. | API code |
| F-05 | A login token with an unknown key id refetches Supabase's key list at most once a minute. | API code |
| F-02 | nginx rate limits on api-super and on fly's SerpApi endpoints. Over the limit: `429 {"code":"rate_limited"}`. | nginx files |
| F-03 | Security headers on all four hosts; CSP in Report-Only on xxl, super and fly; `server_tokens off`; TLS 1.0/1.1 removed from the http-level line. | nginx files |
| F-04 | The web root's modes are fixed now and on every web deploy. | one `chmod`; `deploy_frontend.ps1` |

Scripts, timers and the loader are NOT affected by the timeout: it is set only when `api.main` is imported (checked in step 2).

---

## 1. Pull

```
cd ~/scrp && git status --short | head -5 && git pull origin main && git log --oneline -4
```

**Expect:**
- `git status` prints nothing (or only files you know about).
- The pull fast-forwards. The log shows the three SU11A-49 commits: `docs: SU11A-49 ...`, `chore(security): SU11A-49 ...` and `fix(security): SU11A-49 ...`.

**STOP if** the pull reports a conflict.

## 2. Restart the API (F-01, F-05) and check it

```
sudo /usr/local/bin/xxl-restart.sh scrp-api
systemctl is-active scrp-api
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/health
```

**Expect:** the restart prints the last 30 journal lines with no traceback; then `active`, then `200`.

**STOP if** the API is not active. Roll back with step 9a.

**Timeout is on the API only.** Read-only; prints two setting values, no secret:

```
cd ~/scrp && (set -a; . ./.env; set +a; ulimit -v 800000
  venv/bin/python3 -c 'import api.main; from db.db import get_engine; from sqlalchemy import text; c=get_engine().connect(); print("api:", c.execute(text("SHOW statement_timeout")).scalar())'
  venv/bin/python3 -c 'from db.db import get_engine; from sqlalchemy import text; c=get_engine().connect(); print("scripts:", c.execute(text("SHOW statement_timeout")).scalar())')
```

**Expect:** `api: 15s` and `scripts: 0`.

**STOP if** `scripts:` is anything other than `0`. The loader and the build need no timeout. Roll back with step 9a.

**The cap on a broad old-path query.** One request, `/compare?q=ים`, about 30K name matches:

```
curl -s -o /tmp/c49.json -w 'status %{http_code}  time %{time_total}s\n' "http://127.0.0.1:8000/compare?q=%D7%99%D7%9D"
venv/bin/python3 -c 'import json; d=json.load(open("/tmp/c49.json")); print("total_matches", d.get("total_matches"), "comparable", d.get("comparable_count"), "items", len(d.get("items", [])), "has_more", d.get("has_more"), d.get("code", ""))'
```

**Expect:**
- `status 200` and a time of a few seconds at most. Before this change the request priced all ~30K barcodes.
- `total_matches` around 29–30K (the true match count), `comparable` at most 1000, `items 30`, `has_more True`.

**If you get `status 503` with `query_timeout`:** the 15 s timeout worked (the query was still too slow). Searches stay up. Paste the line; this is a tuning question, not a rollback.

**STOP if** it hangs past 20 s or answers 500.

**JWKS throttle (F-05).** 20 requests with a token whose key id does not exist:

```
T=eyJhbGciOiJFUzI1NiIsImtpZCI6InN1MTFhNDktZm9yZ2VkIiwidHlwIjoiSldUIn0.eyJzdWIiOiJ4In0.c2ln
for i in $(seq 20); do curl -s -o /dev/null -w '%{http_code} ' -H "Authorization: Bearer $T" http://127.0.0.1:8000/me/terms; done; echo
journalctl -u scrp-api --since "-2 min" --no-pager | grep -c "JWKS cache miss"
```

The token is a made-up header (`kid` `su11a49-forged`, `sub` `x`), not a credential.

**Expect:**
- 20× `401`.
- A count of `2` at most: one fetch per gunicorn worker, then none for 60 s. Before this change it was 20.

## 3. Install the nginx files (F-02, F-03)

nginx 1.24 on the server. Every file was checked with `nginx -t` (nginx 1.24.0) against copies of the live site files with these exact edits. A local run also confirmed:
- the 429 JSON;
- CORS on the 429;
- the flights rewrite;
- all the headers.

**3a. Back up what gets edited.** The backup names do not end in `.conf`, so nginx never includes them.

```
cd /etc/nginx
for f in api-super.xxl.co.il super.xxl.co.il xxl.co.il fly.xxl.co.il; do sudo cp -a sites-available/$f sites-available/$f.bak-su11a49; done
sudo cp -a nginx.conf nginx.conf.bak-su11a49
ls -l sites-available/*.bak-su11a49 nginx.conf.bak-su11a49
```

**Expect:** 5 files listed.

**3b. Copy the new files** (2 http-level, 6 snippets) and compare the noindex record:

```
cd ~/scrp/deploy/nginx
sudo install -m 644 -o root -g root xxl-ratelimit-http.conf xxl-hardening-http.conf /etc/nginx/conf.d/
sudo install -m 644 -o root -g root xxl-security-headers.conf xxl-csp-web.conf xxl-csp-fly.conf xxl-api-proxy.conf xxl-ratelimit-api.conf xxl-ratelimit-fly.conf /etc/nginx/snippets/
diff api-noindex.conf /etc/nginx/snippets/api-noindex.conf && echo "noindex record matches"
```

**Expect:** `noindex record matches`.

**If `diff` prints a difference:** the repo copy is only a record; the live file wins. Note it and continue.

**3c. Add the include lines.** Each `sed` matches one exact existing line:

```
cd /etc/nginx
# api-super: after the FIRST "include snippets/api-noindex.conf;" (the 443 server; the port-80 block has a second one)
sudo sed -i '0,/^    include snippets\/api-noindex.conf;$/s//&\n    include snippets\/xxl-security-headers.conf;\n    include snippets\/xxl-ratelimit-api.conf;/' sites-available/api-super.xxl.co.il
# super: after "index index.html;" (443 server), and inside the static-asset location after its add_header
sudo sed -i 's/^    index index.html;$/&\n    include snippets\/xxl-security-headers.conf;\n    include snippets\/xxl-csp-web.conf;/; s/^        add_header Cache-Control public;$/&\n        include snippets\/xxl-security-headers.conf;/' sites-available/super.xxl.co.il
# xxl.co.il (portal, same build as super)
sudo sed -i 's/^    index index.html;$/&\n    include snippets\/xxl-security-headers.conf;\n    include snippets\/xxl-csp-web.conf;/' sites-available/xxl.co.il
# fly
sudo sed -i 's/^    index index.html;$/&\n    include snippets\/xxl-security-headers.conf;\n    include snippets\/xxl-csp-fly.conf;\n    include snippets\/xxl-ratelimit-fly.conf;/' sites-available/fly.xxl.co.il
# http-level TLS line (every 443 server already uses certbot's TLS 1.2/1.3 options)
sudo sed -i 's/^\(\s*\)ssl_protocols TLSv1 TLSv1.1 TLSv1.2 TLSv1.3;/\1ssl_protocols TLSv1.2 TLSv1.3;/' nginx.conf
for f in api-super.xxl.co.il super.xxl.co.il xxl.co.il fly.xxl.co.il; do diff sites-available/$f.bak-su11a49 sites-available/$f; done; diff nginx.conf.bak-su11a49 nginx.conf
```

**Expect exactly these diffs, and nothing else:**

```
3a4,5
>     include snippets/xxl-security-headers.conf;
>     include snippets/xxl-ratelimit-api.conf;
17a18,19
>     include snippets/xxl-security-headers.conf;
>     include snippets/xxl-csp-web.conf;
25a28
>         include snippets/xxl-security-headers.conf;
4a5,6
>     include snippets/xxl-security-headers.conf;
>     include snippets/xxl-csp-web.conf;
5a6,8
>     include snippets/xxl-security-headers.conf;
>     include snippets/xxl-csp-fly.conf;
>     include snippets/xxl-ratelimit-fly.conf;
33c33
< 	ssl_protocols TLSv1 TLSv1.1 TLSv1.2 TLSv1.3; # Dropping SSLv3, ref: POODLE
---
> 	ssl_protocols TLSv1.2 TLSv1.3; # Dropping SSLv3, ref: POODLE
```

**STOP if** the diffs differ, for example an include added twice or a file unchanged. Restore with step 9b.

**Manual alternative** (if you prefer an editor): add the same lines by hand in the same places.
- api-super, 443 server: under `include snippets/api-noindex.conf;`.
- super / xxl / fly, 443 server: under `index index.html;`.
- super's `location ~* \.(js|css|...)` block: under `add_header Cache-Control public;`.

The last one is needed because of the add_header inheritance rule: a location with its own `add_header` inherits none from the server. That static-asset location is the only location with its own add_header in the four sites. The 429 locations inside the new snippets already repeat the headers themselves.

**3d. Test, then reload:**

```
sudo nginx -t && sudo systemctl reload nginx && systemctl is-active nginx
```

**Expect:** `syntax is ok`, `test is successful`, `active`.

**STOP if** `nginx -t` fails: nothing was reloaded, the old config still serves. Restore with step 9b, then paste the error.

## 4. Check headers and limits (PC or server)

**Headers.** These answer from the public hosts:

```
for u in https://xxl.co.il/ https://super.xxl.co.il/ https://fly.xxl.co.il/ https://api-super.xxl.co.il/health; do echo "== $u"; curl -sI "$u" | tr -d '\r' | grep -iE '^(server|strict-transport|x-content-type|referrer-policy|x-frame|permissions-policy|content-security|x-robots)' | cut -c1-90; done
curl -sI "https://super.xxl.co.il/$(curl -s https://super.xxl.co.il/ | grep -o 'assets/index-[^"]*\.js' | head -1)" | tr -d '\r' | grep -iE '^(strict|x-content|cache-control)'
```

**Expect:**
- **Every host:**
  - `Server: nginx` (no version)
  - `Strict-Transport-Security: max-age=31536000`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `X-Frame-Options: DENY`
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- **xxl, super and fly:** also `Content-Security-Policy-Report-Only: default-src 'self'; ...`.
- **api-super:** also `X-Robots-Tag: noindex, nofollow`, and no CSP.
- **The JS bundle:** HSTS, nosniff, and both `Cache-Control` lines (`max-age=31536000` and `public`).

**429 on the API.** About 50 requests to the cheapest endpoint, in parallel, from one IP (yours):

```
for i in $(seq 50); do curl -s -o /dev/null -w '%{http_code}\n' https://api-super.xxl.co.il/health & done | sort | uniq -c; wait
curl -s -D - -H 'Origin: https://super.xxl.co.il' https://api-super.xxl.co.il/health | tr -d '\r' | grep -iE '^(HTTP|access-control|retry-after|content-type)|rate_limited'
```

**Expect:**
- Mostly `200` and a few `429`. With a slow link everything may come back `200`; that is fine.
- If the last request still hits the limit: `HTTP/1.1 429`, `content-type: application/json`, `access-control-allow-origin: https://super.xxl.co.il`, `retry-after: 2`, `{"code":"rate_limited"}`. If it gets `200`, run both lines again right away.
- Your IP is clear again within about 4 seconds.

**Heavy zone, cheaply.** 15 `/compare` requests for a word that matches nothing (no price fetch):

```
for i in $(seq 15); do curl -s -o /dev/null -w '%{http_code}\n' "https://api-super.xxl.co.il/compare?q=zzqqxxsu11a49" & done | sort | uniq -c; wait
```

**Expect:** about 11× `200` and 4× `429` (1 plus a burst of 10).

**Flights SerpApi endpoints.** 8 requests WITHOUT parameters:

```
for i in $(seq 8); do curl -s -o /dev/null -w '%{http_code}\n' https://fly.xxl.co.il/api/search & done | sort | uniq -c; wait
curl -s -o /dev/null -w 'airports %{http_code}\n' "https://fly.xxl.co.il/api/airports?q=lon"
```

**Expect:**
- About 6× `422` (FastAPI: missing `destination`; SerpApi is never called) and 2× `429`.
- `airports 200`: not limited.
- `/api/search` / `/explore` / `/flexible-dates` stay limited for your IP for up to a minute.

**STOP if** normal use breaks: for example the web app shows "the server is busy" while one person browses, or `/api/airports` answers 429. Roll back with step 9b and paste what you saw.

## 5. CSP Report-Only: hash check and a first look

The web policy allows the one inline script in `index.html` by its hash.

**Check the live file still has that script.** Read-only:

```
python3 -c 'import re,hashlib,base64; s=open("/var/www/super.xxl.co.il/index.html",encoding="utf-8").read(); [print("sha256-"+base64.b64encode(hashlib.sha256(m.group(1).encode()).digest()).decode()) for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", s, re.S)]'
grep -o "sha256-[A-Za-z0-9+/=]*" /etc/nginx/snippets/xxl-csp-web.conf
```

**Expect:** the same value twice (`sha256-LO2icOS4USz6HYBRrTSoEr8dKWyC8lMuaisAr14JTZA=`).

**If they differ:** put the new value into `/etc/nginx/snippets/xxl-csp-web.conf` and into the repo copy, then `sudo nginx -t && sudo systemctl reload nginx`. Report-Only blocks nothing, so this is not urgent.

**PC, Chrome.** Open https://super.xxl.co.il and https://xxl.co.il with DevTools → Console:
1. search, open a product, sign in;
2. accept cookies (GA4 loads);
3. open https://fly.xxl.co.il.

Lines starting `[Report Only] Refused to ...` list anything the policy would block. Paste them. After a week with none, the header can be switched to enforcing (a separate session).

## 6. Web root permissions (F-04, one time, no sudo)

```
chmod 755 /var/www/super.xxl.co.il/assets && find /var/www/super.xxl.co.il -type d -exec chmod 755 {} + && find /var/www/super.xxl.co.il -type f -exec chmod 644 {} +
find /var/www/super.xxl.co.il \( -type d ! -perm 755 \) -o \( -type f ! -perm 644 \) | wc -l
stat -c '%a %n' /var/www/super.xxl.co.il/assets
```

**Expect:** `0`, then `755 /var/www/super.xxl.co.il/assets`.

**STOP if** `chmod` reports "Operation not permitted": a file is not owned by dude. Paste `ls -la` of the folder.

Optional: `rm /var/www/super.xxl.co.il/og-super.png.png`. It is a stray 5.6 MB copy, not referenced anywhere.

## 7. Web deploy (PC)

```
.\scripts\deploy_frontend.ps1
```

The script now ends by setting the web root to dirs 755 / files 644 and prints how many entries still differ. Expect `0`, then `Done!`.

**What changes for users:** a 429 or a 503 timeout on the results page shows "השרת עמוס כרגע. נסו שוב בעוד כמה שניות" with the retry button, instead of "לא ניתן לגשת לשרת". It is not retried automatically.

Then re-run the hash check of step 5. The build's inline script is unchanged, so it should match.

## 8. Watch for a day

```
sudo grep -c "limiting requests" /var/log/nginx/api-super.error.log /var/log/nginx/error.log
sudo grep -ho 'zone "[a-z_]*", client: [0-9a-f.:]*' /var/log/nginx/api-super.error.log /var/log/nginx/error.log | sort | uniq -c | sort -rn | head
journalctl -u scrp-api --since "-1 day" --no-pager | grep -c "query timeout"
```

**Expect:** few or no rejections, and no single IP dominating unless it is a bot.

**If real users show up as rejected:** raise the burst in `/etc/nginx/conf.d/xxl-ratelimit-http.conf` or the snippets (and in the repo), then `nginx -t` + reload.

**Privacy note:** nginx's "limiting requests" warning repeats the request line, so it contains search text, like the access log already does. It sits in the nginx error log, rotated after 14 days like the access log. It holds no new kind of data.

## 9. Rollback

**9a. API code** (F-01 / F-05). Commits are made on Windows only; the server only pulls (CLAUDE.md rule 14):

```
# PC, C:\scrp:
git revert --no-edit <fix(security): SU11A-49 hash>
git push origin main
# server:
cd ~/scrp && git pull origin main && sudo /usr/local/bin/xxl-restart.sh scrp-api
```

The nginx changes do not depend on it and can stay. The revert also takes back the timeout; the web's busy message stays harmless.

**9b. nginx** (F-02 / F-03): put the five edited files back and take the two http-level files out:

```
cd /etc/nginx
for f in api-super.xxl.co.il super.xxl.co.il xxl.co.il fly.xxl.co.il; do sudo cp -a sites-available/$f.bak-su11a49 sites-available/$f; done
sudo cp -a nginx.conf.bak-su11a49 nginx.conf
sudo rm -f conf.d/xxl-ratelimit-http.conf conf.d/xxl-hardening-http.conf
sudo nginx -t && sudo systemctl reload nginx
```

- The snippet files can stay in `snippets/`; nothing includes them any more.
- Already-sent HSTS stays in visitors' browsers for a year. That is harmless: every host serves HTTPS.

**To disable only the rate limits:** delete the `include snippets/xxl-ratelimit-api.conf;` / `xxl-ratelimit-fly.conf;` lines, `nginx -t`, reload.

**9c. Web:** redeploy the previous build if the busy message is a problem (it is display-only).

---

## Rate limits (what and why)

Per client IP. nginx is the edge, so `$binary_remote_addr` is the real client. `nodelay` everywhere: a burst is served at once, never queued; over the burst, 429 at once.

| Zone | Where | Rate | Burst | Why |
|---|---|---|---|---|
| `xxl_api` | api-super, everything not listed below (incl. `/search`, `/product`, `/items/*/ratings`, auth'd routes) | 10/s | 40 | One page view is 1–6 API calls. 10/s sustained is ~20× a busy person. A burst of 40 covers several people behind one mobile-carrier NAT IP opening pages at the same moment. |
| `xxl_heavy` (plus `xxl_api`) | `/compare`, `/basket/compare`, `/promos/grouped` | 2/s | 10 | Each prices many barcodes. The web fires `/compare` per typing pause (200 ms debounce, superseded requests aborted), ≤3–4 in a couple of seconds; 10 covers a fast typist plus a neighbour on the same IP. |
| `xxl_suggest` | `/suggest` | 20/s | 60 | One call per keystroke (160 ms debounce on web and mobile): ≤6/s per typist; 60 covers ~10 people typing behind one IP. Answers are cached and cheap. |
| `xxl_img` | `/product/{barcode}/image` | 30/s | 200 | A results page shows 20–30 images at once. These are file reads, but they should not use up the general zone. |
| `xxl_serp` | fly `/api/search`, `/api/explore`, `/api/flexible-dates` | 10/min | 5 | Each cache miss spends paid SerpApi quota. A search page fires `/search` plus `/flexible-dates` together; a person rarely runs more than a few searches a minute. `/api/airports`, `/api/price-calendar` and `/api/me` read the DB only and are not limited. |

`/search` with a city or chain filter cannot be told apart in nginx (they are query parameters). It stays in the general zone; F-01's 1,000-candidate cap and 15 s DB timeout cover its cost.

**Carrier NAT.** Israeli mobile networks share public IPs between many subscribers. The numbers above are per-IP ceilings, set generously because the app's traffic is small today. If the step 8 log check shows one carrier IP being rejected during normal use, raise that zone's burst first (rate second). Do not key on anything a client can choose freely (e.g. a header).

## Files (repo → server)

| Repo | Server | Context |
|---|---|---|
| `deploy/nginx/xxl-ratelimit-http.conf` | `/etc/nginx/conf.d/` | http: zones, 429 status, log level, CORS map for the 429 |
| `deploy/nginx/xxl-hardening-http.conf` | `/etc/nginx/conf.d/` | http: `server_tokens off` |
| `deploy/nginx/xxl-security-headers.conf` | `/etc/nginx/snippets/` | server / location: 5 headers |
| `deploy/nginx/xxl-csp-web.conf` | `/etc/nginx/snippets/` | server: CSP Report-Only, xxl + super |
| `deploy/nginx/xxl-csp-fly.conf` | `/etc/nginx/snippets/` | server: CSP Report-Only, fly |
| `deploy/nginx/xxl-ratelimit-api.conf` | `/etc/nginx/snippets/` | server: api-super limits + 429 JSON |
| `deploy/nginx/xxl-api-proxy.conf` | `/etc/nginx/snippets/` | location: copy of api-super's proxy settings |
| `deploy/nginx/xxl-ratelimit-fly.conf` | `/etc/nginx/snippets/` | server: fly SerpApi limits + 429 JSON |
| `deploy/nginx/api-noindex.conf` | `/etc/nginx/snippets/` (already live since 22 Oct 2026) | record only; Dude applied it, backup `api-super.xxl.co.il.bak-2026-10-22` |
