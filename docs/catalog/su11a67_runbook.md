# SU11A-67 — category browse pages (API + web): runbook

Written 5 Nov 2026 for Dude. Design: `docs/catalog/su11a66_categories_browse_design.md`. Decisions of 5 Nov: the visibility rule, the "linked at 5" rule, the sorts, tobacco and the scope.

**What changes for users**
- **A new "קטגוריות" link in the header** of super.xxl.co.il, next to מבצעים, at every width.
  - `/categories` lists the departments with their item counts.
  - `/categories/<id>` shows a department, category or sub-category, with:
    - breadcrumbs;
    - the sub-categories as chips;
    - filters: city (the remembered city, as on search and promos), chain, sort (הנמכרים ביותר / הזול ביותר / לפי שם) and "רק במבצע";
    - the same product cards as search (promo badges, add-to-basket) and "טעינת עוד".
- **Shown labels:**
  - manual (any);
  - gs1 and rule at high or medium;
  - ai at high.

  Never shown: ai medium, and any low-confidence label. The promos page category filter and the product dialog keep the SU11A-57 rule.
- **Linking:** a category or sub-category is linked only with at least 5 visible items (per build). Its URL still answers below that.
- **Tobacco (D10.C05):** not in the tree, its page is 404, and it is left out of the D10 page. It still appears in normal search. Alcohol is shown normally.
- **The pages are noindex for now:** SEO pre-rendering, the sitemap and the search/compare category filter are SU11A-68.

**Prices:** nothing changes. The pages read the search build (`search_items`, `search_item_prices`). With a city, only the page's 30 items are priced live, through the same code as `/search`.

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
| DB | Nothing (no migration). It needs the su11a52 catalog tables (applied) and the SU11A-47 `search_item_prices` (applied). |
| API | `GET /categories/browse-tree`, `GET /categories/{id}/items` (`db/category_browse.py`, `api/routers/categories.py`). |
| nginx | `deploy/nginx/xxl-ratelimit-api.conf`: `/categories/<id>/items` in xxl_heavy (+ xxl_api), `/categories/browse-tree` in xxl_api. |
| Web | Header link, `/categories` routes (a lazy chunk, about 11 kB). The main chunk grows by 0.45 kB. |

---

## 1. Quiet-time check

**[Server — bash]**

```
date '+%H:%M'; systemctl show -p ActiveState --value scrp-cron; systemctl show -p ActiveState --value scrp-search-items
```

**Expect:**
- a time outside 04:00–04:30, 14:25–15:00, and 10:00 until the cron finishes;
- then `inactive` twice.

**STOP if** either reads `activating`. Wait until both read `inactive`.

## 2. Pull

**[Server — bash]**

```
cd ~/scrp && git pull origin main && git log --oneline -3
```

**Expect:** one of the top lines is `feat: SU11A-67 category browse pages (API + web)`.
**STOP if** the pull fails.

## 3. Restart the API and wait for health

**[Server — bash]**

```
sudo /usr/local/bin/xxl-restart.sh scrp-api && for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] && break; sleep 1; done; curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:8000/health
```

**Expect:** `health 200`.
**STOP if** it is not `200`. Then paste `sudo journalctl -u scrp-api -n 40 --no-pager`.

## 4. curl checks (local, before nginx)

These go to gunicorn directly (`127.0.0.1:8000`), so no rate limit applies yet.

**[Server — bash]**

```
API=http://127.0.0.1:8000
curl -s -o /tmp/su67.json -w 'tree %{http_code} %{time_total}s %{size_download}B\n' $API/categories/browse-tree
curl -s -o /tmp/su67.json -w 'tree-warm %{http_code} %{time_total}s\n' $API/categories/browse-tree
python3 -c "import json; t=json.load(open('/tmp/su67.json')); d=t['departments']; print(len(d), 'departments,', t['total'], 'items,', sum(len(x['children']) for x in d), 'linked categories, tobacco listed:', 'D10.C05' in json.dumps(t))"
it() { for i in 1 2 3; do curl -s -G -o /tmp/su67.json -w "$1 %{http_code} %{time_total}s " "${@:2}"; python3 -c "import json; r=json.load(open('/tmp/su67.json')); print(len(r['items']), 'items, total', r['total'], 'exact', r['total_exact'], 'more', r['has_more'])"; done; }
it big-no-city      $API/categories/D15.C04/items
it big-city         $API/categories/D15.C04/items --data-urlencode 'city=תל אביב-יפו'
it cheese-city      $API/categories/D02.C02/items --data-urlencode 'city=תל אביב-יפו' --data-urlencode 'sort=cheapest'
it dept-promo-city  $API/categories/D02/items --data-urlencode 'city=חיפה' --data-urlencode 'on_promo=true'
curl -s -o /dev/null -w 'tobacco %{http_code}\n' $API/categories/D10.C05/items
curl -s -G -o /dev/null -w 'junk-city %{http_code}\n' $API/categories/D02/items --data-urlencode 'city=עיר שאין'
curl -s -o /dev/null -w 'offset-2001 %{http_code}\n' "$API/categories/D02/items?offset=2001"
curl -s -o /dev/null -w 'limit-61 %{http_code}\n' "$API/categories/D02/items?limit=61"
curl -s -o /dev/null -w 'unknown %{http_code}\n' $API/categories/D99/items
rm -f /tmp/su67.json
```

