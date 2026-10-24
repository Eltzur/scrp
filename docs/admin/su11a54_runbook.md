# SU11A-54 — admin console phase 1: server runbook

Written 25 Oct 2026 for Dude. It puts the admin console on `https://admin.xxl.co.il`, with moderation, platform status and an audit log, and mandatory 2FA.

**How to run it**
- Run the steps in order. Each step says where it runs:
  - **server:** `ssh dude@185.229.226.190`, interactive;
  - **PC:** PowerShell in `C:\scrp`;
  - **browser.**
- Each step says what to expect and when to STOP. If you stop, paste the output to the chat; do not improvise a fix.
- Nothing here prints `.env`, a token or a TOTP secret.
- **Quiet times** (same as SU11A-49): avoid 04:00–04:30, 10:00 until `scrp-cron` is `inactive`, and 14:30.

**What it deploys**

| Part | What changes |
|---|---|
| DB | New table `admin_audit` (`db/migrations/su11a54_admin.sql`). Additive. |
| API | `/admin/*` needs all of: a valid token, an email in `ADMIN_USER_EMAILS`, and a TOTP-verified session (`aal2`). There are new status, history, detail and audit endpoints, and every admin write is audited. `https://admin.xxl.co.il` is allowed in CORS in code. |
| nginx | New site `admin.xxl.co.il` (same web root as super), certificate, admin host added to the 429 CORS map. |
| Web | Same build. On `admin.xxl.co.il` it shows only the console, loaded as its own chunk. |

**Behaviour change for the existing admin endpoints.** `GET /admin/ratings/pending`, `POST /admin/ratings/{id}/moderate` and `POST /admin/ratings/{id}/ban-author` now:
- answer **403** `{"code":"admin_required"}` to non-admins (was 404), and **403** `{"code":"mfa_required"}` to a listed admin without TOTP;
- no longer return user ids in the queue.

Any account in `ADMIN_USER_EMAILS` (the x@ test account too) loses admin access until it enrols TOTP on the console. `scripts/moderation.py` on the server is unchanged; it writes no audit rows.

---

## 1. DNS (PC)

```
Resolve-DnsName admin.xxl.co.il -Type A | Select-Object Name, IPAddress
```

**Expect:** `admin.xxl.co.il  185.229.226.190`. On the server, `dig +short admin.xxl.co.il` should print `185.229.226.190`.

**STOP if** there is no answer or a different IP. Add the A record at the DNS provider, wait for it, and repeat. Nothing else depends on this step until step 6.

## 2. Supabase checks (browser, Supabase dashboard)

1. **TOTP is on:** Authentication → Multi-Factor (or Sign In / Providers → Multi-Factor Authentication) → **TOTP: enabled**. It is on by default; turn it on if not.
2. **The admin account exists:** Authentication → Users → `admin@xxl.co.il` is listed and its email is confirmed. If not, create it there with a strong password from your password manager.

**STOP if** TOTP cannot be enabled on this plan. Without it no one can reach the console.

## 3. The allowlist (server)

Edit `~/scrp/.env` yourself (`nano ~/scrp/.env`). Set `ADMIN_USER_EMAILS` to the admin accounts only, comma-separated, for example `admin@xxl.co.il`. Remove the x@ test account unless it should stay an admin; if it stays, it needs its own TOTP.

Check without printing the addresses:

```
grep '^ADMIN_USER_EMAILS=' ~/scrp/.env | cut -d= -f2- | tr ',' '\n' | grep -c '@'
```

**Expect:** the number of admins, for example `1`.

**STOP if** it prints `0`. An empty list admits nobody, by design.

## 4. Pull and apply the migration (server)

```
cd ~/scrp && git status --short | head -5 && git pull origin main && git log --oneline -4
cat ~/scrp/db/migrations/su11a54_admin.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
```

**Expect:**
- The pull fast-forwards. The log shows the three SU11A-54 commits:
  - `chore(admin): SU11A-54 ...`
  - `feat(web): SU11A-54 ...`
  - `feat(admin): SU11A-54 ...`
- The migration prints `BEGIN`, `CREATE TABLE`, `CREATE INDEX` (twice), `GRANT` (twice) and `COMMIT`.
- Running it again is safe: `NOTICE ... already exists, skipping` lines, then `COMMIT`.

Check the grants (read-only):

```
sudo -u postgres psql xxl_super -tAc "SELECT has_table_privilege('scrp_app','admin_audit','INSERT'), has_table_privilege('scrp_app','admin_audit','UPDATE')"
```

**Expect:** `t|f`. The API can add audit rows but cannot change them.

**STOP if** the pull conflicts or the migration prints `ERROR` (the transaction rolled back; nothing changed).

## 5. Restart the API and check it (server)

