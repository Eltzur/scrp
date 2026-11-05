-- SU11A-65 rollback: drop the promo search trigram indexes.
-- Apply as postgres, outside a transaction (DROP INDEX CONCURRENTLY):
--   cat ~/scrp/db/migrations/su11a65_promo_search_rollback.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
-- The SU11A-65 code works without them (the same rows, as slow as before).
-- pg_trgm stays: search v2 (su11a36) uses it.

DROP INDEX CONCURRENTLY IF EXISTS idx_promos_description_trgm;
DROP INDEX CONCURRENTLY IF EXISTS idx_items_name_trgm;
