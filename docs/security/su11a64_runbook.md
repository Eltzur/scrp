# SU11A-64 — SU11A-63 audit fixes H1, M1, M2, L2 (web / API) + nginx heavy group for the promo endpoints: runbook

Written 5 Nov 2026 for Dude. The audit: `docs/security/su11a63_static_audit.md`.

**What changes**

| Gap | Before | Now |
|---|---|---|
| **H1** `POST /promos/bulk` | any number of stores; every promo row of them (up to ~0.5–1M rows) | at most **300 stores** and **1,000 barcodes** per call (422 above); an answer above **50,000 rows** is 422 `too_many_rows`. The web sends the barcodes on screen (`item_codes`) and splits longer store lists into several calls, so its badges are the same with far smaller answers. |
| **M1** `/promos/today` | any `city` / `chain_id` string became a cache key; concurrent misses each ran the ~11 s rebuild | unknown city or chain: 422 `{"code":"unknown_city"}` / `{"code":"unknown_chain"}`; one rebuild per key and worker at a time (the others wait for it); the cache stays at 256 keys |
| **M2** users row | an account deleted in the Supabase dashboard and re-created with the same email got 500 on every signed-in call | the old row's email becomes `orphaned+<old id>@invalid.local` and the new account gets its own row, in one transaction; nothing moves to the new account; a warning in the log with the two ids, no email |
| **L2** app basket | the website listed `__xxl_mobile_basket__` under הסלים שלי and could delete it | the website does not list it; the API answers 409 to deleting or renaming it, or renaming another basket to it. The app's calls (list, create, update items) are unchanged. |
| nginx | heavy group (2 r/s, burst 10): `/compare`, `/basket/compare`, `/promos/grouped` | plus `/promos/bulk`, `/promos/list`, `/promos/promoted`, `/promos/today`, `/admin/promos/search` |

**Prices:** `/promos/bulk` rows are unchanged (only filtered by the barcodes the caller asks for). The SU11A-58 byte-identical pricing test passes unchanged.

**How to run it**
- Run the steps in order. Each step names where it runs:
  - **[Server — bash]:** `ssh dude@185.229.226.190`, interactive, in `~/scrp`. Type Hebrew only there (CLAUDE.md rule 11).
  - **[PC — PowerShell]:** PowerShell in `C:\scrp`, on the **home PC** (the one with `web/.env.production`).
  - **[Browser].**
- If a step says STOP, paste the output to the chat and do not improvise a fix.
- Nothing here prints `.env`, a token or an email address.
- **The web goes first (step 2), then the API.** The new web works with the old API, which ignores the new `item_codes` field. The old web sends no barcode list, so the new API could refuse a busy results page (`too_many_rows`), which would only drop the promo badges. A browser tab opened before step 2 keeps the old page until it reloads.

---

## 1. Quiet-time check

**[Server — bash]**

```
date '+%H:%M'; systemctl show -p ActiveState --value scrp-cron
```

**Expect:** a time outside 04:00–04:30, 14:25–15:00 and 10:00 until the cron finishes, then `inactive`.
**STOP if** the second line is `activating`. Wait until it reads `inactive`.

## 2. Web deploy, with the guard

**[PC — PowerShell]**

```
git pull origin main; .\scripts\deploy_frontend.ps1
```

**Expect:** `build OK: …`, the upload, `MATCH`, then a green `Done!`.
**STOP if** you see a red line or `MISMATCH`.

## 3. Pull

**[Server — bash]**

```
cd ~/scrp && git pull origin main && git log --oneline -3
```

**Expect:** a top line `fix(security): SU11A-64 audit fixes H1 M1 M2 L2, nginx heavy group for the promo endpoints`.
**STOP if** the pull fails.

## 4. Restart the API and wait for health

**[Server — bash]**

```
sudo /usr/local/bin/xxl-restart.sh scrp-api && for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] && break; sleep 1; done; curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:8000/health
```

