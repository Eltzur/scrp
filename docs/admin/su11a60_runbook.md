# SU11A-60 — promos page: filters first, מבצעים מקודמים, category filter; /promos/today cache: runbook

Written 1 Nov 2026 for Dude.

**What changes for users (super.xxl.co.il/promos)**
- **No default list.** The page opens on the search box, the filters and, when pins match, **מבצעים מקודמים**, plus a short text and one-tap department chips. Before, it opened on "כל הרשתות" and listed the chains alphabetically (Osher Ad first). The city is still the remembered / detected one; a city alone does not open a list.
- **Results appear once you pick a chain, a category or type a product:**
  - **No chain:** one list across chains, sorted by the chosen sort (default הנחה גדולה), 30 at a time with טען עוד. Each card shows chain · branch, and "ועוד N סניפים" when the same deal is in more branches.
  - **A chain:** the chain → branch grouping as today, with pins first inside their branch.
- **Category filter:** department / category / sub-category from the categories tree. A low-confidence label counts only at department level (the SU11A-57 rule); items with no label are found only by text search.
- **מבצעים מקודמים:** the active pins matching the city and the other filters, in pin rank order, at most 10, across chains. Each card shows the chain, the branch, the number of branches, and **ממומן** when sponsored. Hidden promotions never appear. The section is not shown when no pin matches.
- **The URL holds the view** (city, chain, branch, cat, q, sort, bands, types, ending), so a link opens the same view and Back works.

**Prices:** pins and hides still change no price. The SU11A-58 byte-identical tests (search, compare, basket, `/product`, `/promos/bulk`, search build) pass unchanged.

**How to run it**
- Run the steps in order. Each step names where it runs:
  - **[Server — bash]:** `ssh dude@185.229.226.190`, interactive, in `~/scrp`. Type Hebrew only there (CLAUDE.md rule 11); the commands below URL-encode it.
  - **[PC — PowerShell]:** PowerShell in `C:\scrp`, on a PC that has `web/.env.production`.
  - **[Browser].**
- If a step says STOP, paste the output to the chat and do not improvise a fix.
- Nothing here prints `.env`, a token or an email address.
- **Quiet times:** avoid 04:00–04:30, 10:00 until `scrp-cron` is `inactive`, and 14:30.
- **Run steps 2 and 5 close together.** Between them the old web page is still live, and the API now caps its all-chains request at 100 rows (the old page shows 100 promos and no טען עוד).

**What it deploys**

| Part | What changes |
|---|---|
| DB | Nothing (no migration). The category filter reads `categories` / `item_categories` (su11a52); without them it matches nothing and the chips are not shown. |
| API | `/promos/grouped` gains `category`, and without chain / category / q / branch it returns at most 100 rows in all. New `GET /promos/list` (the flat list) and `GET /promos/promoted` (the pins). `/promos/today`: a per-worker cache (below). |
| Web | The promos page above. Shop main JS chunk +5.6 kB raw, **+1.72 kB gzip**. |
| nginx | Nothing. |

**`/promos/today` (no web or app page calls it today):**
- **Before:** 11.4 s on production-sized local data, matching the ~11 s measured on production earlier. Most of it is a join of every active promo row (~840k) to its shelf price over all 7.9M prices, which spills to disk, plus an external sort of 814k rows.
- **Now:** the answer is cached per API worker and per (city, chain).
  - It is rebuilt when a store load lands (`stores.last_loaded_at`), when pins / hides change, or after 5 minutes. A promotion that ends can therefore stay listed up to 5 minutes.
  - A hit takes about 1 ms. If the database fails, the last answer is served.
  - The first call per worker and key still takes about 11 s, under the 15 s limit.
- **Making the cold call cheap** needs a precomputed table filled by the 14:30 build. That's a larger change, not started; see the handoff.

---

## 1. Pull

**[Server — bash]**

```
cd ~/scrp && git pull origin main && git log --oneline -2
```

