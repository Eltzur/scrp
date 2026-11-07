# SU11A-71 — GA4 sends data (gtag fix) + only real pages count: runbook

Written 7 Nov 2026 for Dude. It follows SU11A-70: run the SU11A-69 and SU11A-70 runbooks first if they are not done yet.

**What changes**
- **GA4 (website, one fix for super.xxl.co.il and the portal xxl.co.il / www):**
  - **The bug:** the `gtag` shim in `web/src/utils/analytics.ts` pushed Arrays into `dataLayer`. gtag.js reads only Arguments objects, so every `js` / `config` / `page_view` was ignored. Since launch no hit was sent and no `_ga` cookie was set, so property 537761103 is empty. **GA4 data starts on the day of step 4's deploy; there is no history before it.**
  - **The fix:** Google's canonical shim, `function gtag() { dataLayer.push(arguments); }`. The consent gate is unchanged: nothing loads before "אישור". Declining or withdrawing now also sets Google's opt-out flag `ga-disable-G-YB4X4E5ZKM`, so a tag already loaded stops too.
  - **Path only:** the page path is sent without the query string or hash. `page_location` is the site's address plus the path, and `page_referrer` is only the other site's origin (for example `https://www.google.com/`). Nothing a visitor typed (`?q=…`) or chose (`?city=…`) is sent.
  - **One page view per route:** a query-only change, such as `/promos` → `/promos?city=…`, is no longer a new page view. Before, /promos fired three in one visit.
- **Server statistics:** the site is an SPA, so nginx answers 200 (index.html) for any path, `/wp-admin` and `/xmlrpc.php` too. A page view now also needs the path to be one of the site's own routes (the same list as the top pages). Any other 200 counts as **"נדחו"** (`rejected_requests`).

**Production impact**
- One recompute of the last 7 days of statistics.
- One web deploy.
- Two GA4 settings to check (step 5).
- No migration, no API restart, no nginx change, no price or user data.

**How to run it**
- Run the steps in order. Each step names where it runs:
  - **[Server — bash]:** `ssh dude@185.229.226.190`, interactive, in `~/scrp`.
  - **[PC — PowerShell]:** in `C:\scrp` on the **home PC** (the one with `web/.env.production`).
  - **[Browser].**
- If a step says STOP, paste the output to the chat and do not improvise a fix.
- Nothing here prints `.env`, a raw log line, an IP address or a cookie value: only counts and sums.

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

**Expect:** one of the top lines is `fix: SU11A-71 GA4 gtag shim, path-only page views, stats count real routes only`.
**STOP if** the pull fails.

## 3. One-time recompute of the last 7 days (counts only)

First the sums as they are, then a run with `--days 7`, then the sums again. The run uses the same limits as the timer's unit: dude, the adm group, 400 MB. The stats job starts fresh each run, so no restart is needed.

**[Server — bash]**

```
Q="SELECT metric, sum(value) FROM stats_daily WHERE source = 'web' AND metric IN ('page_views', 'visitors', 'bot_page_views', 'rejected_requests', 'internal_page_views') AND day >= current_date - 7 GROUP BY 1 ORDER BY 1; SELECT 'other_top_path', coalesce(sum(value), 0) FROM stats_daily WHERE source = 'web' AND metric = 'top_path' AND dimension LIKE '%/(other)' AND day >= current_date - 7"
echo BEFORE; sudo -u postgres psql xxl_super -Atc "$Q"
sudo systemd-run --unit=scrp-stats-recompute --uid=dude --gid=dude -p SupplementaryGroups=adm -p EnvironmentFile=/home/dude/scrp/.env -p WorkingDirectory=/home/dude/scrp -p MemoryMax=400M --wait --pipe --collect /home/dude/scrp/venv/bin/python3 -m scripts.stats_collect --sources web,api --days 7
echo AFTER; sudo -u postgres psql xxl_super -Atc "$Q"
```

