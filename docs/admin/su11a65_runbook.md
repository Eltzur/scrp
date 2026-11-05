# SU11A-65 — gift coupons, promo search speed, boost guard, web account-deletion timeout (L1): runbook

Written 5 Nov 2026 for Dude.

**What changes for users**
- **Gift coupons** (for example Rami Levy "קופון שמנת חמוצה … 1 יח' מתנה") now show:
  - the badge "מתנה בקופון";
  - the free quantity ("1 יח' מתנה");
  - the condition when the promotion has one ("מעל ₪X", "בקניית N יח' לפחות");
  - the shelf price as plain text ("מחיר מדף ₪X").

  They never show a percentage or a struck-through price. Before, they showed a "מבצע" badge on the promos page and "100% הנחה" in admin.
- **"הנחה גדולה":** gift coupons come after every real per-item discount. The other sorts are unchanged.
- **A new type chip "מתנה בקופון"** shows only gift coupons. The other type chips no longer include them.
- **Promo search is faster:** the target is under 1.5 s for a search in a city and in all cities. Before, it took 3.3–4.0 s on production. The results are the same rows in the same order.
- **Account deletion on the website:** if the deletion went through on the server but the answer was lost (timeout or connection), the page no longer leaves the user stuck. It retries with the same sign-in. A later attempt that fails with "wrong password" first asks the server, and shows "החשבון נמחק" only if the server confirms it.

**Prices:** nothing that prices changes: search, compare, basket, `/product`, `/promos/bulk`, promo badges, the search build and `/promos/today`.

**How to run it**
- Run the steps in order. Each step names where it runs:
  - **[Server — bash]:** `ssh dude@185.229.226.190`, interactive, in `~/scrp`. Type Hebrew only there (CLAUDE.md rule 11); the commands below URL-encode it.
  - **[PC — PowerShell]:** PowerShell in `C:\scrp`, on the **home PC** (the one with `web/.env.production`).
  - **[Browser].**
- If a step says STOP, paste the output to the chat and do not improvise a fix.
- Nothing here prints `.env`, a token or an email address.

**What it deploys**

| Part | What changes |
|---|---|
| DB | Two indexes: `idx_promos_description_trgm` (promos.promo_description) and `idx_items_name_trgm` (items.item_name), GIN `gin_trgm_ops`. `CREATE INDEX CONCURRENTLY`: the load and the API keep working during the build. pg_trgm is already installed (search v2). |
| API | `/promos/list`, `/promos/grouped`, `/promos/promoted`: `gift_coupon` on every row, the "discount" sort, `promo_type=gift_coupon`, and the indexable search condition. `/admin/promos/search`: `sample.gift_coupon`. |
| Web | The promos page (gift-coupon card, chip), the admin promotion card, and `/account/delete`. |
| nginx | Nothing to install. Only the header comment of `deploy/nginx/xxl-ratelimit-http.conf` changed in the repo (zones unchanged). |

---

## 0. Precondition: SU11A-64 is deployed

Deploy order: SU11A-64 first (`docs/security/su11a64_runbook.md`), then this.

**[Server — bash]**

```
cd ~/scrp && git merge-base --is-ancestor 34b4916 HEAD && echo "SU11A-64 pulled"; curl -s -o /dev/null -w 'today-unknown-city %{http_code}\n' 'http://127.0.0.1:8000/promos/today?city=nowhere'
```

**Expect:** `SU11A-64 pulled` and `today-unknown-city 422`.
**STOP if** either line is missing or the code is not `422`: run the SU11A-64 runbook first.

## 1. Quiet-time check

**[Server — bash]**

```
date '+%H:%M'; systemctl show -p ActiveState --value scrp-cron
```

**Expect:**
- a time outside 04:00–04:30, 14:25–15:00, and 10:00 until the cron finishes;
- then `inactive`.

**STOP if** the second line is `activating` (the daily load is running). Wait until it reads `inactive`. `CREATE INDEX CONCURRENTLY` waits for running writes, so during the load the build would take much longer.

## 2. Timings before (for the comparison in step 7)

**[Server — bash]**

