import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine

SCHEMA = Path(__file__).parent / "schema.sql"
DEFAULT_DB = Path(__file__).parent.parent / "prices.db"

# Rows per INSERT statement for bulk operations.
# 1000 reduces ~7000 per-row round-trips to ~7 statements per store.
# Safe for both SQLite (no param limit) and PostgreSQL (65535 positional limit;
# 1000 rows × 10 cols = 10000 named params — well within bounds).
PRICE_INSERT_BATCH_SIZE = 1000


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set! "
            "Set it in Railway Variables tab."
        )
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    url = url or f"sqlite:///{DEFAULT_DB}"
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _record):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    else:
        engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
        )
    return engine


def connect(db_path: Path = DEFAULT_DB) -> Connection:
    """Return a SQLAlchemy Connection. Uses DATABASE_URL when set, else SQLite at db_path."""
    if os.environ.get("DATABASE_URL"):
        return get_engine().connect()
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine.connect()


def init_db(conn: Connection) -> None:
    """Apply schema.sql. SQLite only — PG schema is managed via schema_postgres.sql."""
    if conn.engine.dialect.name != "sqlite":
        return
    for stmt in SCHEMA.read_text(encoding="utf-8").split(";"):
        stmt = stmt.strip()
        if stmt and not stmt.startswith("--"):
            conn.execute(text(stmt))
    conn.commit()


def upsert_chain(conn: Connection, chain_id: str, name: str = "") -> None:
    conn.execute(text("""
        INSERT INTO chains (chain_id, name) VALUES (:chain_id, :name)
        ON CONFLICT(chain_id) DO UPDATE SET
            name = CASE WHEN excluded.name != '' THEN excluded.name ELSE chains.name END
    """), {"chain_id": chain_id, "name": name})


def upsert_store(conn: Connection, chain_id: str, sub_chain_id: str, store_id: str) -> int:
    row = conn.execute(
        text("SELECT id FROM stores WHERE chain_id=:chain_id AND store_id=:store_id"),
        {"chain_id": chain_id, "store_id": store_id},
    ).fetchone()
    if row:
        return row[0]
    conn.execute(text("""
        INSERT INTO stores (chain_id, sub_chain_id, store_id)
        VALUES (:chain_id, :sub_chain_id, :store_id)
        ON CONFLICT (chain_id, sub_chain_id, store_id) DO NOTHING
    """), {"chain_id": chain_id, "sub_chain_id": sub_chain_id, "store_id": store_id})
    return conn.execute(
        text("SELECT id FROM stores WHERE chain_id=:chain_id AND store_id=:store_id"),
        {"chain_id": chain_id, "store_id": store_id},
    ).scalar()


def upsert_item(conn: Connection, item: dict) -> None:
    conn.execute(text("""
        INSERT INTO items
            (item_code, item_type, item_name, manufacturer_name,
             manufacture_country, unit_qty, quantity, is_weighted,
             unit_of_measure, qty_in_package)
        VALUES
            (:item_code, :item_type, :item_name, :manufacturer_name,
             :manufacture_country, :unit_qty, :quantity, :is_weighted,
             :unit_of_measure, :qty_in_package)
        ON CONFLICT(item_code) DO NOTHING
    """), item)


def upsert_item_chain_name(conn: Connection, chain_id: str, item: dict) -> None:
    conn.execute(text("""
        INSERT INTO item_chain_names (item_code, chain_id, item_name, manufacturer_name)
        VALUES (:item_code, :chain_id, :item_name, :manufacturer_name)
        ON CONFLICT(item_code, chain_id) DO UPDATE SET
            item_name         = excluded.item_name,
            manufacturer_name = excluded.manufacturer_name
    """), {"chain_id": chain_id, **item})


def upsert_price(conn: Connection, store_fk: int, item: dict) -> None:
    conn.execute(text("""
        INSERT INTO prices
            (store_fk, item_code, price_update_date, item_price,
             unit_of_measure_price, allow_discount, item_status)
        VALUES
            (:store_fk, :item_code, :price_update_date, :item_price,
             :unit_of_measure_price, :allow_discount, :item_status)
        ON CONFLICT(store_fk, item_code) DO UPDATE SET
            price_update_date     = excluded.price_update_date,
            item_price            = excluded.item_price,
            unit_of_measure_price = excluded.unit_of_measure_price,
            allow_discount        = excluded.allow_discount,
            item_status           = excluded.item_status
    """), {"store_fk": store_fk, **item})


# ---------------------------------------------------------------------------
# Bulk insert helpers (9g-1 performance improvement)
# ---------------------------------------------------------------------------

