# Search v2 (SU11A-36) — server runbook

Written in SU11A-45 (18 Oct 2026) after a read-only code verification. For Dude, on the server (`ssh dude@185.229.226.190`, interactive). Run the steps in order. Each step lists what to expect and when to STOP. If you stop, paste the output to the chat and do not improvise a fix.

Nothing here prints `.env`. The only `.env` reads are `grep -c`, which prints a count.

**Quiet times.** Avoid:
- 04:00–04:30 backup
- 05:30 account sweep
- 10:00 until the daily load finishes (about 1.5–3 h; `systemctl is-active scrp-cron` prints `inactive` once it is done)
- Sunday 14:00–14:30 GS1 fetch, Sunday 15:00 geocode, Sunday 17:00 image backup
- 14:30 every day, once step g is installed

Good windows are a weekday afternoon after the load has finished, or an evening.

---

## a) Preflight (read-only)

```
cd ~/scrp && git pull origin main && git log --oneline -1
df -h /
free -m
sudo -u postgres psql xxl_super -tAc "SELECT extversion FROM pg_extension WHERE extname = 'pg_trgm'"
sudo -u postgres psql xxl_super -tAc "SELECT coalesce(to_regclass('public.search_items')::text, 'absent')"
sudo -u postgres psql xxl_super -tAc "SELECT coalesce(to_regclass('public.user_blocks')::text, 'absent')"
grep -c '^SEARCH_V2=' .env
systemctl show -p Type scrp-cron.service
systemctl is-active scrp-cron scrp-gs1-fetch scrp-geocode
```

**Expect:**
- The SU11A-45 commit (or later) at the top of the log.
- `/` Avail of at least 5G.
- `free -m` "available" of at least 1500.
- `1.6` for pg_trgm.
- `absent` for search_items.
- `user_blocks`: either `user_blocks` or `absent`. This one is only recorded here; it matters in step f.
- `0` from the grep.
- `Type=oneshot`.
- Three `inactive` lines.

**STOP if:**
- Avail is under 3G, or available memory is under 1200 MB.
- pg_trgm prints nothing.
- The grep count is not 0 (SEARCH_V2 is already set; say so).
- Any of the three units is `active` (wait, then rerun).

If search_items is **not** absent, the migration was already applied. Skip b and say so.

If Type is not `oneshot`, the timer's `After=scrp-cron.service` does not make the build wait for the load. Report it before step g.

## b) Apply the migration (additive, idempotent)

```
cat ~/scrp/db/migrations/su11a36_search_items.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
sudo -u postgres psql xxl_super -c '\d search_items' -c '\d search_lexicon'
sudo -u postgres psql xxl_super -tAc "SELECT tablename, tableowner FROM pg_tables WHERE tablename LIKE 'search\_%' ORDER BY 1"
```

**Expect** this sequence, in order:
- `BEGIN`
- `CREATE EXTENSION` (a NOTICE "already exists, skipping" is fine)
- 4× `CREATE TABLE`, 8× `CREATE INDEX`, 4× `ALTER TABLE`
- `COMMIT`

Then:
- `\d search_items` lists `search_items_pkey`, `idx_search_items_name_trgm` and `idx_search_items_mfr_trgm` (both `gin`), and `idx_search_items_rank`.
- `\d search_lexicon` lists `search_lexicon_pkey`, `idx_search_lexicon_term_trgm` (gin) and a `kind` CHECK.
- The owner query prints 4 rows, `search_items`, `search_items_next`, `search_lexicon` and `search_lexicon_next`, each with owner `scrp_app`.

**STOP if** there is any `ERROR`, or any owner is not `scrp_app`. The build's swap renames the tables and needs ownership.

## c) Build report (read-only)

```
cd ~/scrp && (ulimit -v 1500000; time venv/bin/python3 -m scripts.build_search_items --report --out /tmp/search_items_report.json) 2>&1 | tee /tmp/search_items_report.txt
```

The report is READ ONLY: every connection runs with `default_transaction_read_only`, plus `SET TRANSACTION READ ONLY`. Statements time out after 10 min.