```
API=https://api-super.xxl.co.il
t() { for i in 1 2 3; do curl -s -G -o /tmp/su65.json -w "$1 %{http_code} %{time_total}s " "${@:2}"; python3 -c "import json; print(len(json.load(open('/tmp/su65.json'))), 'rows')"; done; }
t list-city-q $API/promos/list --data-urlencode 'city=תל אביב-יפו' --data-urlencode 'q=שמנת'
t list-all-q  $API/promos/list --data-urlencode 'q=שמנת'
t list-city-q $API/promos/list --data-urlencode 'city=תל אביב-יפו' --data-urlencode 'q=חומוס'
t list-all-q  $API/promos/list --data-urlencode 'q=חומוס'
rm -f /tmp/su65.json
```

**Expect:** every line `200` and `30 rows`. On 5 Nov the times were about 3.3–3.4 s (city) and 3.7–4.0 s (all cities). Note them down.

## 3. Pull

**[Server — bash]**

```
cd ~/scrp && git pull origin main && git log --oneline -3
```

**Expect:** one of the top lines is `feat: SU11A-65 gift coupons, promo search index, boost guard, web deletion timeout (L1)`.
**STOP if** the pull fails.

## 4. Disk check and size estimate

The index holds trigrams of every promo description. On a production-sized test set (842,000 promos, 15-character descriptions) it was 20 MB, about 20% of the promos table. This step sizes it from production's real table, with a generous allowance.

**[Server — bash]**

```
df -h /; sudo -u postgres psql xxl_super -tAc "SELECT pg_size_pretty(pg_relation_size('promos')) AS promos_heap, round(avg(length(promo_description))) AS avg_desc, pg_size_pretty(pg_relation_size('promos') / 2 + 50 * 1024 * 1024) AS index_estimate FROM promos"
```

**Expect:**
- the `df` line for `/`, with the free space in the `Avail` column;
- one line: `promos_heap|avg_desc|index_estimate` (the estimate is half the table plus 50 MB, deliberately high).

**STOP if** `Avail` is less than **3 times** `index_estimate`, or less than 1 GB. Paste both lines.

## 5. Apply the migration (as postgres)

Do **not** add `-1` or `--single-transaction`: `CREATE INDEX CONCURRENTLY` cannot run inside a transaction. psql runs each statement on its own.

**[Server — bash]**

```
time (cat ~/scrp/db/migrations/su11a65_promo_search.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1)
```

**Expect** (in this order):
- `NOTICE: extension "pg_trgm" already exists, skipping`;
- `CREATE EXTENSION`;
- `CREATE INDEX` twice;
- `ANALYZE` twice;
- the `real` time.

On the test set the whole file took 8 s. On production expect about 1–5 minutes: the server is slower, and CONCURRENTLY reads the table twice.

**STOP if:**
- you see an `ERROR`;
- it runs longer than 15 minutes.

Do not press Ctrl-C on a slow build. Paste `sudo -u postgres psql xxl_super -tAc "SELECT pid, state, wait_event_type, left(query, 60) FROM pg_stat_activity WHERE query ILIKE '%CONCURRENTLY%'"`.

**Verify** that the indexes exist and are valid:

**[Server — bash]**

```
sudo -u postgres psql xxl_super -tAc "SELECT c.relname, i.indisvalid, pg_size_pretty(pg_relation_size(c.oid)) FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid WHERE c.relname IN ('idx_promos_description_trgm', 'idx_items_name_trgm') ORDER BY 1"; df -h /
```

**Expect:** two lines, both `t`:
- `idx_items_name_trgm|t|<size>`;
- `idx_promos_description_trgm|t|<size>`.

**STOP if** a line is missing or shows `f`. A failed CONCURRENTLY build leaves an invalid index that a re-run would skip. Then run the rollback (step 9a), paste the output, and do not re-apply without the chat.

## 6. Restart the API and wait for health

**[Server — bash]**

```
sudo /usr/local/bin/xxl-restart.sh scrp-api && for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] && break; sleep 1; done; curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:8000/health
```

**Expect:** `health 200`.
**STOP if** it is not `200`. Then paste `sudo journalctl -u scrp-api -n 40 --no-pager`.

## 7. Timings after (three times each)

**[Server — bash]** Run the same block as in step 2, then this:

