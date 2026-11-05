-- SU11A-65: trigram indexes for the promo search text (db/query.py promo_match_sql).
--
-- The promo lists' search (/promos/list, /promos/grouped, /promos/promoted and
-- /admin/promos/search) matches q against the promotion description and the
-- product name with ILIKE '%q%'. Without an index that is an ILIKE over every
-- active promo row (~840k): 3.3-4.0 s on production on 5 Nov 2026. With these
-- two indexes the planner combines idx_promos_description_trgm with
-- idx_promos_item_code (the name test is written as "item_code = ANY(the
-- items whose name matches)", which reads idx_items_name_trgm): the same rows.
--
-- Apply as the postgres superuser, OUTSIDE a transaction (CREATE INDEX
-- CONCURRENTLY cannot run inside one; psql runs each statement on its own
-- unless given -1 / --single-transaction, so do NOT pass -1):
--   cat ~/scrp/db/migrations/su11a65_promo_search.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
-- CONCURRENTLY: the promo load and the API keep reading and writing during the
-- build. If a build fails it can leave an INVALID index behind, which
-- IF NOT EXISTS would then skip on a re-run: check pg_index.indisvalid
-- (runbook step 5) and, if false, run the rollback file and apply again.
-- Rollback: db/migrations/su11a65_promo_search_rollback.sql.
--
-- pg_trgm 1.6 is already installed on production (SU11A-34 / SU11A-36); the
-- statement below is then a no-op. No GRANTs: indexes need none.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_promos_description_trgm
    ON promos USING gin (promo_description gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_items_name_trgm
    ON items USING gin (item_name gin_trgm_ops);

ANALYZE promos;
ANALYZE items;