The per-item aggregation over about 7.7M price rows runs in Postgres, and only about one row per live item (around 165K at most) comes back. Python peaks at about 180 MiB (measured on 165K synthetic rows), plus the interpreter and the driver buffer. The 1.5 GB virtual-memory cap leaves headroom.

Expect a few minutes of mostly aggregate time. Postgres may spill a few hundred MB of temp files for the GROUP BY.

**Expect:**
- `live stores: …` near 865.
- `live items: …` in the 100K–165K range.
- Then the report.
- `db role: scrp_app`.
- `pg_trgm: {'trigrams_in_חלב': 4 or 5, …}`.
- `tables now`: four tables with `rows 0`, owner `scrp_app`.
- `real` time at the end.

**Paste back** the whole of `/tmp/search_items_report.txt`. It contains product names only. The parts that matter most:
- live items
- pseudo totals and the samples
- the Eilat line
- the expected rows
- the aliases that match nothing
- pg_trgm
- the timings
- the `real` time

**STOP (do not run d) if:**
- `MemoryError` or `Killed`.
- `canceling statement due to statement timeout`.
- db role is not `scrp_app`.
- `trigrams_in_חלב` is 0 or None.
- live items are under 50,000.
- pseudo total is over 5% of live items.
- Eilat `live` is 0.

## d) Build and swap in

```
cd ~/scrp && (ulimit -v 1500000; time venv/bin/python3 -m scripts.build_search_items --apply --out /tmp/search_items_apply.json) 2>&1 | tee /tmp/search_items_apply.txt
sudo -u postgres psql xxl_super -tAc "SELECT count(*), count(*) FILTER (WHERE is_pseudo), min(built_at), max(built_at) FROM search_items" -tAc "SELECT count(*), count(*) FILTER (WHERE kind = 'alias') FROM search_lexicon" -tAc "SELECT count(*) FROM search_items_next"
```

The build fills only `search_items_next` and `search_lexicon_next` (TRUNCATE, INSERT, ANALYZE, one transaction). It then renames the live and staging tables in a second, short transaction. That transaction waits at most 5 s for its locks and makes 3 attempts.

/search is unaffected while SEARCH_V2 is off. Once SEARCH_V2 is on, a v2 request can wait at most those 5 s, once per attempt.

**Expect:**
- Duration is about the report time plus 1–3 min.
- The JSON shows:
  - `search_items` equal to the report's expected rows;
  - `previous_live_rows 0` (first build);
  - `swap_ms` under about 100.
- The psql check shows:
  - the same count;
  - `min(built_at)` = `max(built_at)`, a few minutes ago;
  - the lexicon count with about 118 aliases;
  - `0` rows in `search_items_next` (the previous, empty build).

**STOP if** you see `refusing to swap`, `staged … not swapping`, or `swap failed 3 times`. The live tables are unchanged in each case. Paste the output and do not retry.

**Undoing a bad build:** `cd ~/scrp && venv/bin/python3 -m scripts.build_search_items --swap-back` makes the previous build live again.
- Run it **once**; a second run swaps forward again.
- After the very first build the previous build is empty, so swap-back leaves an empty live table. That is safe: v2 then sees "search_items is empty" and every request uses the old path.

## e) Compare v2 with the old search (read-only)

```
cd ~/scrp && (ulimit -v 2000000; time venv/bin/python3 -m scripts.compare_search_v2 --out /tmp/search_v2_compare.json) 2>&1 | tee /tmp/search_v2_compare.txt
```

The comparison runs in-process with no HTTP, so it does not page the live API. Every connection is READ ONLY, with a 60 s statement timeout.

It runs about 33 queries. v2 runs 3 times per query. The old path also runs 3 times, but only once above 2,000 barcodes. The old path is the slow one (חלב about 15 s, חל about 22 s), so expect **10–25 min** of production load.

The old path holds every matching price row in Python, which is why the cap is 2 GB. A `MemoryError` or timeout on one query is recorded in that query's errors column and is not repeated.

**Paste back** the whole of `/tmp/search_v2_compare.txt`.

**GO to step f only if all of these hold:**
1. **Errors:** the errors column is empty for every v2 run.
2. **Latency:**
   - The v2 median is at most 1,500 ms for every text query and at most 1,000 ms for the barcode queries.
   - For every query with old codes > 1,000, the v2 median is at most 25% of the old median.
