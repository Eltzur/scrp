# Search speed (SU11A-47) — server runbook

Written in SU11A-47 (21 Oct 2026). For Dude, on the server (`ssh dude@185.229.226.190`, interactive). Run the steps in order. Each step lists what to expect and when to STOP. If you stop, paste the output to the chat and do not improvise a fix.

Nothing here prints `.env` or any secret.

**What this deploys.** `search_item_prices`: one precomputed row per barcode and chain (the quote search v2 shows for that chain), filled by the existing daily build. Unfiltered v2 `/search` then prices its page from there instead of the 7.9M-row `prices` table. Also new: `GET /suggest` (type-ahead), a per-worker response cache, and `Server-Timing` / `Cache-Control` headers. Filtered searches (city, chain, group_by=store, engine=v1) and `/compare` work exactly as before.

**Safe by construction.** The API uses `search_item_prices` only while its `built_at` equals `search_items.built_at`, and only for a page whose items all have rows and whose winning promos have not ended. Anything else, including a missing table, falls back to today's live price fetch for that request.

**Quiet times** (as in the SU11A-36 runbook):
- 04:00–04:30 backup
- 05:30 account sweep
- 10:00 until the daily load finishes (`systemctl is-active scrp-cron` prints `inactive` when done)
- 14:30 daily `scrp-search-items` build (the build in step c is the same job; do not run them together)
- Sunday 14:00–14:30 GS1, 15:00 geocode, 17:00 image backup

Good windows: a weekday afternoon after about 15:30, or an evening.

---

## a) Pull

```
cd ~/scrp && git status --short | head -5 && git pull origin main && git log --oneline -4
systemctl is-active scrp-cron scrp-search-items
free -m
```

**Expect:**
- `git status` prints nothing (or only files you know about).
- The pull fast-forwards. The log shows `docs: SU11A-47`, `feat(web): SU11A-47 ...` and `feat(search): SU11A-47 precomputed prices, /suggest, cache`.
- Two `inactive` lines.
- `free -m` "available" of at least 1500.

**STOP if** the pull reports a conflict, either unit is `active` (wait, then rerun), or available memory is under 1200 MB.

The running API is still the old code until step e. It never reads the new table.

## b) Apply the migration (additive, idempotent)

```
cat ~/scrp/db/migrations/su11a47_search_prices.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
sudo -u postgres psql xxl_super -c '\d search_item_prices' -c '\d search_item_prices_next'
sudo -u postgres psql xxl_super -tAc "SELECT tablename, tableowner FROM pg_tables WHERE tablename LIKE 'search\_item\_prices%' ORDER BY 1"
```

**Expect:**
- `BEGIN`, 2× `CREATE TABLE`, 2× `ALTER TABLE`, `COMMIT`.
- Each `\d` lists 21 columns (`item_code` … `built_at`) and one index: `search_item_prices_pkey` / `search_item_prices_next_pkey`, `PRIMARY KEY, btree (item_code, chain_id)`.
- The owner query prints two rows, `search_item_prices|scrp_app` and `search_item_prices_next|scrp_app`.