```
API=https://api-super.xxl.co.il
curl -s -G -o /tmp/su65.json -w 'chip %{http_code} ' $API/promos/list --data-urlencode 'city=חיפה' --data-urlencode 'q=שמנת' --data-urlencode 'promo_type=gift_coupon'; python3 -c "import json; r=json.load(open('/tmp/su65.json')); print(len(r), 'rows, all gift_coupon:', all(x['gift_coupon'] for x in r))"; rm -f /tmp/su65.json
```

**Expect:**
- **step 2 block:** every line `200` with `30 rows`; `list-city-q` and `list-all-q` under 1.5 s. On the test set: 0.17–0.30 s (city) and 0.76–1.08 s (all cities), before 1.6–2.5 s and 2.3–4.3 s.
- **chip line:** `chip 200 N rows, all gift_coupon: True`. `0 rows, all gift_coupon: True` is also fine: Haifa may have no gift coupon on cream that day.

**STOP if:**
- any line is `503`;
- a time is slower than the step 2 time for the same line.

Then also paste:

```
sudo journalctl -u scrp-api --since "10 min ago" --no-pager | grep -E "query timeout|Traceback" | tail -5
```

## 8. Read-only report

It prints:
- the index state;
- the timings, and whether the plan reads the new index;
- why each of the top 15 חומוס rows in Tel Aviv matched;
- the gift-coupon counts per chain with 10 examples.

The last part reads every active promo once (about 1 minute). The session is READ ONLY, with a 120 s statement limit.

**[Server — bash]**

```
cd ~/scrp && ( ulimit -v 2000000; set -a; source .env; set +a; venv/bin/python3 -m scripts.su11a65_promo_report ) 2>&1 | tee ~/su11a65_report.txt | tail -60
```

**Expect:**
- `== indexes`: both indexes `valid=True`.
- `plan reads idx_promos_description_trgm: yes`.
- `== why: חומוס`: every line names `description`, `name` or `barcode`. No line ends with `<-- NO TEXT MATCH`.
  - Lines that match only on `description` show why lentils or peas can appear: their promotion's description names חומוס. This is the open decision in the handoff, not a failure.
- `== gift coupons`:
  - `gift_coupon_rows`, `gift_coupon_promotions`, `gift_coupon_cards`;
  - `free_unit_without_coupon_rows` (1+1 halves and the like; unchanged);
  - the chains and 10 examples, each reading like "קופון … מתנה".

**STOP if:**
- it fails with `statement timeout` or `MemoryError`;
- an index is `MISSING` or `valid=False`;
- a `why` line ends with `NO TEXT MATCH`;
- an example is not a coupon with a free unit.

**Then:** paste the whole of `~/su11a65_report.txt` (it holds no user data) into the chat. The handoff records the numbers.

## 9a. (Only on a STOP in step 5) Drop the indexes

**[Server — bash]**

```
cat ~/scrp/db/migrations/su11a65_promo_search_rollback.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
```

**Expect:** `DROP INDEX` twice. The SU11A-65 code works without the indexes: the same rows, as slow as before.

## 10. Web deploy, with the guard

Only from the home PC (it has `web/.env.production`). The API must already run SU11A-65 (step 6): the new chip sends `promo_type=gift_coupon`, which the old API ignores.

**[PC — PowerShell]**

```
git pull origin main; .\scripts\deploy_frontend.ps1
```

**Expect:** `build OK: …`, the upload, `MATCH`, then a green `Done!`.
**STOP if** you see a red line or `MISMATCH`.

## 11. Browser checks

**11a. Gift coupons**

**[Browser]**
1. Open https://super.xxl.co.il/promos?city=חיפה.
2. Type `שמנת` in the search box. The sort stays on הנחה גדולה.

**Expect:**
- Cards with a % badge first.
- Gift coupons (for example "קופון שמנת חמוצה … 1 יח' מתנה") only after them. Each one shows:
  - the badge "מתנה בקופון";
  - "1 יח' מתנה" (or the stated quantity);
  - the condition if there is one;
  - "מחיר מדף ₪X", not struck through and with no %.
- No card reads "-100%".