**Expect:** the top line is `feat: SU11A-60 promos page filters-first, promoted section, category filter`.
**STOP if** the pull fails.

## 2. Restart the API

**[Server — bash]**

```
sudo /usr/local/bin/xxl-restart.sh scrp-api && systemctl is-active scrp-api
```

**Expect:** `active`.
**STOP if** it is not `active`.

## 3. Timings (three times each)

**3a. Pick a department id and check the tree**

**[Server — bash]**

```
curl -s https://api-super.xxl.co.il/categories/tree | python3 -c "import json,sys; n=json.load(sys.stdin)['nodes']; print(len(n), 'nodes'); [print(x['id'], x['name_he']) for x in n if x['level'] == 1]"
```

**Expect:** about 200 nodes, then the department lines. Note one broad department id (for example the dairy one) and use it as `DEPT` below.
**If it prints `0 nodes`:** the category tables are not applied. Skip the `category` lines in 3b and check 6b with a chain or a search instead; nothing else is affected.

**3b. The timings**

Replace `D07` with your `DEPT` and `7290027600007` with any chain id from `curl -s https://api-super.xxl.co.il/promos/chains`.

**[Server — bash]**

```
DEPT=D07; CHAIN=7290027600007; API=https://api-super.xxl.co.il
t() { for i in 1 2 3; do curl -s -G -o /dev/null -w "$1 %{http_code} %{time_total}s\n" "${@:2}"; done; }
t today        $API/promos/today
t today-tlv    $API/promos/today --data-urlencode 'city=תל אביב-יפו'
t list-dept    $API/promos/list --data-urlencode 'city=תל אביב-יפו' --data-urlencode "category=$DEPT"
t list-q       $API/promos/list --data-urlencode 'city=תל אביב-יפו' --data-urlencode 'q=חלב'
t grouped      $API/promos/grouped --data-urlencode 'city=תל אביב-יפו' --data-urlencode "chain=$CHAIN" --data-urlencode 'limit=300'
t grouped-dept $API/promos/grouped --data-urlencode 'city=תל אביב-יפו' --data-urlencode "category=$DEPT" --data-urlencode 'limit=300'
t promoted     $API/promos/promoted --data-urlencode 'city=תל אביב-יפו'
t promoted-all $API/promos/promoted
```

**Expect** (every line `200`):
- **`today`:** the first one or two calls up to about 12 s (each API worker fills its own cache); later calls under 0.1 s. Once the 3 workers have filled their cache, all calls are fast. `today-tlv` is about 1 s cold.
- **`list-*`, `grouped*`:** under 1.5 s each. Local times were 0.24–0.5 s for Tel Aviv, and 1.1 s for a department across all cities.
- **`promoted*`:** under 0.3 s (local: 0.05–0.1 s).

**STOP if** any line is `503`, or any time other than `today` is above 5 s. Then also paste:

```
sudo journalctl -u scrp-api --since "10 min ago" --no-pager | grep -E "query timeout|serving the cached" | tail -5
```

## 4. (no nginx step)

SU11A-60 changes no nginx file.

## 5. Web deploy, with the guard

Only from a PC with `web/.env.production`.

**[PC — PowerShell]**

```
git pull origin main; .\scripts\deploy_frontend.ps1
```

**Expect:** `build OK: …`, the upload, `MATCH`, then a green `Done!`.
**STOP if** you see a red line.

## 6. Browser checks

Use a private / incognito window for 6a, so no city is remembered.

**6a. Fresh visit**

**[Browser]** Open https://super.xxl.co.il/promos.

**Expect:**
- the search box and the filters (עיר, רשת, קטגוריה, סניף, מיון, the הנחה and סוג chips);
- the text "איזה מבצעים מעניינים אתכם?" with department chips;
- **no promo list**;
- מבצעים מקודמים only if a pin matches the city;
- the address bar shows `?city=…`.

On a phone, or with the browser at 390 px width, there should be no sideways scrolling.

**6b. A department chip**

**[Browser]** Tap a department chip.

