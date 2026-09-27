-- SU10S-17 — stores.last_loaded_at, the freshness signal for the read-path guard.
--
-- INVARIANT: last_loaded_at = max(run_at::timestamptz) over that store's
-- fetch_store_runs rows with status = 'loaded'. NULL = never loaded.
-- The backfill below establishes it; scraper/base.py and scraper/shufersal.py
-- maintain it, in the same transaction as each 'loaded' fetch_store_runs row,
-- using that row's own run_at (not now()). Nothing else writes this column.
--
-- Why denormalised (SU10S-14): computing liveness per request from
-- fetch_store_runs (108K rows) cost 78.5 ms on a 3.5 ms query. A column on the
-- already-joined stores row costs a predicate.
--
-- fetch_store_runs.run_at is TEXT (Python isoformat()), hence the cast. All
-- 108,215 rows were verified to parse before this was written.
--
-- ADDITIVE AND IDEMPOTENT: nullable column; every scraper INSERT into stores
-- uses an explicit column list (SU10S-10 Step 0a), so none can break. The
-- backfill only touches rows whose value differs, so a re-run updates 0.
--
-- Run as scrp_app, which owns `stores`:
--     psql "$DATABASE_URL" -f db/migrations/su10s17_stores_last_loaded_at.sql
-- Back up first (outside the repo):
--     pg_dump -t stores -Fc "$DATABASE_URL" -f ~/backups/stores-<date>.dump

BEGIN;

ALTER TABLE stores ADD COLUMN IF NOT EXISTS last_loaded_at timestamptz;

COMMENT ON COLUMN stores.last_loaded_at IS
    'max(run_at) of this store''s status=loaded fetch_store_runs rows; NULL = never loaded. '
    'Written only by the scraper alongside that row (SU10S-17).';

UPDATE stores s
SET    last_loaded_at = x.last
FROM (
    SELECT store_fk, max(run_at::timestamptz) AS last
    FROM   fetch_store_runs
    WHERE  status = 'loaded'
    GROUP  BY store_fk
) x
WHERE  x.store_fk = s.id
  AND  s.last_loaded_at IS DISTINCT FROM x.last;

COMMIT;
