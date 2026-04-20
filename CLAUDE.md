# Israeli Supermarket Price Comparison — Project Context

## Purpose
Compare grocery prices across Israeli supermarket chains using legally-mandated
price transparency XML files (Price Transparency Regulation 2014).
Each chain publishes Prices, PricesFull, Promos, Stores, etc. as gzipped XML.
The cross-chain join key is `ItemCode` (product barcode).

## Tech Stack
- **Python 3.10+** with virtualenv at `venv/`
- **lxml** — XML and HTML parsing
- **SQLite** (Phase 1) → PostgreSQL (later)
- **requests** — HTTP downloads
- Future: FastAPI (api/), React/Next.js (frontend/)

## Folder Structure
```
scraper/    — per-chain downloaders (shufersal.py, ...)
parser/     — XML parsers (price_parser.py, stores_parser.py)
db/         — schema.sql, db.py helpers
api/        — future FastAPI app
frontend/   — future React app
load.py     — CLI pipeline: parse one XML file → SQLite
search.py   — CLI search by product name (Hebrew/English)
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

## Current State (after Session 2)
- Shufersal scraper downloads PriceFull + StoresFull from prices.shufersal.co.il
- City normalization handles Hebrew abbreviations (י-ם → ירושלים, etc.)
- search.py shows item_name, price, unit_price, store_name, city, chain

## Key Data Sources
- Shufersal listing: http://prices.shufersal.co.il/FileObject/UpdateCategory?catname=PriceFull&page=1
- File host: pricesprodpublic.blob.core.windows.net (signed Azure Blob, URLs expire in hours)
- Filename formats:
  - Old: `PriceFull{ChainId}-{StoreId}-{Timestamp12}.gz`
  - New: `PriceFull{ChainId}-{SubChainId}-{StoreId}-{Date8}-{Time6}.gz`

## Conventions
- All DB writes use INSERT OR IGNORE / ON CONFLICT upserts — safe to re-run
- Hebrew text is UTF-8 throughout; stdout wrapped for Windows terminal compat
- Rate limit: 0.5s between HTTP requests to chain servers
- Raw .gz files saved to sample_data/raw/ then deleted after parsing
