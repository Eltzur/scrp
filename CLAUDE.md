# Israeli Supermarket Price Comparison — Project Context

## Purpose
Compare grocery prices across Israeli supermarket chains using legally-mandated
price transparency XML files (Price Transparency Regulation 2014).
Each chain publishes Prices, PricesFull, Promos, Stores, etc. as gzipped XML.
The cross-chain join key is `ItemCode` (product barcode).

## Tech Stack
- **Python 3.10+** with virtualenv at `venv/`
- **lxml** — XML and HTML parsing (Shufersal HTML listing)
- **SQLite** (Phase 1) → PostgreSQL (later)
- **requests** — HTTP downloads
- **FastAPI** + **uvicorn** — REST API server (api/)
- **Pydantic v2** — response model validation
- **pytest** + **httpx** — smoke tests via TestClient
- Future: React/Next.js (frontend/)

## Folder Structure
```
scraper/    — per-chain downloaders
  base.py       — ChainScraper ABC (shared download/load/run logic)
  shufersal.py  — ShufersalScraper (public HTML listing)
  ramilevi.py   — RamiLeviScraper (Cerberus authenticated portal)
  osherad.py    — OsherAdScraper (Cerberus portal)
  registry.py   — chain_id → scraper class mapping
  city_names.py — Hebrew city normalization
parser/     — XML parsers (price_parser.py)
db/         — schema.sql, db.py helpers, query.py, chain_overlap.py
api/        — FastAPI application
  main.py       — app factory, CORS, router wiring
  models.py     — Pydantic v2 response models
  dependencies.py — get_db() per-request SQLite connection
  routers/
    health.py   — GET /health, GET /stats
    catalog.py  — GET /chains, /stores, /cities
    search.py   — GET /search, /compare
    product.py  — GET /product/{barcode}
  tests/
    test_smoke.py — 11 TestClient smoke tests
frontend/   — future React app
load.py     — CLI pipeline: parse one XML file → SQLite
search.py   — CLI search (--compare, --limit, --store-only flags)
```

## Database Schema (SQLite, prices.db)

```sql
chains      — chain_id (PK), name
stores      — id, chain_id, sub_chain_id, store_id, store_name, city, city_norm, address
items       — item_code (PK/barcode), item_type, item_name, manufacturer_name,
              manufacture_country, unit_qty, quantity, is_weighted,
              unit_of_measure, qty_in_package
              INSERT OR IGNORE — first chain to insert wins the canonical name
item_chain_names — item_code + chain_id (PK), item_name, manufacturer_name
              Per-chain name for each barcode. ON CONFLICT DO UPDATE — last-wins per chain.
              This is the primary search target; items is the fallback for barcodes
              not yet present in item_chain_names.
prices      — id, store_fk, item_code, price_update_date, item_price,
              unit_of_measure_price, allow_discount, item_status
              UNIQUE (store_fk, item_code) — safe to re-run (upserts)
fetch_runs  — id, chain_id, run_at, files_attempted, files_loaded,
              items_inserted, status ('ok'|'partial'|'error')
```

## Chain Sources

### Shufersal (7290027600007)
- Listing: http://prices.shufersal.co.il/FileObject/UpdateCategory (public, no auth)
- File host: pricesprodpublic.blob.core.windows.net (signed Azure Blob, URLs expire in hours)
- Listing layout (newest-first): pages 1-15 = Price, 16-35 = Promo, 36+ = PriceFull/PromoFull
- Store metadata extracted from HTML branch column ("357 - דיל קדימה לב השרון")
- Filename formats:
  - Old: `PriceFull{ChainId}-{StoreId}-{Timestamp12}.gz`
  - New: `PriceFull{ChainId}-{SubChainId}-{StoreId}-{Date8}-{Time6}.gz`

### Osher Ad (7290103152017)
- Portal: same Cerberus portal as Rami Levy (username: `osherad`, empty password)
- 23 stores, warehouse/discount format, founded 2009
- Filename format: NEW format `PriceFull{ChainId}-{SubChainId}-{StoreId}-{Date8}-{Time6}.gz`
- Stores XML: same UTF-16 structure, same government city code system
- Expected: ~55% exclusive barcodes — Kirkland (Costco private label) + imports not found elsewhere
- Implementation: `OsherAdScraper(CerberusScraper)` — 6-line subclass

### Rami Levy (7290058140886)
- Portal: same Cerberus portal (username: `RamiLevi`, empty password)
- ~96 stores, updated daily ~midnight and 6AM
- Filename format: OLD format `PriceFull{ChainId}-{StoreId}-{Timestamp12}.gz`
- Implementation: `RamiLeviScraper(CerberusScraper)` — 6-line subclass

### Cerberus portal shared pattern
- URL: https://url.retail.publishedprices.co.il
- Login: 2-step CSRF flow
  1. GET /login → extract `<meta name="csrftoken">` → POST /login/user with form field `csrftoken`
  2. Re-extract CSRF from /file page → use for all subsequent API calls
