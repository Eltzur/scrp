# SU11A-77 — app notice API + admin screen, has_image on results: runbook

Written 11 Nov 2026 for Dude.

**What changes**
- **New table `app_announcements`** (`db/migrations/su11a77_announcements.sql`): one row per scope (`ios`, `android`, `both`), all **off**.
- **New public endpoint `GET /announcements/active?platform=ios|android`:**
  - the active notice `{id, version, title, body}`, or **204** when none;
  - no auth, no identifiers, cached 5 minutes in the API process;
  - unknown platform → 400.
- **New admin endpoints** `/admin/announcements` (list, save, on / off): admin + 2FA, and every write goes to the audit log. The server rejects links, markup and, for iPhone / both, the words בהרצה / בטא / beta / ניסיון / trial / test version.
- **New admin tab "הודעות לאפליקציה".**
- **`has_image`** (true / false) on every product in `/search`, `/compare` and `/categories/{id}/items` (and `/product/{barcode}`):
  - it comes from one cached listing of the image folder (every 10 minutes);
  - the website's list view no longer asks for an image a product does not have;
  - older apps ignore the new field.
- **The notice stays OFF until app 1.2.4 is live (SU11B-8).** No app reads it before then.

**Production impact**
- One new table (additive, no existing table changed).
- One API restart.
- One web deploy.
- **No nginx change:** `/announcements/active` falls under the general `location /` zone, not the heavy group.
- No price or user data.

**How to run it**
- Run the steps in order. Each step names where it runs:
  - **[Server — bash]:** `ssh dude@185.229.226.190`, interactive, in `~/scrp`;
  - **[PC — PowerShell]:** in `C:\scrp` on the **home PC** (the one with `web/.env.production`);
  - **[Browser].**
- If a step says STOP, paste the output to the chat and do not improvise a fix.
- Nothing here prints `.env` or a secret.

---

## 1. Quiet-time check

**[Server — bash]**

```
date '+%H:%M'; systemctl show -p ActiveState --value scrp-cron; systemctl show -p ActiveState --value scrp-search-items; systemctl show -p ActiveState --value scrp-stats
```

**Expect:**
- a time outside 03:30–03:45, 04:00–04:30, 14:25–15:00, and 10:00 until the cron finishes;
- then `inactive` three times.

**STOP if** any reads `activating`.

## 2. Pull and the new tests

**[Server — bash]**

```
cd ~/scrp && git pull origin main && git log --oneline -3 && venv/bin/python3 -m pytest tests/test_announcements_su11a77.py -q -p no:cacheprovider 2>&1 | tail -1
```

**Expect:**
- one of the top lines is `feat: SU11A-77 app notice API + admin, has_image on results`;
- the last line is `60 passed`.

**STOP if** the pull fails or a test fails.

## 3. Schema backup, then the migration (twice: the second run changes nothing)

**[Server — bash]**

```
mkdir -p ~/backups && sudo -u postgres pg_dump --schema-only xxl_super | gzip > ~/backups/pre-SU11A-77-schema-$(date +%Y%m%dT%H%M%S).sql.gz && ls -l ~/backups/pre-SU11A-77-schema-*.sql.gz
cat ~/scrp/db/migrations/su11a77_announcements.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
cat ~/scrp/db/migrations/su11a77_announcements.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
sudo -u postgres psql xxl_super -Atc "SELECT platform, active, version, length(title), length(body) FROM app_announcements ORDER BY id; SELECT tableowner FROM pg_tables WHERE tablename = 'app_announcements'"
```

**Expect:**
- `ls` shows one `.sql.gz` file larger than a few KB;
- each migration run prints `BEGIN`, `DO`, `CREATE TABLE` (the second time: a NOTICE that it already exists), `INSERT 0 3` (the second time `INSERT 0 0`), `ALTER TABLE`, `COMMIT`;
- then the rows `ios|f|0|0|0`, `android|f|0|0|0`, `both|f|0|0|0`, and the owner `scrp_app`.

**STOP if:**
- `admin_audit is missing` appears;
- any `ERROR` appears;
- the dump file is empty.

## 4. Restart the API and check it