**Expect:**
- **`tree`:** `200`, under about 1 s cold and about 100 kB at most. `tree-warm` is under 0.05 s (cached).
- **The summary line:** `16 departments, <about 116,000> items, <about 150> linked categories, tobacco listed: False`. The production coverage of 5 Nov had 132,451 live items with 88% usable. The visible count is lower, because ai medium is left out.
- **`big-no-city`:** three lines `200`, `30 items`, `exact True`, `more True`, each **under 0.3 s**. The first can be slower (a cold cache).
- **`big-city`, `cheese-city`, `dept-promo-city`:** `200`, `30 items` (fewer is fine for the promo line), each **under 1.5 s**. `exact False` is normal in a city: the total is then the category's nationwide count, shown as "כ-N".
- **The rest:**
  - `tobacco 404`;
  - `junk-city 422`;
  - `offset-2001 422`;
  - `limit-61 422`;
  - `unknown 404`.

**Bench** (synthetic, production-sized: 7.9M prices, 73k live items; largest category 4,256 visible items):

| Request | Time |
|---|---|
| no city | 19–260 ms |
| Tel Aviv, page 1 | 0.18–0.65 s |
| small town, page 1 | 0.12–0.43 s |
| Tel Aviv, offset 1,980 | 1.2–1.3 s |
| browse tree, cold | 80 ms |

**STOP if:**
- any line is `500` or `503`;
- `tobacco listed: True`;
- a no-city time is over 0.3 s on all three tries;
- a city time is over 1.5 s on all three tries.

Then also paste `sudo journalctl -u scrp-api --since "10 min ago" --no-pager | grep -E "Traceback|timeout" | tail -5`.

## 5. nginx: the two new locations

**5a. Back up the installed snippet, outside `/etc/nginx/snippets`** (so nginx never includes the copy)

**[Server — bash]**

```
sudo mkdir -p /var/backups/xxl-nginx && sudo cp -p /etc/nginx/snippets/xxl-ratelimit-api.conf /var/backups/xxl-nginx/xxl-ratelimit-api.conf.bak-su11a67-$(date +%F-%H%M) && ls -l /var/backups/xxl-nginx/
```

**Expect:** the listing shows the new `…bak-su11a67-<date>` file next to the older backups.

**5b. Compare (nothing changes yet)**

**[Server — bash]**

```
diff /etc/nginx/snippets/xxl-ratelimit-api.conf ~/scrp/deploy/nginx/xxl-ratelimit-api.conf
```

**Expect:** only the SU11A-67 additions (lines starting with `>`):
- the comment lines `#   SU11A-67:` and `#   /categories/<id>/items …`;
- the `location ~ ^/categories/[A-Za-z0-9.]+/items$` block;
- the `location = /categories/browse-tree` block with its comment.

**STOP if** the diff shows any other difference (the installed file was edited by hand). Paste it.

**5c. Install and test**

**[Server — bash]**

```
sudo cp ~/scrp/deploy/nginx/xxl-ratelimit-api.conf /etc/nginx/snippets/xxl-ratelimit-api.conf && sudo nginx -t
```

**Expect:** `syntax is ok` and `test is successful`.

**STOP if** not. Restore the backup: `sudo cp -p /var/backups/xxl-nginx/xxl-ratelimit-api.conf.bak-su11a67-<date> /etc/nginx/snippets/xxl-ratelimit-api.conf && sudo nginx -t`. Do **not** reload.

