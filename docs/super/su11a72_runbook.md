# SU11A-72 — result view modes (grid / list / comparison table): runbook

Written 9 Nov 2026 for Dude. **Web only: no API, nginx, DB or app change**, so there is no server step. The list and the table read the per-chain quotes that `/search`, `/compare` and `/categories/{id}/items` already return.

**What changes**
- **Where:** on search results (super.xxl.co.il and the portal search) and on category pages (`/categories/<id>`). The promos page is unchanged.
- **The switcher:** a segmented control "רשת / רשימה / טבלת השוואה" appears above the results. "פריטים בעמוד" sits next to it in the list and the table.
- **רשת:** today's cards, unchanged, with "load more".
- **רשימה:**
  - one closed row per product: thumbnail, name, "הכי זול ב<רשת>", "רשתות: N", the saving badge, the cheapest price and a chevron;
  - opening a row lists every chain's price, cheapest first. The cheapest line is green **and** says "הכי זול";
  - each open row has the basket button and "כל N הרשתות", which opens the product window;
  - 10 / 25 / 50 / 100 / הכל items per page, default 25, with הקודם / הבא.
- **טבלת השוואה:**
  - products × chains. The default columns are the 5 chains with the most listed products, and the chips change them (at most 8);
  - the product column stays in place while the chains scroll sideways on a phone;
  - "—" means not sold there; the cheapest cell of a row is green, with "הכי זול" for screen readers;
  - the total row marks the cheapest total **only among chains that carry every product**. The others show "חסר N";
  - 10 / 25 / 50 per page. A remembered 100 / הכל shows 50 with a short note.
- **Remembered per browser:** the view, the page size and the table's chains (localStorage `xxl_result_view`, `xxl_result_page_size`, `xxl_table_chains`). Nothing goes into the account or the URL, and a view change is not a GA4 page view.
- **Group by branch:** when search results are grouped by branch ("קיבוץ לפי: סניף"), only the grid is available, with a short note.

**Production impact**
- One web deploy, which updates super.xxl.co.il and the portal together.
- Main chunk 176.51 → 179.51 kB. The list / table code is a lazy chunk, loaded only when someone picks those views.

**How to run it**
- Run the steps in order. Each step names where it runs:
  - **[PC — PowerShell]:** in `C:\scrp` on the **home PC** (the one with `web/.env.production`).
  - **[Browser]:** desktop Chrome, and the phone, or DevTools device mode at 390 px.
- If a step says STOP, paste what you see to the chat and do not improvise a fix.

---

## 1. Web deploy, with the guard

**[PC — PowerShell]**

```
git pull origin main; .\scripts\deploy_frontend.ps1
```

**Expect:** `build OK: …`, the sitemap lines, the upload, `MATCH` and a green `Done!`.
**STOP if** you see a red line or `MISMATCH`.

**If needed:** to undo, deploy the previous commit the same way. No server state depends on this change.

## 2. Browser checks

**[Browser]** https://super.xxl.co.il, in a private window. Search `חלב` with a city chosen.

1. **Switcher:**
   - "רשת / רשימה / טבלת השוואה" appears above the results, with רשת selected;
   - the cards are as before, and "טעינת עוד" still works.
2. **List:**
   - click "רשימה": the rows are **all closed**, and "פריטים בעמוד" shows 25;
   - open a row: every chain's price, cheapest first, and the cheapest line is green **and** reads "הכי זול";
   - a multi-buy promo shows "מבצע" and "N יח' ב-₪X";
   - the basket button adds to the basket;
   - "כל N הרשתות" opens the product window.
3. **Page sizes:**
   - 10: הקודם / הבא move one page at a time, and the line "מוצגים 11–20" follows;
   - הכל: up to 100 rows in one go. If the search has more, a note says how many are shown out of the total;
   - after a reload (F5) the list and the size are still selected.
4. **Table:**
   - "טבלת השוואה" with up to 5 chain columns;
   - click chips to add and remove chains. A 9th chain is refused with "אפשר לבחור עד 8 רשתות.";
   - the "—" cells are products a chain does not sell; the cheapest cell of each row is green;
   - in the total row, only a chain with no "חסר" can carry "הסכום הזול ביותר";
   - the note above the table names the city. With "כל הערים", it says the chain's lowest price nationwide;
   - after a reload the same chains are still selected;
   - with a remembered size of 100 or הכל, the table shows 50 and says so.
5. **Category page:** https://super.xxl.co.il/categories, then open a department. The same three views work there; "הכל" shows up to 60.
6. **Phone width** (390 px):
   - the switcher wraps without overlap, and list rows read well;
   - in the table, the product column stays put while the chains scroll sideways.
7. **Keyboard:**
   - Tab reaches the switcher buttons, the size select, every list row, the chips and the pager, each with a visible green focus ring;
   - Enter or Space opens and closes a row.
8. **Screen reader** (NVDA, or VoiceOver on the phone), spot check:
   - the switcher buttons read as pressed / not pressed;
   - a list row reads its name and "expanded" / "collapsed";
   - the table has a caption ("השוואת מחירים: N מוצרים לפי רשת") and column and row headers;
   - a "—" cell reads "לא נמכר", and the cheapest cell adds "הכי זול".
9. **Group by branch:**
   - turn off "מצב השוואה" and set "קיבוץ לפי: סניף": only רשת is enabled, and a note explains why;
   - set it back to רשת: the remembered view returns.
10. **No URL change, no extra page views:**
    - switching views or the page size does not change the address bar;
    - in DevTools → Network (filter `collect`), with cookies accepted, it sends **no** new `page_view`.
11. **Portal:** https://xxl.co.il search works the same.

**STOP if:**
- a view shows wrong prices against the grid for the same product;
- a list row opens with nothing in it;
- the table marks a total as cheapest while that chain shows "חסר";
- anything is conveyed by colour only;
- a view change creates a `page_view` or changes the URL.

**Note:** the website has no dark mode (no page uses one), so the views follow the light theme; there is nothing to check in dark mode.
