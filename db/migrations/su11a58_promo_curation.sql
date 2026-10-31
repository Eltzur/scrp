-- SU11A-58 — promo curation: admin pins and hides (promo_curation).
--
-- NOT APPLIED IN SU11A-58. ADDITIVE AND IDEMPOTENT. ONE TRANSACTION.
-- NEEDS promos and stores (su10a5_promos.sql) and admin_audit (su11a54_admin.sql);
-- the DO block below stops the transaction with a clear message when one is missing.
-- The SU11A-58 API runs without this table: the public promo endpoints then
-- apply no curation, and the admin promo endpoints answer 500.
--
-- Identity. promos.id does NOT survive a daily reload (Shufersal deletes and
-- re-inserts a store's promos; the others upsert on (store_fk, item_code,
-- promo_id)). The stable key is the chain's own PromotionId: (chain_id,
-- promo_id). One PromotionId covers every store and item of that promotion, so
-- a pin or a hide applies to the whole promotion, in every branch.
--
-- Contents:
--   promo_curation   one row per admin decision.
--     kind             pin | hide
--     chain_id         stores.chain_id of the promotion (no FK: chains rows are
--                      upserted by the loader, and a pin outlives a feed hiccup)
--     promo_id         promos.promo_id (no FK: the promotion comes and goes with
--                      the daily data)
--     rank             pins only, 1..50; the API keeps active pins numbered
--                      1..n without gaps (inserting at N shifts the rest down)
--     starts_at        the pin / hide applies from here
--     ends_at          and until here (NULL = until removed)
--     sponsored        pins only: paid placement, the card shows "ממומן"
--     note             the admin's note / the hide reason, at most 200 characters
--     active           false = removed by an admin (kept for the record)
--     actor_hash       the admin, hashed as in admin_audit (no email, no user id)
--   Expiry needs no job: the read path ignores a row whose ends_at has passed
--   or whose promotion is no longer in promos, and the admin list shows both
--   as expired ("פג תוקף").
--   One ACTIVE row per (kind, chain_id, promo_id): a partial unique index.
--
-- Pricing. NOTHING here feeds search, compare, basket, the cheapest-price
-- ranking or any price: only the promo lists (/promos/grouped, /promos/today)
-- read this table.
--
-- OWNER scrp_app (the role in DATABASE_URL): the API reads and writes it;
-- ownership covers the sequence too.
--
-- Apply (postgres cannot read files under ~dude, so pipe it rather than psql -f):
--     cat ~/scrp/db/migrations/su11a58_promo_curation.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.promos') IS NULL OR to_regclass('public.stores') IS NULL THEN
        RAISE EXCEPTION 'promos / stores are missing: this is not the xxl_super database (su10a5_promos.sql)';
    END IF;
    IF to_regclass('public.admin_audit') IS NULL THEN
        RAISE EXCEPTION 'admin_audit is missing: apply db/migrations/su11a54_admin.sql first';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS promo_curation (
    id          BIGSERIAL   PRIMARY KEY,
    kind        TEXT        NOT NULL CHECK (kind IN ('pin', 'hide')),
    chain_id    TEXT        NOT NULL,
    promo_id    TEXT        NOT NULL,
    rank        SMALLINT    NULL,
    starts_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ends_at     TIMESTAMPTZ NULL,
    sponsored   BOOLEAN     NOT NULL DEFAULT false,
    note        TEXT        NULL CHECK (note IS NULL OR char_length(note) <= 200),
    active      BOOLEAN     NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_hash  TEXT        NOT NULL,
    CONSTRAINT promo_curation_rank CHECK (
        (kind = 'pin' AND rank IS NOT NULL AND rank BETWEEN 1 AND 50)
        OR (kind = 'hide' AND rank IS NULL AND NOT sponsored)),
    CONSTRAINT promo_curation_dates CHECK (ends_at IS NULL OR ends_at > starts_at)
);

-- One active pin and one active hide per promotion (409 already_curated in the API).
CREATE UNIQUE INDEX IF NOT EXISTS uq_promo_curation_active
    ON promo_curation (kind, chain_id, promo_id) WHERE active;
-- The public read path: the active rows, pins in rank order (tens of rows).
CREATE INDEX IF NOT EXISTS idx_promo_curation_read
    ON promo_curation (kind, rank) WHERE active;
-- The admin "expired" check joins promos on (promo_id); store_fk leads the
-- existing promos indexes, so this one serves "does the promotion still exist".
CREATE INDEX IF NOT EXISTS idx_promos_promo_id ON promos (promo_id);

ALTER TABLE promo_curation OWNER TO scrp_app;

COMMIT;

-- ---------------------------------------------------------------------------
-- ROLLBACK (manual; NOT part of the migration). The SU11A-58 API keeps working
-- (no curation applied); the admin promo tab answers errors. Drops every pin
-- and hide; the audit rows stay in admin_audit.
-- ---------------------------------------------------------------------------
-- BEGIN;
-- DROP TABLE IF EXISTS promo_curation;
-- DROP INDEX IF EXISTS idx_promos_promo_id;
-- COMMIT;
