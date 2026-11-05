# SU11A-66 — categories for users: browse and search design (proposal, not built)

5 Nov 2026. Nothing here is built. The figures marked **[A1]** are placeholders until Dude runs the coverage script on the server:

    cd ~/scrp && ( ulimit -v 2000000; set -a; source .env; set +a; venv/bin/python3 -m scripts.su11a66_category_coverage ) 2>&1 | tee ~/su11a66_coverage.txt

The script (`scripts/su11a66_category_coverage.py`) is read-only (READ ONLY session, 120 s statement timeout). It reads no user data: the suggestions table is read as counts only. Until it runs, this document uses the SU11A-56 export numbers (24 Oct, 131,225 live non-pseudo items) and says so.

## 1. What exists today

**Data** (`db/migrations/su11a52_catalog.sql`, applied and imported on production; deployed in SU11A-57):
- `categories`: taxonomy v1.2 (`docs/catalog/taxonomy_v1_2.csv`), 16 departments, 153 categories and 35 sub-types (204 nodes). Ids are stable; retired nodes stay with `active = false`.
- `item_categories`: one label per barcode, with confidence high / medium / low and source rule / gs1 / ai / manual.
  - Precedence is manual > ai > gs1 > rule, enforced in `scripts/catalog/store.py`.
  - Index `idx_item_categories_category (category_id, confidence)`.
- `item_attributes`: about 92k rows (size, pack, kosher, diet flags), not shown anywhere yet.
- `category_suggestions` (`su11a57_category_suggestions.sql`): user suggestions, reviewed in the admin console.

**Flow:**
- The 14:30 search build (`scripts/build_search_items.py classify_new_items`) labels NEW live barcodes with rule / gs1 rows.
- Imports (`scripts/catalog/import_categories.py`) and admin edits (`api/categories.py write_manual`) write the rest.

**Display rule (SU11A-57, `api/categories.py public_path`):**
- A high or medium label shows its node.
- A low label shows only its department (`partial = true`).

**API:**
- `GET /categories/tree` (`api/routers/categories.py`): the active nodes, public, `Cache-Control` 1 h; cached for 10 min per worker (`TREE_TTL_S`).
- `GET /items/{code}/category`: the item's path, cut to the department for low confidence.
- `POST /items/{code}/category-suggestions`: signed in, behind the ratings gates.
- `/promos/list|grouped|promoted?category=` (SU11A-60, `db/query.py CategoryFilter`, `api/routers/promos.py _filters`): the node and its subtree. Low labels count only when the node is a department.
- The SU11A-62 promo search boost (`api/categories.py promo_search`): a search text that names a category ranks its items half a tier higher. It only re-ranks; it adds no rows (SU11A-65).
- `/search`, `/compare` and `/suggest` have **no** category parameter.
- Admin: `/admin/categories/*` (`api/routers/admin_categories.py`): search, set, confirm, bulk, revert, and four queues.

**Web:**
- `web/src/components/CategoryLine.tsx`: the path and "הצעת עדכון קטגוריה" in the product dialog.
- `web/src/pages/PromosPage.tsx`: the category select, indented; tree cached for 1 h by react-query.
- The admin קטגוריות tab.
- There is no browse page. Routes are in `web/src/App.tsx`. The sitemap (`web/public/sitemap-super.xml`) is static with 5 URLs, and the head tags come from `web/src/utils/seoMeta.ts`.

**Mobile (read, not changed):**
- `src/components/category-suggest.tsx` on product-detail.
- `fetchCategoryTree` / `fetchItemCategory` in `src/api/client.ts`.
- Four `NativeTabs` in `src/components/app-tabs.tsx`: scan / search / basket / settings.
- A drawer, `src/components/app-drawer.tsx`.
- Add-to-basket on search rows and the product page (`src/components/search-row.tsx`, SU11B-5).

## 2. Coverage and quality (what we know before A1)

**Coverage**, from the SU11A-56 export of 24 Oct (131,225 live items), under the display rule:

