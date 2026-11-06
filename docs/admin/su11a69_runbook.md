# SU11A-69 — admin statistics dashboard: runbook

Written 6 Nov 2026 for Dude.

**What it adds**
- A new admin tab, **"סטטיסטיקות"** (admin.xxl.co.il, admin + 2FA like every `/admin` route), plus a "תנועה ושימוש" card on the dashboard. It shows:
  - website page views, visitors (estimate), bot share, top pages and referrer domains, from the nginx logs, next to GA4;
  - API requests per platform (web / Android / iPhone);
  - Google Play installs;
  - App Store downloads, impressions and product page views.
- A daily job, `scrp-stats.timer`, at 03:30 Israel time. It stores **daily counts only**, in `stats_daily` / `stats_runs`. It never stores an IP address, a user agent, a full URL, a query string, a user id or an email.

**What works when**
- **Now (no credentials):** the nginx-based cards (website and app activity). They need steps 1–10.
- **Later:** GA4, Google Play and App Store show "לא מחובר" until you follow "Connect later" C1–C3. Each section ends with a test that turns its card into data.

**Production impact**
- One migration, adding two small tables.
- One nginx change: the shared `access.log` gets the site name (`$host`) at the end of each line. Nothing else in the log changes, and retention stays 14 days.
- One new systemd timer.
- An API restart and a web deploy.
- No price, search or user data is touched.

**How to run it**
- Run the steps in order. Each step names where it runs:
  - **[Server — bash]:** `ssh dude@185.229.226.190`, interactive, in `~/scrp`.
  - **[PC — PowerShell]:** in `C:\scrp` on the **home PC** (the one with `web/.env.production`).
  - **[Browser].**
- If a step says STOP, paste the output to the chat and do not improvise a fix.
- **Nothing here prints `.env`, a key or a token.** No command prints a raw log line either: they would show IP addresses. The commands print counts, owners and modes only.

---

## 1. Quiet-time check

**[Server — bash]**

```
date '+%H:%M'; systemctl show -p ActiveState --value scrp-cron; systemctl show -p ActiveState --value scrp-search-items
```

**Expect:**
- a time outside 04:00–04:30, 14:25–15:00, and 10:00 until the cron finishes;
- then `inactive` twice.

**STOP if** either reads `activating`.

## 2. Pull

**[Server — bash]**

```
cd ~/scrp && git pull origin main && git log --oneline -3
```

**Expect:** one of the top lines is `feat: SU11A-69 admin statistics dashboard`.
**STOP if** the pull fails.

## 3. Read-only checks: where nginx logs, who can read it

**[Server — bash]**

```
sudo grep -rn "access_log" /etc/nginx/ | grep -v "^\s*#" ; echo ---; sudo stat -c '%n %U:%G %a' /var/log/nginx/access.log /var/log/nginx/api-super.access.log; echo ---; grep -n "create" /etc/logrotate.d/nginx; echo ---; id -nG dude; ls /var/log/nginx/ | sed -E 's/\.[0-9]+(\.gz)?$//' | sort | uniq -c
```

**Expect:**
- `access_log` lines:
  - exactly one in `/etc/nginx/nginx.conf`: `access_log /var/log/nginx/access.log;`;
  - one for api-super (`/var/log/nginx/api-super.access.log`);
  - nothing for super / xxl / www / fly / admin.
- **Both logs** are `www-data:adm 640`.
- The logrotate line is `create 0640 www-data adm`.
- `id -nG dude` does **not** list `adm`. That is intended: the job gets the group for its own process only (`SupplementaryGroups=adm` in the unit), and your login stays as it is.
- The file list shows `access.log`, `api-super.access.log` and the error logs, each with its rotated copies.

**STOP if:**
- another site has its own `access_log` (for example fly.xxl.co.il). The job's default file list would then miss it.
- the owner, group or mode is different.

## 4. Migration (+ verify)

**[Server — bash]**

```
cat ~/scrp/db/migrations/su11a69_stats.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
sudo -u postgres psql xxl_super -Atc "SELECT tablename, tableowner FROM pg_tables WHERE tablename LIKE 'stats_%' ORDER BY 1"
```

