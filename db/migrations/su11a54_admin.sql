-- SU11A-54 — admin console phase 1: the audit log of admin actions.
--
-- NOT APPLIED IN SU11A-54. ADDITIVE AND IDEMPOTENT. ONE TRANSACTION.
-- APPLY BEFORE deploying the SU11A-54 API: every admin write (moderate,
-- ban-author) inserts its admin_audit row in the same transaction as the change,
-- so without this table those requests fail with 500 and change nothing.
-- Read-only admin endpoints (queue, detail, status) work without it;
-- GET /admin/audit and the audit part of GET /admin/ratings/history do not.
--
-- Contents:
--   admin_audit   one row per admin write. No email and no raw user id:
--                 actor_hash = sha256(fixed salt in api/admin_audit.py + the
--                 admin's Supabase user id), ip_hash the same for the client IP.
--                 Retention: proposed 1 year (docs/store_privacy_inventory.md);
--                 no purge job yet.
--
-- GRANTS (lesson from 9d-2, see su10r1_ratings.sql): migrations run as the postgres
-- superuser and the API connects as scrp_app, so the grants are in this file.
-- The API only INSERTs and SELECTs: no UPDATE / DELETE grant, so the API role
-- cannot rewrite the log.
-- (postgres cannot read files under ~dude, so pipe it rather than psql -f):
--     cat ~/scrp/db/migrations/su11a54_admin.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1

BEGIN;

CREATE TABLE IF NOT EXISTS admin_audit (
    id          BIGSERIAL   PRIMARY KEY,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_hash  TEXT        NOT NULL,
    action      TEXT        NOT NULL,
    target_type TEXT        NULL,
    target_id   TEXT        NULL,
    detail      JSONB       NULL,
    ip_hash     TEXT        NULL
);

-- GET /admin/audit pages newest first.
CREATE INDEX IF NOT EXISTS idx_admin_audit_at ON admin_audit (at DESC);
-- GET /admin/ratings/history looks up the last action per rating.
CREATE INDEX IF NOT EXISTS idx_admin_audit_target ON admin_audit (target_type, target_id, at DESC);

-- ---------------------------------------------------------------------------
-- GRANTS — table AND sequence.
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT ON admin_audit TO scrp_app;
GRANT USAGE, SELECT ON SEQUENCE admin_audit_id_seq TO scrp_app;

COMMIT;

-- ---------------------------------------------------------------------------
-- ROLLBACK (manual; NOT part of the migration). Deploy the pre-SU11A-54 API
-- first, or every admin write answers 500. Drops the whole audit log.
-- ---------------------------------------------------------------------------
-- BEGIN;
-- DROP TABLE IF EXISTS admin_audit;
-- COMMIT;