| | Items | Share |
|---|---:|---:|
| high + medium: usable at the category or below | 115,807 | 88.3% |
| low: department only | 13,265 | 10.1% |
| no label | 2,153 | 1.6% |

**[A1]:**
- today's numbers;
- the same for items sold by at least 3 and at least 5 chains;
- the per-department split and the thin / fat pages.

The bench run of the script (synthetic labels, below) proves only that the script runs, not these numbers.

**Quality**, from section f of the script. It reads the repo files, so it ran here:

| Sample | n | Exact id wrong | Department wrong | Shown wrong under the display rule |
|---|---:|---:|---:|---:|
| review_graded_v1: rule, high | 75 | 12.0% | 10.7% | 12.0% |
| review_graded_v1: gs1, high | 57 | 8.8% | 0.0% | 8.8% |
| review_graded_v1: ai (high 7 / low 8) | 15 | 53% | 27% | 40% |
| ai_audit_graded_v1: ai, high | 34 | 17.6% | 8.8% | 17.6% |
| ai_audit_graded_v1: ai, medium | 33 | 36.4% | 21.2% | 36.4% |
| ai_audit_graded_v1: ai, low | 33 | 54.5% | 30.3% | 30.3% (department shown) |

"Shown wrong" means the node a user would see is not the correct node or one of its ancestors.

**Caveats:**
- The review sample's predictions are the v1 labels. The v1.1 fixes were written from these same rows (147 of 150 match in v1.1), so the rule and gs1 rates are pre-fix, not an independent measure.
- Eight review rows were moved to v1.2 nodes that did not exist when they were predicted (spring water, newspapers, pickles), so those rows count as errors here.
- The AI audit sample covers AI-only labels, which are the hardest rows.

**Findings:**
- **AI medium is the weak spot:** about 1 in 3 shown wrong.
- **AI low is correctly kept at the department.** Even there, 30% of the department is wrong.
- **Most errors are in** D09 drinks (9 of 34), D08 snacks (8 of 36), D12 personal care (8 of 29) and D07 pantry (7 of 27). The most common department move is D16 → D11: party / disposables confused with cleaning and paper.

**The browse risk:** there are about 3,900 AI medium labels (3,933 on the export). At a 36% error rate, about 1,400 items would show in a wrong category. They are mostly single-chain items (AI labels went to the unclassified tail), so the popular-item error rate should be lower. **[A1]:** source × confidence for at least 3 chains.

## 3. Web design

### 3.1 Entry and pages
- **Header:** a "קטגוריות" link next to "מבצעים" in the app header (super.xxl.co.il). On mobile web it goes in the same menu.
- **Pages:**
  - `/categories` lists the 16 departments as cards: Hebrew name, item count, and a fixed icon per department (lucide, no new assets).
  - `/categories/D02` is a department page. It shows the department's categories as chips or links with counts, then the product grid for the whole department.
  - `/categories/D02.C01` is a category page: the sub-type chips (if any), then the grid.
  - `/categories/D02.C01.S01` is a sub-category page.
  - Each page has breadcrumbs: קטגוריות › department › category.
- **URL:** the id, plus an optional Hebrew slug for people and search engines, e.g. `/categories/D02.C01/חלב`. The id is the key; a wrong or old slug redirects (replace) to the right one. Ids never change (SU11A-52), so links stay valid when a name is renamed.
- **Product grid:**
  - The same cards as search results (the `/search` result shape), with the cheapest chain and price, and the "N רשתות" count.
  - Clicking opens the product dialog (CategoryLine included).
  - Each card has add-to-basket, as on search results.
  - Pagination is "הצג עוד" (load more), 30 per page, with `?page=` in the URL so a page is linkable.
- **Filters**, in the URL like `/promos`:
  - city: the existing city select;
  - chain;
  - sort: popular, which is the default (chains_live, then stores), or cheapest;
  - "רק במבצע": only items with a live promo in the filter.
- **Thin pages:**
  - A category or sub-category with fewer than `MIN_BROWSE` (proposed 5) usable live items is not linked from its parent. Its URL still answers, noindex, with a link up.
  - A department always shows.
