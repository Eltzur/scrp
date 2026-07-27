# GS1 Israel integration

Fetches the GS1 Israel product catalog into a dedicated `gs1` Postgres schema.

Referenced as existing in the 9d-11 handoff entry, but the file was never actually
committed — written fresh in **SU10A-1**.

**Scope:** this component is fully isolated. It does not read or write any
supermarket scraper table (`items`, `prices`, `stores`, `city_canonical`) and
shares no code with the scrapers or city resolution.

---

## Endpoint

```
POST https://hq.gs1ildigital.org/external/app_query/select_query.json
Content-Type: application/json
```

**Auth:** HTTP Basic. Credentials live in `~/scrp/.env` on Kamatera as
`GS1_USERNAME` / `GS1_PASSWORD`.

> **Uppercase, deliberately.** CLAUDE.md's convention is to default *new* env var
> names to lowercase, but these already exist on the server under these names, and
> the convention defers to what a file already uses. Renaming them is what caused
> SU10A-1's day of misleading 401s — a `GS1_Username` / `$GS1_USERNAME` mismatch
> that `source` accepts silently, because bash variable names are case-sensitive.
> Do not rename them.

**Allowlisting:** the account is IP-allowlisted. Both addresses are in
CLAUDE.md § Network reference — `185.229.226.190` (Kamatera, for the cron/server
run) and `149.106.243.120` (dev machine, for local testing).

### Request body

```json
{
  "query": "modification_timestamp > DATE_SUB(NOW(), INTERVAL 3650 DAY)",
  "get_chunks": { "start": 0, "rows": 500 }
}
```

- `query` — a filter expression. The dialect is MySQL-flavoured (`NOW()`,
  `DATE_SUB(...)`), so incremental runs pass a quoted `'YYYY-MM-DD HH:MM:SS'`
  literal.
- `get_chunks` — pagination. `start` advances by `rows` each page; the sweep
  stops when a page returns zero rows.

A single query covers **all suppliers connected to our account** — there is no
per-supplier loop.

---

## Schema

Migration: `db/migrations/su10a1_gs1_catalog.sql`

### `gs1.products`

| column | type | notes |
|---|---|---|
| `id` | TEXT PK | GS1's own record id |
| `product_code` | TEXT UNIQUE NOT NULL | |
| `gtin` | TEXT | indexed |
| `supplier_gln` | TEXT | indexed |
| `retailer_gln` | TEXT | |
| `group_id` / `group_name` | TEXT | |
| `brandname` | TEXT | |
| `trade_item_description` | TEXT | |
| `product_status` | TEXT | |
| `effective_date_time` | TIMESTAMPTZ | |
| `discontinued_date_time` | TIMESTAMPTZ | |
| `modification_timestamp` | TIMESTAMPTZ | indexed DESC — drives the watermark |
| `full_content` | JSONB NULL | **phase 2** |
| `fetched_at` | TIMESTAMPTZ | set on every upsert |
| `full_content_fetched_at` | TIMESTAMPTZ NULL | **phase 2** |

`id` is TEXT rather than BIGINT on purpose: it is an external system's
identifier and no live payload has been inspected yet. Tightening it later is a
one-line migration; having the first production run abort on a non-numeric id is
not worth the risk.

The phase-1 upsert **never writes** `full_content` or `full_content_fetched_at`,
so re-running the sweep cannot clobber detail that phase 2 has already fetched.

### `gs1.sync_runs`

| column | type | notes |
|---|---|---|
| `id` | SERIAL PK | |
| `started_at` / `completed_at` | TIMESTAMPTZ | |
| `rows_fetched` | INTEGER | |
| `last_modification_timestamp` | TIMESTAMPTZ | the watermark |
| `status` | TEXT | `running` \| `ok` \| `error` |

The watermark is the **highest `modification_timestamp` actually observed**, not
`now()` — using `now()` would silently skip rows modified while the sweep was in
flight. It is only advanced on success, so a failed run causes the next one to
re-cover the same window rather than leaving a hole.

### Grants

The migration includes `GRANT ... TO scrp_app` for the schema, tables and
sequences, plus `ALTER DEFAULT PRIVILEGES` for whatever phase 2 adds. Migrations
run as the `postgres` superuser while the app connects as `scrp_app`; without
these the app gets `permission denied` (lesson from 9d-2).

---

## Running it

Apply the migration (once):

```bash
sudo -u postgres psql -d scrp -f ~/scrp/db/migrations/su10a1_gs1_catalog.sql
```

Then, from `~/scrp` with the venv active and `.env` sourced:

```bash
# dry run — fetches and parses, writes nothing
python3 -m scraper.gs1_fetch --dry-run --max-pages 1

# incremental (default): picks up from the last successful watermark
python3 -m scraper.gs1_fetch

# ignore the watermark and re-sweep everything
python3 -m scraper.gs1_fetch --full
```

Flags: `--full`, `--dry-run`, `--page-size N` (default 500), `--max-pages N`
(default 2000, a safety valve against an endless loop).

### Checking a run

```sql
SELECT id, started_at, completed_at, rows_fetched,
       last_modification_timestamp, status
FROM gs1.sync_runs ORDER BY started_at DESC LIMIT 5;

SELECT count(*) FROM gs1.products;
```

---

## Unconfirmed against a live response

No live payload has been captured yet, so the following are **assumptions**, and
the first `--dry-run` exists specifically to check them:

1. **Response envelope.** `_extract_rows()` accepts a bare list or a dict keyed
   `results` / `result` / `rows` / `data` / `records` / `items`, and logs the
   top-level keys if none match.
2. **Field names/casing.** `_FIELD_MAP` accepts snake_case and camelCase per
   column. The first page logs its row keys so the real names can be confirmed.
3. **Timestamp format** in the query filter (`_GS1_TS_FORMAT`). Only affects
   incremental mode; a full sweep uses the `DATE_SUB` form already proven by hand.
4. **Page size.** 500 is conservative; the endpoint's real ceiling is unknown.

---

## Phase 2 (not built)

Per-product detail fetch populating `full_content` JSONB. The partial index
`idx_gs1_products_needs_full_content` (`WHERE full_content IS NULL`) exists so
the backlog query is cheap from day one.
