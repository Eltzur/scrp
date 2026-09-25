-- SU10R-1: item ratings, reports, and a moderation blacklist.
--
-- Ratings are scoped to an item_code on a 1-3 scale:
--   1 = poor (X), 2 = neutral (XX), 3 = very good (XXX)
--
-- THE PERCENTAGE IS NEVER STORED. The API computes it at read time as
-- avg(rating)/3*100, the same "store raw, stay re-fixable" rule the promo
-- discount logic already follows (db/query.py). Storing a derived percentage
-- would freeze today's formula into historical rows.
--
-- GRANTS (lesson from 9d-2): migrations run as the postgres superuser, but the
-- scraper and API connect as scrp_app. Every new table AND every new sequence
-- must be granted in this same file or the app gets "permission denied".
-- The sequence grant matters as much as the table grant — INSERT fails without
-- USAGE on a SERIAL sequence. GRANT is idempotent, hence no IF NOT EXISTS.

-- ---------------------------------------------------------------------------
-- ratings
-- ---------------------------------------------------------------------------
--
-- One row per (user_id, item_code); re-rating UPDATEs in place. There is no
-- history table by design — this pass keeps only the current opinion.
--
-- item_code is deliberately NOT a foreign key to items(item_code). The catalog
-- is rebuilt continuously by the scrapers, and an FK would either block a
-- rating for an item that has not been ingested yet or, with ON DELETE CASCADE,
-- silently destroy user-authored content when a chain stops publishing a
-- product. User content must outlive catalog churn.

CREATE TABLE IF NOT EXISTS ratings (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_code   TEXT     NOT NULL,
    rating      SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 3),
    comment     TEXT,
    -- active        — visible publicly
    -- pending_review — flagged, awaiting a human; NOT public
    -- hidden        — blocked (blacklist or moderator); NOT public
    status      TEXT     NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'pending_review', 'hidden')),
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT ratings_user_item_uniq UNIQUE (user_id, item_code)
);

-- The public read path is always "active ratings for one item_code", so the
-- index carries status to keep it index-only for that filter.
CREATE INDEX IF NOT EXISTS idx_ratings_item_status ON ratings (item_code, status);
-- Moderation queue: everything not active, newest first.
CREATE INDEX IF NOT EXISTS idx_ratings_status_created ON ratings (status, created_at DESC);

-- ---------------------------------------------------------------------------
-- rating_reports
-- ---------------------------------------------------------------------------
--
-- Deliberately NO uniqueness on (rating_id, reporter_user_id): the same rating
-- being reported by many users is the signal worth having, and ten reports must
-- be distinguishable from one.
--
-- reporter_user_id is NULLable purely so a blacklist auto-hide can file a
-- system-generated report with no human author. ON DELETE SET NULL rather than
-- CASCADE keeps the moderation record intact if the reporting account is later
-- deleted — losing the report would lose the reason the content was hidden.

CREATE TABLE IF NOT EXISTS rating_reports (
    id                SERIAL PRIMARY KEY,
    rating_id         INTEGER NOT NULL REFERENCES ratings(id) ON DELETE CASCADE,
    reporter_user_id  TEXT REFERENCES users(id) ON DELETE SET NULL,
    reason            TEXT,
    -- 'user' = a human pressed report; 'blacklist' = automatic at submission.
    source            TEXT NOT NULL DEFAULT 'user'
                      CHECK (source IN ('user', 'blacklist')),
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rating_reports_rating ON rating_reports (rating_id);

-- ---------------------------------------------------------------------------
-- rating_blacklist
-- ---------------------------------------------------------------------------
--
-- A TABLE, not a constant in the source. Moderation vocabulary changes far more
-- often than code ships, and a deploy (plus a gunicorn restart) to block one
-- new slur is the wrong cost. A table is editable with one INSERT.
--
-- `term` is matched case-insensitively as a substring by the API. Kept as plain
-- text rather than regex on purpose: the list is meant to be editable by
-- someone who is not debugging a regex against Hebrew word boundaries.

CREATE TABLE IF NOT EXISTS rating_blacklist (
    id         SERIAL PRIMARY KEY,
    term       TEXT NOT NULL UNIQUE,
    note       TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- GRANTS — required, see header note. One per table AND per sequence.
-- ---------------------------------------------------------------------------

GRANT SELECT, INSERT, UPDATE, DELETE ON ratings          TO scrp_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON rating_reports   TO scrp_app;
-- The app only ever reads the blacklist; edits are a DBA/admin action.
GRANT SELECT                          ON rating_blacklist TO scrp_app;

GRANT USAGE, SELECT ON SEQUENCE ratings_id_seq          TO scrp_app;
GRANT USAGE, SELECT ON SEQUENCE rating_reports_id_seq   TO scrp_app;
GRANT USAGE, SELECT ON SEQUENCE rating_blacklist_id_seq TO scrp_app;