- **Fat pages:** above about 2,000 items, the sub-type or brand chips at the top matter more than the grid. **[A1]:** which categories are above 2,000.

### 3.2 Search and compare
- **`/search` and `/compare` get a category filter.** A department / category select appears under the results once there are results, built from the result set's own departments ("in this search: מוצרי חלב 120, ממתקים 14"). Choosing one reruns the request with `&category=`.
- **Facet counts are only shown when cheap.** They come from the candidate list of search v2 (search_items × item_categories, one indexed join). When the filtered path cannot count exactly, they are shown as "about".
- **The promos page keeps its own category select** (SU11A-60). It gets a link "לכל המוצרים בקטגוריה" to the browse page of the chosen node, and the browse page gets "מבצעים בקטגוריה", a link to `/promos?cat=<id>`.

### 3.3 SEO
- **Rendering:**
  - The web is a client-rendered SPA (Vite). Googlebot renders JavaScript, but slowly and not always.
  - **Recommendation:** at build time, pre-render the 16 department pages and the categories that pass `MIN_BROWSE` into static HTML shells: title, H1, breadcrumbs, the child links and a short text, without prices. Prices change daily and are fetched live.
  - This is a small step in `deploy_frontend.ps1`'s build (a node script over the tree JSON, which is public).
- **Head tags:**
  - `seoMeta.ts` gets a `/categories/*` rule.
  - Title: "<category> — השוואת מחירים | XXL סופר".
  - Canonical: the id URL with the current slug, without filters, so filtered views canonicalise to the base page.
  - City and sort variants are not indexed (canonical to the base).
  - Pages past page 1 canonicalise to themselves and are not in the sitemap.
- **Sitemap:** generated `sitemap-super.xml` entries for the departments and the categories that pass `MIN_BROWSE`, at the same build step. `lastmod` is the taxonomy version date, not the price date.
- **Structured data:** a `BreadcrumbList` JSON-LD on every category page. Not `Product`: no offers are in the static HTML.

### 3.4 Accessibility (IS 5568 baseline)
- Real `<nav aria-label="פירורי לחם">` breadcrumbs with `aria-current="page"`.
- Department cards and chips are `<a>` links (they navigate), not buttons. They are keyboard-reachable and the focus ring stays.
- One `<h1>` per page.
- The grid is a `<ul>` of cards. "הצג עוד" is a `<button>` that announces "נטענו עוד 30 מוצרים" through a polite live region, and focus moves to the first new card.
- Filter selects have visible labels, as on `/promos`.
- Never colour alone: the promo badge keeps its text.
- Contrast: reuse the existing card styles (already checked).
- RTL: breadcrumbs separate with "›" in logical order, as `path_he`.
- Department icons are decorative (`aria-hidden`), and the name is the text.

## 4. Mobile design (the app version after 1.2.3)

### 4.1 Placement

| Option | For | Against |
|---|---|---|
| A. 5th tab "קטגוריות" | always one tap away; the most discoverable | five tabs crowd small Android phones; changes the bar everyone knows; the scan tab loses prominence |
| **B. A "קטגוריות" entry on the search screen** (a grid of the 16 departments in the empty state, plus a "קטגוריות" chip row) | browsing is a kind of searching; no new tab; the empty search screen has room | less visible once the user has typed |
| C. The drawer | no layout change | the drawer holds settings-like items; few users would find it |

**Recommendation: B.**
- On the search tab, before typing, show the department grid: 16 tiles, 2 columns, each with a Hebrew name and an icon.
- After a search, show the result-set department chips (as on the web, 3.2).
- Add a drawer entry later if usage asks for it.
- A 5th tab can be revisited when there is usage data: GA4 events on department taps, consent-gated.

