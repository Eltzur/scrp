# SU11A-59 — /chains fix, admin CORS (PATCH) fix, clickable dashboard cards: runbook

Written 1 Nov 2026 for Dude.

It fixes three things:
- **`GET /chains` returned 503 on every call since 22 Oct.** The query joined every row of `prices` (7.9M) and counted distinct barcodes, which takes more than 15 s. The SU11A-49 API `statement_timeout` (15 s) has cancelled it since 22 Oct. The new query reads only `chains`, `stores` and the search build's `search_item_prices`: about 40 ms cold on production-sized local data (the old one: 44–78 s). Each API worker also caches the answer until the next search build, so a cold start cannot time out. If the database fails, the worker serves its last list.
- **Admin console, מבצעים → "ביטול ממומן" showed "אין חיבור לשרת".** That button sends `PATCH`, and the API's CORS list had no `PATCH`, so the browser's preflight got 400. `PATCH` is now allowed for `https://admin.xxl.co.il` only. The other allowed origins keep GET / POST / PUT / DELETE; there is no wildcard.
- **לוח בקרה:** the titles of the ביקורות, קטגוריות and קידום והסתרת מבצעים cards are links to their tabs. קטגוריות opens on הצעות קטגוריה when suggestions are pending, and קידום והסתרת מבצעים opens on מקודמים. The chain freshness and search build titles stay plain text.

**What users saw from 22 Oct (until step 2 below):** on super.xxl.co.il, the chain filter on the search / compare page had no chains to pick, and the basket drawer showed "רשתות · כל הרשתות" with no chain buttons. Search, compare and the basket still worked across all chains, and nothing showed an error. The promos page and the admin console use `/promos/chains` and were not affected. The mobile app does not call `/chains`.

**How to run it**
- Run the steps in order. Each step names where it runs:
  - **[Server — bash]:** `ssh dude@185.229.226.190`, interactive, in `~/scrp`.
  - **[PC — PowerShell]:** PowerShell in `C:\scrp`, on a PC that has `web/.env.production`.
  - **[Browser].**
- If a step says STOP, paste the output to the chat and do not improvise a fix.
- Nothing here prints `.env`, a token or an email address.
- **Quiet times** (same as SU11A-49): avoid 04:00–04:30, 10:00 until `scrp-cron` is `inactive`, and 14:30.

**What it deploys**

| Part | What changes |
|---|---|
| DB | Nothing (no migration). |
| API | `/chains` uses the new query and the per-worker cache (`db/query.py`). CORS: `PATCH` is allowed from `https://admin.xxl.co.il` only (`api/main.py`). |
| Web | Admin dashboard card links (admin chunk only). Shop main JS chunk: +0.08 kB (+0.03 kB gzip). |
| nginx | Nothing. The 400 came from the API's CORS layer, not from nginx. |

**`/chains` fields:** `chain_id`, `name` and `total_stores_loaded` are the same as before: every chain, with all its stores. `total_barcodes` now counts the items with a live price in that chain, taken from the search build. Before, it counted every barcode ever loaded, including dead stores. No client reads the two counts; the web uses only `chain_id` and `name`.

---

## 1. Pull

**[Server — bash]**

```
cd ~/scrp && git pull origin main && git log --oneline -2
```

**Expect:** the top line is `feat: SU11A-59 /chains fix, admin CORS PATCH, dashboard card links`.
**STOP if** the pull fails or prints a merge conflict.

## 2. Restart the API

**[Server — bash]**

```
sudo /usr/local/bin/xxl-restart.sh scrp-api && systemctl is-active scrp-api
```

**Expect:** the service log tail, then `active`.
**STOP if** it is not `active`.

## 3. nginx

Nothing to do. SU11A-59 changes no nginx file.

## 4. Check the API

**4a. `/chains` three times: status and time**

**[Server — bash]**

```
for i in 1 2 3; do curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' https://api-super.xxl.co.il/chains; done
```

**Expect:** three lines starting with `200`. The first can take up to about 1 s; the others are about 0.1 s or less.
**STOP if** any line shows `503`, or any time is above 3 s.

**4b. The list**

**[Server — bash]**

```
curl -s https://api-super.xxl.co.il/chains | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d), 'chains;', sum(c['total_barcodes'] > 0 for c in d), 'with items;', sum(c['total_stores_loaded'] for c in d), 'stores')"
```

**Expect:** about 14–16 chains (every row of `chains`). Most chains have items, and the store total is the size of the `stores` table (about 1,000).
**STOP if** it prints `0 chains`.

**4c. CORS preflight for the sponsored toggle**

**[Server — bash]**

```
for o in https://admin.xxl.co.il https://super.xxl.co.il; do curl -s -o /dev/null -X OPTIONS -H "Origin: $o" -H 'Access-Control-Request-Method: PATCH' -H 'Access-Control-Request-Headers: authorization,content-type' -w "$o %{http_code}\n" https://api-super.xxl.co.il/admin/promos/curation/1; done
```

**Expect:** `https://admin.xxl.co.il 200`, then `https://super.xxl.co.il 400`. The shop's origin may not send `PATCH`.
**STOP if** the admin line is not `200`.

**4d. No timeouts since the restart**

**[Server — bash]**

```
sudo journalctl -u scrp-api --since "15 min ago" --no-pager | grep -c "query timeout"
```

**Expect:** `0`.
**STOP if** the count is above 0. Then also paste `sudo journalctl -u scrp-api --since "15 min ago" --no-pager | grep "query timeout" | tail -5`.