**Expect:**
- `BEGIN`, `CREATE TABLE` ×2, `CREATE INDEX`, `DO`, `COMMIT`;
- then `stats_daily|scrp_app` and `stats_runs|scrp_app`.

**STOP if** there is an `ERROR`.

## 5. nginx: the site name in the shared access log (one-time)

The default `combined` format has no host, so the job cannot tell super.xxl.co.il, xxl.co.il, fly.xxl.co.il and admin.xxl.co.il apart. The new file `deploy/nginx/xxl-log-format.conf` is `combined` plus ` "$host"` at the end. Every existing grep, including those in the su11a49 runbook, still works.

**[Server — bash]**

```
sudo cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak-su11a69
sudo cp ~/scrp/deploy/nginx/xxl-log-format.conf /etc/nginx/conf.d/xxl-log-format.conf
sudo sed -i 's|^\(\s*\)access_log /var/log/nginx/access.log;|\1# SU11A-69: in conf.d/xxl-log-format.conf (format xxl_vhost)\n\1# access_log /var/log/nginx/access.log;|' /etc/nginx/nginx.conf
grep -n "access_log" /etc/nginx/nginx.conf; sudo nginx -t && sudo systemctl reload nginx
curl -s -o /dev/null https://super.xxl.co.il/ ; curl -s -o /dev/null https://xxl.co.il/ ; sleep 1
sudo tail -n 2 /var/log/nginx/access.log | awk -F'"' '{print $(NF-1)}'
```

**Expect:**
- the `grep` shows only the two commented lines in nginx.conf;
- `nginx -t` says `syntax is ok` / `test is successful`;
- the last command prints **only host names**, `super.xxl.co.il` and `xxl.co.il`.

**STOP if:**
- `nginx -t` fails. Undo it: `sudo cp /etc/nginx/nginx.conf.bak-su11a69 /etc/nginx/nginx.conf && sudo rm /etc/nginx/conf.d/xxl-log-format.conf && sudo nginx -t && sudo systemctl reload nginx`. Then paste the output.
- the last command prints anything other than host names.

**Note:** lines written before this step have no host. The first run's 7-day backfill counts those days under "לא ידוע" (unknown). From tomorrow every day is per site. The card says so in a note until the old days age out of the 7-day window.

## 6. Install the unit and the timer

The unit runs as `dude` with `SupplementaryGroups=adm`, the least privilege that reads `/var/log/nginx`. It also has `MemoryMax=400M`, `Nice=10` and idle I/O.

**[Server — bash]**

```
sudo cp ~/scrp/deploy/systemd/scrp-stats.service ~/scrp/deploy/systemd/scrp-stats.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now scrp-stats.timer
systemctl cat scrp-stats.timer | grep -E "OnCalendar|TimeZone"; systemd-analyze calendar "*-*-* 03:30:00 Asia/Jerusalem" | grep -E "Next elapse|in UTC"
systemctl list-timers scrp-stats.timer --no-pager | head -3
```

**Expect:**
- `OnCalendar=*-*-* 03:30:00 Asia/Jerusalem` (inline timezone), and **no** `TimeZone=` line;
- the next elapse is tonight or tomorrow at 03:30 Israel time;
- `list-timers` shows `scrp-stats.timer`.

**STOP if** the timer is not listed.

## 7. First run by hand (counts only)

**[Server — bash]**

```
sudo systemctl start scrp-stats.service; systemctl show scrp-stats.service -p Result -p MemoryPeak; journalctl -u scrp-stats -n 80 --no-pager -o cat
sudo -u postgres psql xxl_super -Atc "SELECT source, count(*), min(day), max(day) FROM stats_daily GROUP BY 1 ORDER BY 1; SELECT source, status, as_of, left(coalesce(note,''), 80) FROM stats_runs ORDER BY 1"
```

**Expect (the output is counts only):**
- `[web]`: a line like `files=15 read=8 lines=… unparsed=0 no_host=… admin=… other_host=…`. Then one line per day, for example `2026-11-05 bot_page_views[super.xxl.co.il]=… page_views[(unknown)]=… visitors[(unknown)]=…`, and `stored N rows, as of <yesterday>`.
  - The first run backfills up to 7 days.
  - A day the logs do not reach back to the start of is listed as `partial (not stored)`.
