# SU11A-58 — promo pins and hides in the admin console (+ the pending SU11A-57 web deploy): server runbook

Written 31 Oct 2026 for Dude.

> **Web deploy only from a PC that has `web/.env.production`** (the production API and Supabase values). `scripts\deploy_frontend.ps1` now refuses to upload a build that lacks the production hosts, and prints a red STOP. The travel PC used to build SU11A-58 is not a deploy PC.

It adds:
- the **מבצעים** tab in the admin console on `https://admin.xxl.co.il`: search a promotion, preview it, **קידום** (rank, dates, ממומן) or **הסתרה** (reason); lists of active pins (reorder with up / down), active hides and expired rows;
- on the website's promos page: pinned promotions lead each branch, hidden ones are gone, and a sponsored card shows the label **ממומן**;
- the SU11A-57 accept fix: accepting with category X accepts the suggestions for X and rejects the item's other open suggestions;
- the deploy guard, recent-search normalisation, the "since the last restart" counter label, and non-breaking `npm audit fix` updates (axios 1.21, react-router 7.18.5, postcss, ws and more).

**One web deploy covers SU11A-57 and SU11A-58.** Do not run step 4 of `docs/admin/su11a57_runbook.md` on its own; step 5 here replaces it, and step 6 includes the SU11A-57 browser checks (its 6a–6d).

**How to run it**
- Run the steps in order. Every step and every code block is labelled with where it runs:
  - **[Server — bash]:** `ssh dude@185.229.226.190`, interactive, in `~/scrp`;
  - **[PC — PowerShell]:** PowerShell in `C:\scrp`, on a PC with `web/.env.production`;
  - **[Browser].**
- Each step says what to expect and when to STOP. If you stop, paste the output to the chat; do not improvise a fix.
- Nothing here prints `.env`, a token or an email address.
- **Quiet times** (same as SU11A-49): avoid 04:00–04:30, 10:00 until `scrp-cron` is `inactive`, and 14:30. Step 3 builds an index on `promos`, which briefly blocks the loader's promo writes.

**What it deploys**

| Part | What changes |
|---|---|
| DB | New table `promo_curation` and a new index `idx_promos_promo_id` on `promos` (`db/migrations/su11a58_promo_curation.sql`). Additive. |
| API | **Public:** `/promos/grouped` and `/promos/today` apply pins and hides; their rows gain `pinned` and `sponsored`. **Admin (aal2, audited):** `/admin/promos/*`. `GET /admin/status` gains `promo_curation`. **Fix:** `POST /admin/category-suggestions/{code}/accept` now accepts only the chosen id's suggestions and rejects the rest. |
| Web | Promos page: ממומן label. Admin: the מבצעים tab (lazy chunk), a status card, the counter label. Recent searches: "זירו 1.5" / "זירו1.5" / "1.5זירו" are one entry; old entries are deduped on load. Shop main JS chunk: +1.2 kB (+0.45 kB gzip). Plus everything SU11A-57 shipped. |
| Deploy script | Fails before upload on a non-production build; after upload prints MATCH / MISMATCH; no "Done!" after a failure. |
| nginx | Nothing. |

**What a pin or a hide never changes:** search, compare, basket, the cheapest-price ranking, `/product`, `/promos/bulk` (the promo badges on search results) and the search build. A hidden promotion still prices its items exactly as before. `tests/test_promo_curation_su11a58_pg.py` checks that these answers are byte-identical with and without pins and hides.

