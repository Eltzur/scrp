# SU11A-62 — promo search relevance, promo list cleanup, admin pin coverage (+ SU11A-63 H2): runbook

Written 5 Nov 2026 for Dude.

**What changes for users (super.xxl.co.il/promos)**
- **Search shows real matches first.** Searching "שמנת" used to list snacks such as "בייגלה שטוחים טעם שמנת בצל" ahead of cream, because the list was sorted only by discount. Now the order is:
  1. the promotion's own description matches;
  2. the product name starts with the term;
  3. the name contains it;
  4. the term appears only in a flavour phrase ("טעם X", "בטעם X", "בטעמי X").

  Within each level the order is the chosen sort (default הנחה גדולה). A product labelled in a category the term names (for example שמנת → "שמנת וקצפת") moves half a level up. A low-confidence label counts only when the named category is a department (the SU11A-57 rule).
- **The search now also matches the promotion's description,** not only the product name.
- **The term is marked** in the product name.
- **On מבצעים מקודמים, a search card shows the best-matching product,** with "ועוד N מוצרים תואמים" when more of the promotion's products match.
- **Search text under 2 characters** (or only `%`, `_` or spaces) is no search. The page stays on its start screen with "הקלידו לפחות 2 אותיות כדי לחפש".
- **No "-0%" cards** (the promo price rounds to the shelf price).
- **No coupon or spend-threshold cards** (for example "קופון איש 50 מעל 249" or "מעל ₪100") unless the row has a real per-item discount.

Both cleanup rules apply to the promo lists only: `/promos/list`, `/promos/grouped`, `/promos/promoted`.

**What changes for admins (admin.xxl.co.il → מבצעים)**
- **Search results** rank the same way, and the card's example is the best-matching product ("מוצר תואם:", term marked, "ועוד N מוצרים תואמים").
- **Coverage on search results and on מקודמים:** "מוצג ב-N ערים", with the list on expand.
  - A red warning when the promotion shows in no city.
  - An amber warning when it does not show in the **check city** ("עיר לבדיקת הקידום", at the top of the tab).
- **The check city** defaults to the admin's last choice in this browser, else תל אביב-יפו. The console runs on its own address, so it cannot read the city remembered on the shop.

**Security (SU11A-63 H2):**
- Promo search text is escaped before it reaches LIKE, in the public endpoints and in the admin search. `%` and `_` now match literally.
- Search text under 2 real characters is no search.
- `q` is limited to 100 characters (422 above that).

**Unfiltered lists:** `/promos/list` and `/promos/grouped` with no chain, category, search text or branch now return `[]` at once, without a DB query. Before, they took about 15.2 s and returned 503 on production. A city alone is still only a scope. `/promos/list?q=%25` is unfiltered too.

**Prices:** nothing that prices changes: search, compare, basket, `/product`, `/promos/bulk`, promo badges, the search build and `/promos/today`. The SU11A-58 byte-identical pricing test passes unchanged.

**How to run it**
- Run the steps in order. Each step names where it runs:
  - **[Server — bash]:** `ssh dude@185.229.226.190`, interactive, in `~/scrp`. Type Hebrew only there (CLAUDE.md rule 11); the commands below URL-encode it.
  - **[PC — PowerShell]:** PowerShell in `C:\scrp`, on the **home PC** (the one with `web/.env.production`).
  - **[Browser].**
- If a step says STOP, paste the output to the chat and do not improvise a fix.
- Nothing here prints `.env`, a token or an email address.
- **Run steps 3 and 6 close together.** In between, the old web page is live against the new API. Two effects:
  - Its search shows the new order and cleanup, with no marking.
  - A one-letter search shows "אין מבצעים תואמים" instead of the hint.

**What it deploys**

| Part | What changes |
|---|---|
| DB | Nothing (no migration). The category boost reads `categories` / `item_categories` (su11a52); without them there is no boost. |
| API | `/promos/list`, `/promos/grouped`, `/promos/promoted`: relevance order, description match, cleanup rules, escaped `q` (max 100). `/promos/list` and `/promos/grouped` return `[]` when unfiltered. `/admin/promos/search`: relevance, best-matching `sample`, `matches`, `cities`. `/admin/promos/curation`: `cities` on pins. |
| Web | The promos page and the admin מבצעים tab, as above. |
| nginx | Nothing. The strict rate-limit group for the promo endpoints is SU11A-64. |

---

## 1. Quiet-time check

**[Server — bash]**

```
date '+%H:%M'; systemctl show -p ActiveState --value scrp-cron
```