- `[api]`: per day `calls[android]=… calls[ios]=… calls[web]=… calls[other]=… calls[bot]=…`.
- `[ga4]`, `[play]`, `[appstore]`: `not connected (missing setting: …)`.
- `result: web=ok api=ok ga4=not_configured play=not_configured appstore=not_configured`.
- `Result=success` and a MemoryPeak well under 400M.
- psql: rows for `api` and `web`; `stats_runs` with `ok` ×2 and `not_configured` ×3.

**STOP if:**
- `ERROR` appears next to web or api. For example, `no log files found` means the adm group did not apply; paste the lines.
- `Result` is not `success`.

## 8. Restart the API and wait for health

**[Server — bash]**

```
sudo /usr/local/bin/xxl-restart.sh scrp-api && for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] && break; sleep 1; done; curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:8000/health
curl -s -w ' %{http_code}\n' http://127.0.0.1:8000/admin/stats
```

**Expect:** `health 200`, then `{"code":"admin_required"} 403`. That is the admin gate; the data is only visible in the console with 2FA.

**STOP if** health is not 200, or `/admin/stats` answers anything but 403.

## 9. Web deploy, with the guard

**[PC — PowerShell]**

```
git pull origin main; .\scripts\deploy_frontend.ps1
```

**Expect:** `build OK: …`, the sitemap lines (SU11A-68), the upload, `MATCH` and a green `Done!`.
**STOP if** you see a red line or `MISMATCH`.

## 10. Browser check

**[Browser]** https://admin.xxl.co.il (sign in with 2FA)

1. **Dashboard:** a card "תנועה ושימוש" shows page views, visitors and API requests for yesterday ("נכון ליום …"). Its title opens the new tab.
2. **Tab "סטטיסטיקות":**
   - **"אתר":** a "מחובר" chip with "מעודכן עד <yesterday>", and a table per site with a total row. For the days before step 5 the rows read "לא ידוע", with the note about step 5.
   - **GA4:** "לא מחובר" with its hint.
   - **"למה המספרים שונים?"** opens the explanation.
   - **Top pages and referrers:** paths only, like `/promos` or `/categories/D02`, plus "(דפים אחרים)"; domains only, like `google.com`, plus "(כניסה ישירה)".
   - **"שימוש באפליקציות ובאתר":** rows for אתר / אנדרואיד / iPhone / אחר / בוטים וכלים. Android and iPhone are non-zero once app users were active.
   - **Google Play and App Store:** "לא מחובר" with hints.
   - **The range buttons** 7 / 30 / 90 change the charts. "הצגת הנתונים כטבלה" opens each chart's numbers.
3. Keyboard only: Tab reaches the range buttons, the refresh button and every "הצגת הנתונים כטבלה", each with a visible focus ring.

**STOP if:**
- an error box appears;
- any number looks like an IP address;
- a top path shows text after a `?`.

## 11. Rollback

**[Server — bash]**

```
sudo systemctl disable --now scrp-stats.timer; sudo rm /etc/systemd/system/scrp-stats.service /etc/systemd/system/scrp-stats.timer; sudo systemctl daemon-reload
cat ~/scrp/db/migrations/su11a69_stats_rollback.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
sudo cp /etc/nginx/nginx.conf.bak-su11a69 /etc/nginx/nginx.conf && sudo rm /etc/nginx/conf.d/xxl-log-format.conf && sudo nginx -t && sudo systemctl reload nginx
```

- The API and the web need no rollback. Without the tables, the tab shows "טבלאות הסטטיסטיקה עדיין לא קיימות" and the dashboard card shows "אין עדיין נתונים".
- For a full code rollback:
  - **[PC — PowerShell]:** `git revert --no-edit <the SU11A-69 feat commit>; git push origin main; .\scripts\deploy_frontend.ps1`;
  - **[Server — bash]:** `cd ~/scrp && git pull origin main && sudo /usr/local/bin/xxl-restart.sh scrp-api`.

---

# Connect later

