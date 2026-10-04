-- Store position accuracy scoreboard (SU11A-15). READ-ONLY.
--
--   psql "$DATABASE_URL" -f scripts/accuracy_scoreboard.sql
--
-- Population: LIVE physical stores. "Live" is the same rule as
-- db/query.py live_store_clause: last_loaded_at within 3 days of the chain's
-- own latest load (never wall-clock).
-- Tiers: house = geo_precision 'address', street = 'street',
--        city = 'city' (CBS centroid only), none = no coordinate.
-- Run it before and after a geocode run; the transaction is read-only and
-- rolled back.

BEGIN TRANSACTION READ ONLY;

\echo '== Live physical stores: position accuracy (all chains)'
WITH live AS (
    SELECT s.*
    FROM stores s
    JOIN (SELECT chain_id, max(last_loaded_at) - interval '3 days' AS cutoff
          FROM stores WHERE last_loaded_at IS NOT NULL GROUP BY chain_id) c
      ON c.chain_id = s.chain_id
    WHERE s.is_physical AND s.last_loaded_at >= c.cutoff
)
SELECT count(*)                                                        AS total,
       count(*) FILTER (WHERE lat IS NOT NULL AND geo_precision = 'address') AS house,
       round(100.0 * count(*) FILTER (WHERE lat IS NOT NULL AND geo_precision = 'address') / nullif(count(*), 0), 1) AS house_pct,
       count(*) FILTER (WHERE lat IS NOT NULL AND geo_precision = 'street')  AS street,
       round(100.0 * count(*) FILTER (WHERE lat IS NOT NULL AND geo_precision = 'street') / nullif(count(*), 0), 1) AS street_pct,
       count(*) FILTER (WHERE lat IS NOT NULL AND geo_precision = 'city')    AS city_only,
       round(100.0 * count(*) FILTER (WHERE lat IS NOT NULL AND geo_precision = 'city') / nullif(count(*), 0), 1) AS city_pct,
       count(*) FILTER (WHERE lat IS NULL)                                   AS none,
       round(100.0 * count(*) FILTER (WHERE lat IS NULL) / nullif(count(*), 0), 1) AS none_pct,
       round(100.0 * count(*) FILTER (WHERE lat IS NOT NULL AND geo_precision IN ('address', 'street')) / nullif(count(*), 0), 1) AS exact_pct
FROM live;

\echo '== By chain'
WITH live AS (
    SELECT s.*
    FROM stores s
    JOIN (SELECT chain_id, max(last_loaded_at) - interval '3 days' AS cutoff
          FROM stores WHERE last_loaded_at IS NOT NULL GROUP BY chain_id) c
      ON c.chain_id = s.chain_id
    WHERE s.is_physical AND s.last_loaded_at >= c.cutoff
)
SELECT coalesce(ch.name, l.chain_id)                                    AS chain,
       count(*)                                                           AS total,
       count(*) FILTER (WHERE l.lat IS NOT NULL AND l.geo_precision = 'address') AS house,
       count(*) FILTER (WHERE l.lat IS NOT NULL AND l.geo_precision = 'street')  AS street,
       count(*) FILTER (WHERE l.lat IS NOT NULL AND l.geo_precision = 'city')    AS city_only,
       count(*) FILTER (WHERE l.lat IS NULL)                                     AS none,
       round(100.0 * count(*) FILTER (WHERE l.lat IS NOT NULL AND l.geo_precision IN ('address', 'street')) / nullif(count(*), 0), 1) AS exact_pct
FROM live l
LEFT JOIN chains ch ON ch.chain_id = l.chain_id
GROUP BY coalesce(ch.name, l.chain_id)
ORDER BY total DESC;

ROLLBACK;
