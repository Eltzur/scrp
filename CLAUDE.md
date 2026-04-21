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
- Future: FastAPI (api/), React/Next.js (frontend/)

## Folder Structure
```
scraper/    — per-chain downloaders
  base.py       — ChainScraper ABC (shared download/load/run logic)
  shufersal.py  — ShufersalScraper (public HTML listing)
  ramilevi.py   — RamiLeviScraper (Cerberus authenticated portal)
  registry.py   — chain_id → scraper class mapping
  city_names.py — Hebrew city normalization
parser/     — XML parsers (price_parser.py)
db/         — schema.sql, db.py helpers, chain_overlap.py
api/        — future FastAPI app
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

### Rami Levy (7290058140886)
- Portal: https://url.retail.publishedprices.co.il (Cerberus web client — requires auth)
- Login: 2-step CSRF flow
  1. GET /login → extract `<meta name="csrftoken">` → POST /login/user with form field `csrftoken`
  2. Re-extract CSRF from /file page → use for all subsequent API calls
- File listing: POST /file/json/dir with `csrftoken` + DataTables params → JSON `aaData`
- Download: GET /file/d/{filename} (session cookie required)
- Stores XML: `Stores{ChainId}-000-{Date}-{Time}.xml` — UTF-16 encoded, NOT gzipped
  - City field is numeric code (3000 = ירושלים, 5000 = תל אביב, etc.) — see CITY_CODES in ramilevi.py
- PriceFull: old filename format `PriceFull{ChainId}-{StoreId}-{Timestamp12}.gz`
- ~96 stores, 190 PriceFull files, updated daily ~midnight and 6AM

## Multi-Chain Architecture
All scrapers inherit from `ChainScraper` (scraper/base.py):
- Implement `load_stores(conn)` → populate stores table, return store_id → metadata
- Implement `build_pricefull_index(target_store_ids)` → return store_id → entry with filename/url
- Inherited: `load_prices_for_stores()`, `run()`, `_download_gz()`, `_decompress()`
- entry["filename"] must be WITHOUT .gz — base class appends .gz for download, .xml for temp

## search.py Flags
- Default: one row per (item_code, store), sorted by price, max 30 results
- `--compare`: group by barcode, show cheapest price per chain + delta, only multi-chain items
- `--limit N`: change result cap
- `--store-only STORE_ID`: filter to one store

## db/chain_overlap.py
Run as `python -m db.chain_overlap` — prints:
- Unique barcode count per chain
- Pairwise barcode overlap (count + % of union)
- Top 10 price deltas for shared items

## Conventions
- All DB writes use INSERT OR IGNORE / ON CONFLICT upserts — safe to re-run
- Hebrew text is UTF-8 throughout; stdout wrapped for Windows terminal compat
- Rate limit: 0.5s between HTTP requests to chain servers
- Raw .gz files saved to sample_data/raw/ then deleted after parsing
- upsert_store matches by (chain_id, store_id) first to avoid orphan rows when sub_chain_id differs
