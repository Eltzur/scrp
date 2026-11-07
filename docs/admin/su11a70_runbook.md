# SU11A-70 — honest visitor counts, App Store badge, Super logo link: runbook

Written 7 Nov 2026 for Dude. It follows SU11A-69. If the SU11A-69 runbook has not been run yet, run it first: its step 5 then installs this session's log-format file directly, and step 3 below just confirms it.

**What changes**
- **Statistics:**
  - **A page view is now only** a browser (`Mozilla/…`, not a known bot / tool) loading a page with GET / HEAD and status 200 or 304.
  - **Everything else** on a site that is not one of a page's own files is counted per site per day as **"נדחו"** (`rejected_requests`, no paths): redirects, 4xx scanner probes such as `/wp-admin` and `/.env`, 5xx, POST, non-browser clients.
  - **The admin console's API calls** are their own row ("קונסולת ניהול"), and they are left out of the dashboard card's API total.
  - **New switch "לא לספור את הדפדפן הזה"** in the statistics tab. It sets the cookie `xxl_internal=1` on `.xxl.co.il` for a year. nginx logs only a flag for it ("1" or "-"), never the cookie's value. Those page views move to **"מהצוות"** (`internal_page_views`).
  - **A re-run replaces a day**, so the one-time 7-day recompute (step 5) removes the counts the new rules no longer allow.
- **App Store:** the iOS app is live. Apple's official badge (black, Hebrew / English) links to https://apps.apple.com/il/app/super-xxl/id6829450422 in three places:
  - the portal's Super card;
  - the Super home section "SUPER XXL באפליקציה";
  - the footer.

  The iPhone banner links there too, and "בקרוב גם ל-iPhone" is gone.
- **Super logo:** on super.xxl.co.il the header logo goes to Super's home ("/"). On xxl.co.il / www it still goes to https://xxl.co.il. Super's footer gains the link "כל שירותי XXL".

**Production impact**
- One nginx file is replaced: one more log field.
- An API restart, because `/admin/status` now leaves admin calls out of the card total (`db/stats.py`).
- One recompute of the stored statistics.
- One web deploy.
- No migration, no price or user data.

**How to run it**
- Run the steps in order. Each step names where it runs:
  - **[Server — bash]:** `ssh dude@185.229.226.190`, interactive, in `~/scrp`.
  - **[PC — PowerShell]:** in `C:\scrp` on the **home PC** (the one with `web/.env.production`).
  - **[Browser].**
- If a step says STOP, paste the output to the chat and do not improvise a fix.
- Nothing here prints `.env`, a raw log line, an IP address or a cookie value: only host names, the flag, counts and sums.

---

## 1. Quiet-time check

**[Server — bash]**

```
date '+%H:%M'; systemctl show -p ActiveState --value scrp-cron; systemctl show -p ActiveState --value scrp-search-items; systemctl show -p ActiveState --value scrp-stats
```

**Expect:**
- a time outside 03:30–03:45, 04:00–04:30, 14:25–15:00, and 10:00 until the cron finishes;
- then `inactive` three times.

**STOP if** any reads `activating`.

## 2. Pull

**[Server — bash]**

```
cd ~/scrp && git pull origin main && git log --oneline -3
```

**Expect:** one of the top lines is `feat: SU11A-70 honest visitor counts, App Store badge, Super logo link`.
**STOP if** the pull fails.

## 3. nginx: the internal flag field

The file `deploy/nginx/xxl-log-format.conf` now has:
- a `map`: the cookie `xxl_internal` becomes `"1"` or `"-"`, and nothing else is ever written;
- that flag as one more quoted field after `"$host"`.

**[Server — bash]**

```
ls -l /etc/nginx/conf.d/xxl-log-format.conf && sudo cp /etc/nginx/conf.d/xxl-log-format.conf /etc/nginx/xxl-log-format.conf.bak-su11a70
sudo cp ~/scrp/deploy/nginx/xxl-log-format.conf /etc/nginx/conf.d/xxl-log-format.conf && sudo nginx -t && sudo systemctl reload nginx
curl -s -o /dev/null https://super.xxl.co.il/ ; sleep 1; sudo tail -n 1 /var/log/nginx/access.log | awk -F'"' '{print $(NF-3), "|", $(NF-1)}'
curl -s -o /dev/null -H 'Cookie: xxl_internal=1' https://super.xxl.co.il/ ; sleep 1; sudo tail -n 1 /var/log/nginx/access.log | awk -F'"' '{print $(NF-3), "|", $(NF-1)}'
curl -s -o /dev/null -H 'Cookie: xxl_internal=SOMETHING-ELSE' https://super.xxl.co.il/ ; sleep 1; sudo tail -n 1 /var/log/nginx/access.log | awk -F'"' '{print $(NF-3), "|", $(NF-1)}'
```

**Expect:**
- `ls` shows the file. It is the SU11A-69 one, installed by that runbook's step 5.
- `nginx -t` says `syntax is ok` / `test is successful`.
- Then three lines:
  - `super.xxl.co.il | -`, a curl without the cookie: **the last field prints only `-`**;
  - `super.xxl.co.il | 1`;
  - `super.xxl.co.il | -`: any other cookie value logs as `-`, never the value.

**STOP if:**
- `ls` says no such file. The SU11A-69 runbook is not done; run it first.
- `nginx -t` fails.
- a line shows anything else, especially `SOMETHING-ELSE`.

