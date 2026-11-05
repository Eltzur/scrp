# SU11A-66 Part B — hide customer-compensation coupons from the promo lists: runbook

Written 5 Nov 2026 for Dude.

**What changes for users**
- **The lists no longer show compensation promotions.** A promotion whose description names a customer compensation is left out of `/promos/list`, `/promos/grouped` and `/promos/promoted`. That covers the promos page, its search, the type chips (including "מתנה בקופון") and מבצעים מקודמים. Examples: "קופון פיצוי לקוח 20שח מוצרי שסטוביץ" (Rami Levy), "קופון פיצוי לקוח 2 יחידות תפוגן" (Carrefour), "35ש"ח-קופון פיצוי פריניר" (Shufersal).
  - **Rule:** the description contains פיצוי, the defective spelling פצוי, or the plural (regex `פי?צוי`).
  - **Look-alike words stay** (פיצוחים, פיצה): they have no וי after the צ.
- **Admin search is unchanged.** It still lists these promotions, and their card reads "פיצוי ללקוח — מוסתר מהרשימות" in place of the city coverage.

**Not changed:**
- `/promos/today` (the home page block): it never had the list cleanup;
- prices: search, compare, basket, `/product`, `/promos/bulk`, promo badges and the search build.

**How to run it**
- Run the steps in order. Each step names where it runs:
  - **[Server — bash]:** `ssh dude@185.229.226.190`, interactive, in `~/scrp`. Type Hebrew only there (CLAUDE.md rule 11).
  - **[PC — PowerShell]:** in `C:\scrp` on the **home PC** (the one with `web/.env.production`).
  - **[Browser].**
- If a step says STOP, paste the output to the chat and do not improvise a fix.
- Nothing here prints `.env`, a token or an email address.

**What it deploys**

| Part | What changes |
|---|---|
| DB | Nothing (no migration). |
| API | The list cleanup rule `compensation` (`db/query.py CLEANUP_RULES`), and `compensation` on `/admin/promos/search` hits. |
| Web | The admin promotion card only (the note). The public pages need no deploy: the API leaves the rows out. |

---

## 0. Precondition: SU11A-65 and its follow-up are deployed

**[Server — bash]**

```
cd ~/scrp && git merge-base --is-ancestor a24f469 HEAD && echo "SU11A-65 follow-up pulled"
```

**Expect:** `SU11A-65 follow-up pulled`.
**STOP if** the line is missing.

## 1. Quiet-time check

**[Server — bash]**

```
date '+%H:%M'; systemctl show -p ActiveState --value scrp-cron
```

**Expect:**
- a time outside 04:00–04:30, 14:25–15:00, and 10:00 until the cron finishes;
- then `inactive`.

**STOP if** it reads `activating`. Wait until it reads `inactive`.

## 2. Before (for the comparison in step 5)

**[Server — bash]**

```
API=https://api-super.xxl.co.il
c() { curl -s -G -o /tmp/su66.json -w "$1 %{http_code} %{time_total}s " "${@:2}"; python3 -c "import json, re; r=json.load(open('/tmp/su66.json')); print(len(r), 'rows,', sum(1 for x in r if re.search('פי?צוי', x.get('promo_description') or '')), 'compensation,', 'all gift_coupon:', all(x['gift_coupon'] for x in r))"; }
c haifa-cream-chip $API/promos/list --data-urlencode 'city=חיפה' --data-urlencode 'q=שמנת' --data-urlencode 'promo_type=gift_coupon' --data-urlencode 'limit=100'
c all-chip         $API/promos/list --data-urlencode 'promo_type=gift_coupon' --data-urlencode 'chain=7290058140886' --data-urlencode 'limit=100'
c q-compensation   $API/promos/list --data-urlencode 'q=פיצוי' --data-urlencode 'limit=100'
rm -f /tmp/su66.json
```

`7290058140886` is the Rami Levy chain id (the one with 278 gift-coupon promotions on 5 Nov).

**Expect:** three lines with `200`. Note the `compensation` numbers: today some should be above 0.
**STOP if** a line is not `200`.

## 3. Pull

**[Server — bash]**

```
cd ~/scrp && git pull origin main && git log --oneline -4
```