3. **No lost queries:** no query has old total > 0 and v2 total = 0.
4. **Counts:** v2 total_matches is at least 90% of old for every text query. v2 may be higher, because of normalisation and aliases. It may be lower only by pseudo items.
5. **Top 10 on the 12 standard queries** (חלב, לחם, שמן, קפה, שוקולד, תנובה, "חלב תנובה 3%", "שמן זית", "קוקה קולה", coca cola, "חלב תנובא", שוקלד):
   - top10 overlap is at least 3 on at least 8 of the 12;
   - in the printed v2 top-10 lists, no item is obviously unrelated to its query.

   Low overlap alone is not a NO-GO, because v2 ranks without price on purpose. In that case the v2 list for that query has to read as more relevant.
6. **Coupons:** no v2 top-10 name starts with "קופון" or "הנ.קופון". Every line under "coupon pseudo-items that left the old top 10" is a coupon or ₪0.01 item.
7. **Eilat:** in the last line, the v2 count of Eilat-cheapest results is 0. It can be non-zero only for items sold only in Eilat.
8. **Typos:** "חלב תנובא" and "שוקלד" show a `corrected_from` value, or results.
9. **UPC-A:** the UPC-A barcode query returns exactly 1 item.

## f) SEARCH_V2=test (v2 only when a request asks for it)

**STOP before the restart in this step if** preflight showed `user_blocks` as `absent`. `git pull` brought the SU11A-44 API code, which needs `db/migrations/su11a44_ugc_blocks_terms_moderation.sql` applied first. Otherwise sign-in and ratings break after the restart. Apply that migration first (SU11A-44 deploy order), or stop here.

```
cd ~/scrp && grep -c '^SEARCH_V2=' .env
```

That must print `0`. Then:

```
printf '\nSEARCH_V2=test\n' >> ~/scrp/.env && grep -c '^SEARCH_V2=test$' ~/scrp/.env
sudo /usr/local/bin/xxl-restart.sh scrp-api
```

The grep should print `1`. The API reads `.env` only through systemd's EnvironmentFile, so the restart is required.

Next, run server-side checks. Hebrew is URL-encoded (CLAUDE.md rule 11). The four queries are חלב, במבה, the typo שוקלד, and the popular barcode taken from step e. Each one runs once with `engine=v2` and once with `engine=v1`, followed by one request with no engine:

```
cd ~/scrp
BC=$(venv/bin/python3 -c 'import json; print(json.load(open("/tmp/search_v2_compare.json"))["barcodes"]["popular"]["item_code"])')
for q in %D7%97%D7%9C%D7%91 %D7%91%D7%9E%D7%91%D7%94 %D7%A9%D7%95%D7%A7%D7%9C%D7%93 "$BC"; do
  for e in v2 v1; do
    t=$(curl -s -o /tmp/sv2.json -w '%{http_code} %{time_total}s' "http://127.0.0.1:8000/search?q=$q&limit=30&engine=$e")
    echo "== engine=$e  $t"
    venv/bin/python3 -c 'import json; d = json.load(open("/tmp/sv2.json")); print(" ", d.get("query"), "| engine", d.get("engine", "(none: old path)"), "| total", d.get("total_matches"), "| items", len(d.get("items", [])), "| has_more", d.get("has_more"), "| corrected_from", d.get("corrected_from")); [print("   ", i["product"]["item_code"], i["product"]["canonical_name"], "| chains", i["chains_count"], "| cheapest", i["cheapest_price"]) for i in d.get("items", [])[:3]]'
  done
done
curl -s "http://127.0.0.1:8000/search?q=%D7%97%D7%9C%D7%91&limit=1" | venv/bin/python3 -c 'import json, sys; print("no engine param -> engine key present:", "engine" in json.load(sys.stdin))'
journalctl -u scrp-api --since "15 min ago" --no-pager | grep -c "search v2"
```