### 4.2 Screens
- **Route `category/[id]`** (expo-router, a Stack push over the tabs, like product-detail).
  - The header is the node name, with the path as a small subtitle.
  - The children are a horizontal chip row.
  - The grid is a FlashList of the `search-row` component, which brings the SU11B-5 add-to-basket on every row and the same accessibility labels.
  - Infinite scroll with `limit` / `offset`, 30 per page.
  - The city and chain filters reuse the search screen's filter sheet; the city defaults to the user's saved city.
- **Thin nodes** are hidden by the same `MIN_BROWSE` rule as the web. The server returns the counts, so the app needs no rule of its own.

### 4.3 Tree caching
- **Fetch:** `GET /categories/tree` (already used by category-suggest) plus the counts endpoint (5.1), stored in AsyncStorage with the taxonomy version and the build stamp.
- **Refresh:** stale-while-revalidate after 24 h, the same as `/stores/coordinates`.
- **Size:** about 204 nodes, about 15 kB gzip with the counts.
- **Offline:** the cached tree still shows. The grid needs the network and shows the existing offline message.

### 4.4 Text
- **New strings** go in `src/i18n/he.ts`:
  - "קטגוריות";
  - "כל המוצרים ב…";
  - an empty-category message;
  - "הצג עוד" on the web.
- **No new user data:** no privacy-inventory change, per the CLAUDE.md five-place rule. The GA4 events, if added, are already covered by the analytics consent.

## 5. API design

### 5.1 Endpoints

**`GET /categories/counts`**
- Returns `{version, built_at, counts: {node_id: usable_live_items}}`.
- Computed once per search build: `search_items` × `item_categories`, high / medium for categories and sub-categories, every label for departments.
- Cached by the build stamp (`search_items.built_at`), as `/chains` since SU11A-59. It never scans `prices` (security baseline).
- **Public:** `Cache-Control` 1 h.

**`GET /categories/{id}/items`** with:
- `city`, `chain` (repeatable, capped at 14);
- `sort`: `popular` | `cheapest`;
- `promo_only`: bool;
- `limit` ≤ 50 (default 30), `offset` ≤ 3,000.

It returns the `/search` result shape (`SearchResult`), so web and mobile reuse their renderers, plus `category: {id, path}`. Details:
- **Low confidence (SU11A-57):** a department page includes low labels of that department; a category or sub-category page only high and medium. The same rule as the promos `CategoryFilter`, reused, not copied.
- **Pseudo rows** (coupons, service rows) and nameless rows are left out, as in search v2.
- **No city, no chain:** the page comes from `search_items` (order: chains_live DESC, stores_live DESC, item_code) and the prices from `search_item_prices`. That is the precomputed path of SU11A-47, with the same fallback to the live fetch.
- **City or chain:** the candidate walk of `db/search_filtered.py`. The category's items in popular order are the candidates instead of the name matches. The batches are 200 / 400 / 800 / 1,600, the ceiling 3,000, and only the page's items are priced live. Reusing the module keeps the Eilat rule, liveness, the ₪0 drop and promo-only quotes identical to `/search`.
- **`sort=cheapest`:**
  - Nationwide: `min(search_item_prices.effective)` per item over the category.
  - In a city: inside the walked candidates only (as `/search` does with v2 relevance), documented as "cheapest of the most widely sold" when the walk stopped early.
- **`promo_only`:** nationwide, `search_item_prices.promo_unit_price IS NOT NULL`; in a city, the walk keeps items whose city quote has a promo.

**Other changes:**
- `/search` and `/compare` get **`category`** (a node id, max 32 characters, an unknown or inactive id gives 0 results, as on `/promos`). Search v2 adds `AND item_code IN (labels under the node)` to `ranked_candidates` as one semi-join. The v1 fallback path gets the same filter on its candidate query. `/suggest` is unchanged.
- **Facets for 3.2:** a `facets=department` option on `/search` returns department counts of the v2 candidate list (at most the CEILING of 3,000 candidates, so cheap).

### 5.2 Security baseline
- **Caps:**
  - `limit` ≤ 50, `offset` ≤ 3,000 (the walk ceiling);
  - `chain` ≤ 14 values;
  - `category` max 32 characters, matched against the cached tree (never used in SQL text);
  - `city` as on `/search` (an exact `city_canonical` value, max 64).
  - There is no free text, so no wildcard escaping is needed.