Credentials go into **files on the server, outside the repo**, in `/etc/xxl/stats/` (mode 700, files 600, owned by dude). Their settings go into `~/scrp/.env`, which is the unit's EnvironmentFile; edit it with `nano`, and never `cat` it. The API does not read these settings, so it needs no restart.

**Create the directory once:**

**[Server — bash]**

```
sudo install -d -m 700 -o dude -g dude /etc/xxl /etc/xxl/stats; sudo chmod 755 /etc/xxl; stat -c '%n %U:%G %a' /etc/xxl/stats
```

**Expect:** `/etc/xxl/stats dude:dude 700`.

**The test after each section** prints that source's lines of a full run:

**[Server — bash]**

```
sudo systemctl start scrp-stats.service; journalctl -u scrp-stats -n 60 --no-pager -o cat | grep -A6 "^\[<source>\]"
```

Replace `<source>` with `ga4`, `play` or `appstore`. Then reload the סטטיסטיקות tab.

## C1. GA4 (website users, sessions, page views per site)

1. **[Browser]** https://console.cloud.google.com → project **scrp**:
   1. **APIs & Services → Library**: search for "Google Analytics Data API" and press **Enable**.
   2. **IAM & Admin → Service Accounts → + Create service account**:
      - name `xxl-stats`, ID `xxl-stats`, then **Create and continue**;
      - **no role**, then **Done**.
   3. Open `xxl-stats@scrp.iam.gserviceaccount.com` → **Keys → Add key → Create new key → JSON → Create**. A `.json` file downloads.

   **STOP if** Google says that service account key creation is disabled (an organisation policy).
2. **[Browser]** https://analytics.google.com, on the property that holds G-YB4X4E5ZKM:
   1. **Admin → Property → Property access management → + → Add users**: the e-mail `xxl-stats@scrp.iam.gserviceaccount.com`, role **Viewer**, "Notify" off → **Add**.
   2. **Admin → Property details**: copy the **PROPERTY ID**, a number like `512345678`. G-YB4X4E5ZKM is the measurement id, not this.
3. **[PC — PowerShell]** (the file name is the one that downloaded):

   ```
   scp "$env:USERPROFILE\Downloads\scrp-XXXXXXXX.json" dude@185.229.226.190:/etc/xxl/stats/google.json
   ```

   Then delete the downloaded file from Downloads (keep a copy only in your password manager).
4. **[Server — bash]** Run `chmod 600 /etc/xxl/stats/google.json; stat -c '%U:%G %a' /etc/xxl/stats/google.json`.

   **Expect:** `dude:dude 600`.
5. **[Server — bash]** Run `nano ~/scrp/.env` and add two lines, with your property id:

   ```
   stats_google_key_file=/etc/xxl/stats/google.json
   stats_ga4_property_id=512345678
   ```
6. **Test** with `ga4`.

   **Expect:** `stored N rows, as of <yesterday or the day before>`, and per-day lines `page_views[super.xxl.co.il]=…`. In the tab, the GA4 chip is "מחובר", the table gains the GA4 columns, and the chart gains the dashed "Google Analytics" line.

   **STOP if** you see `ERROR`:
   - `HTTP 403 PERMISSION_DENIED`: the Viewer access from 2.1 is missing, or the API from 1.1 is not enabled;
   - `numeric`: you pasted the G- id.

## C2. Google Play (installs, uninstalls, active devices)

It uses the same service account as C1. If C1 is not done, do its steps 1.2, 1.3, 3, 4 and the first line of 5.

1. **[Browser]** https://play.google.com/console:
   1. **Users and permissions → Invite new users**: e-mail `xxl-stats@scrp.iam.gserviceaccount.com`.
      - **Account permissions:** only **"View app information and download bulk reports (read-only)"**.
      - Then **Invite user**.
   2. **Download reports → Statistics**: press **Copy Cloud Storage URI**. It looks like `gs://pubsite_prod_rev_01234567890987654321/stats/installs/`.
2. **[Server — bash]** Run `nano ~/scrp/.env` and add the bucket line; the job keeps only the bucket name from the URI. Also add the key line if C1 did not:

   ```
   stats_play_bucket=gs://pubsite_prod_rev_01234567890987654321/stats/installs/
   stats_google_key_file=/etc/xxl/stats/google.json
   ```