**STOP if** there is any `ERROR`, or an owner is not `scrp_app` (the build's swap renames the tables and needs ownership).

## c) Build and swap in (search_items + search_item_prices)

```
cd ~/scrp && (ulimit -v 1500000; time venv/bin/python3 -m scripts.build_search_items --apply --out /tmp/search_items_apply47.json) 2>&1 | tee /tmp/search_items_apply47.txt
sudo -u postgres psql xxl_super -tAc "SELECT (SELECT max(built_at) FROM search_items) = (SELECT max(built_at) FROM search_item_prices), (SELECT count(*) FROM search_item_prices), (SELECT count(DISTINCT item_code) FROM search_item_prices), (SELECT count(*) FROM search_items)"
```

What happens: the usual search_items build, then 16 `search_item_prices chunk k/16: N ms` lines (each one statement in Postgres, under the 10-minute statement timeout; nothing is pulled into Python), then one swap of both tables.

**Expect:**
- `live stores: …` near 865 and `live items: …` around 130K, as in every timer run.
- 16 chunk lines. Each chunk takes one item_code range (1/16 of the barcodes), reads its price rows and runs the same promo pick as a live search. For scale, a local synthetic run (20K items, 1.16M prices, everything in RAM) took 44 s in total, about 5 min if scaled to 132K items. The server reads `prices` from disk, so expect roughly 5–20 min in total, or under 1–2 min per chunk.
- The JSON at the end has `"search_item_prices": {"rows": …, "items": …, "build_items": …, "chunks": 16, "swapped": true}`, with `items` within 2% of `build_items` and `rows` roughly 3–5× `items` (one row per item and chain).
- `real` time: the SU11A-36 build plus the chunks.
- The psql line: `t|<rows>|<items>|<search_items rows>`.

**STOP (do not run d) if:**
- `MemoryError`, `Killed`, or `canceling statement due to statement timeout`.
- Any single chunk takes more than 5 minutes (the statement timeout is 10). Let it finish, then paste the chunk lines: the 14:30 timer would hit the same time.
- Any `WARNING: search_item_prices ...` line, or `"swapped": false`. search_items is still swapped in and searches keep working exactly as today (live price fetch). Paste the output.
- The psql line starts with `f`.

## d) Check precomputed prices against the live fetch (read-only)

```
cd ~/scrp && (ulimit -v 1500000; time venv/bin/python3 -m scripts.compare_search_v2 --check-precomputed 300 --out /tmp/check_precomputed.json) 2>&1 | tee /tmp/check_precomputed.txt; echo "exit $?"
```

All connections are READ ONLY with a 60 s statement timeout. For 300 random live items, in pages of 30, it builds each page's JSON from `search_item_prices` and from the live fetch (the same functions the API uses) and compares them.

**Expect:**
- `search_items built_at X; search_item_prices built_at X (N rows)`, with the two timestamps equal.
- `items 300; compared 300; MISMATCHES 0; not served by search_item_prices ...: 0` (a few "not served" are fine: an item whose winning promo ended since the build is served live, by design).
- A `page of 30, ms` line: precomputed in single-digit ms against hundreds of ms for live.
- `exit 0`.

**STOP if** MISMATCHES is not 0 (exit 1), or the first line says STOP (exit 2). Paste the whole of `/tmp/check_precomputed.txt`; it holds barcodes and field names only. To undo the build while waiting: step g1.

## e) Restart the API

```
sudo /usr/local/bin/xxl-restart.sh scrp-api
systemctl is-active scrp-api
curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:8000/health"
```

**Expect:** `active` and `200`.

**STOP if** the API does not come back (`journalctl -u scrp-api -n 50 --no-pager`, paste it) and roll back with g2.

## f) Timings (Server-Timing) and the cache

Run against the API directly (no nginx). Each query is sent three times; there are 2 gunicorn workers with a cache each, so the first call to each worker is a miss and later ones are hits.

```
cd ~/scrp
BC=$(sudo -u postgres psql xxl_super -tAc "SELECT item_code FROM search_items WHERE NOT is_pseudo ORDER BY chains_live DESC, item_code LIMIT 1")
for q in %D7%97%D7%9C%D7%91 %D7%9C%D7%97%D7%9D %D7%A9%D7%95%D7%A7%D7%95%D7%9C%D7%93 "$BC"; do
  for n in 1 2 3; do
    curl -s -o /dev/null -D /tmp/h47.txt -w "search $n  %{http_code}  %{time_total}s  " "http://127.0.0.1:8000/search?q=$q&limit=30"
    grep -i -E '^(server-timing|cache-control)' /tmp/h47.txt | tr -d '\r' | tr '\n' ' '; echo
  done
done
for n in 1 2 3; do
  curl -s -o /tmp/s47.json -D /tmp/h47.txt -w "suggest $n  %{http_code}  %{time_total}s  " "http://127.0.0.1:8000/suggest?q=%D7%97%D7%9C"
  grep -i -E '^(server-timing|cache-control)' /tmp/h47.txt | tr -d '\r' | tr '\n' ' '; echo
done
venv/bin/python3 -c 'import json; d=json.load(open("/tmp/s47.json")); print(len(d["items"]), [i["kind"] for i in d["items"]])'
curl -s -o /dev/null -D - -H "Authorization: Bearer x" "http://127.0.0.1:8000/search?q=%D7%97%D7%9C%D7%91&limit=30" | grep -i -c '^cache-control'
curl -s -o /dev/null -D - "http://127.0.0.1:8000/search?q=%D7%97%D7%9C%D7%91&city=%D7%97%D7%99%D7%A4%D7%94" | grep -i -E '^(server-timing|cache-control)'
```

The queries are חלב, לחם, שוקולד, the most-carried barcode, and `/suggest?q=חל`.

**Expect:**
- Every status `200`.
- A miss looks like `server-timing: candidates;dur=…, prices;dur=…;desc=precomputed, total;dur=…` with `cache-control: public, max-age=300`. Targets: `prices` under 10 ms, `total` under 100 ms (חלב has the most candidates and is the slowest), and `time_total` close to `total`.
- A hit looks like `server-timing: cache;desc=hit, total;dur=0.x`. At least one of the three calls per query should be a hit.
- The barcode: total of a few ms.
- `/suggest`: misses well under 50 ms; then a line like `8 ['term', 'term', 'term', 'brand', ..., 'product', ...]`.
- The Authorization request prints `0` (no Cache-Control for signed-in calls).
- The city-filtered search prints only `server-timing: total;dur=…` (the old path, unchanged, no Cache-Control).

**STOP if:**
- Any status is not `200`.
- `desc=live` on every miss: the API is not using the table. Check `journalctl -u scrp-api -n 50 --no-pager | grep -i search_item_prices` and paste the output. Searches still work; nothing needs undoing.
- `/suggest` returns 0 items for חל.

**After this:** the daily 14:30 `scrp-search-items` timer runs the same `--apply` and maintains `search_item_prices` automatically. There is nothing new to install. After a build the API picks up the new stamp within 60 seconds, and the response caches empty themselves.

## g) Rollback

**g1. Bad prices data, code fine.** Either one works.
- Swap the previous build back. This swaps both tables. Right after the first build, the previous prices table is the empty one from the migration, so the API falls back to the live fetch.
  ```
  cd ~/scrp && venv/bin/python3 -m scripts.build_search_items --swap-back
  ```
- Or empty only the precomputed table, so search_items stays as built. Within 60 s every request uses the live fetch.
  ```
  sudo -u postgres psql xxl_super -c 'TRUNCATE search_item_prices'
  ```

**g2. Code.** Revert the two SU11A-47 code commits and restart. Leave the tables; the old code never reads them.

```
cd ~/scrp && git log --oneline -4
git revert --no-edit <feat(web) SU11A-47 hash> <feat(search) SU11A-47 hash>
sudo /usr/local/bin/xxl-restart.sh scrp-api
```

The reverted build script stops filling `search_item_prices`, and the old API ignores it.

**g3. Remove the tables** (only after g2):

```
sudo -u postgres psql xxl_super -c 'DROP TABLE IF EXISTS search_item_prices, search_item_prices_next'
```

**Web:** `scripts\deploy_frontend.ps1` after step f. The new search box calls `/suggest` and degrades to no suggestions if the API is still old. **Mobile:** ships in build 9; the app also ignores a failing `/suggest`.
