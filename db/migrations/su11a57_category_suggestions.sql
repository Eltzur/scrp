-- SU11A-57 — user category suggestions (category_suggestions).
--
-- NOT APPLIED IN SU11A-57. ADDITIVE AND IDEMPOTENT. ONE TRANSACTION.
-- NEEDS su11a52_catalog.sql FIRST (categories is referenced); the DO block below
-- stops the transaction with a clear message when it is missing.
-- APPLY BEFORE deploying the SU11A-57 API: POST /items/{code}/category-suggestions
-- and the admin suggestion queue answer 500 without this table. The rest of the
-- SU11A-57 API (category read, tree, admin category edits) only needs su11a52.
--
-- Contents:
--   category_suggestions  one row per user suggestion "this item belongs in X".
--     user_id               the suggester; ON DELETE CASCADE, so DELETE /account
--                           (which deletes the users row) removes every suggestion
--                           the user made. The admin API never returns it.
--     current_category_id   the item's category when the user suggested (NULL when
--                           the item had no label); a record, not checked later.
--     suggested_category_id an active categories id, different from the current one
--                           (the API checks both; the FK only checks it exists).
--     comment               optional, at most 200 characters. A comment that hits
--                           rating_blacklist is not stored (NULL) and
--                           comment_blocked = true; the user is not told (same
--                           do-not-surface rule as ratings).
--     status                open / accepted / rejected; decided_at set on a decision.
--   One OPEN suggestion per (user_id, item_code): a partial unique index. A user may
--   suggest again for the same item after a decision.
--
-- No FK from item_code to items (as in su11a36 / su11a52): the price loader's
-- deletes must not depend on this table.
--
-- OWNER scrp_app (the role in DATABASE_URL): the API reads and writes it; ownership
-- covers the sequence too.
--
-- Apply (postgres cannot read files under ~dude, so pipe it rather than psql -f):
--     cat ~/scrp/db/migrations/su11a57_category_suggestions.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.categories') IS NULL THEN
        RAISE EXCEPTION 'categories is missing: apply db/migrations/su11a52_catalog.sql first';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS category_suggestions (
    id                    BIGSERIAL   PRIMARY KEY,
    item_code             TEXT        NOT NULL,
    user_id               TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    current_category_id   TEXT        NULL REFERENCES categories(id),
    suggested_category_id TEXT        NOT NULL REFERENCES categories(id),
    comment               TEXT        NULL CHECK (comment IS NULL OR char_length(comment) <= 200),
    comment_blocked       BOOLEAN     NOT NULL DEFAULT false,
    status                TEXT        NOT NULL DEFAULT 'open'
                                      CHECK (status IN ('open', 'accepted', 'rejected')),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at            TIMESTAMPTZ NULL
);

-- One open suggestion per user and item (409 already_suggested in the API).
CREATE UNIQUE INDEX IF NOT EXISTS uq_category_suggestions_open
    ON category_suggestions (user_id, item_code) WHERE status = 'open';
-- The admin queue: open suggestions grouped by item; accept / reject by item.
CREATE INDEX IF NOT EXISTS idx_category_suggestions_queue
    ON category_suggestions (status, item_code);
-- The per-user daily limit (20 / 24 h).
CREATE INDEX IF NOT EXISTS idx_category_suggestions_user
    ON category_suggestions (user_id, created_at DESC);

ALTER TABLE category_suggestions OWNER TO scrp_app;

COMMIT;

-- ---------------------------------------------------------------------------
-- ROLLBACK (manual; NOT part of the migration). Deploy the pre-SU11A-57 API
-- first, or the suggestion endpoints answer 500. Drops every suggestion.
-- ---------------------------------------------------------------------------
-- BEGIN;
-- DROP TABLE IF EXISTS category_suggestions;
-- COMMIT;