- File listing: POST /file/json/dir with `csrftoken` + DataTables params → JSON `aaData`
- Download: GET /file/d/{filename} (session cookie required)
- Stores XML: `Stores{ChainId}-000-{Date}-{Time}.xml` — UTF-16 encoded, NOT gzipped
  - City field is numeric government code — see `CITY_CODES` in `scraper/cerberus.py`
- Both old and new PriceFull filename formats handled in `CerberusScraper.build_pricefull_index()`
- Adding a new Cerberus chain = 6-line subclass (CHAIN_ID, USERNAME, CHAIN_NAME)

## Multi-Chain Architecture
Hierarchy: `ChainScraper` (base.py) → `CerberusScraper` (cerberus.py) → `RamiLeviScraper` / `OsherAdScraper`

All scrapers inherit from `ChainScraper` (scraper/base.py):
- Implement `load_stores(conn)` → populate stores table, return store_id → metadata
- Implement `build_pricefull_index(target_store_ids)` → return store_id → entry with filename/url
- Inherited: `load_prices_for_stores()`, `run()`, `_download_gz()`, `_decompress()`
- entry["filename"] must be WITHOUT .gz — base class appends .gz for download, .xml for temp

## Search Architecture (barcode-first, name-second)
search.py uses a two-phase approach:
1. **Barcode discovery**: query `item_chain_names` UNION `items` for barcodes matching ALL query words
   (AND per word, any order, LIKE per field). Multi-word queries split on whitespace.
2. **Price fetch**: for matched barcodes, pull all prices joined via `item_chain_names` so each
   chain sees its own product name variant.

This ensures cross-chain matches even when chains use different word orders for the same product.

## search.py Flags
- Default: one row per (item_code, store), sorted by price, max 30 results
- `--compare`: group by barcode; multi-chain products shown first with `[N chains]` badge and
  delta vs cheapest; single-chain products follow with `[Chain only]` badge
- `--limit N`: change result cap (default 30)
- `--city CITY`: filter prices to stores in that city (uses normalize_city)
- `--store-only STORE_ID`: filter to one store (disables --compare with a warning)

## Known Issues / Future Work
- **Hebrew substring over-matching**: short tokens (e.g. חלב) match inside longer words
  (חלבה, שוקולד חלב). Multi-word AND queries mitigate this. Full fix requires SQLite FTS5
  with Hebrew tokenizer — deferred.
- **Shared barcode names**: until re-scraped, item_chain_names has the same canonical name for
  both chains on shared barcodes. Real per-chain names populate on next scraper run.

## db/chain_overlap.py
Run as `python -m db.chain_overlap` — N-chain analysis, prints:
- Per-chain stats: unique barcodes, price rows, stores loaded
- Pairwise overlap matrix (NxN)
- All-chains intersection count + % of union
- Top 20 price deltas (any 2+ chains, cheapest vs most expensive)
- Exclusive barcode counts per chain (Osher Ad ~55% exclusive due to Kirkland/imports)
- Top 10 exclusive products per chain by price

## API Layer (Session 5)

### Running the server
```bash
uvicorn api.main:app --reload        # dev server, hot-reload
uvicorn api.main:app --port 8000     # production-style
```
Interactive docs at http://localhost:8000/docs (Swagger UI).

### Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Liveness check |
| GET | /stats | DB counts + last fetch per chain |
| GET | /chains | All chains with barcode/store counts |
| GET | /stores | Store branches (filter: ?chain=&city=) |
| GET | /cities | Distinct cities with data |
| GET | /search | Product search (?q=&limit=&city=&chain=) |
| GET | /compare | Cross-chain only (?q=&limit=&city=) |
| GET | /product/{barcode} | All prices for one barcode |

### Pydantic v2 models (api/models.py)
- `ChainSummary`, `Store`, `PriceQuote`, `Product`, `ProductWithPrices`, `SearchResult`, `StatsResponse`
- All use `ConfigDict(from_attributes=True)` for SQLite Row compatibility

### db/query.py — shared query engine
Extracted from search.py; used by both CLI and API:
- `find_barcodes(conn, words)` — UNION search across item_chain_names + items
- `fetch_prices(conn, barcodes, city, chain_id)` — full join with delta computation
- `group_by_product(rows)` — group/sort by item_code, build quotes list
- `fetch_chains / fetch_stores / fetch_cities / fetch_stats / fetch_product`

### Running tests
```bash
python -m pytest api/tests/test_smoke.py -v
```

## Conventions
- All DB writes use INSERT OR IGNORE / ON CONFLICT upserts — safe to re-run
- Hebrew text is UTF-8 throughout; stdout wrapped for Windows terminal compat
- Rate limit: 0.5s between HTTP requests to chain servers
- Raw .gz files saved to sample_data/raw/ then deleted after parsing
- upsert_store matches by (chain_id, store_id) first to avoid orphan rows when sub_chain_id differs
