-- SU11A-28 — deleted_accounts: one row per account-deletion request (DELETE /account).
--
-- NOT APPLIED IN SU11A-28. ADDITIVE AND IDEMPOTENT.
-- MUST BE APPLIED BEFORE the SU11A-28 API code is deployed: api/auth.py looks this
-- table up on every authenticated request, and without it those requests fail.
--
-- Rows:
--   user_id          the Supabase auth user id (users.id is TEXT; Supabase ids are UUIDs)
--   requested_at     when DELETE /account ran its database step
--   auth_deleted_at  when the Supabase auth user was deleted; NULL = still pending
--   attempts         failed Supabase delete attempts so far
--   last_error       a short error code only (e.g. 'timeout', 'http_500', 'config') —
--                    never a secret, never an email
-- No email column, by design: the row only blocks a deleted account's still-valid
-- token from recreating its users row, and drives the retry sweep
-- (scripts/sweep_account_deletes.py), which purges completed rows after 7 days.
--
-- GRANTS (lesson from 9d-2, see su10r1_ratings.sql): migrations run as the postgres
-- superuser and the API connects as scrp_app, so the grant is in this file.
-- (postgres cannot read files under ~dude, so pipe it rather than psql -f):
--     cat ~/scrp/db/migrations/su11a28_deleted_accounts.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1

BEGIN;

CREATE TABLE IF NOT EXISTS deleted_accounts (
    user_id          UUID        PRIMARY KEY,
    requested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    auth_deleted_at  TIMESTAMPTZ NULL,
    attempts         INTEGER     NOT NULL DEFAULT 0,
    last_error       TEXT        NULL
);

CREATE INDEX IF NOT EXISTS idx_deleted_accounts_pending
    ON deleted_accounts (requested_at)
    WHERE auth_deleted_at IS NULL;

GRANT SELECT, INSERT, UPDATE, DELETE ON deleted_accounts TO scrp_app;

COMMIT;
