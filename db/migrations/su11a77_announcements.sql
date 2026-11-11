-- SU11A-77: server-delivered app notices (for app 1.2.4, SU11B-8).
--
-- One row per platform scope: 'ios', 'android', 'both'. The public endpoint
-- GET /announcements/active?platform=ios|android returns the active row for
-- that platform (its own row first, else 'both'), or 204. No user data: the
-- request carries no identifier and the table holds only the notice text.
--
-- The API validates every save (api/routers/admin_announcements.py,
-- db/announcements.py): plain text only, no links or markup (Apple 3.1.1,
-- Play Billing); for 'ios' / 'both' no "בהרצה" / beta / trial wording (Apple
-- 2.2). The CHECKs below are the database's last line, lengths only.
-- `version` grows whenever the title or body changes, so a device shows a new
-- text once even if it dismissed the previous one.
--
-- OWNER scrp_app (the role in DATABASE_URL): the API reads and writes it, and
-- nothing else needs it. Not a Supabase table (no anon / authenticated grants).
--
-- Apply (postgres cannot read files under ~dude, so pipe it rather than psql -f):
--     cat ~/scrp/db/migrations/su11a77_announcements.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
-- Idempotent: a second run changes nothing.

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.admin_audit') IS NULL THEN
        RAISE EXCEPTION 'admin_audit is missing: apply db/migrations/su11a54_admin.sql first';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS app_announcements (
    id               SERIAL      PRIMARY KEY,
    platform         TEXT        NOT NULL UNIQUE CHECK (platform IN ('ios', 'android', 'both')),
    title            TEXT        NOT NULL DEFAULT '' CHECK (length(title) <= 60),
    body             TEXT        NOT NULL DEFAULT '' CHECK (length(body) <= 600),
    active           BOOLEAN     NOT NULL DEFAULT false,
    version          INTEGER     NOT NULL DEFAULT 0 CHECK (version >= 0),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by_hash  TEXT        NULL CHECK (updated_by_hash IS NULL OR length(updated_by_hash) = 64),
    -- an active notice always has text
    CONSTRAINT app_announcements_active_text CHECK (NOT active OR (length(title) > 0 AND length(body) > 0))
);

INSERT INTO app_announcements (platform) VALUES ('ios'), ('android'), ('both')
ON CONFLICT (platform) DO NOTHING;

ALTER TABLE app_announcements OWNER TO scrp_app;

COMMIT;

-- ---------------------------------------------------------------------------
-- ROLLBACK (manual; NOT part of the migration). The API then answers 204 on
-- /announcements/active (a missing table reads as "no notice") and the admin
-- screen shows an error. The audit rows stay in admin_audit.
-- ---------------------------------------------------------------------------
-- BEGIN;
-- DROP TABLE IF EXISTS app_announcements;
-- COMMIT;
