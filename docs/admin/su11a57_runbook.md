# SU11A-57 — categories in the admin console + user category suggestions: server runbook

Written 25 Oct 2026 for Dude. It adds:
- the **קטגוריות** tab to the admin console on `https://admin.xxl.co.il`: search, item panel, four queues, bulk move and undo;
- the **הצעת עדכון קטגוריה** button on the web product dialog. The app gets the same button in build 9 (`docs/handoff_mobile.md`).

**How to run it**
- Run the steps in order. Every step and every code block is labelled with where it runs:
  - **[Server — bash]:** `ssh dude@185.229.226.190`, interactive, in `~/scrp`;
  - **[PC — PowerShell]:** PowerShell in `C:\scrp`;
  - **[Browser].**
- Each step says what to expect and when to STOP. If you stop, paste the output to the chat; do not improvise a fix.
- Nothing here prints `.env`, a token or an email address.
- **Quiet times** (same as SU11A-49): avoid 04:00–04:30, 10:00 until `scrp-cron` is `inactive`, and 14:30.

**Needs first:** the catalog tables from `docs/catalog/su11a52_runbook.md`, applied with taxonomy v1.2 (sections 1–3). Step 0 checks this.

**What it deploys**

| Part | What changes |
|---|---|
| DB | New table `category_suggestions` (`db/migrations/su11a57_category_suggestions.sql`). Additive. It references `users` (ON DELETE CASCADE, so `DELETE /account` removes a user's suggestions) and `categories`. |
| API | **Public:** `GET /categories/tree` and `GET /items/{code}/category`. A low-confidence label shows the department only. **Signed in:** `POST /items/{code}/category-suggestions`, with the same gates as ratings plus terms always required, 20 per day, one open per item. **Admin (aal2, audited):** `/admin/categories/*` and `/admin/category-suggestions/*`. `GET /admin/status` gains `category_suggestions`. |
| Web | The product dialog shows the category path and the suggestion button. The picker dialog is a lazy chunk; the main JS chunk grew by 3.8 kB (0.9 kB gzip). The admin console gains the קטגוריות tab, as a lazy chunk. |
| nginx | Nothing. |

**Every admin category write is a manual label:** `source = manual`, `reviewed = true`. The automated import and the 14:30 build never overwrite it (precedence in `scripts/catalog/store.py`). Each write records an audit row with the old and new label, and "ביטול השינוי" in the item panel writes the old label back.

---

## 0. Check the catalog tables are there (server)

```
# [Server — bash]
sudo -u postgres psql xxl_super -tAc "SELECT (SELECT count(*) FROM categories WHERE active), (SELECT max(taxonomy_version) FROM categories), (SELECT count(*) FROM item_categories)"
```

**Expect:** about `204|v1.2|129072`. The first number is 204 active categories; the last is the number of labels from the su11a52 import (section 6 of its runbook).

**STOP if** it says `relation "categories" does not exist` or the version is not `v1.2`. Finish `docs/catalog/su11a52_runbook.md` first. The migration in step 2 refuses to run without `categories`.

## 1. Pull (server)

```
# [Server — bash]
cd ~/scrp && git status --short | head -5 && git pull origin main && git log --oneline -3
venv/bin/python3 -c "import api.main; print('api imports ok')"
```

**Expect:**
- The pull fast-forwards. The log's top line is the SU11A-57 commit, `feat: SU11A-57 categories in the admin console and user category suggestions`.
- `api imports ok`. The API now imports `scripts/catalog/store.py`, which this checks.

**STOP if** the pull conflicts, or the import prints a traceback. Nothing has changed yet.

## 2. Apply the migration (server)

```
# [Server — bash]
cat ~/scrp/db/migrations/su11a57_category_suggestions.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
cat ~/scrp/db/migrations/su11a57_category_suggestions.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
sudo -u postgres psql xxl_super -tAc "SELECT tableowner FROM pg_tables WHERE tablename = 'category_suggestions'"
sudo -u postgres psql xxl_super -tAc "SELECT indexname FROM pg_indexes WHERE tablename = 'category_suggestions' ORDER BY 1"
```

**Expect:**
- **First run:** `BEGIN`, `DO`, `CREATE TABLE`, `CREATE INDEX` (three times), `ALTER TABLE`, `COMMIT`.
- **Second run:** the same, with `NOTICE: ... already exists, skipping` lines. It is idempotent.
- **Owner:** `scrp_app`.
- **Indexes:** `category_suggestions_pkey`, `idx_category_suggestions_queue`, `idx_category_suggestions_user`, `uq_category_suggestions_open`.

**STOP if** it prints `ERROR` (the transaction rolled back; nothing changed). The most likely error is `categories is missing: apply db/migrations/su11a52_catalog.sql first`; go back to step 0.

## 3. Restart the API and check it (server)

```
# [Server — bash]
sudo /usr/local/bin/xxl-restart.sh scrp-api
systemctl is-active scrp-api
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/categories/tree | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['version'], len(d['nodes']))"
curl -s http://127.0.0.1:8000/items/7290000066332/category; echo
curl -s -w ' %{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{"category_id":"D08"}' http://127.0.0.1:8000/items/7290000066332/category-suggestions
curl -s -w ' %{http_code}\n' http://127.0.0.1:8000/admin/categories/queue/low
curl -s -w ' %{http_code}\n' -H 'Authorization: Bearer garbage' http://127.0.0.1:8000/admin/category-suggestions/7290000066332/reject -X POST
```

**Expect:**
- the restart prints its journal lines with no traceback; then `active` and `200`;
- the tree: `v1.2 204`;
- the item (Osem Apropo, graded D08.C05.S02 in the review): `{"item_code":"7290000066332","category_id":"D08.C05.S02","path":[...three steps...],"partial":false}`. Its label is high-confidence, so the full path shows; a low-confidence label would show one step and `"partial":true`;
- the anonymous suggestion: `{"code":"login_required"} 401`;
- the two admin calls: `{"code":"admin_required"} 403` each.

**STOP if** the API is not active, or the tree call errors. Roll back with step 8a.

## 4. Web deploy (PC)

```
# [PC — PowerShell]
git pull
.\scripts\deploy_frontend.ps1
```

**Expect:** the build, the upload, then `0`, then `Done!`. The script prints `Done!` even when scp fails, so compare the bundle hash:

```
# [PC — PowerShell]
(Select-String -Path web\dist\index.html -Pattern 'assets/index-[^"]+\.js').Matches.Value
curl.exe -s https://super.xxl.co.il/ | Select-String -Pattern 'assets/index-[^"]+\.js' | ForEach-Object { $_.Matches.Value }
```

**Expect:** the same file name twice.

**STOP if** they differ. Run the deploy again; if it still differs, paste both lines.

## 5. Load the graded files as manual rows (server)

The SU11A-55 review and the SU11A-57 AI audit share no barcode, so the order does not matter. Skip 5a if `review_graded_v1.csv` was already applied (su11a52 runbook, section 5); its dry run then shows `"manual_changes": {"unchanged": 150}`.

**5a. Dude's 150-row review:**

```
# [Server — bash]
cd ~/scrp && venv/bin/python3 -m scripts.catalog.import_categories --manual docs/catalog/review_graded_v1.csv 2>/dev/null | grep -A3 -E '"manual_(rows|bad_ids|changes)"'
venv/bin/python3 -m scripts.catalog.import_categories --manual docs/catalog/review_graded_v1.csv --apply 2>/dev/null | grep -E '"(mode|manual_rows)"'
```

**5b. Dude's 100 graded AI-only labels:**

```
# [Server — bash]
cd ~/scrp && venv/bin/python3 -m scripts.catalog.import_categories --manual docs/catalog/ai_audit_graded_v1.csv 2>/dev/null | grep -A3 -E '"manual_(rows|bad_ids|changes)"'
venv/bin/python3 -m scripts.catalog.import_categories --manual docs/catalog/ai_audit_graded_v1.csv --apply 2>/dev/null | grep -E '"(mode|manual_rows)"'
```

**Expect (dry run):**
- `"manual_rows": 150` for 5a, `100` for 5b;
- `"manual_bad_ids": []`;
- `manual_changes` mostly `update`, plus a few `insert` for barcodes that had no label. A barcode that is no longer live still gets its row.

**Expect (apply):** `"mode": "apply"` and the same `manual_rows`.

**Check:**

```
# [Server — bash]
sudo -u postgres psql xxl_super -tAc "SELECT detail, count(*) FROM item_categories WHERE source = 'manual' GROUP BY 1 ORDER BY 1"
```

**Expect:** `manual: ai_audit_graded_v1.csv|100` and `manual: review_graded_v1.csv|150`, plus any rows the console has written (`manual: admin console`).

**STOP if** `manual_bad_ids` is not `[]` in a dry run. Do not apply; paste the list.

## 6. Checks (browser, then server)

**6a. [Browser] The shop, signed out.** On `https://super.xxl.co.il`, search for במבה and open a product.
- Under the barcode: a line with the category path, then **הצעת עדכון קטגוריה**.
- Tap it: the note **האפשרות זמינה למשתמשים רשומים בלבד** appears, with התחברות · הרשמה links. No dialog opens.

**6b. [Browser] The shop, signed in** with the x@ test account:
- Tap the button: the dialog shows the current path and a searchable list. The current category is greyed out as נוכחית.
- Pick another category, add a short comment, send. The dialog closes and **תודה, ההצעה תיבדק** shows.
- Send again for the same product: **כבר שלחת הצעה למוצר הזה…**

**6c. [Browser] The console.** Open `https://admin.xxl.co.il` and sign in with 2FA.
- **לוח בקרה:** the new card קטגוריות shows `1` pending suggestion.
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

**STOP if** any page shows an error box, or the console shows a user's email or id. Paste a screenshot.

## 7. Afterwards

- Nothing to schedule. The queues read live data.
- A later import (`import_categories --apply`) skips every console and manual row; its dry run counts them as `protected`.
- **Accepting suggestions** writes the category you choose and marks every open suggestion of that product accepted. Undo it from the product's history; the suggestions stay accepted.

## 8. Rollback

**8a. API (server)**, if step 3 failed or the new endpoints misbehave. This goes back to the previous API; the table stays, unused:

```
# [Server — bash]
cd ~/scrp && git log --oneline -3
git checkout HEAD~1 -- api/ && sudo /usr/local/bin/xxl-restart.sh scrp-api && systemctl is-active scrp-api
```

**Expect:** `active`. Afterwards `git status` shows `api/` modified. Run `git checkout HEAD -- api/` to return to the release before the next pull.

**8b. Web (PC):** deploy the previous build from the commit before SU11A-57:

```
# [PC — PowerShell]
git checkout HEAD~1 -- web/; .\scripts\deploy_frontend.ps1; git checkout HEAD -- web/
```

**Expect:** `Done!`, and the hash check from step 4 matches the older build.

**8c. Table (server)**, only after 8a. This drops every suggestion:

```
# [Server — bash]
sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1 -c "BEGIN; DROP TABLE IF EXISTS category_suggestions; COMMIT;"
```

**8d. Manual rows from step 5 (server)**, only if they must go. Delete one file's rows, then let the normal import refill those barcodes with automated labels:

```
# [Server — bash]
sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1 -c "DELETE FROM item_categories WHERE source = 'manual' AND detail = 'manual: ai_audit_graded_v1.csv'"
cd ~/scrp && venv/bin/python3 -m scripts.catalog.import_categories --apply 2>/dev/null | grep -E '"mode"'
```

**Expect:** `DELETE 100`, then `"mode": "apply"`. Console changes are undone in the console, from each product's history (ביטול השינוי).
