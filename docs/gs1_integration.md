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

**Authorized scope: 77 suppliers** — 72 originally approved, plus 5 smaller ones
added directly by GS1. Confirmed against GS1's own supplier list, and matching
the 77 distinct `gln` values the first full sweep returned.

**No supplier filtering is applied.** The fetch deliberately pulls everything the
account can see, so a supplier added or removed on GS1's side is picked up with
no code change. If the distinct-`gln` count drifts from 77, that reflects a
change in account authorization, not a bug in the sweep — check it with:

```sql
SELECT count(DISTINCT gln) FROM gs1.products;
```

### Response shape

Confirmed against the live endpoint in SU10A-1. Two things to know:

- It is served as `content-type: text/html` despite being JSON.
- The body is a **doubly nested bare list** — `[[ {row}, {row}, ... ]]`. The row
  list is `payload[0]`, *not* `payload`. `_extract_rows()` unwraps this (bounded
  to 3 levels) and still accepts a dict envelope in case the API ever changes.

Each row has 13 keys:

```
Product_Status, brandname, content, discontinued_date_time,
effective_date_time, gln, group_id, group_name, gtin, id,
modification_timestamp, product_code, trade_item_description
```

Note `Product_Status` is capitalised while everything else is not. Rather than
special-casing it, `_normalise()` lowercases every incoming key before matching
against `_FIELD_MAP`, so future casing surprises cannot cause a silent NULL.

**Dates use two different formats in the same row:** `modification_timestamp` is
`'2025-12-28 12:51:03'`, but `effective_date_time` is `'21/02/2018'` —
**DD/MM/YYYY**, day-first per the Israeli convention. Both are handled by
`_TS_FORMATS`; an unparseable value logs a warning and stores NULL rather than
aborting the sweep.

`content` is present in the list response but is **not** read in phase 1 — its
size and structure have not been examined yet. See Phase 2.

---

## Schema

Migration: `db/migrations/su10a1_gs1_catalog.sql`

### `gs1.products`

| column | type | notes |
|---|---|---|
| `id` | TEXT PK | GS1's own record id (returned as a string, e.g. `'10982'`) |
| `product_code` | TEXT UNIQUE NOT NULL | e.g. `IL_7290000200002_7290013906892_1519196448768` |
| `gtin` | TEXT | indexed |
| `gln` | TEXT | indexed. **One column** — the API has no supplier/retailer split |
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

Apply the migrations (once each, in order). Note the database is **`xxl_super`**
— the repo, the server directory and the DB role are all called `scrp`, but the
database is not:

```bash
cd ~/scrp
sudo -u postgres psql -d xxl_super -f db/migrations/su10a1_gs1_catalog.sql
sudo -u postgres psql -d xxl_super -f db/migrations/su10a1b_gs1_gln_consolidate.sql
```

`sudo -u postgres` is **not** in the passwordless whitelist — it prompts, so it
has to be run interactively (`ssh -t`).

Then, from `~/scrp` with the venv active. **No `source .env` needed** — the
script loads the repo-root `.env` itself via python-dotenv, because a plain
`source .env` does not export to a python3 subprocess:

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

## Still unconfirmed

The response envelope, field names and date formats are all confirmed against a
live response (see Response shape). What remains open:

1. **Timestamp format in the *query filter*** (`_GS1_TS_FORMAT`). The rows come
   back as `'YYYY-MM-DD HH:MM:SS'`, which is what we send, but incremental mode
   has not yet been exercised end-to-end — the first sweep runs with no
   watermark. Verify the second run returns a sensibly smaller result set.
2. **Page size.** 500 is conservative; the endpoint's real ceiling is unknown.
3. **`content`.** Present in every row, never inspected. May make phase 2
   redundant, or may be a fragment/media ref.

---

## Phase 2 (not built)

Per-product detail fetch populating `full_content` JSONB. The partial index
`idx_gs1_products_needs_full_content` (`WHERE full_content IS NULL`) exists so
the backlog query is cheap from day one.
