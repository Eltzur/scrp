-- Performance indexes added in session 9d-10 (June 2026).
-- These were created CONCURRENTLY on the live server; this file is the
-- canonical record.  Re-running is safe: all statements use IF NOT EXISTS.

-- Covering index so city-filtered price queries can do index-only scans on
-- the prices table, avoiding ~1.8M random heap reads per search.
-- Used by the _PRICE_SQL_CITY path in db/query.py (fetch_prices with city).
CREATE INDEX IF NOT EXISTS idx_prices_item_store_cover
    ON prices(item_code, store_fk)
    INCLUDE (item_price, unit_of_measure_price, price_update_date);

GRANT SELECT ON prices TO scrp_app;
