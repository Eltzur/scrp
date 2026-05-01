-- Migration: users and saved_baskets tables for session 9b auth + saved baskets.
-- Run manually on Railway: psql $DATABASE_URL -f db/migrations/add_users_saved_baskets.sql
-- Idempotent: IF NOT EXISTS throughout.

CREATE TABLE IF NOT EXISTS users (
    id           TEXT PRIMARY KEY,           -- Supabase user UUID
    email        TEXT NOT NULL UNIQUE,
    display_name TEXT,
    created_at   TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at   TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS saved_baskets (
    id         SERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    items      JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_saved_baskets_user_id ON saved_baskets(user_id);
