-- SU11A-44 — UGC stage 2 (designed in SU11A-42): user blocks, terms consent,
-- bans and moderator review state.
--
-- NOT APPLIED IN SU11A-44. ADDITIVE AND IDEMPOTENT. ONE TRANSACTION.
-- APPLY BEFORE deploying the SU11A-44 API: GET /items/{code}/ratings reads
-- user_blocks for signed-in callers, the rating / report endpoints read
-- users.banned_at and users.terms_version, and the moderation queue reads
-- ratings.reviewed_at. Without this file those requests fail.
--
-- Contents:
--   user_blocks              who blocked whose ratings (the blocker never learns
--                            the author's id; the API resolves it from a rating)
--   users.terms_version      terms version the user accepted (NULL = none recorded)
--   users.terms_accepted_at  when
--   users.banned_at          set by a moderator; a banned user cannot rate or report
--   ratings.reviewed_at      last moderator decision; reports filed after it put the
--                            rating back in the queue
--   rating_reports.source    gains 'block' (a block also files a report)
--
-- GRANTS (lesson from 9d-2, see su10r1_ratings.sql): migrations run as the postgres
-- superuser and the API connects as scrp_app, so the grants are in this file.
-- (postgres cannot read files under ~dude, so pipe it rather than psql -f):
--     cat ~/scrp/db/migrations/su11a44_ugc_blocks_terms_moderation.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1

BEGIN;

-- ---------------------------------------------------------------------------
-- user_blocks
-- ---------------------------------------------------------------------------
-- id is the opaque handle the client unblocks with. source_rating_id only labels
-- the row in GET /me/blocks (item name + comment excerpt); SET NULL keeps the
-- block when that rating is deleted. Both user columns CASCADE, so deleting
-- either account removes the row (DELETE /account needs no change).
CREATE TABLE IF NOT EXISTS user_blocks (
    id               SERIAL      PRIMARY KEY,
    blocker_id       TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    blocked_id       TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_rating_id INTEGER     NULL REFERENCES ratings(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT user_blocks_pair_uniq UNIQUE (blocker_id, blocked_id),
    CONSTRAINT user_blocks_not_self  CHECK (blocker_id <> blocked_id)
);
-- The unique pair index serves "WHERE blocker_id = :uid"; this one serves the
-- CASCADE when a blocked account is deleted.
CREATE INDEX IF NOT EXISTS idx_user_blocks_blocked ON user_blocks (blocked_id);

-- ---------------------------------------------------------------------------
-- users: terms consent + ban
-- ---------------------------------------------------------------------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_version     TEXT        NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMPTZ NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS banned_at         TIMESTAMPTZ NULL;

-- ---------------------------------------------------------------------------
-- ratings: last moderator decision
-- ---------------------------------------------------------------------------
ALTER TABLE ratings ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ NULL;

-- ---------------------------------------------------------------------------
-- rating_reports.source: add 'block'
-- ---------------------------------------------------------------------------
-- su10r1_ratings.sql declared the CHECK inline, so Postgres named it. Find every
-- CHECK on rating_reports that mentions source and drop it by its real name,
-- then add the new one under a fixed name. Re-running finds and replaces
-- rating_reports_source_check itself, so the file stays idempotent.
DO $$
DECLARE
    c record;
BEGIN
    FOR c IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'rating_reports'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%source%'
    LOOP
        EXECUTE format('ALTER TABLE rating_reports DROP CONSTRAINT %I', c.conname);
    END LOOP;
END
$$;
ALTER TABLE rating_reports ADD CONSTRAINT rating_reports_source_check
    CHECK (source IN ('user', 'blacklist', 'block'));

-- The queue asks "any report on this rating newer than reviewed_at"; the existing
-- idx_rating_reports_rating (rating_id) does not cover created_at.
CREATE INDEX IF NOT EXISTS idx_rating_reports_rating_created
    ON rating_reports (rating_id, created_at);

-- ---------------------------------------------------------------------------
-- GRANTS — one per table AND per sequence. users / ratings / rating_reports
-- already carry theirs (new columns inherit table privileges).
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON user_blocks TO scrp_app;
GRANT USAGE, SELECT ON SEQUENCE user_blocks_id_seq TO scrp_app;

COMMIT;

-- ---------------------------------------------------------------------------
-- ROLLBACK (manual; NOT part of the migration). Deploy the pre-SU11A-44 API first.
-- Drops every block, consent record and ban; 'block' reports must be removed
-- (or re-labelled) before the old CHECK can be restored.
-- ---------------------------------------------------------------------------
-- BEGIN;
-- DROP TABLE IF EXISTS user_blocks;
-- ALTER TABLE users   DROP COLUMN IF EXISTS terms_version;
-- ALTER TABLE users   DROP COLUMN IF EXISTS terms_accepted_at;
-- ALTER TABLE users   DROP COLUMN IF EXISTS banned_at;
-- ALTER TABLE ratings DROP COLUMN IF EXISTS reviewed_at;
-- DROP INDEX IF EXISTS idx_rating_reports_rating_created;
-- DELETE FROM rating_reports WHERE source = 'block';
-- ALTER TABLE rating_reports DROP CONSTRAINT IF EXISTS rating_reports_source_check;
-- ALTER TABLE rating_reports ADD  CONSTRAINT rating_reports_source_check
--     CHECK (source IN ('user', 'blacklist'));
-- COMMIT;
