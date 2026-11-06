-- SU11A-69 — admin statistics: daily AGGREGATES only (stats_daily) and the
-- per-source state of the collector (stats_runs).
--
-- NOT APPLIED IN SU11A-69. ADDITIVE AND IDEMPOTENT. ONE TRANSACTION.
-- Rollback: db/migrations/su11a69_stats_rollback.sql.
--
-- Privacy rule (CLAUDE.md): these tables hold counts per day, never an IP
-- address, a user agent, a full URL, a query string, a user id or an email.
-- The only free text is
--   stats_daily.dimension   a host, a platform, a path WITHOUT its query string,
--                           a referrer DOMAIN, or '' (scripts/stats_logs.py);
--   stats_runs.last_error   the class / HTTP status of the last failure, with
--                           anything that looks like a token removed
--                           (scripts/stats_collect.py safe_error).
--
--   stats_daily   one value per (source, metric, dimension, day); re-runs upsert.
--     source      web | api | ga4 | play | appstore
--     metric      e.g. page_views, visitors, bot_page_views, top_path, referrer,
--                 calls, errors_5xx, users, sessions, installs, downloads ...
--     dimension   '' when the metric has none
--     day         the Israel-time day the value counts
--   stats_runs    one row per source: last run / success / error, the latest
--                 day with data (as_of) and status ok | error | not_configured.
--
-- Size: about 200 rows a day, so no retention job (a year is ~75k tiny rows).
--
-- OWNER scrp_app (the role in DATABASE_URL): the job writes, the API reads.
--
-- Apply (postgres cannot read files under ~dude, so pipe it rather than psql -f):
--     cat ~/scrp/db/migrations/su11a69_stats.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1

BEGIN;

CREATE TABLE IF NOT EXISTS stats_daily (
    source      TEXT        NOT NULL CHECK (source IN ('web', 'api', 'ga4', 'play', 'appstore')),
    metric      TEXT        NOT NULL CHECK (length(metric) BETWEEN 1 AND 40),
    dimension   TEXT        NOT NULL DEFAULT '' CHECK (length(dimension) <= 200),
    day         DATE        NOT NULL,
    value       BIGINT      NOT NULL CHECK (value >= 0),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source, metric, dimension, day)
);

CREATE INDEX IF NOT EXISTS idx_stats_daily_day ON stats_daily (day, source);

CREATE TABLE IF NOT EXISTS stats_runs (
    source           TEXT        PRIMARY KEY CHECK (source IN ('web', 'api', 'ga4', 'play', 'appstore')),
    status           TEXT        NOT NULL CHECK (status IN ('ok', 'error', 'not_configured')),
    last_run_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_success_at  TIMESTAMPTZ NULL,
    last_error_at    TIMESTAMPTZ NULL,
    last_error       TEXT        NULL CHECK (length(last_error) <= 300),
    as_of            DATE        NULL,
    note             TEXT        NULL CHECK (length(note) <= 300)
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scrp_app') THEN
        ALTER TABLE stats_daily OWNER TO scrp_app;
        ALTER TABLE stats_runs  OWNER TO scrp_app;
    END IF;
END $$;

COMMIT;