If Haifa shows no gift coupon on cream that day, use one of the step 8 examples (its product name, in its city).

**11b. The chip**

**[Browser]** Open סינון and press "מתנה בקופון".

**Expect:**
- Only gift-coupon cards, and the chip shows as pressed.
- Pressing it again shows all cards.
- With "1+1 / מתנה" alone, no "מתנה בקופון" card appears.

**11c. Admin**

**[Browser]** In https://admin.xxl.co.il → מבצעים → חיפוש, search `קופון` with the chain רמי לוי.

**Expect:** a gift-coupon card reads "מתנה בקופון · 1 יח' מתנה". It never reads "100% הנחה".

**11d. חומוס**

**[Browser]** https://super.xxl.co.il/promos?city=תל%20אביב-יפו, search `חומוס`.

**Expect:**
- Chickpea and hummus products first.
- A lentil or pea card appears only if its promotion's description contains חומוס (step 8 shows which). Compare with the 5 Nov list: lentils and peas at positions 9–10.

**STOP if** a card has חומוס neither in its name nor in its description. Paste the card text.

**11e. Account deletion (a throwaway user only)**

Never use a real account, x@xxl.co.il, gplay@xxl.co.il or appreview@xxl.co.il.

**[Browser]**
1. In Supabase → Authentication → Users → Add user, create a throwaway user with Auto Confirm on.
2. Sign in with it on https://super.xxl.co.il.
3. Open https://super.xxl.co.il/account/delete.
4. Enter a **wrong** password and confirm.

**Expect:** "הסיסמה שגויה. נסו שוב." The account still exists: you are still signed in.

5. Enter the right password and confirm.

**Expect:** "החשבון נמחק" and you are signed out. In Supabase the user is gone, or goes within 24 hours.

## 12. Rollback

The server only pulls, so the revert is a commit made on the PC.

**12a. Revert commit**

**[PC — PowerShell]**

```
git pull origin main; git log --oneline -8
```

Note the hash of the `feat: SU11A-65 …` commit (`<HASH>`). Then:

**[PC — PowerShell]**

```
git revert --no-edit <HASH>; git push origin main
```

**Expect:** the files changed, then the push.
**STOP if** the revert reports a conflict. Run `git revert --abort` and paste the output.

**12b. API**

**[Server — bash]**

```
cd ~/scrp && git pull origin main && sudo /usr/local/bin/xxl-restart.sh scrp-api && for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] && break; sleep 1; done; curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:8000/health
```

**Expect:** `health 200`.

**12c. Indexes**

**[Server — bash]**

```
cat ~/scrp/db/migrations/su11a65_promo_search_rollback.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
```

**Expect:** `DROP INDEX` twice.

You can also keep the indexes after a code revert. The old code does not use them (its condition joins two tables), but they cost only disk space and a little time on the daily load.

**12d. Web**

**[PC — PowerShell]** (the home PC)

```
.\scripts\deploy_frontend.ps1
```

**Expect:** `MATCH`, `Done!`.

---

## Reference

- **Code:**
  - `db/query.py`:
    - `_GIFT_COUPON_SQL`, `is_gift_coupon`, `PROMO_TYPE_FILTERS`, `_PROMO_SORTS["discount"]`;
    - the `gift_*` layouts, `count_gift_coupons`;
    - `PROMO_MATCH_INDEXED` and `promo_match_sql`.
  - `api/models.py GroupedPromoItem.gift_coupon`.
  - `api/routers/admin_promos.py _promo_out` (`sample.gift_coupon`).
  - `scripts/su11a65_promo_report.py`.
  - `db/migrations/su11a65_promo_search.sql`, `su11a65_promo_search_rollback.sql`.
- **Web:**
  - `web/src/utils/giftCoupon.ts`;
  - `web/src/pages/PromosPage.tsx` (`GiftCouponCard`, chip);
  - `web/src/admin/screens/promos/PromoCard.tsx`;
  - `web/src/utils/deleteAccountFlow.ts`, `web/src/pages/DeleteAccountPage.tsx`.
- **Tests:**
  - `tests/test_promo_su11a65_pg.py`;
  - `web/scripts/gift-coupon.test.mjs`, `web/scripts/delete-account.test.mjs`.
