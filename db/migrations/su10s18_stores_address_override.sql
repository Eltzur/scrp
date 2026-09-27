-- SU10S-18 — stores.address_override: a hand-corrected address the nightly
-- cron cannot overwrite.
--
-- WHY A SEPARATE COLUMN (measured SU10S-18, real load_stores() against the
-- live feeds, rolled back): the store upserts do
--     address = COALESCE(excluded.address, stores.address)
-- so a feed NULL never overwrites, but ANY non-NULL value does - including ''.
--   Cerberus / PublishPrice (Osher Ad, Carrefour, Rami Levy, ...): a hand-set
--       address is replaced by the feed's value every night.
--   binaprojects (King Store, Shefa Birkat, Shuk HaIr): passes "" always, so a
--       hand-set address is blanked to '' every night.
--   Victory / Shufersal / Hazi Hinam: never write address at all.
-- A manual fix written to `address` is therefore only safe by accident.
--
-- NOTHING IN THE LOADERS WRITES THIS COLUMN, and nothing can by accident:
-- every write to `stores` names its columns explicitly (no wildcard, ORM,
-- to_sql or COPY). Verified SU10S-18 across all 7 INSERT paths and every
-- UPDATE. Consumers read the effective address as
--     COALESCE(NULLIF(btrim(address_override), ''), address)
-- (scripts/geo_nominatim.py).
--
-- ADDITIVE AND IDEMPOTENT. Run as scrp_app, which owns `stores`:
--     psql "$DATABASE_URL" -f db/migrations/su10s18_stores_address_override.sql
-- Back up first (outside the repo):
--     pg_dump -t stores -Fc "$DATABASE_URL" -f ~/backups/stores-<date>.dump

BEGIN;

ALTER TABLE stores ADD COLUMN IF NOT EXISTS address_override text;

COMMENT ON COLUMN stores.address_override IS
    'Hand-corrected street address; wins over the feed-owned `address`. '
    'Never written by the scrapers (SU10S-18).';

COMMIT;