**Expect:**
- one list across chains, sorted הנחה גדולה (the biggest % first);
- each card shows chain · branch, and "ועוד N סניפים" where the deal is in more branches;
- 30 cards, then טען עוד, which adds 30 more;
- the address bar gains `&cat=D…`.

**6c. A chain**

**[Browser]** Pick a chain in רשת.

**Expect:** the chain → branch grouping as before. The סניף select is now enabled.

**6d. Search**

**[Browser]** Clear the chain (כל הרשתות) and type `חלב` in the search box.

**Expect:** after a moment, a flat list of milk deals, and `q=…` in the address bar.

**6e. A shared URL**

**[Browser]**
1. Pick a sort (חיסכון בשקלים) and a הנחה chip, then copy the address.
2. Open it in a new tab.
3. Press Back in the first tab.

**Expect:**
- The new tab shows the same city, category / search, sort and chips, and the same list.
- Back in the first tab returns to the previous choice.

**6f. Pins**

**[Browser]**
1. In https://admin.xxl.co.il → מבצעים → חיפוש, pin two live promotions from **different chains**, both with an end date (the field "מסתיים") a few days ahead.
   - First: rank 1 ("מקום"), with "קידום בתשלום (ממומן)" ticked.
   - Second: rank 2, without ממומן.
   - Both should have a branch in the city you test with.
2. Within 30 seconds, reload super.xxl.co.il/promos (same city).

**Expect:**
- מבצעים מקודמים shows the rank-1 promotion first (with **ממומן**), then the rank-2 one (without the label).
- Each card shows its chain and branch count.
- They stay on top when you then pick a department or search, as long as they match it.

**6g. Remove both pins**

**[Browser]** Admin → מבצעים → מקודמים → הסרה on both, then reload the promos page.

**Expect:** the section is gone (if no other pin matches).

## 7. Rollback

**7a. API**, if step 3 fails. This goes back to the SU11A-59 API:

**[Server — bash]**

```
cd ~/scrp && git log --oneline -3
git checkout HEAD~1 -- api/ db/query.py db/promo_curation.py && sudo /usr/local/bin/xxl-restart.sh scrp-api && systemctl is-active scrp-api
```

**Expect:** `active`. Before the next pull, run `git checkout HEAD -- api/ db/`.

If the SU11A-60 web is already live, do 7b as well: the new page needs `/promos/list` and `/promos/promoted`. Without them it shows the start state and, after a choice, "שגיאה בטעינת המבצעים".

**7b. Web.** Run on a PC with `web/.env.production`:

**[PC — PowerShell]**

```
git checkout HEAD~1 -- web/; .\scripts\deploy_frontend.ps1; git checkout HEAD -- web/
```

**Expect:** `MATCH`, then `Done!`.

## 8. Follow-up (1 Nov 2026): the page never waits on the city

This is a web-only fix to the SU11A-60 page; the API is unchanged. If SU11A-60 is already deployed, do 8a and 8b only; otherwise step 5 above already ships it.

**What was wrong** (reproduced with Playwright on production, read-only loads):
- **The spinner that never ended.** The page resolved the city once per mount (a `resolved` ref). The header "מבצעים" link drops `?city` while the page stays mounted, so the city stayed unresolved. That left a spinner forever, the city select disabled on "כל הערים", and no new requests.
- **The city "detection" was not GPS.** No page uses `navigator.geolocation`. It was `fetch('http://ip-api.com/…')` with no timeout, which browsers block as mixed content on https (SU11A-48 F-12). Where the browser held it instead of failing it, the page waited on it.
- **The whole content area waited** for the city and the promoted section before showing anything.
- **Slow networks:** on a slow phone profile (3G, 6× CPU) a direct load took 10.7–11.6 s to show content. Most of that (6.8 s) is downloading the site's ~280 kB of JS, before any page code runs; the gating added the rest.

