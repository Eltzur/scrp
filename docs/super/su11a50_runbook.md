# Filtered search on the v2 path (SU11A-50) — server runbook

Written in SU11A-50 (22 Oct 2026). For Dude, on the server (`ssh dude@185.229.226.190`, interactive). Run the steps in order. Each step lists what to expect and when to STOP. If you stop, paste the output to the chat and do not improvise a fix.

Nothing here prints `.env` or any secret. The `.env` commands only count or edit the `SEARCH_V2_FILTERED` line.

**What this deploys.** Behind a new flag, `SEARCH_V2_FILTERED` (default `off`):
- **Endpoints:** `/compare` (the web's default view) and `/search` with a city, a chain or `group_by=store`.
- **Candidates:** found and ranked by search v2, as the mobile app's search already is.
- **Filter:** checked against the filter in small batches.
- **Pricing:** only the page is priced, live for a city and from `search_item_prices` for a chain or `/compare` without a city.
- **Candidate step:** v2's candidate step for broad words (חלב, שוקולד) also gets faster for every search. It counts and orders in SQL and ranks only the rows near the page.

With the flag `off` (the state after step e's restart), `/compare` and filtered `/search` answer exactly as before. The candidate-step change is live for every v2 search from the restart; its results are identical by construction, and step d checks that on production.

**No migration and no build change in SU11A-50.** The nationwide modes need the SU11A-47 table `search_item_prices`.
- **Prerequisite:** run the SU11A-47 runbook (`docs/super/su11a47_search_speed_runbook.md`, steps a–f) first.
- **Recommended:** run the SU11A-49 runbook (`docs/security/su11a49_runbook.md`) first too.
- **Without SU11A-47:** the city modes still work, the chain filter prices live, and `/compare` without a city keeps the old path.

**Safe by construction.** The filtered path runs inside a SAVEPOINT. Any error or timeout there logs one warning, which names the exception type but not the query, and the old path answers that request. Rollback is the flag (step g1).

**Quiet times:** as in the SU11A-47 runbook. Avoid 10:00 until the load finishes, and 14:30–15:00 (the daily `scrp-search-items` build). Good windows: a weekday afternoon after about 15:30, or an evening.

---

## a) Pull

```
cd ~/scrp && git status --short | head -5 && git pull origin main && git log --oneline -4
systemctl is-active scrp-cron scrp-search-items
free -m
```

**Expect:**
- `git status` prints nothing (or only files you know about).
- The pull fast-forwards. The log shows `docs: SU11A-50 runbook` and `feat(search): SU11A-50 filtered v2 path, faster candidate step` on top.
- Two `inactive` lines.
- `free -m` "available" of at least 1500.

**STOP if** the pull reports a conflict, either unit is `active` (wait, then rerun), or available memory is under 1200 MB.

The running API is still the old code until step e.

## b) Migration

**None in SU11A-50.** The token table proposed for the candidate step was not needed: the time went into shipping and ranking every match in Python, not into the trigram match. So there is no `su11a50_*.sql` to apply and nothing to check here. Go to c.

## c) Prerequisite check: the SU11A-47 tables are live and from one build (read-only)

There is no new build. This only confirms that the nationwide modes (chain filter, `/compare` without a city) can use `search_item_prices`.

```
sudo -u postgres psql xxl_super -tAc "SELECT to_regclass('public.search_item_prices') IS NOT NULL"
sudo -u postgres psql xxl_super -tAc "SELECT (SELECT max(built_at) FROM search_items), (SELECT max(built_at) FROM search_items) = (SELECT max(built_at) FROM search_item_prices), (SELECT count(*) FROM search_item_prices), (SELECT count(*) FROM search_items)"
```

**Expect:**
- First line: `t`.
- Second line: `<today's or yesterday's build time>|t|<rows>|<items>`, with `rows` roughly 3–5× `items`.

**If the first line is `f`, or the second has `f` in the second field:** SU11A-47 is not deployed, or its last price fill did not swap in. You can still continue. In step d, `search_item_prices usable` will say `False` and the nationwide rows will use the live fetch (chain) or show an error for `/compare` without a city, which in the API means "the old path answers". Better: finish the SU11A-47 runbook first.

## d) Compare old and new on production (read-only, go / no-go)

```
cd ~/scrp && (ulimit -v 1500000; time venv/bin/python3 -m scripts.compare_search_v2 --filtered --out /tmp/search_filtered_compare.json) 2>&1 | tee /tmp/search_filtered_compare.txt; echo "exit $?"
```

Every connection is READ ONLY with a 60 s statement timeout. In-process, independent of the flag:
1. **Candidate stream:** the 12 standard queries' top 10 from the new stream vs the full SU11A-36 ranking, with both timings.
2. **/compare in a city:** חלב, לחם, במבה, שוקולד, קפה, ים × רמת גן, בני ברק, ירושלים, אילת. The old path runs once per pair (it is the heavy one: about 1–2 s each, longer for ים), the new path 3 times.
3. **Nationwide:** the chain filter for the 3 largest chains × חלב, שוקולד, and `/compare` without a city × חלב, במבה.

Expect about 1–3 minutes in all.

**Expect:**
- `search_item_prices usable: True`.
- **Section 1:** `same top 10` is `True` on every row. `new ms` is well under `old ms` for חלב, לחם, שוקולד, קפה (target: new under about 20–30 ms).
- **Sections 2 and 3:** one line per case. `new ms min/med` is the new path; the target is under 400 ms per case, mostly much less. `PRICE MISMATCHES` is `0` on every line.
- **Overlap:** a low `overlap first 20` is expected, because the new order is search v2's relevance and the old order is "cheapest first".
- **Not in reference:** a non-zero count is fine in section 2. These are items the old path never priced, because it stops at 1,000 candidates.
- **Eilat:** `eilat ok` is `True` wherever it is printed.
- **Last lines:** `SUMMARY: stream differences 0 | price mismatches 0 | new p50 … ms | new errors 0 | Eilat failures 0`, then `GO` and `exit 0`.

**STOP (do not run e–f; the flag stays off) if** the output says `NO-GO` (exit 1), any price mismatch or stream difference is listed, the new path shows an error or `statement_timeout`, or `MemoryError` / `Killed`. Paste the whole of `/tmp/search_filtered_compare.txt`; it holds barcodes, chain ids and timings only.

An old-path `statement_timeout` (for example ים in a big city) is the reason for this session, not a stop.

## e) Restart, then SEARCH_V2_FILTERED=test (the new path only with engine=v2)

First restart with the flag absent. This puts the new code live with the filtered path off; only v2's faster candidate step changes.

```
cd ~/scrp && grep -c '^SEARCH_V2_FILTERED=' .env
sudo /usr/local/bin/xxl-restart.sh scrp-api
systemctl is-active scrp-api
curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:8000/health"
```

**Expect:** `0` (the flag is not set yet), `active`, `200`.

Then turn on test mode:

```
printf '\nSEARCH_V2_FILTERED=test\n' >> ~/scrp/.env && grep -c '^SEARCH_V2_FILTERED=test$' ~/scrp/.env
sudo /usr/local/bin/xxl-restart.sh scrp-api
systemctl is-active scrp-api
```

**Expect:** `1`, then `active`.

Now compare the same requests with `engine=v2` (new path) and `engine=v1` (old path), against the API directly (127.0.0.1:8000, no nginx). Hebrew is URL-encoded (CLAUDE.md rule 11): חלב = `%D7%97%D7%9C%D7%91`, ים = `%D7%99%D7%9D`, במבה = `%D7%91%D7%9E%D7%91%D7%94`, רמת גן = `%D7%A8%D7%9E%D7%AA%20%D7%92%D7%9F`, בני ברק = `%D7%91%D7%A0%D7%99%20%D7%91%D7%A8%D7%A7`, אילת = `%D7%90%D7%99%D7%9C%D7%AA`.

```
cd ~/scrp
A=http://127.0.0.1:8000
CH=$(sudo -u postgres psql xxl_super -tAc "SELECT chain_id FROM stores GROUP BY 1 ORDER BY count(*) DESC LIMIT 1")
for u in "compare?q=%D7%97%D7%9C%D7%91&city=%D7%A8%D7%9E%D7%AA%20%D7%92%D7%9F&limit=20" \
         "compare?q=%D7%91%D7%9E%D7%91%D7%94&city=%D7%91%D7%A0%D7%99%20%D7%91%D7%A8%D7%A7&limit=20" \
         "compare?q=%D7%99%D7%9D&city=%D7%A8%D7%9E%D7%AA%20%D7%92%D7%9F&limit=20" \
         "compare?q=%D7%97%D7%9C%D7%91&city=%D7%90%D7%99%D7%9C%D7%AA&limit=20" \
         "search?q=%D7%97%D7%9C%D7%91&city=%D7%A8%D7%9E%D7%AA%20%D7%92%D7%9F&limit=20" \
         "search?q=%D7%97%D7%9C%D7%91&chain=$CH&limit=20" \
         "search?q=%D7%97%D7%9C%D7%91&city=%D7%A8%D7%9E%D7%AA%20%D7%92%D7%9F&group_by=store&limit=20"; do
  for e in v2 v1; do
    curl -s -o /tmp/r50.json -D /tmp/h50.txt -w "$e %{http_code} %{time_total}s  " "$A/$u&engine=$e"
    grep -i '^server-timing' /tmp/h50.txt | tr -d '\r' | tr '\n' ' '
    venv/bin/python3 -c 'import json; d=json.load(open("/tmp/r50.json")); print("| q", d["query"], "| items", len(d["items"]), "| total", d["total_matches"], "| comparable", d["comparable_count"], "| more", d["has_more"], "| engine", d.get("engine", "-"))'
  done
done
journalctl -u scrp-api --since "10 min ago" --no-pager | grep -c "filtered search"
```

The cases are:
- `/compare`: חלב in רמת גן, במבה in בני ברק, ים in רמת גן, חלב in אילת;
- `/search`: חלב with city רמת גן, חלב with the largest chain, חלב by store in רמת גן.

**Expect, per case, a `v2` line and a `v1` line:**
- **Status:** every status is `200`, and `q` echoes the Hebrew word (not `???`).
- **`v2` lines:** `server-timing: candidates;dur=…, filter;dur=…, prices;dur=…;desc=live|precomputed, total;dur=…`. The `total` is under 400 ms, mostly well under; the chain case shows `desc=precomputed`.
- **`/search` with `v2`:** `engine v2`. `/compare` lines show `engine -` with both engines: /compare keeps its exact fields.
- **`v1` lines:** `server-timing: total;dur=…` only (the old path). They are much slower; ים in a city may answer `503` here (the SU11A-49 timeout), and that is the old path.
- **Items:** the `v2` line has items for every case (some for ים, which matches words containing ים). `more True` when there are more than 20.
- **Counts:** the `total` numbers can differ between `v2` and `v1`. See "Counts" below.
- **Journal:** the last command prints `0`, meaning no fallback warnings.

**STOP if** a `v2` line is not `200`, has no `filter;dur` (the new path fell back: the journal count is then above 0; run `journalctl -u scrp-api --since "10 min ago" --no-pager | grep "filtered search"` and paste it), or its `total` is over 1000 ms. Rollback: g1.

**Counts (what the web shows as "נמצאו N מוצרים · M ניתנים להשוואה").** The old path counted the items it priced. Since SU11A-49 that was the name-match count when there were more than 1,000 matches.

The new path gives exact counts for the filter when it walked every candidate, which is typical for specific queries. For broad words it stops early and reports the nationwide name-match counts, the same numbers an unfiltered search shows.

## f) SEARCH_V2_FILTERED=on

```
sed -i 's/^SEARCH_V2_FILTERED=.*/SEARCH_V2_FILTERED=on/' ~/scrp/.env && grep -c '^SEARCH_V2_FILTERED=on$' ~/scrp/.env
sudo /usr/local/bin/xxl-restart.sh scrp-api
systemctl is-active scrp-api
cd ~/scrp
A=http://127.0.0.1:8000
for u in "compare?q=%D7%97%D7%9C%D7%91&city=%D7%A8%D7%9E%D7%AA%20%D7%92%D7%9F&limit=20" \
         "compare?q=%D7%97%D7%9C%D7%91&city=%D7%91%D7%A0%D7%99%20%D7%91%D7%A8%D7%A7&limit=20" \
         "compare?q=%D7%97%D7%9C%D7%91&limit=20" \
         "compare?q=%D7%99%D7%9D&limit=20" \
         "compare?q=%D7%97%D7%9C%D7%91&city=%D7%A8%D7%9E%D7%AA%20%D7%92%D7%9F&limit=20&offset=20"; do
  curl -s -o /tmp/r50.json -D /tmp/h50.txt -w "%{http_code} %{time_total}s  " "$A/$u"
  grep -i '^server-timing' /tmp/h50.txt | tr -d '\r' | tr '\n' ' '
  venv/bin/python3 -c 'import json; d=json.load(open("/tmp/r50.json")); print("| items", len(d["items"]), "| total", d["total_matches"], "| more", d["has_more"])'
done
curl -s -o /dev/null -D /tmp/h50.txt -w "v1 %{http_code} %{time_total}s  " "$A/compare?q=%D7%97%D7%9C%D7%91&city=%D7%A8%D7%9E%D7%AA%20%D7%92%D7%9F&limit=20&engine=v1"; grep -i '^server-timing' /tmp/h50.txt | tr -d '\r'
```

The requests are what the web sends:
- `/compare?q=חלב` with city רמת גן, with city בני ברק, and with no city;
- `/compare?q=ים` with no city (was a 503);
- the second page of the first;
- then `engine=v1`, which must still give the old path.

**Expect:**
- `1`, `active`.
- Five `200` lines with `filter;dur=` in Server-Timing and `total` under 400 ms. The two without a city show `desc=precomputed` and are fastest. ים answers `200` with items instead of the old `503`.
- The second page has items too (when the first said `more True`).
- The `v1` line shows `server-timing: total;dur=…` only.

Then open https://super.xxl.co.il in a browser. The default view (compare, auto-detected city) should show results for חלב within about a second, and "טען עוד" should add more.

**STOP if** any status is not `200`, or any `total` is over 1000 ms: roll back with g1 and paste the output.

**Day after:** `journalctl -u scrp-api --since yesterday --no-pager | grep -c "filtered search"` should be `0` or close to it. A few `not available here` info lines are normal while `search_item_prices` is not usable, for example after a failed price fill. `failed` lines name only an exception type; paste them if there are more than a handful.

## g) Rollback

**g1. Flag off** (instant; the old path answers everything filtered, exactly as before SU11A-50):

```
sed -i 's/^SEARCH_V2_FILTERED=.*/SEARCH_V2_FILTERED=off/' ~/scrp/.env && sudo /usr/local/bin/xxl-restart.sh scrp-api
```

To remove the line altogether (same effect): `sed -i '/^SEARCH_V2_FILTERED=/d' ~/scrp/.env && sudo /usr/local/bin/xxl-restart.sh scrp-api`.

**g2. The candidate-step change** (v2's ranking stream) is not behind the flag; its results are identical by construction, and step d checks that. If it misbehaves:
- **Unfiltered searches:** `SEARCH_V2=off` + restart sends them to the old path (the SU11A-36 rollback).
- **Code:** ask for a revert commit (made on Windows, CLAUDE.md rule 14), then `git pull` + restart here.

**g3. Build / tables:** nothing to undo. SU11A-50 adds no table and no migration, and does not change the build, so `--swap-back` and a migration rollback do not apply. The SU11A-47 tables keep their own rollback (SU11A-47 runbook, g).
