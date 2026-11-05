# SU11A-68 — categories phase 1b: category search, category filter on search, city "cheapest", SEO, home link: runbook

Written 6 Nov 2026 for Dude. Follows SU11A-67 (deployed 5 Nov). No migration and no nginx change: `q` and the city sort use the existing `/categories/<id>/items` location (xxl_heavy). `/categories/dominant` and the `category` parameter on `/search` and `/compare` fall under the locations those paths already have.

**What changes for users**
- **Category pages** (`/categories/<id>`):
  - **A search box "חיפוש ב<קטגוריה>"** filters the category by text, with the same matcher as the search page (search v2). The best text matches come first, then the chosen sort. It needs 2 real characters; `%` alone is ignored. The text stays in the URL (`?q=`).
  - **With text, a link "חיפוש "<q>" בכל האתר"** opens the search page with that text and the category preselected.
  - **"הזול ביותר" in a city now orders by the city's own lowest price**, the price the card shows. Before, it used the nationwide cheapest.
- **Search page:**
  - A "קטגוריה" select (department › category › sub-category; tobacco is not listed).
  - A button **"הצג רק ב<קטגוריה>"** when most results share one category.
  - Without a category, search is exactly as before.
- **Home page:** a "קטגוריות" section with the departments, below the search box (start screen only).
- **SEO:**
  - The category pages are indexable, with:
    - the title "<קטגוריה> — השוואת מחירים בכל הרשתות | SUPER XXL";
    - a Hebrew description;
    - a canonical without parameters;
    - a breadcrumb JSON-LD.
  - A filtered view (city / chain / sort / רק במבצע / text) is noindex.
  - The deploy writes the linked category URLs into `sitemap-super.xml` from the live browse tree. If the API cannot be read, the deploy keeps the committed `/categories` + 16 departments.
  - Pre-rendering is not in this session (follow-up).

**Prices:** nothing changes. The city sort reads the same price rows as the card. The category filter on search only removes items; it never changes a price or the order of the rest.

**How to run it**
- Run the steps in order. Each step names where it runs:
  - **[Server — bash]:** `ssh dude@185.229.226.190`, interactive, in `~/scrp`. Type Hebrew only there (CLAUDE.md rule 11).
  - **[PC — PowerShell]:** in `C:\scrp` on the **home PC** (the one with `web/.env.production`).
  - **[Browser].**
- If a step says STOP, paste the output to the chat and do not improvise a fix.
- Nothing here prints `.env`, a token or an email address.

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

**Expect:** one of the top lines is `feat: SU11A-68 category search, category filter on search, city cheapest, category SEO`.
**STOP if** the pull fails.

## 3. Restart the API and wait for health

**[Server — bash]**

```
sudo /usr/local/bin/xxl-restart.sh scrp-api && for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] && break; sleep 1; done; curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:8000/health
```

**Expect:** `health 200`.
**STOP if** it is not `200`. Then paste `sudo journalctl -u scrp-api -n 40 --no-pager`.

## 4. curl checks (local)

**[Server — bash]**

```
API=http://127.0.0.1:8000
it() { for i in 1 2 3; do curl -s -G -o /tmp/su68.json -w "$1 %{http_code} %{time_total}s " "${@:2}"; python3 -c "import json; r=json.load(open('/tmp/su68.json')); print(len(r['items']), 'items, total', r['total'], 'q', r.get('q'))"; done; }
it q-no-city   $API/categories/D02/items --data-urlencode 'q=גבינה'
it q-tlv       $API/categories/D02/items --data-urlencode 'q=גבינה' --data-urlencode 'city=תל אביב-יפו'
it q-percent   $API/categories/D02/items --data-urlencode 'q=%'
curl -s -G -o /dev/null -w 'q-101 %{http_code}\n' $API/categories/D02/items --data-urlencode "q=$(python3 -c 'print("א"*101)')"
curl -s -G -o /tmp/su68.json -w 'cheapest-tlv %{http_code} %{time_total}s\n' $API/categories/D02.C02/items --data-urlencode 'city=תל אביב-יפו' --data-urlencode 'sort=cheapest'
python3 -c "import json; r=json.load(open('/tmp/su68.json')); p=[x['cheapest_price'] for x in r['items']]; print('first prices', p[:8], 'sorted:', p == sorted(p))"
curl -s -G -o /dev/null -w 'cheapest-tlv-again %{http_code} %{time_total}s\n' $API/categories/D02.C02/items --data-urlencode 'city=תל אביב-יפו' --data-urlencode 'sort=cheapest' --data-urlencode 'offset=30'
curl -s -G -o /tmp/su68.json -w 'search-cat %{http_code} %{time_total}s ' $API/search --data-urlencode 'q=חלב' --data-urlencode 'category=D02.C02'
python3 -c "import json; r=json.load(open('/tmp/su68.json')); print(len(r['items']), 'items, total', r['total_matches'])"
curl -s -G -o /tmp/su68.json -w 'compare-cat %{http_code} %{time_total}s ' $API/compare --data-urlencode 'q=חלב' --data-urlencode 'category=D02.C02' --data-urlencode 'city=תל אביב-יפו'
python3 -c "import json; r=json.load(open('/tmp/su68.json')); print(len(r['items']), 'items'); open('/tmp/su68.codes','w').write('\n'.join(i['product']['item_code'] for i in r['items']))"
for c in $(head -5 /tmp/su68.codes); do curl -s $API/items/$c/category | python3 -c "import json,sys; d=json.load(sys.stdin); print(' ', d['item_code'], d['category_id'])"; done
curl -s -G -o /dev/null -w 'search-tobacco %{http_code}\n' $API/search --data-urlencode 'q=סיגריות' --data-urlencode 'category=D10.C05'
curl -s -G -o /dev/null -w 'search-nocat %{http_code} %{time_total}s\n' $API/search --data-urlencode 'q=חלב'
rm -f /tmp/su68.json /tmp/su68.codes
```