**Expect:** `health 200`.
**STOP if** it is not `200`. Then paste `sudo journalctl -u scrp-api -n 40 --no-pager`.

## 5. API checks (from the server, before the nginx change)

**[Server — bash]**

```
API=https://api-super.xxl.co.il
python3 -c "import json; print(json.dumps({'stores': [{'chain_id': 'X', 'store_id': str(i)} for i in range(301)]}))" > /tmp/su64_big.json
curl -s -o /tmp/su64.out -w 'bulk-301   %{http_code}\n' -H 'Content-Type: application/json' --data @/tmp/su64_big.json $API/promos/bulk; head -c 160 /tmp/su64.out; echo
curl -s -w '\nbulk-small %{http_code}\n' -H 'Content-Type: application/json' --data '{"stores":[{"chain_id":"X","store_id":"1"}],"item_codes":["7290000000001"]}' $API/promos/bulk
curl -s -G -w '\ntoday-junk %{http_code}\n' $API/promos/today --data-urlencode 'city=junk-city'
curl -s -G -w '\ntoday-chain %{http_code}\n' $API/promos/today --data-urlencode 'chain_id=junk'
curl -s -G -o /dev/null -w 'list-page  %{http_code} %{time_total}s\n' $API/promos/list --data-urlencode 'city=תל אביב-יפו' --data-urlencode 'q=חלב'
rm -f /tmp/su64_big.json /tmp/su64.out
```

**Expect:**
- `bulk-301   422`, then a JSON detail mentioning `at most 300`.
- `{}` then `bulk-small 200`.
- `{"code":"unknown_city"}` then `today-junk 422`.
- `{"code":"unknown_chain"}` then `today-chain 422`.
- `list-page  200` and a time under 3 s.

**STOP if** any status differs.

## 6. nginx: the heavy group for the promo endpoints

**6a. Back up the installed snippet, outside `/etc/nginx/snippets`** (so nginx never includes the copy)

**[Server — bash]**

```
sudo mkdir -p /var/backups/xxl-nginx && sudo cp -p /etc/nginx/snippets/xxl-ratelimit-api.conf /var/backups/xxl-nginx/xxl-ratelimit-api.conf.bak-su11a64-$(date +%F-%H%M) && ls -l /var/backups/xxl-nginx/
```

**Expect:** a line `xxl-ratelimit-api.conf.bak-su11a64-<date>`.
**STOP if** the copy fails.

**6b. Install, test, reload**

**[Server — bash]**

```
sudo cp ~/scrp/deploy/nginx/xxl-ratelimit-api.conf /etc/nginx/snippets/xxl-ratelimit-api.conf && sudo nginx -t
```

**Expect:** `syntax is ok` and `test is successful`.
**STOP if** not. Restore the backup: `sudo cp -p /var/backups/xxl-nginx/xxl-ratelimit-api.conf.bak-su11a64-<date> /etc/nginx/snippets/xxl-ratelimit-api.conf && sudo nginx -t`. Do **not** reload.

**[Server — bash]**

```
sudo systemctl reload nginx && systemctl is-active nginx && sudo nginx -T 2>/dev/null | grep -nA3 "location = /promos/\|location = /admin/promos/search"
```

**Expect:**
- `active`.
- Six location blocks: `/promos/grouped`, `/promos/bulk`, `/promos/list`, `/promos/promoted`, `/promos/today`, `/admin/promos/search`. Each block has `limit_req zone=xxl_heavy burst=10 nodelay;`, then `limit_req zone=xxl_api burst=40 nodelay;`, then `include snippets/xxl-api-proxy.conf;`.

**STOP if** a block is missing.

**6c. One burst test, then stop**

`/promos/list` with only a city answers `[]` without a DB query (SU11A-62), so this costs nothing.

**[Server — bash]**

