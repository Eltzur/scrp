-- 9d-8: add city_canonical column for CBS-verified canonical city names
ALTER TABLE stores ADD COLUMN IF NOT EXISTS city_canonical TEXT;
CREATE INDEX IF NOT EXISTS idx_stores_city_canonical ON stores(city_canonical);
GRANT UPDATE ON stores TO scrp_app;
