# XXL Scraper — Technical Stack Reference
> Read this before touching any code. Never guess column names or API patterns.

## Database Schema (PostgreSQL, db: xxl_super, user: scrp_app)

### prices
id (PK), store_fk (FK→stores.id), item_code (text), item_price (float8), 
unit_of_measure_price (float8), price_update_date (text), allow_discount (int), item_status (int)
Indexes: prices_pkey, idx_prices_item_code, idx_prices_store_fk, prices_store_fk_item_code_key (UNIQUE)

### stores
id (PK), chain_id (text), sub_chain_id (text), store_id (text), store_name (text), 
city (text), city_norm (text), city_canonical (text), address (text)
Indexes: idx_stores_city_norm, idx_stores_city_canonical, idx_stores_chain_city

### promos
id (PK), store_fk (FK→stores.id), item_code (text), promo_id (text), promo_description (text),
promo_type (text), reward_type (int), discount_rate (float8), discount_price (float8),
min_qty (float8), min_purchase_amount (float8), allow_multiple_discounts (bool),
promo_start (timestamp), promo_end (timestamp)
Indexes: idx_promos_store_fk, idx_promos_item_code

### chains
chain_id (PK), name (text)

### fetch_runs
id (PK), chain_id (text), run_at (timestamp), status (text), files_loaded (int), 
items_inserted (int), errors (int)

### fetch_store_runs
id (PK), fetch_run_id (FK→fetch_runs.id), chain_id (text), store_fk (FK→stores.id),
store_id (text), run_at (timestamp), files_loaded (int), items_inserted (int), status (text)

### item_chain_names
item_code (text), chain_id (text), name (text), canonical_name (text)

### city_canonical
city_norm (text), canonical (text)

## API (FastAPI, api/)
- Base URL: https://api-super.xxl.co.il
- Routers in api/routers/: search.py, coverage.py, promos.py, health.py
- Response models in api/models.py
- DB queries in db/query.py
- DB connection/bulk inserts in db/db.py
- Start: sudo systemctl restart scrp-api.service
- Logs: sudo journalctl -u scrp-api.service -f

## Frontend (React + Vite + TypeScript + Tailwind, web/)
- Served by nginx on Kamatera at super.xxl.co.il
- API calls in web/src/api/client.ts
- Main components: web/src/components/
- Deploy: .\scripts\deploy_frontend.ps1 (builds + uploads to Hostinger)
- NOTE: Hostinger is the live frontend host, NOT Kamatera nginx

## Scraper (Python, scraper/)
- Registry: scraper/registry.py
- Base class: scraper/base.py (ChainScraper)
- Active stores: scraper/active_stores.yaml (source of truth for cron)
- Cron entry: scraper/cron_main.py
- Delta chains: DELTA_CHAINS in registry.py
- Run one chain: python3 -m scripts.run_one {chain_id} [--full]
- Seed one store: python3 -m scripts.seed_one_store {chain_id} {store_id}
- Cron timer: sudo systemctl status scrp-cron.timer (runs 10:00 IDT)

## Key conventions
- store_id is always zero-padded 3 digits (e.g. "073", "005") EXCEPT Carrefour which has mixed 3/4-digit IDs
- chain_id is always 13-digit string
- city_canonical is the source of truth for city data (NOT city_norm)
- DELTA_CHAINS use Price (delta) files daily; others use PriceFull
- New DB tables need GRANT SELECT,INSERT,UPDATE ON TABLE ... TO scrp_app in same migration
- Hebrew RTL in terminal is NEVER a bug
- PowerShell: use separate lines, not &&

## Common mistakes to avoid
- prices.price does NOT exist — column is item_price
- discount_price in promos is bundle price when min_qty > 1 (not single-item price)
- Never use city_norm for filtering — use city_canonical
- active_stores.yaml store_ids must match DB store_id padding exactly
- publishprice.py handles both Format A (chain-store-date) and Format B (chain-subchain-store-date) filenames

## Permissions (pre-authorized, no need to ask)
- Read any file in the repo
- Edit any file in web/, api/, scraper/, db/, scripts/, docs/
- Run git add, git commit, git push origin main
- Create new files anywhere in the repo
- Run deployment script .\scripts\deploy_frontend.ps1
- SSH commands are NOT available — server commands must be run manually by operator