**5d. Reload and verify**

**[Server — bash]**

```
sudo systemctl reload nginx && systemctl is-active nginx && sudo nginx -T 2>/dev/null | grep -nA4 "location ~ ^/categories\|location = /categories/browse-tree"
API=https://api-super.xxl.co.il
curl -s -o /dev/null -w 'public-tree %{http_code} %{time_total}s\n' $API/categories/browse-tree
curl -s -o /dev/null -w 'public-items %{http_code} %{time_total}s\n' $API/categories/D15.C04/items
for i in $(seq 1 16); do curl -s -o /dev/null -w '%{http_code} ' $API/categories/D15.C04/items; done; echo
```

**Expect:**
- `active`, then the two blocks: the regex one with `zone=xxl_heavy` and `zone=xxl_api`, the browse-tree one with `zone=xxl_api` only, and both with `include snippets/xxl-api-proxy.conf`;
- `public-tree 200` and `public-items 200`;
- the burst line: mostly `200`, with some `429` near the end (2 r/s, burst 10). All `200` is also fine on a slow connection.

**STOP if** `public-items` is `404` or `502` (the proxy include is missing). Then roll back nginx (step 9).

## 6. Web deploy, with the guard

The API must already run SU11A-67 (step 3). Run it from the home PC (it has `web/.env.production`).

**[PC — PowerShell]**

```
git pull origin main; .\scripts\deploy_frontend.ps1
```

**Expect:** `build OK: …`, the upload, `MATCH`, then a green `Done!`.
**STOP if** you see a red line or `MISMATCH`.

## 7. Browser checks

**[Browser]** https://super.xxl.co.il (a normal window, signed in or not).

1. **Header:** "קטגוריות" is next to "🔥 מבצעים". On a phone width it is still there (the row may wrap).
2. **Departments:** "קטגוריות" opens a grid of departments, each with a count and up to four category names. There is no tobacco anywhere, and alcohol is there.
3. **A big category:** open כלי בית → the tableware category (D15.C04, `/categories/D15.C04`).
   - Change the sort to "הזול ביותר": the cheapest prices come first. "לפי שם" sorts by name.
   - Pick a chain: every card shows only that chain.
   - Tick "רק במבצע": cards carry a promo badge (the badges load a moment after the cards).
   - Press "טעינת עוד": 30 more cards; no duplicates.
   - The URL keeps the filters (`?city=…&chain=…&sort=…&promo=1`); Back restores the previous view.
4. **Sub-category chips:** open the cheese category (`/categories/D02.C02`). It shows chips for its sub-categories (only those with 5+ items), and each chip opens its page. The breadcrumbs lead back.
5. **Add to basket:** on any category page press "הוסף לסל" on a card. The basket count in the header goes up, and the basket drawer lists the item.
6. **Keyboard:**
   - Tab from the header link through the breadcrumbs, the chips, the four filters and the cards, with a visible focus ring at each stop.
   - Enter on a chip or breadcrumb opens it; Space ticks "רק במבצע".
   - Screen-reader names: the filters are labelled עיר / רשת / מיון / רק במבצע.
7. **A bad id** (`/categories/D10.C05` or `/categories/xyz`): "הקטגוריה לא נמצאה." with a link back.

**STOP if:**
- a page shows an error box instead of cards;
- a tobacco item or department link appears;
- add-to-basket does nothing.

## 8. Record

Paste the step 4 lines into the chat. The handoff records the production timings in the SU11A-67 entry.

## 9. Rollback

**nginx only:**

**[Server — bash]**

```
ls /var/backups/xxl-nginx/ && sudo cp -p /var/backups/xxl-nginx/xxl-ratelimit-api.conf.bak-su11a67-<date> /etc/nginx/snippets/xxl-ratelimit-api.conf && sudo nginx -t && sudo systemctl reload nginx && systemctl is-active nginx
```

Without the two blocks the endpoints fall under `location /`: they work, in the general zone only.

**Everything:**

**[PC — PowerShell]**

```
git pull origin main; git revert --no-edit <the SU11A-67 feat commit>; git push origin main; .\scripts\deploy_frontend.ps1
```

**[Server — bash]**

```
cd ~/scrp && git pull origin main && sudo /usr/local/bin/xxl-restart.sh scrp-api
```

- The header link and pages disappear, and the two endpoints answer 404.
- Nothing in the database changed.
