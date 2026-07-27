-- SU10A-1b: collapse gs1.products supplier_gln/retailer_gln into a single `gln`
--
-- The SU10A-1 dry run showed the live endpoint returns ONE `gln` field per row —
-- there is no supplier/retailer split. Keeping two columns that can never be
-- populated is a trap for the next reader, so this consolidates to one.
--
-- gs1.products is empty at time of writing, so there is no data migration: the
-- rename is purely structural. Written idempotently (DO blocks guarding the
-- non-IF-EXISTS-able DDL) so a re-run after a partial apply is safe.
--
-- No new GRANTs needed: renaming a column or index does not change table-level
-- privileges, and su10a1_gs1_catalog.sql already granted scrp_app on the schema.

-- 1. supplier_gln -> gln, but only if that is still the shape on disk.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'gs1' AND table_name = 'products' AND column_name = 'supplier_gln'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'gs1' AND table_name = 'products' AND column_name = 'gln'
    ) THEN
        ALTER TABLE gs1.products RENAME COLUMN supplier_gln TO gln;
        RAISE NOTICE 'renamed gs1.products.supplier_gln -> gln';
    END IF;
END $$;

-- 2. If neither existed (fresh table from a future edit of migration 1), add gln.
ALTER TABLE gs1.products ADD COLUMN IF NOT EXISTS gln TEXT;

-- 3. Drop the columns the API cannot fill. Safe: table is empty, and IF EXISTS
--    makes this a no-op once already applied.
ALTER TABLE gs1.products DROP COLUMN IF EXISTS supplier_gln;
ALTER TABLE gs1.products DROP COLUMN IF EXISTS retailer_gln;

-- 4. Carry the index name over so it still describes the column it covers.
--    A column rename keeps the index working but leaves the old name in place.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'gs1' AND indexname = 'idx_gs1_products_supplier_gln'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'gs1' AND indexname = 'idx_gs1_products_gln'
    ) THEN
        ALTER INDEX gs1.idx_gs1_products_supplier_gln RENAME TO idx_gs1_products_gln;
        RAISE NOTICE 'renamed index idx_gs1_products_supplier_gln -> idx_gs1_products_gln';
    END IF;
END $$;

-- 5. Safety net: if step 3 dropped the column the old index depended on, the
--    index went with it. Recreate against the surviving column.
CREATE INDEX IF NOT EXISTS idx_gs1_products_gln ON gs1.products (gln);