```
sudo /usr/local/bin/xxl-restart.sh scrp-api
systemctl is-active scrp-api
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/health
curl -s -w ' %{http_code}\n' http://127.0.0.1:8000/admin/me
curl -s -w ' %{http_code}\n' -H 'Authorization: Bearer garbage' http://127.0.0.1:8000/admin/ratings/pending
curl -sI http://127.0.0.1:8000/admin/me | tr -d '\r' | grep -iE '^(cache-control|server-timing)'
```

**Expect:**
- the restart prints its journal lines with no traceback;
- `active`
- `200`
- `{"code":"admin_required"} 403`, twice;
- `cache-control: no-store` and `server-timing: total;dur=...`.

**STOP if** the API is not active. Roll back with step 11a.

## 6. nginx: certificate first, then the site (server)

**6a. Back up what gets edited.**

```
cd /etc/nginx
sudo cp -a conf.d/xxl-ratelimit-http.conf /etc/nginx/xxl-ratelimit-http.conf.bak-su11a54
ls -l /etc/nginx/xxl-ratelimit-http.conf.bak-su11a54
```

The backup sits outside `conf.d/`, so nginx never loads it.

**6b. Bootstrap site and certificate.** The full site names certificate files that do not exist yet, so a placeholder answers port 80 while certbot proves the domain:

```
cd ~/scrp/deploy/nginx
sudo install -m 644 -o root -g root admin.xxl.co.il.bootstrap.conf /etc/nginx/sites-available/admin.xxl.co.il
sudo ln -s /etc/nginx/sites-available/admin.xxl.co.il /etc/nginx/sites-enabled/admin.xxl.co.il
sudo nginx -t && sudo systemctl reload nginx
sudo certbot certonly --nginx -d admin.xxl.co.il
sudo ls /etc/letsencrypt/live/admin.xxl.co.il/
```

**Expect:**
- `test is successful`;
- certbot prints `Successfully received certificate` and the renewal date;
- the last line lists `cert.pem  chain.pem  fullchain.pem  privkey.pem  README`.

This is `certonly`, not plain `certbot --nginx`: certbot only fetches the certificate and does not rewrite the site, because the real site file comes next.

**STOP if** certbot fails, typically because DNS is not pointing here yet. Remove the bootstrap with `sudo rm /etc/nginx/sites-enabled/admin.xxl.co.il && sudo nginx -t && sudo systemctl reload nginx`, then paste the error.

**6c. The real site and the CORS map:**

```
cd ~/scrp/deploy/nginx
sudo install -m 644 -o root -g root admin.xxl.co.il.conf /etc/nginx/sites-available/admin.xxl.co.il
sudo install -m 644 -o root -g root xxl-ratelimit-http.conf /etc/nginx/conf.d/
diff /etc/nginx/xxl-ratelimit-http.conf.bak-su11a54 /etc/nginx/conf.d/xxl-ratelimit-http.conf
sudo nginx -t && sudo systemctl reload nginx && systemctl is-active nginx
```

**Expect:**
- The diff shows only the map change: one added comment line and the regex now with `admin\.`:
  ```
  > # SU11A-54: admin.xxl.co.il added (the admin console calls api-super too).
  <     "~^https://(www\.|super\.)?xxl\.co\.il$"    $http_origin;
  >     "~^https://(www\.|super\.|admin\.)?xxl\.co\.il$"    $http_origin;
  ```
  The `default` line also differs, by whitespace only.
- `syntax is ok`, `test is successful`, `active`.

**STOP if** `nginx -t` fails: nothing was reloaded. Restore with step 11b and paste the error.

**Renewal:** `sudo certbot renew --dry-run --cert-name admin.xxl.co.il` should end in `Congratulations, all simulated renewals succeeded`. The port-80 server answers 301 from a `location`, so certbot can still insert its challenge location there.

## 7. Web deploy (PC)

```
.\scripts\deploy_frontend.ps1
```

**Expect:** the build, the upload, then `0`, then `Done!`. As always, compare the bundle hash, because the script prints `Done!` even when scp fails:

```
(Select-String -Path web\dist\index.html -Pattern 'assets/index-[^"]+\.js').Matches.Value
curl.exe -s https://super.xxl.co.il/ | Select-String -Pattern 'assets/index-[^"]+\.js' | ForEach-Object { $_.Matches.Value }
```

**Expect:** the same file name twice.

## 8. Header and access checks (PC)

```
curl.exe -sI http://admin.xxl.co.il/ | Select-String -Pattern '^(HTTP|Location)'
curl.exe -sI https://admin.xxl.co.il/ | Select-String -Pattern '^(HTTP|strict-transport|x-frame|x-robots|content-security|cache-control)'
curl.exe -s https://admin.xxl.co.il/robots.txt
curl.exe -s -w " %{http_code}`n" https://api-super.xxl.co.il/admin/me
curl.exe -s -w " %{http_code}`n" https://api-super.xxl.co.il/admin/status
curl.exe -s -o NUL -D - -X OPTIONS -H "Origin: https://admin.xxl.co.il" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization" https://api-super.xxl.co.il/admin/me | Select-String -Pattern '^(HTTP|access-control-allow-origin)'
```

**Expect:**
- **http:** `HTTP/1.1 301` and `Location: https://admin.xxl.co.il/`.
- **https:** `HTTP/1.1 200`, plus:
  - `Strict-Transport-Security`;
  - `X-Frame-Options: DENY`;
  - `X-Robots-Tag: noindex, nofollow`;
  - `Content-Security-Policy-Report-Only: ...`, which lists `api-super` and `supabase.co` and has no googletagmanager;
  - `Cache-Control: no-store`.