**Expect:**
- `BEFORE`: the metric sums, then `other_top_path|N`. N is the page views that were not routes.
- The run prints `[web]`, per day `page_views[…]=… rejected_requests[…]=…`, and `stored N rows, as of <yesterday>`; then `[api]`; and `result: web=ok api=ok`.
  - The oldest day may be listed as `partial (not stored)`. That is expected, and a partial day keeps its old numbers.
- `AFTER`:
  - `page_views` is lower than or equal to BEFORE, by about BEFORE's `other_top_path`;
  - `rejected_requests` is higher by about the same number;
  - `visitors` and `bot_page_views` are the same or lower;
  - `other_top_path|0`, apart from a partial oldest day.

**STOP if:**
- `ERROR` appears;
- the run does not end with `result: web=ok api=ok`;
- `page_views` AFTER is **higher** than BEFORE.

**Record:** paste the BEFORE and AFTER lines into the chat, for the SU11A-71 entry.

## 4. Web deploy, with the guard

**[PC — PowerShell]**

```
git pull origin main; .\scripts\deploy_frontend.ps1
```

**Expect:** `build OK: …`, the sitemap lines, the upload, `MATCH` and a green `Done!`.
**STOP if** you see a red line or `MISMATCH`.

**Record:** the date. GA4 data starts on it.

## 5. GA4 settings: no automatic page views, no site search

The site sends its own page views, one per route and path only. GA4's "Enhanced measurement" can add page views of its own on every history change, with the full address, and its "Site search" reads `?q=` from the address. Both work against the two rules above.

**[Browser]**

1. https://analytics.google.com → Admin → Data collection and modification → Data streams → the web stream (G-YB4X4E5ZKM) → Enhanced measurement → the gear icon.
2. Page views → Show advanced settings: turn **off** "Page changes based on browser history events". Leave "Page views" itself on.
3. Turn **off** "Site search".
4. Save.

**Expect:** Enhanced measurement still on, page views on, history-change page views off, site search off.

**If needed:** the same screen turns both back on.

## 6. Browser check: GA4 receives the visit, path only, one hit per page

**[Browser]** Chrome without ad blockers or privacy extensions. If GA shows nothing, rule out client-side blocking first (CLAUDE.md, Analytics).

1. Open a private window, then DevTools (F12) → Network, and type `collect` in the filter box.
2. Open https://super.xxl.co.il/promos. The cookie banner shows, and the Network tab lists **no** `collect` request.
3. Click **"אישור"**. Within a few seconds one `…/g/collect?v=2&tid=G-YB4X4E5ZKM…` request appears with `en=page_view`.
   - Click it → Payload (or Headers → Query String Parameters): `dl` is `https://super.xxl.co.il/promos` with **no `?`**, and `ep.page_path` is `/promos`.
   - DevTools → Application → Cookies → https://super.xxl.co.il: `_ga` and `_ga_YB4X4E5ZKM` exist.
4. Choose a city on the promos page. The address gains `?city=…`, but **no** new `page_view` appears.
5. Click "קטגוריות" in the header. **One** new `page_view` appears, with `dl` `https://super.xxl.co.il/categories` and `dr` `https://super.xxl.co.il/promos`.
6. In GA4 → Reports → Realtime, the visit shows within about a minute, with the pages /promos and /categories.
7. Optional: open https://xxl.co.il in another private window and accept. Its `page_view` has `dl` `https://xxl.co.il/`.
8. Footer → "עוגיות" (it clears the choice), then "דחייה". Then click a header link: no new `collect` request.

**STOP if:**
- a `collect` request appears before "אישור";
- any `dl`, `dr` or `ep.page_path` contains `?` or `#`;
- one route shows two `page_view` requests;
- nothing appears in Realtime after 5 minutes **and** the Network tab showed a `collect` request with status 204. Without that request, it is client-side blocking; use a clean browser.

**Note:** GA4 standard reports fill in after 24–48 hours. Realtime is the check for today.