**If needed:** to undo, copy `/etc/nginx/xxl-log-format.conf.bak-su11a70` back to `/etc/nginx/conf.d/xxl-log-format.conf`, then run `sudo nginx -t` and reload nginx. The parser reads both line shapes.

## 4. Restart the API (yes: `db/stats.py` changed)

The stats job needs no restart: each run starts fresh. The API does, because the dashboard card's API total now leaves the admin console out.

**[Server — bash]**

```
sudo /usr/local/bin/xxl-restart.sh scrp-api && for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] && break; sleep 1; done; curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:8000/health; curl -s -w ' %{http_code}\n' http://127.0.0.1:8000/admin/stats
```

**Expect:** `health 200`, then `{"code":"admin_required"} 403`.
**STOP if** health is not 200.

## 5. One-time recompute of the last 7 days (counts only)

First the sums as they are, then a run with `--days 7` under the same limits as the timer's unit (dude, the adm group, 400 MB), then the sums again.

**[Server — bash]**

```
Q="SELECT metric, sum(value) FROM stats_daily WHERE source = 'web' AND metric IN ('page_views', 'visitors', 'rejected_requests', 'internal_page_views') AND day >= current_date - 7 GROUP BY 1 ORDER BY 1; SELECT dimension, sum(value) FROM stats_daily WHERE source = 'api' AND metric = 'calls' AND day >= current_date - 7 GROUP BY 1 ORDER BY 1"
echo BEFORE; sudo -u postgres psql xxl_super -Atc "$Q"
sudo systemd-run --unit=scrp-stats-recompute --uid=dude --gid=dude -p SupplementaryGroups=adm -p EnvironmentFile=/home/dude/scrp/.env -p WorkingDirectory=/home/dude/scrp -p MemoryMax=400M --wait --pipe --collect /home/dude/scrp/venv/bin/python3 -m scripts.stats_collect --sources web,api --days 7
echo AFTER; sudo -u postgres psql xxl_super -Atc "$Q"
```

**Expect:**
- `BEFORE`: `page_views|…` and `visitors|…`, then the API rows per platform. There is no `admin` row yet; the admin calls were not counted at all before.
- The run prints `[web]`, then per day `page_views[…]=… rejected_requests[…]=… visitors[…]=…` and `stored N rows, as of <yesterday>`; then `[api]` with `calls[admin]=…`; and `result: web=ok api=ok`.
  - The oldest day may be listed as `partial (not stored)`. That is expected: the 14-day logs reach back only so far, and a partial day keeps its old numbers.
- `AFTER`:
  - `page_views` and `visitors` are the same or lower than BEFORE;
  - a `rejected_requests` row is new;
  - `internal_page_views` appears only after someone has used the switch;
  - an `admin` row appears under the API.

**STOP if:**
- `ERROR` appears;
- the run does not end with `result: web=ok api=ok`;
- `page_views` AFTER is **higher** than BEFORE.

**Record:** paste the BEFORE and AFTER lines into the chat, for the SU11A-70 entry.

## 6. Web deploy, with the guard

**[PC — PowerShell]**

```
git pull origin main; .\scripts\deploy_frontend.ps1
```

**Expect:** `build OK: …`, the sitemap lines, the upload, `MATCH` and a green `Done!`.
**STOP if** you see a red line or `MISMATCH`.

## 7. Browser checks

**[Browser]**

1. **Logo:**
   - On https://super.xxl.co.il/promos the header logo goes to https://super.xxl.co.il/. A screen reader names it "SUPER XXL — דף הבית".
   - On https://xxl.co.il/promos the logo goes to https://xxl.co.il.
2. **Footer:** on super.xxl.co.il the footer has "כל שירותי XXL", which opens https://xxl.co.il. On xxl.co.il it is not there.
3. **Badges:**
   - On the Super home page ("SUPER XXL באפליקציה"), in the footer, and in the portal's SUPER XXL card, the App Store badge comes first (on the right), then Google Play. Their black badges are the same height.
   - The App Store badge is Hebrew on a Hebrew page; switch the language to EN and it is English.
   - The App Store badge opens https://apps.apple.com/il/app/super-xxl/id6829450422, and the Play badge opens the Play page.
   - With Tab, both get a visible focus ring.
4. **iPhone banner:** on an iPhone (Safari, in a private tab so a past "close" is forgotten), the banner at the top reads "SUPER XXL זמינה ל-iPhone — הורידו מ-App Store" and opens the App Store page. On Android it still links to Google Play.
5. **Statistics** (https://admin.xxl.co.il → סטטיסטיקות):
   - **The switch "לא לספור את הדפדפן הזה"** is off. Turn it on: it reads "פעיל: …". In DevTools → Application → Cookies → https://super.xxl.co.il there is `xxl_internal` = `1`, domain `.xxl.co.il`, Secure, Lax, expiring in a year. Turn it off: the cookie is gone. Leave it **on** in every browser and phone you use.
   - The website table has the columns "נדחו" and "מהצוות". After step 5, "נדחו" has numbers for the recomputed days.
   - "שימוש באפליקציות ובאתר" has a "קונסולת ניהול" row.
   - **Dashboard card:** its small print says "ללא בקשות קונסולת הניהול."

**STOP if:**
- a badge opens a wrong page, or looks cropped, stretched or recoloured;
- the logo on super.xxl.co.il still leaves the site;
- the switch says the browser refused the cookie on admin.xxl.co.il.

**Note:** the internal flag counts from the moment the switch is on, and only on website page views. API calls from your browser (search, prices) are still counted under "אתר".
