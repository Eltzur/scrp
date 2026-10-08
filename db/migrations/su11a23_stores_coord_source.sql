-- SU11A-23 — stores: where each coordinate comes from, who verified it, and a display label.
--
-- Decision (Dude, 2026-10-08): Google results are the single source of truth for store
-- coordinates (coordinates first, address text second). OSM / Nominatim / Overture are retired
-- as coordinate sources. Loaded by scripts/import_google_coordinates.py.
--
--   coord_source  where the stored lat/lon came from (allow-list below)
--   verified_at   when that coordinate was loaded or confirmed
--   verified_by   the session or person that did it (e.g. 'SU11A-23')
--   geo_label     the human-readable address that goes with the coordinate (secondary to it)
--
-- NOT APPLIED IN SU11A-23 PHASE 1. ADDITIVE AND IDEMPOTENT. Run as scrp_app, which owns `stores`:
--     psql "$DATABASE_URL" -f db/migrations/su11a23_stores_coord_source.sql
-- Back up first (outside the repo):
--     pg_dump -t stores -Fc "$DATABASE_URL" -f ~/backups/pre-su11a23-migration-<date>.dump

BEGIN;

ALTER TABLE stores ADD COLUMN IF NOT EXISTS coord_source text;
ALTER TABLE stores ADD COLUMN IF NOT EXISTS verified_at  timestamptz;
ALTER TABLE stores ADD COLUMN IF NOT EXISTS verified_by  text;
ALTER TABLE stores ADD COLUMN IF NOT EXISTS geo_label    text;

-- Adding a source is a DELIBERATE change: extend this list, the importer's ALLOWED_SOURCES
-- (scripts/import_google_coordinates.py) and the geocoder guards together, in one reviewed commit.
ALTER TABLE stores DROP CONSTRAINT IF EXISTS stores_coord_source_check;
ALTER TABLE stores ADD CONSTRAINT stores_coord_source_check
    CHECK (coord_source IS NULL OR coord_source IN ('osm_house', 'manual_pin', 'google_exact', 'google_reviewed'));

-- Backfill the provenance of what is already stored (only rows not yet labelled).
UPDATE stores SET coord_source = 'osm_house'
 WHERE coord_source IS NULL AND geo_source = 'nominatim' AND geo_precision = 'address';
UPDATE stores SET coord_source = 'manual_pin'
 WHERE coord_source IS NULL AND geo_source = 'manual';

COMMENT ON COLUMN stores.coord_source IS
    'Where lat/lon came from: osm_house | manual_pin | google_exact | google_reviewed (SU11A-23). '
    'Adding a value is a deliberate change (CHECK constraint + importer allow-list + geocoder guards).';
COMMENT ON COLUMN stores.verified_at IS 'When the stored coordinate was loaded or confirmed (SU11A-23).';
COMMENT ON COLUMN stores.verified_by IS 'Session or person that loaded/confirmed the coordinate, e.g. SU11A-23.';
COMMENT ON COLUMN stores.geo_label   IS 'Human-readable address for the stored coordinate; secondary to lat/lon (SU11A-23).';

COMMIT;