## 5. Web deploy, with the guard

Only from a PC with `web/.env.production`.

**[PC — PowerShell]**

```
git pull origin main; .\scripts\deploy_frontend.ps1
```

**Expect:**
- `build OK: contains https://api-super.xxl.co.il and https://…supabase.co`
- the upload
- `MATCH`
- a green `Done!`

**STOP if** you see a red line (the guard, a failed build or `MISMATCH`).

## 6. Browser checks

**6a. Chain filter**

**[Browser]** Open https://super.xxl.co.il and search `חלב`.

**Expect:** the chain filter (placeholder "כל הרשתות") lists the chains, and picking one narrows the results. In the basket drawer, the רשתות row shows a button for each chain.

**6b. ביטול ממומן**

**[Browser]** Open https://admin.xxl.co.il, then מבצעים, then מקודמים.
- On a pin marked **ממומן**, click **ביטול ממומן**.
  - **Expect:** the toast "נשמר", and the ממומן tag is gone from the card.
  - If that pin really is a paid placement, click **סימון כממומן** and confirm, to put the label back.
- If there is no sponsored pin: in חיפוש, pin any live promotion with ממומן ticked. Then click ביטול ממומן on it in מקודמים, and remove the test pin (הסרה). Both writes show in יומן פעולות.

**STOP if** "אין חיבור לשרת" still appears. Then run step 4c again and paste both outputs.

**6c. Dashboard links**

**[Browser]** Open לוח בקרה and check each card title:

| Card title | Opens |
|---|---|
| ביקורות | ביקורות לטיפול |
| קטגוריות | קטגוריות, on the הצעות קטגוריה sub-tab when the card shows pending suggestions > 0; otherwise on חיפוש |
| קידום והסתרת מבצעים | מבצעים, on מקודמים |
| עדכון מחירים לפי רשת, בניית החיפוש | not links (no tab yet) |

Also check the keyboard: press Tab until a card title has a green focus ring, then press Enter; it should open that tab. The browser's Back button returns to לוח בקרה.

## 7. Rollback

**7a. API**, if step 4 fails. This goes back to the SU11A-58 API, with the old `/chains` (503 again) and no PATCH in CORS:

**[Server — bash]**

```
cd ~/scrp && git log --oneline -3
git checkout HEAD~1 -- api/main.py db/query.py && sudo /usr/local/bin/xxl-restart.sh scrp-api && systemctl is-active scrp-api
```

**Expect:** `active`. Before the next pull, run `git checkout HEAD -- api/main.py db/query.py` to return those files to the release.

**7b. Web**, if the dashboard misbehaves. Run on a PC with `web/.env.production`:

**[PC — PowerShell]**

```
git checkout HEAD~1 -- web/; .\scripts\deploy_frontend.ps1; git checkout HEAD -- web/
```

**Expect:** `MATCH`, then `Done!`.

---

## Reference

**Why `/chains` was slow** (local EXPLAIN on 14 chains, 936 stores and 7.9M prices, 1.5 GB):
- **Old:** a nested loop over all 937 store rows, with an index-only scan of `prices` per store: 7.9M rows into a sort for `COUNT(DISTINCT)`, spilling 52k temp blocks to disk. It ran 78 s under EXPLAIN and 44 s warm.
- **New:** `stores` (936 rows) and `search_item_prices` (one row per item and live chain), both grouped by chain: 44 ms under EXPLAIN and 35 ms plain.
- Production's `prices` is 3.7 GB on a 3.8 GiB box, so the old query was disk-bound there and always took more than 15 s. The ANALYZE you ran could not help, because the plan was never the problem.

**Cache:** per worker. The search build stamp (`search_items.built_at` and `search_item_prices.built_at`) is re-read at most once a minute, the list is rebuilt when the stamp changes (after the 14:30 build), and it is refreshed at least every 6 h. If the database fails, the last list is served and logged as `/chains: serving the cached list (…)`. Only a worker that has never loaded the list can still fail.

**Other public endpoints with the same risk** (report only; not changed):
- **`/promos/today`:** an earlier production measurement was 10.9–11.1 s for 200 rows (archive, "Cost (median, interleaved, cache warm)"), close to the 15 s limit. It did not show in the 22 Oct – 1 Nov timeout logs. It could not be re-timed here: there is no production-sized promo data on this PC.
- **`/stats`** (the web StatsBar): `COUNT(*)` over all of `prices`, plus a scan of `prices.store_fk`. Locally 1.0 s cold and 0.2 s warm; on production it is disk-bound like the old `/chains`, but below 15 s so far (no timeouts logged).
- Every other public GET (`/cities`, `/stores`, `/stores/coordinates`, `/coverage`, `/freshness`, `/promos/chains`, `/promos/cities`, `/categories/tree`) reads small tables or is filtered by index. None is above 5 s locally.

**Tests:**
- `tests/test_chains_cors_su11a59.py` (60): the cache (hit, stamp change, max age, store-only query without the build tables, a failing DB serves the cached list, a cold worker raises, the route answers 200 from the cache), and the CORS preflight. The preflight tests take every call in `web/src/admin/api.ts` and check: 200 from the admin origin with the method listed and no wildcard; 400 and no Allow-Origin from other origins; no PATCH for the shop's origin.
- `tests/test_chains_su11a59_pg.py` (4): the same chains, order and store counts as the old query, `total_barcodes` equal to the build, the store-only variant, and the endpoint with invalidation by stamp.
- `web/scripts/admin-nav.test.mjs`: the hash helpers, the card link markup and the three dashboard links.
