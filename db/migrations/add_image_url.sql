-- Migration: add product_image_url and name_source columns to items table.
-- Idempotent: IF NOT EXISTS safe to re-run on both SQLite (3.37+) and PostgreSQL.

ALTER TABLE items ADD COLUMN IF NOT EXISTS product_image_url TEXT;
ALTER TABLE items ADD COLUMN IF NOT EXISTS name_source TEXT DEFAULT 'chain';