- **nginx:**
  - `/categories/` + id + `/items` goes into the `xxl_heavy` group (`deploy/nginx/xxl-ratelimit-api.conf`, 2 r/s per IP, burst as for the other heavy endpoints). With a city it reads prices.
  - `/categories/tree` and `/categories/counts` stay in `xxl_api` (cached, cheap).
  - `/search` and `/compare` are already heavy.
- **Caching:** page responses with no city, chain or promo filter are cached by (id, sort, offset, build stamp) in `api/response_cache.py`, the `/promos/today` pattern. City pages are not cached (too many keys).
- **Statement timeout:** the existing API statement timeout of 15 s; the walk stays far below it (5.3).

### 5.3 Query cost (bench)

The bench is the throwaway Postgres 18 of SU11A-65 (14 chains, 936 stores, 7.9M prices, 842k promos, 75k items). The following were synthetic and filled for this test:
- `search_items`: 73,450 live rows from the bench prices;
- `search_item_prices`: 118,300 rows, the cheapest branch per item and chain;
- 52k labels on 176 nodes (no sub-types).

Production has 131k items and about 1.7 times the labels.

| Query | Plan | Time |
|---|---|---:|
| category page, nationwide, largest category (4,839 labels), page 1 | Bitmap on `idx_item_categories_category` + seq scan of search_items (hash join) | 23 ms |
| same, offset 3,000 | same | 39 ms |
| page prices (30 barcodes) from search_item_prices | `search_item_prices_pkey` | 20 ms |
| department count (D03, all labels) | seq scans of both small tables | 33 ms |
| cheapest-first nationwide, largest category | seq scan of search_item_prices (118k) | 43 ms |
| **city filter as one join** (Tel Aviv, largest category) | parallel seq scan of all 7.9M prices | **761 ms** |
| city filter as one join, small category (585 labels) | the same seq scan | 578 ms |
| city filter, two ANY arrays (store set × all 4,839 items) | `prices_store_fk_item_code_key`, 42k rows | **2,711 ms** (worse) |
| same, small category | the same | 78 ms |
| **city walk batch** (the search_filtered shape): 200 / 600 / 1,600 candidates in popular order × Tel Aviv stores | `prices_store_fk_item_code_key` | **42 / 120 / 313 ms** |

**Conclusions:**
- Nationwide pages are cheap from the search build, under 50 ms on the bench; expect under about 100 ms on production. No new index is needed:
  - `idx_item_categories_category` serves the label lookup;
  - the search_items primary key serves the join;
  - `search_item_prices_pkey` serves the page prices.
- **A city page must use the batched walk.** A single "every item of the category in this city" query is 0.6–2.7 s. The walk needs one batch of 200 (about 40 ms) for a normal category in a big city, and more batches only in small towns.
- Production ran about 1.3 times slower than the bench in SU11A-65. A city page should be about 0.1–0.4 s. Measure on production before turning it on.
- An optional index `item_categories (category_id) INCLUDE (confidence, item_code)` would allow index-only scans; it is not needed at these sizes.

## 6. Gaps that block a good browse experience

All **[A1]** until the script runs on the server.

1. **Department-only items (low).** On the export they are 10% of live items. They appear only on department pages, never in a category. A department page sorted by popularity is still useful. Category pages simply miss them.
2. **AI medium errors** (section 2). The most visible wrong labels will be AI medium in D09, D08, D12 and D07.
3. **Thin categories:** nodes with 0–4 usable items. On the export, the new v1.2 nodes are well filled (D09.C11 about 270, D16.C08 about 55, D07.C08.S01 about 620). **[A1]** d lists the rest.
4. **Fat categories:** more than 2,000 items. They need sub-type or brand chips to be browsable. The taxonomy has only 35 sub-types, so most large categories have none. **[A1]** d lists them.
5. **Unlabelled popular items.** Only 1.6% of all items have no label, but every popular one missing from its category is noticed. **[A1]** a/b for at least 3 and 5 chains.
6. **New barcodes:** the build labels them with rules / GS1 only. An item the rules cannot place stays unlabelled until the next import. **[A1]** e: rows per day.

