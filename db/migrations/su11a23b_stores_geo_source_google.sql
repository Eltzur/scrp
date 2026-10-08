-- SU11A-23b — allow geo_source = 'google' in stores_geo_source_chk.
--
-- WHY: SU10S-10 (su10s10_store_coordinates.sql) created stores_geo_source_chk with
-- ('cbs_centroid', 'nominatim', 'manual'). SU11A-23 loads the Google coordinates with
-- geo_source = 'google'; the first --apply was refused by this constraint and rolled back cleanly.
-- LESSON: a new geo_source value must extend this constraint (and coord_source values must extend
-- stores_coord_source_check) in the same reviewed change as the code that writes it.
--
-- Run as scrp_app, which owns `stores`:
--     psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/su11a23b_stores_geo_source_google.sql

BEGIN;

ALTER TABLE stores DROP CONSTRAINT IF EXISTS stores_geo_source_chk;
ALTER TABLE stores ADD CONSTRAINT stores_geo_source_chk
    CHECK (geo_source IS NULL OR geo_source IN ('cbs_centroid', 'nominatim', 'manual', 'google'));

COMMIT;
