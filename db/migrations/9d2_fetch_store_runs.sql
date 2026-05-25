-- 9d-2: per-store coverage metric
-- One row per store per cron run. fetch_runs stays per-chain; this is the per-store sibling.

CREATE TABLE IF NOT EXISTS fetch_store_runs (
    id              SERIAL PRIMARY KEY,
    fetch_run_id    INTEGER NOT NULL REFERENCES fetch_runs(id) ON DELETE CASCADE,
    chain_id        TEXT NOT NULL,
    store_fk        INTEGER NOT NULL REFERENCES stores(id),
    store_id        TEXT NOT NULL,
    run_at          TEXT NOT NULL,
    files_loaded    INTEGER DEFAULT 0,
    items_inserted  INTEGER DEFAULT 0,
    status          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fsr_chain_runat ON fetch_store_runs(chain_id, run_at);
CREATE INDEX IF NOT EXISTS idx_fsr_store_runat ON fetch_store_runs(store_fk, run_at);

CREATE OR REPLACE VIEW v_store_coverage_72h AS
SELECT
    chain_id,
    COUNT(DISTINCT store_fk) FILTER (WHERE status = 'loaded') AS stores_loaded_72h,
    COUNT(DISTINCT store_fk)                                  AS stores_seen_72h
FROM fetch_store_runs
WHERE run_at >= to_char(now() - interval '72 hours', 'YYYY-MM-DD"T"HH24:MI:SS')
GROUP BY chain_id;