**Expect:** a time outside 04:00–04:30, 14:25–15:00 and 10:00 until the cron finishes, then `inactive`.
**STOP if** the second line is `activating` (the daily load is running). Wait until it reads `inactive`.

## 2. Pull

**[Server — bash]**

```
cd ~/scrp && git pull origin main && git log --oneline -3
```

**Expect:** one of the top lines is `feat: SU11A-62 promo search relevance, promo list cleanup, pin coverage (SU11A-63 H2)`.
**STOP if** the pull fails.

## 3. Restart the API and wait for health

**[Server — bash]**

```
sudo /usr/local/bin/xxl-restart.sh scrp-api && for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] && break; sleep 1; done; curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:8000/health
```

**Expect:** `health 200`.
**STOP if** it is not `200`. Then paste `sudo journalctl -u scrp-api -n 40 --no-pager`.

## 4. Timings (three times each)

Replace `D02` with the dairy department id if it differs (`curl -s https://api-super.xxl.co.il/categories/tree | python3 -c "import json,sys; [print(x['id'], x['name_he']) for x in json.load(sys.stdin)['nodes'] if x['level'] == 1]"`).

**[Server — bash]**

```
DEPT=D02; API=https://api-super.xxl.co.il
t() { for i in 1 2 3; do curl -s -G -o /tmp/su62.json -w "$1 %{http_code} %{time_total}s " "${@:2}"; python3 -c "import json; print(len(json.load(open('/tmp/su62.json'))), 'rows')"; done; }
t list-unfiltered  $API/promos/list
t grouped-unfilt   $API/promos/grouped
t list-q-pct       $API/promos/list --data-urlencode 'q=%'
t list-q-space     $API/promos/list --data-urlencode 'q= '
t grouped-q-pct    $API/promos/grouped --data-urlencode 'q=%'
t list-city-dept   $API/promos/list --data-urlencode 'city=תל אביב-יפו' --data-urlencode "category=$DEPT"
t list-city-q      $API/promos/list --data-urlencode 'city=תל אביב-יפו' --data-urlencode 'q=שמנת'
t list-all-q       $API/promos/list --data-urlencode 'q=שמנת'
t promoted-city    $API/promos/promoted --data-urlencode 'city=תל אביב-יפו'
rm -f /tmp/su62.json
```

**Expect** (every line `200`):
- **`list-unfiltered`, `grouped-unfilt`, `list-q-pct`, `list-q-space`, `grouped-q-pct`:** `0 rows` and under 0.1 s. Before, these took about 15.2 s and returned 503.
- **`list-city-dept`:** under 1.5 s (SU11A-60 measured 0.24–0.5 s).
- **`list-city-q`, `list-all-q`:** under 3 s. The search now also reads the promotion description and ranks the matches.
- **`promoted-city`:** under 0.3 s.

**STOP if:**
- any line is `503`;
- any of the first five is not `0 rows`;
- `list-city-q` or `list-all-q` is above 5 s.

Then also paste:

```
sudo journalctl -u scrp-api --since "10 min ago" --no-pager | grep -E "query timeout|Traceback" | tail -5
```

## 5. Before / after report (read-only)

This prints the top 10 for שמנת, חלב, במבה, קפה and חומוס in Tel Aviv and in all cities. "Before" is the pre-SU11A-62 list; "after" is the new one. Then it prints how many rows each cleanup rule removes, with 10 examples each.

Part 2 reads every active promo once (about 1 minute). The session is READ ONLY, with a 120 s statement limit.

**[Server — bash]**

```
cd ~/scrp && ( ulimit -v 2000000; set -a; source .env; set +a; venv/bin/python3 -m scripts.su11a62_promo_report ) 2>&1 | tee ~/su11a62_report.txt | tail -80
```

**Expect:**
- For each term and scope, a `before:` and an `after:` list of up to 10 lines: `chain | product | % | description`.
- In the `after:` lists, products whose name starts with the term come first; for שמנת, real cream products ahead of "טעם שמנת" snacks.
- Then `== cleanup` with:
  - `rows_before_cleanup`: hundreds of thousands;
  - `no_discount` and `coupon`: the rows each rule removes;
  - 10 example lines each.

**STOP if:**
- it fails with `statement timeout` or `MemoryError`;
- an `after:` list is empty where `before:` was not;
- `no_discount` or `coupon` is more than a third of `rows_before_cleanup`.

**Then:** paste the whole of `~/su11a62_report.txt` (it holds no user data) into the chat. The handoff records these numbers.

## 6. Web deploy, with the guard

Only from the home PC (it has `web/.env.production`).

**[PC — PowerShell]**