3. **Test** with `play`.

   **Expect:** `stored N rows` and per-day `installs=… uninstalls=… active_devices=…`.
   - Google publishes the export a few days late.
   - Bucket access for a newly invited account can take up to 24–48 h. Until then the line reads `ERROR play export: HTTP 403`. Re-run the test the next day before you STOP.

   **STOP if:**
   - the 403 is still there after 48 h;
   - it reads `no installs export for these months yet` after a week.

## C3. App Store (downloads; impressions and product page views)

Use a **separate** key. The EAS "App Manager" key `B3NWA8C97L` is refused by the job.

1. **[Browser]** https://appstoreconnect.apple.com → **Users and Access → Integrations → App Store Connect API → Team Keys → +**:
   1. Name `xxl-stats`, Access **Sales and Reports**. Then **Generate**.
   2. **Download API Key**: `AuthKey_<KEYID>.p8`. Apple lets you download it **once**.
   3. Note the **Key ID** of the row and the **Issuer ID** shown above the table.
2. **Vendor number:** **[Browser]** App Store Connect → **Payments and Financial Reports**. The vendor number is under your name, top left; it is also in **Sales and Trends → Reports**.
3. **[PC — PowerShell]**

   ```
   scp "$env:USERPROFILE\Downloads\AuthKey_<KEYID>.p8" dude@185.229.226.190:/etc/xxl/stats/asc_stats.p8
   ```

   Then delete the downloaded file from Downloads (password manager copy only).

   **[Server — bash]** Run `chmod 600 /etc/xxl/stats/asc_stats.p8; stat -c '%U:%G %a' /etc/xxl/stats/asc_stats.p8`.

   **Expect:** `dude:dude 600`.
4. **[Server — bash]** Run `nano ~/scrp/.env` and add:

   ```
   stats_asc_key_file=/etc/xxl/stats/asc_stats.p8
   stats_asc_key_id=<KEYID>
   stats_asc_issuer_id=<issuer id>
   stats_asc_vendor_number=<vendor number>
   ```

   **Test** with `appstore`.

   **Expect:**
   - `stored N rows` and per-day `downloads=… redownloads=… updates=…`;
   - the line `analytics report request missing`. That is expected until step 5.
   - A day without sales, 3+ days old, counts 0. The newest 1–2 days appear on a later run, because Apple publishes late.

   **STOP if** you see `ERROR … HTTP 401` (a wrong key id, issuer or file) or `HTTP 403` (the role).
5. **Analytics Reports, once.** Apple lets only an **Admin** key create the ongoing report request; the daily Sales and Reports key then reads the reports.
   1. **[Browser]** Generate a **temporary** Team Key with Access **Admin**, named `xxl-stats-setup`. Download it.
   2. **[PC — PowerShell]** Run `scp "$env:USERPROFILE\Downloads\AuthKey_<ADMINKEYID>.p8" dude@185.229.226.190:/etc/xxl/stats/asc_admin_tmp.p8`.
   3. **[Server — bash]**

      ```
      chmod 600 /etc/xxl/stats/asc_admin_tmp.p8; cd ~/scrp && (set -a; source .env; set +a; venv/bin/python3 -m scripts.stats_collect --asc-request-analytics --admin-key-file /etc/xxl/stats/asc_admin_tmp.p8 --admin-key-id <ADMINKEYID>); rm -f /etc/xxl/stats/asc_admin_tmp.p8
      ```

      **Expect:** `analytics report request: created` (or `exists`).
   4. **[Browser]** **Revoke** the `xxl-stats-setup` key in Team Keys. Delete its download on the PC.

   Apple builds the first reports in 1–2 days. After that, the test with `appstore` no longer prints the "missing" line, and the App Store card shows impressions and product page views.

   **STOP if** step 3 prints `ERROR … HTTP 403`.

## Removing a source later

1. Delete its lines from `~/scrp/.env` and its file from `/etc/xxl/stats/`.
2. Revoke the key: in Google Cloud for the service account, in App Store Connect for the API key.

The card then turns back to "לא מחובר" on the next run. Its stored daily counts stay; they are aggregates.