**Expect:**
- **`q-no-city`:** `200`, `q גבינה`, each **under 0.3 s** after the first.
- **`q-tlv`:** `200`, each **under 1.5 s**.
- **`q-percent`:** `200` and `q None`: ignored, the same as no text.
- **`q-101`:** `422`.
- **`cheapest-tlv`:** `200`, under 1.5 s (bench: 0.76–0.88 s cold), and `sorted: True`: the first items are the city's cheapest.
- **`cheapest-tlv-again`** (the next page): well under 0.3 s; the walk is cached for 5 minutes.
- **`search-cat` / `compare-cat`:** `200`. The five barcodes printed under `compare-cat` all have a `category_id` that starts with `D02.C02`.
- **`search-tobacco`:** `422`.
- **`search-nocat`:** `200`, as fast as before the deploy.

**Bench** (synthetic, 7.9M prices, 73k live items):

| Request | Time |
|---|---|
| category + q, no city | 30–137 ms |
| category + q, Tel Aviv | 110–454 ms |
| city cheapest, cold | 0.76–0.88 s |
| city cheapest, next page | 0.1 s |
| search v2 + category | 34–39 ms (31–35 ms without) |
| filtered search in a city + category | 110–291 ms |

**STOP if:**
- any line is `500` or `503`;
- `sorted: False`;
- a barcode under `compare-cat` is not in D02.C02;
- `q-101` or `search-tobacco` is not `422`;
- a no-city `q` time is over 0.3 s, or a Tel Aviv time over 1.5 s, on all three tries.

## 5. nginx

Nothing to install: no new location. `/categories/<id>/items` (with `q`) is already in xxl_heavy since SU11A-67.

## 6. Web deploy, with the guard

**[PC — PowerShell]**

```
git pull origin main; .\scripts\deploy_frontend.ps1
```

**Expect:**
- `build OK: …`;
- `Refreshing the category URLs in the sitemap...`, then `sitemap: N category URLs (web/dist/sitemap-super.xml)`, with N about 17 + the linked categories and sub-categories (roughly 150–200);
- the upload, `MATCH` and a green `Done!`.

A yellow `WARN: sitemap category URLs not refreshed` is not a STOP: the deployed sitemap then lists `/categories` and the 16 departments only. Re-run the deploy later.

**STOP if** you see a red line or `MISMATCH`.

## 7. Browser checks

**[Browser]** https://super.xxl.co.il

1. **Home:** under the search box, "קטגוריות" lists the departments, plus "לכל הקטגוריות". Each opens its department page.
2. **Category search:** open `/categories/D02`.
   - Type `גבינה` in "חיפוש במוצרי חלב". About a third of a second after you stop typing, the list shows cheeses, and the URL gets `?q=…`.
   - Back restores the previous text.
   - Clearing the box shows everything again.
3. **Carry-over:** with text in the box, press "חיפוש "גבינה" בכל האתר". The search page opens with `גבינה` in the box, the category select set to מוצרי חלב, and only dairy results. Choose "כל הקטגוריות" in the select: all results again.
4. **Search page category filter:**
   - Search `שוקולד` and pick a category in the "קטגוריה" select: only that category. "טעינת עוד" keeps the filter.
   - Search `במבה`. If most results are snacks, "הצג רק ב…" appears; pressing it sets the select.
5. **City cheapest:** on `/categories/D02.C02`, with your city selected, choose "הזול ביותר". The card prices go up from the first card.
6. **SEO (view-source and the tab title):**
   - Open `/categories/D02.C02`. The tab title reads "<קטגוריה> — השוואת מחירים בכל הרשתות | SUPER XXL".
   - In DevTools → Elements → `<head>`:
     - `link rel="canonical"` is `https://super.xxl.co.il/categories/D02.C02`;
     - there is no `meta name="robots"`;
     - `script#ld-breadcrumb` holds a BreadcrumbList.
   - Add `?sort=name`: `meta name="robots" content="noindex"` appears, and the canonical stays the same.
   - View-source (Ctrl+U) shows the static shell only. The tags are set by the app, and Google renders them; pre-rendering is a follow-up.
7. **Sitemap:** https://super.xxl.co.il/sitemap-super.xml lists `/categories`, the departments and the linked categories. No `D10.C05`.

**STOP if:**
- a page shows an error box;
- a search with a category shows items from another department;
- tobacco appears.

## 8. Record

Paste the step 4 lines and the sitemap count from step 6 into the chat. The handoff records them in the SU11A-68 entry.

## 9. Rollback

**[PC — PowerShell]**

```
git pull origin main; git revert --no-edit <the SU11A-68 feat commit>; git push origin main; .\scripts\deploy_frontend.ps1
```

**[Server — bash]**

```
cd ~/scrp && git pull origin main && sudo /usr/local/bin/xxl-restart.sh scrp-api
```

- After the rollback, the category pages are SU11A-67's again (noindex, no search box).
- The search page has no category select.
- Nothing in the database changed.