```
git pull origin main; .\scripts\deploy_frontend.ps1
```

**Expect:** `build OK: …`, the upload, `MATCH`, then a green `Done!`.
**STOP if** you see a red line or `MISMATCH`.

## 7. Browser checks

**7a. The promos page search**

**[Browser]**
1. Open https://super.xxl.co.il/promos?city=תל%20אביב-יפו.
2. Type `שמנת` in the search box.

**Expect:**
- **Real cream products first** (שמנת מתוקה, שמנת חמוצה, שמנת לבישול…), the word שמנת marked in each name.
- **Flavour products** ("טעם שמנת בצל", "בטעמי שמנת") only after them.
- **No card reads "-0%".**
- **No card is a coupon / "מעל ₪…" deal** without a per-item price.

**7b. Too short**

**[Browser]** Replace the text with `%`, then with a single letter.

**Expect:** the start screen ("איזה מבצעים מעניינים אתכם?") with "הקלידו לפחות 2 אותיות כדי לחפש", and no list.

**7c. Admin search**

**[Browser]** In https://admin.xxl.co.il → מבצעים → חיפוש, search `שמנת` with the chain אושר עד.

**Expect:**
- The first cards are promotions on real cream products, each showing "מוצר תואם:" with the cream product (שמנת marked).
- The bagel / Tan Chips / Jelly Land promotions appear only further down, with the cream-flavour product as their example.
- Each card shows "מוצג ב-N ערים" (expand it for the list).

**7d. Pin coverage**

**[Browser]**
1. At the top of the מבצעים tab, set "עיר לבדיקת הקידום" to תל אביב-יפו.
2. Pin one promotion from the search with an end date a few days ahead, choosing one whose coverage does not list תל אביב-יפו (for example a Carrefour branch outside Tel Aviv).
3. Open מקודמים.

**Expect:**
- The pin shows "מוצג ב-N ערים" and the amber "לא מוצג בתל אביב-יפו".
- Changing the check city to one in its list removes the amber line.
- A pin whose promotion shows nowhere has the red "לא מוצג באף עיר" line.

**7e. Remove the test pin**

**[Browser]** מקודמים → הסרה on the test pin, then confirm.

**Expect:** the toast "הוסר"; the pin is gone from מקודמים.

## 8. Rollback

The server only pulls, so the revert is a commit made on the PC.

**8a. Revert commit**

**[PC — PowerShell]**

```
git pull origin main; git log --oneline -8
```

Note the hash of the `feat: SU11A-62 …` commit (`<HASH>`). Then:

**[PC — PowerShell]**

```
git revert --no-edit <HASH>; git push origin main
```

**Expect:** `1 file changed` or more, then the push.
**STOP if** the revert reports a conflict. Run `git revert --abort` and paste the output.

**8b. API**

**[Server — bash]**

```
cd ~/scrp && git pull origin main && sudo /usr/local/bin/xxl-restart.sh scrp-api && for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] && break; sleep 1; done; curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:8000/health
```

**Expect:** `health 200`.

**8c. Web**

**[PC — PowerShell]** (the home PC)

```
.\scripts\deploy_frontend.ps1
```

**Expect:** `MATCH`, `Done!`.

**Note:** a rollback brings back two problems:
- the SU11A-60 cap on an unfiltered list, which still scans every promo (15 s, 503);
- SU11A-63 H2.

---

## Reference

- Code:
  - `db/query.py`:
    - `clean_promo_q`, `PromoSearch`, `promo_match_sql`;
    - the cleanup rules `CLEANUP_RULES`;
    - the `coverage` / `cleanup_*` layouts of `_fetch_grouped_promos_raw`;
    - `fetch_promo_coverage`, `count_promo_list_cleanup`.
  - `api/categories.py promo_search` (the category boost).
  - `api/routers/promos.py _unfiltered`.
  - `api/routers/admin_promos.py search_promos` / `list_curation`.
  - `scripts/su11a62_promo_report.py`.
- Web:
  - `web/src/components/Highlight.tsx`;
  - `web/src/utils/promosView.ts promoSearchText`;
  - `web/src/pages/PromosPage.tsx`;
  - `web/src/admin/screens/PromosScreen.tsx`, `promos/PromoCard.tsx`, `promos/CurationList.tsx`.
- Tests:
  - `tests/test_promo_search_su11a62_pg.py`;
  - updated `tests/test_promos_page_su11a60_pg.py` and `tests/test_promo_curation_su11a58_pg.py` (an unfiltered list is now empty);
  - `web/scripts/promos-page.test.mjs`.
