-- Adds a cross-vertical subscription tier to the shared `users` table.
-- users already holds every authenticated xxl.co.il identity (super + flights,
-- upserted from the Supabase JWT sub/email). Putting tier here — not a new
-- profiles table — means every vertical reads ONE value, no extra joins.
-- No billing exists yet: defaults to 'free'; 'paid' is set manually via SQL.
-- Idempotent — safe to re-run.

ALTER TABLE users ADD COLUMN IF NOT EXISTS tier TEXT NOT NULL DEFAULT 'free';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_tier_check'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_tier_check CHECK (tier IN ('free', 'paid'));
    END IF;
END $$;