```
for i in $(seq 1 20); do curl -s -G -o /dev/null -w '%{http_code} ' https://api-super.xxl.co.il/promos/list --data-urlencode 'city=תל אביב-יפו'; done; echo; curl -s -G https://api-super.xxl.co.il/promos/list --data-urlencode 'city=תל אביב-יפו'; echo
```

**Expect:**
- About 11 `200`, then `429` for the rest.
- The last line `{"code":"rate_limited"}`.
- Only this server's IP is limited, and only for a few seconds.

**STOP if** there is no `429` (the snippet is not in effect) or any `5xx`.

## 7. Browser checks

**7a. Saved baskets**

**[Browser]** On super.xxl.co.il, sign in with an account that has used the Android app signed in (it has the app basket), then open הסלים שלי.

**Expect:** the saved baskets, and no entry named `__xxl_mobile_basket__`.

**7b. Search badges**

**[Browser]** Search `חלב`, then press טען עוד once.

**Expect:**
- Products with promotions still show their promo badges (for example "-N%" or "2 ב-…"), also on the cards added by טען עוד.
- In DevTools → Network, the `bulk` requests answer 200 and carry `item_codes`.

**7c. Promos page and admin**

**[Browser]**
1. super.xxl.co.il/promos: pick a department, then search `שמנת`.
2. admin.xxl.co.il → מבצעים: search `שמנת`.

**Expect:**
- Lists as before.
- No "busy, try again" message in normal use.

**STOP if** a normal page shows a busy / rate-limit message. Paste the DevTools request that got `429`.

## 8. Rollback

**nginx**

**[Server — bash]**

```
ls /var/backups/xxl-nginx/ && sudo cp -p /var/backups/xxl-nginx/xxl-ratelimit-api.conf.bak-su11a64-<date> /etc/nginx/snippets/xxl-ratelimit-api.conf && sudo nginx -t && sudo systemctl reload nginx && systemctl is-active nginx
```

**Expect:** `syntax is ok`, `test is successful`, `active`.

**Code** (the server only pulls, so the revert is a commit made on the PC)

**[PC — PowerShell]**

```
git pull origin main; git log --oneline -6
```

Note the hash of the `fix(security): SU11A-64 …` commit (`<HASH>`). Then:

**[PC — PowerShell]**

```
git revert --no-edit <HASH>; git push origin main; .\scripts\deploy_frontend.ps1
```

**Expect:** the revert commit, the push, `MATCH`, `Done!`.
**STOP if** the revert reports a conflict. Run `git revert --abort` and paste the output.

**[Server — bash]**

```
cd ~/scrp && git pull origin main && sudo /usr/local/bin/xxl-restart.sh scrp-api && for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] && break; sleep 1; done; curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:8000/health
```

**Expect:** `health 200`.

**Note:** an M2 tombstone already written stays after a rollback. The old row keeps its `orphaned+<id>@invalid.local` email, which is correct: the address belongs to the new account.

---

## Reference

- **Code:**
  - `api/routers/promos.py`: `BULK_MAX_STORES`, `BULK_MAX_ITEMS`, `BULK_MAX_ROWS`; the `/promos/today` key check.
  - `db/query.py`: `_fetch_promos_bulk_all(item_codes, max_rows)`, `PromoBulkTooLarge`, `today_key_values`, `_today_key_lock`.
  - `api/auth.py`: `_upsert_user`, `orphan_email`.
  - `api/routers/saved_baskets.py`: `RESERVED_BASKET_NAME`.
- **Web:**
  - `web/src/utils/promoBulk.ts`, used by `web/src/api/client.ts` `getPromosBulk` and `web/src/components/ResultsList.tsx`;
  - `web/src/utils/savedBaskets.ts`, used by `web/src/pages/MyBasketsPage.tsx`.
- **nginx:** `deploy/nginx/xxl-ratelimit-api.conf`. The zones are unchanged (`deploy/nginx/xxl-ratelimit-http.conf`).
- **Tests:** `tests/test_audit_fixes_su11a64_pg.py`, `web/scripts/promo-bulk.test.mjs`.
