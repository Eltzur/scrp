-- SU10S-10 — store coordinates for the "nearby stores" feature.
--
-- ADDITIVE AND IDEMPOTENT. Every column is nullable (except is_physical,
-- which has a default), so no existing INSERT can break: all six scraper
-- paths use explicit column lists and their ON CONFLICT clauses name only
-- store_name / city / city_norm / address, never a wildcard (verified
-- SU10S-10 Step 0a). Coordinates therefore survive the daily upsert.
--
-- Run as scrp_app, which owns `stores` — same as su10r1_ratings.sql.
--
--     psql "$DATABASE_URL" -f db/migrations/su10s10_store_coordinates.sql
--
-- Back up first (outside the repo):
--     pg_dump -t stores -Fc "$DATABASE_URL" -f ~/backups/stores-<date>.dump

BEGIN;

ALTER TABLE stores
    ADD COLUMN IF NOT EXISTS lat           double precision,
    ADD COLUMN IF NOT EXISTS lon           double precision,
    ADD COLUMN IF NOT EXISTS geo_precision text,
    ADD COLUMN IF NOT EXISTS geo_source    text,
    -- The exact "address | city" string that produced these coordinates.
    -- The scrapers keep address fresh via COALESCE(excluded.address, …), so an
    -- upstream address change would otherwise leave a stale coordinate with
    -- nothing to detect it. Comparing this against the current address is how
    -- the weekly job knows to re-geocode.
    ADD COLUMN IF NOT EXISTS geo_input     text,
    ADD COLUMN IF NOT EXISTS geocoded_at   timestamptz,
    -- Online / fulfilment / pickup rows. NOT derived from a name regex at
    -- read time: the patterns disagree across chains (see the UPDATE below)
    -- and a new chain will spell it a fourth way. Set once, by id.
    ADD COLUMN IF NOT EXISTS is_physical   boolean NOT NULL DEFAULT true;

-- CHECK constraints are not IF NOT EXISTS-able before PG 16; add them only
-- when absent so a re-run is a no-op.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'stores_geo_precision_chk') THEN
        ALTER TABLE stores ADD CONSTRAINT stores_geo_precision_chk
            CHECK (geo_precision IS NULL OR geo_precision IN ('address','street','city'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'stores_geo_source_chk') THEN
        ALTER TABLE stores ADD CONSTRAINT stores_geo_source_chk
            CHECK (geo_source IS NULL OR geo_source IN ('cbs_centroid','nominatim','manual'));
    END IF;
END $$;

-- Only ever scanned for "rows still needing coordinates", which is a small
-- and shrinking set; partial index keeps it tiny.
CREATE INDEX IF NOT EXISTS stores_needs_geo_idx
    ON stores (id) WHERE is_physical AND lat IS NULL;

-- ---------------------------------------------------------------------------
-- Non-physical stores. All 26 rows matching online/fulfilment wording, listed
-- by id rather than by pattern so the rule cannot drift.
--
-- Three of these currently serve prices (the SU10S-9 pilot's three). The other
-- 23 are idle today, but MOST CARRY A REAL city_canonical — so a city-centroid
-- fill would place them in real cities and they would enter the coordinates
-- feed the moment they start serving. שוק העיר 304 is the clearest example: its
-- city is ירושלים, so it would look like an ordinary Jerusalem branch.
-- ---------------------------------------------------------------------------
UPDATE stores SET is_physical = false WHERE id IN (
    -- serving today
    39248,  -- קרפור   "קרפור אונליין כפר סבא"
    6116,   -- שופרסל  "413 - שופרסל ONLINE"   (city literally 'אונליין')
    18848,  -- שוק העיר "304 אונליין - רמות"   (city ירושלים — the dangerous one)
    -- idle, same nature
    71,     -- ויקטורי   "אינטרנט"
    2143,   -- רמי לוי   "מרלוג אינטרנט"        (logistics centre)
    4574,   -- שופרסל    "413 - שופרסל ONLINE"  (duplicate row)
    18788,  -- קינג סטור "50 אינטרנט"
    23328,  -- יוחננוף   "הדרים פיקאפ"
    61544,  -- קרפור     "קרפור אונליין כפר סבא" (duplicate row)
    -- טיב טעם fulfilment/picking sites ("ליקוט")
    17121, 17122, 17123, 17124, 17125, 17126, 17127,
    -- שוק העיר online branches
    18849, 18850, 18851, 18852, 18853, 18854, 18855, 18856, 18857, 18858
);

COMMIT;