**Expect:**
- Every line shows `200`.
- `query` echoes the Hebrew word, not `???`.
- `engine=v2` answers show `engine v2` and take well under 2 s.
- `engine=v1` answers show `(none: old path)` with the old timing (חלב about 15 s).
- The typo shows `corrected_from שוקלד` under v2.
- The barcode shows `total 1` under v2.
- The no-engine request prints `False`: in test mode only `engine=v2` uses v2.
- The journal count is `0`, meaning no fallback warnings.

**Compare** v2 with v1:
- total counts are close;
- the v2 top 3 are relevant;
- the v2 cheapest is never an Eilat-only price when other stores exist.

**STOP if** you see any 5xx, a `query` shown as `???`, an `engine=v2` answer with no `engine` key, or a non-zero journal count. Paste `journalctl -u scrp-api --since "15 min ago" --no-pager | grep -A3 "search v2"` (it may contain the search text, never secrets), then set SEARCH_V2 back to off as in step h.

## g) Install the daily rebuild timer

```
sudo cp ~/scrp/deploy/systemd/scrp-search-items.service ~/scrp/deploy/systemd/scrp-search-items.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now scrp-search-items.timer
systemctl list-timers scrp-search-items.timer --no-pager
```

**Expect:** the `NEXT` column shows the coming 14:30 Israel time, with `ACTIVATES scrp-search-items.service`.

The timer schedule is `OnCalendar=*-*-* 14:30:00 Asia/Jerusalem`, inline as SU10S-8 requires, with `After=scrp-cron.service`. 14:30 does not overlap 04:00, 05:30, 10:00 (load), Sunday 14:00 (GS1, about 15 min), Sunday 15:00 or Sunday 17:00. Like the other units, it has no MemoryMax or TimeoutStartSec. The build bounds itself with a 10 min statement timeout.

**Next day:**

```
systemctl status scrp-search-items.service --no-pager | head -5
journalctl -u scrp-search-items --since today --no-pager | tail -25
```

**Expect:** `status=0/SUCCESS`, and the apply JSON with a fresh `built_at`.

**STOP if** the run failed. The previous build stays live. v2 falls back to the old search on its own once `built_at` is more than 48 h old.

## h) Later: SEARCH_V2=on, rollback, abandon

**Switching to `on`** is a separate decision. Do it only after:
- the timer has succeeded on 2 consecutive days;
- the web load-more duplicate (SU11A-45 finding 9b) is dealt with or accepted.

```
sed -i 's/^SEARCH_V2=.*/SEARCH_V2=on/' ~/scrp/.env && grep -c '^SEARCH_V2=on$' ~/scrp/.env
sudo /usr/local/bin/xxl-restart.sh scrp-api
curl -s "http://127.0.0.1:8000/search?q=%D7%97%D7%9C%D7%91&limit=1" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("engine"))'
```

**Expect** `1`, then `v2`.

With `on`, v2 serves requests that have no city and no chain filter, with group_by=chain. That covers the mobile app and the web without filters. City, chain or store requests and /compare always use the old path. `engine=v1` forces the old path.

**Rollback** (instant): set the flag back to off and restart.

```
sed -i 's/^SEARCH_V2=.*/SEARCH_V2=off/' ~/scrp/.env && sudo /usr/local/bin/xxl-restart.sh scrp-api
```

If a bad build is live: `cd ~/scrp && venv/bin/python3 -m scripts.build_search_items --swap-back`, once.

**Abandon v2** (in this order: flag off, then the timer, then the tables):

```
sed -i 's/^SEARCH_V2=.*/SEARCH_V2=off/' ~/scrp/.env && sudo /usr/local/bin/xxl-restart.sh scrp-api
sudo systemctl disable --now scrp-search-items.timer
sudo rm /etc/systemd/system/scrp-search-items.service /etc/systemd/system/scrp-search-items.timer && sudo systemctl daemon-reload
sudo -u postgres psql xxl_super -c "DROP TABLE search_items, search_items_next, search_lexicon, search_lexicon_next"
sed -i '/^SEARCH_V2=/d' ~/scrp/.env && sudo /usr/local/bin/xxl-restart.sh scrp-api
```

With the flag off, nothing reads these tables. Dropping them with the flag still on would only produce fallback warnings, but turn the flag off first anyway.