def bulk_upsert_items(conn: Connection, items: list[dict]) -> None:
    """
    Bulk-insert items in batches of PRICE_INSERT_BATCH_SIZE.
    ON CONFLICT(item_code) DO NOTHING — first writer wins canonical name.
    Applied in both replace and append modes (items table is never DELETEd).
    """
    if not items:
        return
    cols = (
        "item_code", "item_type", "item_name", "manufacturer_name",
        "manufacture_country", "unit_qty", "quantity", "is_weighted",
        "unit_of_measure", "qty_in_package",
    )
    for i0 in range(0, len(items), PRICE_INSERT_BATCH_SIZE):
        batch = items[i0 : i0 + PRICE_INSERT_BATCH_SIZE]
        placeholders, params = [], {}
        for j, item in enumerate(batch):
            placeholders.append(
                f"(:a{j}0,:a{j}1,:a{j}2,:a{j}3,:a{j}4,"
                f":a{j}5,:a{j}6,:a{j}7,:a{j}8,:a{j}9)"
            )
            params.update({
                f"a{j}0": item.get("item_code"),
                f"a{j}1": item.get("item_type"),
                f"a{j}2": item.get("item_name"),
                f"a{j}3": item.get("manufacturer_name"),
                f"a{j}4": item.get("manufacture_country"),
                f"a{j}5": item.get("unit_qty"),
                f"a{j}6": item.get("quantity"),
                f"a{j}7": item.get("is_weighted"),
                f"a{j}8": item.get("unit_of_measure"),
                f"a{j}9": item.get("qty_in_package"),
            })
        conn.execute(text(
            f"INSERT INTO items ({','.join(cols)}) VALUES {','.join(placeholders)}"
            " ON CONFLICT(item_code) DO NOTHING"
        ), params)


def bulk_upsert_item_chain_names(conn: Connection, chain_id: str, items: list[dict]) -> None:
    """
    Bulk-upsert per-chain item names in batches.
    ON CONFLICT(item_code, chain_id) DO UPDATE — always refreshes chain name.
    Applied in both replace and append modes (item_chain_names is never DELETEd).
    """
    if not items:
        return
    cols = ("item_code", "chain_id", "item_name", "manufacturer_name")
    for i0 in range(0, len(items), PRICE_INSERT_BATCH_SIZE):
        batch = items[i0 : i0 + PRICE_INSERT_BATCH_SIZE]
        placeholders, params = [], {}
        for j, item in enumerate(batch):
            placeholders.append(f"(:b{j}0,:b{j}1,:b{j}2,:b{j}3)")
            params.update({
                f"b{j}0": item.get("item_code"),
                f"b{j}1": chain_id,
                f"b{j}2": item.get("item_name"),
                f"b{j}3": item.get("manufacturer_name"),
            })
        conn.execute(text(
            f"INSERT INTO item_chain_names ({','.join(cols)}) VALUES {','.join(placeholders)}"
            " ON CONFLICT(item_code, chain_id) DO UPDATE SET"
            " item_name=excluded.item_name,"
            " manufacturer_name=excluded.manufacturer_name"
        ), params)


def bulk_insert_prices(conn: Connection, store_fk: int, items: list[dict],
                       replace: bool) -> int:
    """
    Bulk-insert price rows in batches. Returns total rows inserted.

    replace=True:  plain INSERT, no ON CONFLICT clause.
                   Safe because the caller already DELETEd all prices for this
                   store_fk — there are no existing rows that could conflict.
    replace=False: INSERT ... ON CONFLICT(store_fk, item_code) DO UPDATE
                   (append mode — existing rows are updated in place).
    """
    if not items:
        return 0
    cols = (
        "store_fk", "item_code", "price_update_date", "item_price",
        "unit_of_measure_price", "allow_discount", "item_status",
    )
    conflict_clause = (
        "" if replace else
        " ON CONFLICT(store_fk, item_code) DO UPDATE SET"
        " price_update_date=excluded.price_update_date,"
        " item_price=excluded.item_price,"
        " unit_of_measure_price=excluded.unit_of_measure_price,"
        " allow_discount=excluded.allow_discount,"
        " item_status=excluded.item_status"
    )
    total = 0
    for i0 in range(0, len(items), PRICE_INSERT_BATCH_SIZE):
        batch = items[i0 : i0 + PRICE_INSERT_BATCH_SIZE]
        placeholders, params = [], {}
        for j, item in enumerate(batch):
            placeholders.append(
                f"(:c{j}0,:c{j}1,:c{j}2,:c{j}3,:c{j}4,:c{j}5,:c{j}6)"
            )
            params.update({
                f"c{j}0": store_fk,
                f"c{j}1": item["item_code"],
                f"c{j}2": item.get("price_update_date"),
                f"c{j}3": item["item_price"],
                f"c{j}4": item.get("unit_of_measure_price"),
                f"c{j}5": item.get("allow_discount"),
                f"c{j}6": item.get("item_status"),
            })
        conn.execute(text(
            f"INSERT INTO prices ({','.join(cols)})"
            f" VALUES {','.join(placeholders)}{conflict_clause}"
        ), params)
        total += len(batch)
    return total
