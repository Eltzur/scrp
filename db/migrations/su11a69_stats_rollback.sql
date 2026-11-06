-- SU11A-69 rollback: drop the statistics tables (aggregates only; nothing else
-- reads them). Stop the timer first: sudo systemctl disable --now scrp-stats.timer
--   cat ~/scrp/db/migrations/su11a69_stats_rollback.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
-- The SU11A-69 API answers /admin/stats with every source "never_run" without them.

BEGIN;
DROP TABLE IF EXISTS stats_daily;
DROP TABLE IF EXISTS stats_runs;
COMMIT;
