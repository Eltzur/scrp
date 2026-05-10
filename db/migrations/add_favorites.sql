-- Migration: favorites table for session 9c.
-- Run manually on Railway via the Query editor.
-- Idempotent: IF NOT EXISTS throughout.

CREATE TABLE IF NOT EXISTS favorites (
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    barcode    TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    PRIMARY KEY (user_id, barcode)
);

CREATE INDEX IF NOT EXISTS idx_favorites_user_id ON favorites(user_id);