**Options:**
- **(a) Hide thin nodes.** Do not link nodes with fewer than `MIN_BROWSE` items; their items still show on the parent page. This costs nothing and is part of the API (counts).
- **(b) Merge** thin sub-types into their category, as a taxonomy change (v1.3). Only if A1 shows many of them.
- **(c) A targeted labelling pass for popular items:**
  - Every item sold by at least 3 chains that is low, AI medium or unlabelled goes into the admin queue (SU11A-57 queues already sort by chains_live).
  - Dude grades the top 300–500 by hand. They become manual rows, about 2–3 hours at the SU11A-55 pace.
  - The tail goes to a re-run AI pass for those rows only. The SU11A-56 Sonnet pilot failed its gate, so either Haiku with the v1.2 rules or a better prompt, with a new graded gate.
- **(d) Show low labels on category pages behind "אולי גם", ranked below.** Not recommended: it breaks the SU11A-57 rule that a low label never shows a specific category.

## 7. Phasing

| Phase | Contents | Rough size |
|---|---|---|
| 1. API + web browse + search filter | `/categories/counts`, `/categories/{id}/items` (nationwide from the build, city via the search_filtered walk), `category` on `/search` and `/compare`, department facets; web `/categories` pages, header link, grid with add-to-basket, filters, breadcrumbs, prerendered shells + sitemap, accessibility; tests (pg: the order and the low rule, caps, walk equivalence with `/search`); nginx heavy group; runbook | 2 sessions (API + tests 1, web + SEO 1) |
| 2. Mobile (app version after 1.2.3) | department grid on the search tab, `category/[id]` screen with search-row + add-to-basket, chips after a search, tree + counts cache; strings; no new user data | 1 session, plus a store build (Dude) |
| 3. Labelling improvements | popular-item queue export and a graded file (Dude), AI re-run for the tail with a gate, optional taxonomy v1.3 merges / sub-types for fat categories | 1 session + Dude's grading time; an AI run is cents to a few dollars (SU11A-56 pilot: $0.07 per 100) |

Phase 1 needs no migration (no new table; the optional index is not needed). Phase 3 can start in parallel with phase 1: the queue sizes come from A1.

## 8. Open decisions for Dude

1. **Mobile placement.** Recommendation: **B**, the department grid on the search screen. Revisit a 5th tab with usage data.
2. **Show low-confidence items on category pages?** Recommendation: **no**. Keep SU11A-57: department pages only.
3. **`MIN_BROWSE`, the threshold for linking a node.** Recommendation: **5** usable live items. Decide after A1 section d.
4. **Default sort.** Recommendation: **popular** (chains_live): the cheapest first fills with odd single-chain items. Offer "הזול ביותר" as an option.
5. **Alcohol and tobacco on browse pages** (the parked hide switch; A1 g gives the size). Recommendation: a **D10 department page like any other, with tobacco (D10.C05) not linked and noindex**. Advertising tobacco is restricted in Israel; confirm with your legal view. A full hide is one tree flag either way.
6. **SEO pre-rendering.** Recommendation: **yes**, static shells for the departments and the linked categories, without prices.
7. **The labelling pass (option c).** Recommendation: **yes, before phase 1 ships.** Grade the top 300–500 popular items that are low, AI medium or unlabelled.
8. **Ship order.** Recommendation: **web first** (phase 1), mobile in the app version after 1.2.3, as the release gate already plans one version in review at a time.

## 9. Not verified here

- Every production figure: A1 has not run; this session has no server access.
- The bench is synthetic: no sub-types, 75k rather than 131k items, labels spread artificially. It shows the query shapes and their plans, not production timings.
- Whether the walk's 200-candidate first batch fills a page in small towns: measure on production in phase 1.
- Google's handling of the pre-rendered shells: check in Search Console after the deploy.