- **robots.txt:** `User-agent: *` and `Disallow: /`.
- **API without a token:** `{"code":"admin_required"} 403`, twice.
- **CORS preflight:** `HTTP/1.1 200` and `access-control-allow-origin: https://admin.xxl.co.il`.

**The shop is unchanged:** `https://super.xxl.co.il/` shows the shop as before, and its page source contains no admin screens. The admin code is a separate file that only the admin host loads (checked in SU11A-54 with `npm run check:admin-chunk`).

## 9. First login and TOTP enrolment (browser, phone)

1. Open `https://admin.xxl.co.il`. Expect the **כניסה לניהול** screen, titled "XXL Admin", with no shop header.
2. Sign in as `admin@xxl.co.il`.
3. **Check `aal1` is refused.** Before typing any code, open DevTools → Network and select the `me` request to `api-super.xxl.co.il/admin/me`. Expect status **403** and the body `{"code":"mfa_required"}`.
4. The **הגדרת אימות דו־שלבי** screen shows a QR code and a key. Scan it with an authenticator app (Google Authenticator, Microsoft Authenticator, 1Password). Then type the 6-digit code and press **אימות**.
   - Keep a backup: store the key in your password manager now. Without the phone you would be locked out, and recovery means deleting the factor in the Supabase dashboard (Authentication → Users → the user → MFA factors).
5. Expect **לוח בקרה**:
   - every chain listed, with a green, amber or red dot and its last update time;
   - the search build times;
   - review counts, request counters and server figures. Anything the API cannot read shows "לא זמין".
6. Open **ביקורות לטיפול**. The queue matches `venv/bin/python3 -m scripts.moderation queue` on the server. Open one rating: you see its comment, its reports, and "הכותב: חסום / לא חסום", but no email or user id.
7. If there is a real case, apply one action. A confirm dialog appears, then a toast. Check that **יומן פעולות** shows the row and **היסטוריה** shows the decision.
8. Sign out with **יציאה**, sign in again: this time only the 6-digit code is asked.
9. **Optional:** sign in with an account that is not on the list. Expect **אין הרשאת ניהול**, and no QR code.

**STOP if** step 5 shows **אין הרשאת ניהול** for `admin@xxl.co.il`: the email in `.env` does not match. Fix it (step 3) and restart the API (step 5).

## 10. Watch (server, next day)

```
sudo -u postgres psql xxl_super -tAc "SELECT action, count(*) FROM admin_audit GROUP BY 1 ORDER BY 1"
journalctl -u scrp-api --since today | grep -c 'admin request failed'
```

**Expect:** your actions counted, then `0`.

---

## 11. Rollback

**11a. API and web.**
```
cd ~/scrp && git log --oneline -6        # note the commit before the three SU11A-54 commits
git checkout <that commit> -- api/ && sudo /usr/local/bin/xxl-restart.sh scrp-api
```
The old API ignores `admin_audit`, so the table can stay. For the web, deploy the previous build from the PC. Restore the files to `main` (`git checkout main -- api/`) once the fix is in.

**11b. nginx.**
```
sudo rm /etc/nginx/sites-enabled/admin.xxl.co.il
sudo cp -a /etc/nginx/xxl-ratelimit-http.conf.bak-su11a54 /etc/nginx/conf.d/xxl-ratelimit-http.conf
sudo nginx -t && sudo systemctl reload nginx
```
The certificate can stay; `sudo certbot delete --cert-name admin.xxl.co.il` removes it.

**11c. The table** (only after 11a; drops the whole audit log): the commented `ROLLBACK` block at the end of `db/migrations/su11a54_admin.sql`.

**To lock the console without a deploy:** empty `ADMIN_USER_EMAILS` in `.env` and restart the API. Every `/admin/*` call then answers 403.

## Files

| Repo file | Goes to |
|---|---|
| `db/migrations/su11a54_admin.sql` | piped into `psql xxl_super` (step 4) |
| `deploy/nginx/admin.xxl.co.il.bootstrap.conf` | `/etc/nginx/sites-available/admin.xxl.co.il`, until the certificate exists (6b) |
| `deploy/nginx/admin.xxl.co.il.conf` | `/etc/nginx/sites-available/admin.xxl.co.il` (6c) |
| `deploy/nginx/xxl-ratelimit-http.conf` | `/etc/nginx/conf.d/` (6c) |