**Expect:** one of the top lines is `fix: SU11A-66 Part B hide customer-compensation coupons from promo lists`.
**STOP if** the pull fails.

## 4. Restart the API and wait for health

**[Server — bash]**

```
sudo /usr/local/bin/xxl-restart.sh scrp-api && for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] && break; sleep 1; done; curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:8000/health
```

**Expect:** `health 200`.
**STOP if** it is not `200`. Then paste `sudo journalctl -u scrp-api -n 40 --no-pager`.

## 5. Curl checks (after)

**[Server — bash]** Run the same block as in step 2.

**Expect:**
- **`haifa-cream-chip`:** `200`, `0 compensation`, `all gift_coupon: True`. The row count may be lower than in step 2 (the compensation rows are gone), and `0 rows` is fine.
- **`all-chip`:** `200`, `0 compensation`, `all gift_coupon: True`, with some rows still: the chip still works.
- **`q-compensation`:** `200`, `0 compensation`. It may still list rows whose product name has the word but whose description does not.
- Times similar to step 2.

**STOP if:**
- any `compensation` count is above 0;
- a line is `503`;
- `all-chip` shows `0 rows` while step 2 showed rows with fewer compensation rows than the total.

## 6. Read-only report: counts per chain, examples, spelling check

It reads every in-force promo (about 1–2 minutes). The session is READ ONLY with a 120 s statement limit.

**[Server — bash]**

```
cd ~/scrp && ( ulimit -v 2000000; set -a; source .env; set +a; venv/bin/python3 -m scripts.su11a65_promo_report --compensation-only ) 2>&1 | tee ~/su11a66b_report.txt
```

**Expect** `== compensation coupons hidden from the lists`, with:
- `rows: N, promotions: M`, then the per-chain lines;
- 10 example promotions spread over the chains, each reading like "קופון פיצוי …";
- `matched WITHOUT 'קופון' (possible false positives)`: the descriptions the rule catches that do not say קופון. Read them: each should still be a compensation ("פיצוי ללקוח …"), not a public offer.
- `near misses NOT matched`: descriptions with פיצו / פצו / compens that the rule leaves on the lists (פיצוחים, …). Read them: none should be a compensation coupon.

**STOP if:**
- it fails with `statement timeout` or `MemoryError`;
- a "possible false positive" is a public offer;
- a "near miss" is a compensation coupon.

In the last two cases paste the lines: the rule is one regex in `db/query.py` (`_COMPENSATION_RE`).

**Then:** paste the whole of `~/su11a66b_report.txt` into the chat (it holds no user data). The handoff records the counts.

## 7. Web deploy, with the guard

Only the admin card changed. Run it from the home PC (it has `web/.env.production`), after step 4.

**[PC — PowerShell]**

```
git pull origin main; .\scripts\deploy_frontend.ps1
```

**Expect:** `build OK: …`, the upload, `MATCH`, then a green `Done!`.
**STOP if** you see a red line or `MISMATCH`.

## 8. Browser checks

**8a. Promos page**

**[Browser]**
1. Open https://super.xxl.co.il/promos?city=חיפה and type `שמנת`.
2. Open סינון and press "מתנה בקופון".

**Expect:**
- No card's description contains "פיצוי".
- The chip still shows gift-coupon cards (or none, if Haifa has none on cream that day), and pressing it again shows all cards.

**8b. Admin**

**[Browser]** In https://admin.xxl.co.il → מבצעים → חיפוש, search `פיצוי` with the chain רמי לוי.

**Expect:**
- The compensation promotions are listed.
- Each card shows "פיצוי ללקוח — מוסתר מהרשימות" (amber) in place of "מוצג ב-N ערים".
- A pin on one of them is allowed but shows nowhere: it is not on the lists.

## 9. Rollback

**[PC — PowerShell]**

```
git pull origin main; git revert --no-edit <the Part B commit>; git push origin main
```

**[Server — bash]**

```
cd ~/scrp && git pull origin main && sudo /usr/local/bin/xxl-restart.sh scrp-api
```

- The lists show the compensation promotions again.
- The admin card without the API flag simply shows the coverage again; a web redeploy (step 7) is optional.
- Nothing in the database changed, so there is nothing to undo there.
