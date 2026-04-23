"""
One-shot migration: copy all data from local prices.db (SQLite) into
the Railway PostgreSQL database specified by DATABASE_URL.

Usage:
    DATABASE_URL=postgresql://user:pass@host:port/db \
        python -m db.migrate_sqlite_to_postgres

Tables are migrated in FK-safe order:
    chains → stores → items → item_chain_names → prices → fetch_runs

After insert, sequences on serial columns are reset so future inserts work.
"""
import os
import sqlite3
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

SQLITE_PATH = Path(__file__).parent.parent / "prices.db"
SCHEMA_PATH = Path(__file__).parent / "schema_postgres.sql"
BATCH_SIZE  = 1000

# Insertion order respects FK dependencies
TABLES = ["chains", "stores", "items", "item_chain_names", "prices", "fetch_runs"]

# Tables with SERIAL primary keys that need sequence reset after bulk copy
SERIAL_TABLES = [("stores", "id"), ("prices", "id"), ("fetch_runs", "id")]


def pg_connect() -> psycopg2.extensions.connection:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("ERROR: DATABASE_URL env var not set.", file=sys.stderr)
        print("       Export it before running this script.", file=sys.stderr)
        sys.exit(1)
    # psycopg2 accepts both postgres:// and postgresql://
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)


def run_schema(pg: psycopg2.extensions.connection) -> None:
    with pg.cursor() as cur:
        cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    pg.commit()
    print("Schema applied.")


def sqlite_rows(lite: sqlite3.Connection, table: str) -> tuple[list[str], list[tuple]]:
    cur = lite.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


def insert_table(
    pg: psycopg2.extensions.connection,
    table: str,
    cols: list[str],
    rows: list[tuple],
) -> None:
    if not rows:
        return
    placeholders = ",".join(["%s"] * len(cols))
    col_list     = ",".join(cols)
    sql = (
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
        f" ON CONFLICT DO NOTHING"
    )
    with pg.cursor() as cur:
        for i in range(0, len(rows), BATCH_SIZE):
            psycopg2.extras.execute_batch(cur, sql, rows[i : i + BATCH_SIZE])
    pg.commit()


def reset_sequences(pg: psycopg2.extensions.connection) -> None:
    with pg.cursor() as cur:
        for table, col in SERIAL_TABLES:
            cur.execute(
                f"SELECT setval("
                f"  pg_get_serial_sequence('{table}', '{col}'),"
                f"  COALESCE(MAX({col}), 1)"
                f") FROM {table}"
            )
    pg.commit()
    print("Sequences reset.")


def count_pg(pg: psycopg2.extensions.connection, table: str) -> int:
    with pg.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()["count"]


def main() -> None:
    if not SQLITE_PATH.exists():
        print(f"ERROR: {SQLITE_PATH} not found — run the scrapers first.", file=sys.stderr)
        sys.exit(1)

    lite = sqlite3.connect(SQLITE_PATH)
    pg   = pg_connect()

    print(f"Source: {SQLITE_PATH}")
    print(f"Target: {os.environ['DATABASE_URL'][:40]}…\n")

    run_schema(pg)

    sqlite_counts: dict[str, int] = {}
    pg_counts:     dict[str, int] = {}

    for table in TABLES:
        cols, rows = sqlite_rows(lite, table)
        sqlite_counts[table] = len(rows)
        print(f"  {table:20s}: {len(rows):>7,} rows → inserting…", end="", flush=True)
        insert_table(pg, table, cols, rows)
        pg_counts[table] = count_pg(pg, table)
        print(f" {pg_counts[table]:>7,} in PG")

    reset_sequences(pg)

    # ---------- validation ----------
    print("\nValidation:")
    all_ok = True
    for table in TABLES:
        s, p  = sqlite_counts[table], pg_counts[table]
        badge = "✅" if s == p else "❌"
        print(f"  {table:20s}: SQLite={s:>7,}  PostgreSQL={p:>7,}  {badge}")
        if s != p:
            all_ok = False

    print()
    if all_ok:
        print("All tables match ✅  Migration complete.")
    else:
        print("Mismatch detected ❌  Check for constraint violations above.")
        sys.exit(1)

    lite.close()
    pg.close()


if __name__ == "__main__":
    main()