**[Server — bash]**

```
sudo /usr/local/bin/xxl-restart.sh scrp-api && for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] && break; sleep 1; done
curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:8000/health
curl -s -o /dev/null -w 'ios %{http_code}\n' 'http://127.0.0.1:8000/announcements/active?platform=ios'
curl -s -o /dev/null -w 'android %{http_code}\n' 'http://127.0.0.1:8000/announcements/active?platform=android'
curl -s -w ' %{http_code}\n' 'http://127.0.0.1:8000/announcements/active?platform=web'
curl -s -w ' %{http_code}\n' http://127.0.0.1:8000/admin/announcements
curl -s 'http://127.0.0.1:8000/search?q=%D7%97%D7%9C%D7%91&limit=20' | python3 -c 'import json,sys; d=json.load(sys.stdin); v=[i["product"].get("has_image") for i in d["items"]]; print("search", len(v), "has_image true", v.count(True), "false", v.count(False), "missing", sum(x is None for x in v))'
curl -s 'http://127.0.0.1:8000/categories/D02/items?limit=20' | python3 -c 'import json,sys; d=json.load(sys.stdin); v=[i["product"].get("has_image") for i in d["items"]]; print("category", len(v), "has_image true", v.count(True), "false", v.count(False), "missing", sum(x is None for x in v))'
```

**Expect:**
- `health 200`;
- `ios 204` and `android 204` (every notice is off);
- `{"code":"unknown_platform"} 400`;
- `{"code":"admin_required"} 403`;
- `search 20 has_image true N false M missing 0`, with N + M = 20 and both usually above 0;
- the same for `category`.

**STOP if:**
- health is not 200;
- ios or android is not 204;
- `missing` is above 0. The API cannot read the image folder: check that `gs1_images_dir` (or `~/gs1_images`) is the same folder `/product/<barcode>/image` serves. Do not change it here.

**If needed:** to undo the API part, `git checkout` the previous commit's `api/` and `db/announcements.py` and restart (the same form as the SU11A-58 runbook's undo). To undo the table, run the commented ROLLBACK block at the end of the migration file. No other table depends on it.

## 5. nginx

Nothing to do. The new public endpoint is under the general `location /` limit (`deploy/nginx/xxl-ratelimit-api.conf`). It is cheap (one tiny table, at most every 5 minutes per worker), so it is not in the `xxl_heavy` group.

## 6. Web deploy, with the guard

**[PC — PowerShell]**

```
git pull origin main; .\scripts\deploy_frontend.ps1
```

**Expect:** `build OK: …`, the sitemap lines, the upload, `MATCH` and a green `Done!`.
**STOP if** you see a red line or `MISMATCH`.

## 7. Browser checks

**[Browser]**

1. **The new tab:** https://admin.xxl.co.il → **הודעות לאפליקציה**.
   - Three cards: iPhone, Android, שתי הפלטפורמות. Each reads **כבויה**, version 0, and shows the rules.
   - The iPhone and both-platforms cards also show the Apple 2.2 rule.
2. **The server's rules** (on the iPhone card; nothing is saved when it refuses):
   - title `גרסת בטא` + any text → Save → "ב-iPhone אסור להשתמש במילה "בטא" (Apple 2.2). (בכותרת)";
   - text with `https://example.com` → "אסור לכלול קישור או כתובת.";
   - a valid title and text → "נשמר (גרסה 1).", and the preview shows them.
3. **Audit log:** **יומן פעולות** shows `announcement.update` for `ios`.
4. **Leave every notice OFF.** Do not switch any card on until app 1.2.4 is live (SU11B-8); the automated tests cover the switch.
5. **List view without needless images:**
   - on https://super.xxl.co.il search `חלב`, then choose **רשימה**;
   - in DevTools → Network, filter `image`;
   - requests appear only for rows that show a picture. Rows with the grey placeholder icon make **no** request.

**STOP if:**
- the tab is missing;
- a forbidden word or a link is saved;
- the list view still requests images for placeholder rows.

**If needed:** the web change is undone by deploying the previous commit the same way. The website then ignores `has_image` and asks for every row's image, as before.
