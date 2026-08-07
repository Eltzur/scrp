-- SU10A-7: three promo signals the parser now extracts - club restriction,
-- purchase cap, and the "N for M" offer quantity. Additive and non-destructive;
-- table-level GRANTs already cover new columns, so no new GRANT is needed.
ALTER TABLE promos ADD COLUMN IF NOT EXISTS club_id    INTEGER;
ALTER TABLE promos ADD COLUMN IF NOT EXISTS max_qty    NUMERIC;
ALTER TABLE promos ADD COLUMN IF NOT EXISTS gift_count INTEGER;
