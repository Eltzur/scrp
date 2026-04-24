import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine

SCHEMA = Path(__file__).parent / "schema.sql"
DEFAULT_DB = Path(__file__).parent.parent / "prices.db"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url or f"sqlite:///{DEFAULT_DB}"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = _database_url()
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
            name = CASE WHEN excluded.name != '' THEN excluded.name ELSE name END
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