**What changed:**
- **City:** URL `city`, else the remembered city, else כל הערים, decided synchronously. It is written to the URL with replace, and the same happens on an in-app link. The select is never disabled.
- **IP lookup removed** from the promos page and the search page (`web/src/utils/city.ts`).
- **מבצעים מקודמים and the list are separate queries.** Each renders when its own data arrives, with its own loading line / spinner and its own נסו שוב on failure. A newer filter choice aborts the superseded requests.

**Playwright, local production build with the API mocked:**

| Scenario | Content (filters, start text, chips) | Other |
|---|---|---|
| Direct `/promos`, promoted request held for 3 s | 0.42 s | promoted section at 3.5 s |
| Home → header link | 0.18 s | |
| On `/promos?city=…&cat=…` → header link | 0.06 s | |
| Promoted returns 500 | 0.46 s | its own retry at 1.6 s (after one retry) |
| A category with promoted held for 3 s | list at 0.59 s | |
| Two quick filter changes | | the superseded `/promos/list` and `/promos/promoted` requests aborted |

**8a. Web deploy.** Run on a PC with `web/.env.production`:

**[PC — PowerShell]**

```
git pull origin main; .\scripts\deploy_frontend.ps1
```

**Expect:** `build OK`, `MATCH`, `Done!`.
**STOP on** a red line.

**8b. Checks**

**[Browser]**
1. On super.xxl.co.il/promos?city=… pick a category.
2. Click the header "מבצעים" icon.
   - **Expect:** at once, the filters, the start text and the chips; the city select is enabled; the address bar shows `?city=…`.
3. Refresh the page (Ctrl+F5).
   - **Expect:** the filters and chips within about a second. מבצעים מקודמים may show "טוען מבצעים מקודמים…" briefly.
4. In DevTools → Console, check there is **no** "Mixed Content … ip-api.com" error any more, on the promos page or on the search page.

**Rollback:** step 7b, using the commit before this fix (`git checkout HEAD~1 -- web/`).

---

## Reference

**Local timings, before → after** (14 chains, 936 stores, 7.9M prices / 1.4 GB, 842k promos, 75k items, 50k category labels; three runs, warm):

| Read | Before | After |
|---|---|---|
| `/promos/today` (all) | 11.2–11.6 s | first call per worker and key 10.8 s, then 1 ms |
| `/promos/today` city Tel Aviv | 0.76–0.89 s | the same cold, then 1 ms |
| `/promos/grouped` chain + Tel Aviv, 300 | 0.42–0.49 s | unchanged |
| `/promos/grouped` Tel Aviv + department, 300 | (no category filter) | 0.24–0.26 s |
| `/promos/list` Tel Aviv + department, page 1 / page 5 | — | 0.24 s / 0.22 s |
| `/promos/list` all cities + department | — | 1.1–1.3 s |
| `/promos/list` Tel Aviv + q=חלב | — | 0.35–0.39 s |
| `/promos/list` Tel Aviv, nothing chosen (capped at 100; the page never asks) | — | 1.6–1.8 s |
| `/promos/promoted` Tel Aviv / all cities, 5 pins | — | 0.05 s / 0.1 s (8.9 s for all cities before the `promo_id` pre-filter was added) |

**Tests:**
- `tests/test_promos_page_su11a60_pg.py` (19) covers:
  - category matching, including the low-confidence department-only rule, unlabelled items and the combination with chain and bands;
  - the flat list: the same (chain, item) set as grouped, branch counts that add up, all three sorts, exact paging, live stores only;
  - the unfiltered cap;
  - promoted: order, city counts, chain / category filters, the hide winning, sponsored, the cap;
  - the `/promos/today` cache: same output, stamp invalidation, curation key, DB failure.
- `tests/test_promo_curation_su11a58_pg.py` (byte-identical pricing) passes unchanged.
- `web/scripts/promos-page.test.mjs` (7, server-rendered real page): the start state has no list; a chain, a category or search text asks for results; a city alone doesn't; the promoted section shows chain, branches and ממומן; the URL restores the filters; the view round-trips.