**How a promotion is identified:** by the chain and its own PromotionId (`chain_id`, `promo_id`). `promos.id` does not survive the daily reload (Shufersal deletes and re-inserts a store's promos), but the PromotionId does. One PromotionId covers every branch and every product of that promotion, so a pin or a hide applies to all of them.

**How fast a change shows:** each API worker caches the pins and hides for 30 seconds. The worker that handled the admin write sees it at once; the others within 30 s. `/promos/*` answers are not in the search response cache.

---

## 0. Where the server is (server, read-only)

```
# [Server — bash]
cd ~/scrp && git log --oneline -1
sudo -u postgres psql xxl_super -tAc "SELECT to_regclass('public.admin_audit') IS NOT NULL, to_regclass('public.categories') IS NOT NULL, to_regclass('public.category_suggestions') IS NOT NULL, to_regclass('public.promo_curation') IS NOT NULL"
```

**Expect:** the log shows the commit the server runs now. The query prints four flags, normally `t|t|t|f` or `t|t|f|f`:
- 1st `t`: `admin_audit` (SU11A-54) is there;
- 2nd `t`: the catalog tables (SU11A-52) are there;
- 3rd: `category_suggestions` (SU11A-57). `f` means step 2 applies it;
- 4th `f`: `promo_curation` is not there yet.

**STOP if** the 1st or 2nd flag is `f`. Finish `docs/admin/su11a54_runbook.md` or `docs/catalog/su11a52_runbook.md` first.

## 1. Pull (server)

```
# [Server — bash]
cd ~/scrp && git status --short | head -5 && git pull origin main && git log --oneline -3
venv/bin/python3 -c "import api.main; print('api imports ok')"
```

**Expect:**
- The pull fast-forwards. The top line is the SU11A-58 commit, `feat: SU11A-58 promo pins and hides in the admin console`; SU11A-57 (`ebf5653`) is below it.
- `api imports ok`.

**STOP if** the pull conflicts, or the import prints a traceback. Nothing has changed yet.

## 2. The SU11A-57 migration, only if step 0 printed `f` for it (server)

```
# [Server — bash]
cat ~/scrp/db/migrations/su11a57_category_suggestions.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
sudo -u postgres psql xxl_super -tAc "SELECT tableowner FROM pg_tables WHERE tablename = 'category_suggestions'"
```

**Expect:** `BEGIN`, `DO`, `CREATE TABLE`, `CREATE INDEX` (three times), `ALTER TABLE`, `COMMIT`; then `scrp_app`.

**STOP if** it prints `ERROR` (the transaction rolled back; nothing changed).

If SU11A-57 step 5 (the 150 + 100 graded manual rows) has not been run yet, run it now from `docs/admin/su11a57_runbook.md` section 5. It does not depend on the web deploy.

## 3. Apply the SU11A-58 migration, twice (server)

```
# [Server — bash]
cat ~/scrp/db/migrations/su11a58_promo_curation.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
cat ~/scrp/db/migrations/su11a58_promo_curation.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
sudo -u postgres psql xxl_super -tAc "SELECT tableowner FROM pg_tables WHERE tablename = 'promo_curation'"
sudo -u postgres psql xxl_super -tAc "SELECT indexname FROM pg_indexes WHERE tablename IN ('promo_curation', 'promos') ORDER BY 1"
```

**Expect:**
- **First run:** `BEGIN`, `DO`, `CREATE TABLE`, `CREATE INDEX` (three times), `ALTER TABLE`, `COMMIT`. The third `CREATE INDEX` (on `promos`, about 560K rows) takes a few seconds.
- **Second run:** the same, with `NOTICE: ... already exists, skipping` lines. It is idempotent.
- **Owner:** `scrp_app`.
- **Indexes:** among them `idx_promo_curation_read`, `idx_promos_promo_id`, `promo_curation_pkey`, `uq_promo_curation_active`.

**STOP if** it prints `ERROR` (the transaction rolled back; nothing changed). `promos / stores are missing` means the wrong database; `admin_audit is missing` means SU11A-54 is not applied.

## 4. Restart the API and check it (server)

```
# [Server — bash]
sudo /usr/local/bin/xxl-restart.sh scrp-api
systemctl is-active scrp-api
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/health
curl -s 'http://127.0.0.1:8000/promos/grouped?limit=1' | python3 -c "import json,sys; r=json.load(sys.stdin)[0]; print(r['pinned'], r['sponsored'])"
curl -s 'http://127.0.0.1:8000/promos/today' | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d), d[0]['pinned'])"
curl -s -w ' %{http_code}\n' http://127.0.0.1:8000/admin/promos/curation
curl -s -w ' %{http_code}\n' -H 'Authorization: Bearer garbage' -X POST -H 'Content-Type: application/json' -d '{"chain_id":"x","promo_id":"y","rank":1}' http://127.0.0.1:8000/admin/promos/pins
curl -s http://127.0.0.1:8000/categories/tree | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['version'], len(d['nodes']))"
```

**Expect:**
- the restart prints its journal lines with no traceback; then `active` and `200`;
- `False False` (no pins yet);
- `200 False` (or a smaller first number on a quiet day);
- the two admin calls: `{"code":"admin_required"} 403` each;
- the SU11A-57 tree: `v1.2 204`.

**STOP if** the API is not active, or a promo call errors. Roll back with step 8a.

## 5. One web deploy for SU11A-57 + SU11A-58 (PC with web/.env.production)

```
# [PC — PowerShell]
git pull
Test-Path web\.env.production
.\scripts\deploy_frontend.ps1
```

**Expect:**
- `True` from `Test-Path`. If `False`, STOP: this PC cannot deploy.
- The build, then `build OK: contains https://api-super.xxl.co.il and https://<project>.supabase.co`;
- the upload, then `0` (web root modes);
- then `local index-XXXX.js | live index-XXXX.js` with the same name twice, `MATCH`, and a green `Done! Site live at https://super.xxl.co.il`.

**STOP if:**
- a red `STOP: this build is not a production build`: nothing was uploaded. The PC's `web/.env.production` is missing or holds other hosts. Fix that PC or use another; do not edit `web/deploy-hosts.json` to make it pass;
- a red `MISMATCH`: run the script again once; if it still says MISMATCH, paste the two names;
- any other red line. There is no `Done!` after a failure.

## 6. Checks (browser, then server)

### SU11A-57 checks (its runbook 6a–6d)

**6a. [Browser] The shop, signed out.** On `https://super.xxl.co.il`, search for במבה and open a product.
- Under the barcode: a line with the category path, then **הצעת עדכון קטגוריה**.
- Tap it: the note **האפשרות זמינה למשתמשים רשומים בלבד** appears, with התחברות · הרשמה links. No dialog opens.

**6b. [Browser] The shop, signed in** with the x@ test account:
- Tap the button: the dialog shows the current path and a searchable list. The current category is greyed out as נוכחית.
- Pick another category, add a short comment, send. The dialog closes and **תודה, ההצעה תיבדק** shows.
- Send again for the same product: **כבר שלחת הצעה למוצר הזה…**

**6c. [Browser] The console.** Open `https://admin.xxl.co.il` and sign in with 2FA.
- **לוח בקרה:** the card קטגוריות shows `1` pending suggestion.
- **קטגוריות › הצעות קטגוריה:** the test suggestion appears, with its count, the suggested path and the comment. No user name or email appears anywhere.
- Press **דחייה**, then אישור. The toast says ההצעות נדחו and the queue is empty. This cleans up the test.
- **קטגוריות › חיפוש:** type במבה, open the product. Source, confidence, chains and history are shown.
- Optional: press **נכון** on a product whose label is correct. It is then marked נבדק, and the history shows אישור קטגוריה with **ביטול השינוי**.

**6d. [Server] Read-only check of what 6b–6c wrote:**

```
# [Server — bash]
sudo -u postgres psql xxl_super -tAc "SELECT status, count(*) FROM category_suggestions GROUP BY 1"
sudo -u postgres psql xxl_super -tAc "SELECT action, count(*) FROM admin_audit WHERE target_type = 'item_category' GROUP BY 1"
```

**Expect:** `rejected|1`, and `category_suggestion.reject|1` (plus `category.confirm|1` if you pressed נכון).

### SU11A-58 checks

**6e. [Browser] The console, לוח בקרה.**
- A new card **קידום והסתרת מבצעים**: `0`, `0`, `0`.
- The requests card is titled **בקשות מאז ההפעלה האחרונה**, and its note says the counters reset on every API restart, with the start time.

**6f. [Browser] Note a price first.** On the shop, open **מבצעים**, choose all cities and one chain. Pick a promotion in the middle of a branch list (not the first card). Write down its product, branch and the price on the card. Then search the shop for that product and write down the price shown for that chain.

**6g. [Browser] Pin it, sponsored.** Console › **מבצעים** › **חיפוש**: type the product name (or its barcode). The promotion shows as a card with its chain, PromotionId, branches and end date.
- Press **קידום**. The form shows a yellow box: **קידום בתשלום חייב להיות מסומן כממומן…**. Keep rank 1, tick **קידום בתשלום (ממומן)**, press **קידום**.
- The confirm dialog says **…כמבצע ממומן? התווית ״ממומן״ תוצג לכל המשתמשים.** Confirm. The toast says **המבצע קודם**.
- **מקודמים:** the promotion at **מקום 1**, with the badge **ממומן**.

**6h. [Browser] The shop.** Reload the promos page (allow 30 seconds), same chain:
- in every branch of that chain carrying the promotion, its card is now FIRST and shows **ממומן**;
- search the shop for the product again: the price for that chain is the one you wrote down in 6f. **A pin never changes a price.**

**6i. [Browser] Hide another promotion.** Console › חיפוש: find a second promotion of the same chain. Press **הסתרה**. The form says the hide does not change prices; the button stays disabled until you type a reason. Type `בדיקה`, press **הסתרה**, confirm.
- **מוסתרים:** it is listed with **סיבה: בדיקה**.
- The shop's promos page (after 30 s): that promotion is gone. A shop search for its product shows the same price as before.

**6j. [Browser] Recent searches.** On the shop, search `זירו 1.5`, then `זירו1.5`. Clear the box: the recent list shows ONE entry, the last spelling.

**6k. [Browser] Clean up.** Console › **מקודמים**: press **הסרה** on the pin, confirm (toast **הוסר**). **מוסתרים**: the same for the hide. Both lists are empty. **יומן פעולות** shows the pin, the hide and both removals.

**6l. [Server] Read-only check of what 6g–6k wrote:**

```
# [Server — bash]
sudo -u postgres psql xxl_super -tAc "SELECT kind, active, sponsored, count(*) FROM promo_curation GROUP BY 1, 2, 3 ORDER BY 1, 3"
sudo -u postgres psql xxl_super -tAc "SELECT action, count(*) FROM admin_audit WHERE target_type = 'promo' GROUP BY 1 ORDER BY 1"
```

**Expect:** `hide|f|f|1` and `pin|f|t|1` (both removed, kept for the record); then `promo.hide|1`, `promo.pin|1`, `promo.remove|2`.

**STOP if** any page shows an error box, a shop price changed in 6h or 6i, or the console shows a user's email or id. Paste a screenshot.

## 7. Afterwards

- Nothing to schedule. A pin or hide whose end date passes, or whose promotion leaves the feed, stops applying by itself and shows under **פג תוקף**. Remove it there when you like.
- **Paid placement must be marked ממומן.** The console warns on every pin; the label is on the web promos page. The app shows no promo lists today, so there is nothing to label there (`docs/handoff_mobile.md`).
- At most 50 active pins. Pinning at rank N moves N and below down one; removing a pin closes the gap.
- **Decision for Dude, not changed in SU11A-58:** a hidden promotion still feeds search, compare and basket prices (and the promo badges on search results). If a promotion is hidden because its data is wrong, its wrong price can still win "cheapest". Options are in the SU11A-58 handoff entry.

## 8. Rollback

**8a. API (server)**, if step 4 failed or the new endpoints misbehave. This goes back to SU11A-57's API (same table set; `promo_curation` stays, unused):

```
# [Server — bash]
cd ~/scrp && git log --oneline -3
git checkout HEAD~1 -- api/ db/query.py db/promo_curation.py && sudo /usr/local/bin/xxl-restart.sh scrp-api && systemctl is-active scrp-api
```

**Expect:** `active`. `git status` then shows those paths modified (and `db/promo_curation.py` deleted). Run `git checkout HEAD -- api/ db/` to return to the release before the next pull.

**8b. Web (PC with web/.env.production):** deploy the SU11A-57 build (the commit before SU11A-58):

```
# [PC — PowerShell]
git checkout HEAD~1 -- web/; .\scripts\deploy_frontend.ps1; git checkout HEAD -- web/
```

**Expect:** `MATCH`, then `Done!`. The guard keeps working: `git checkout HEAD~1 -- web/` leaves files that exist only in SU11A-58 (`web/deploy-hosts.json`, `web/scripts/check-deploy.mjs`) in place, and `scripts\deploy_frontend.ps1` is not under `web/`.

**8c. Table (server)**, only after 8a. Drops every pin and hide; their audit rows stay:

```
# [Server — bash]
sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1 -c "BEGIN; DROP TABLE IF EXISTS promo_curation; DROP INDEX IF EXISTS idx_promos_promo_id; COMMIT;"
```

**Expect:** `BEGIN`, `DROP TABLE`, `DROP INDEX`, `COMMIT`. The SU11A-58 API (if still running) then applies no curation and its admin promo tab shows errors.
