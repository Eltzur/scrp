import os
import sqlite3
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

SCHEMA = Path(__file__).parent / "schema.sql"
DEFAULT_DB = Path(__file__).parent.parent / "prices.db"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        # Railway provides postgres:// — SQLAlchemy 2.x requires postgresql://
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


def connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()


def upsert_chain(conn: sqlite3.Connection, chain_id: str, name: str = "") -> None:
    conn.execute(
        """INSERT INTO chains (chain_id, name) VALUES (?, ?)
           ON CONFLICT(chain_id) DO UPDATE SET name = CASE WHEN excluded.name != '' THEN excluded.name ELSE name END""",
        (chain_id, name),
    )


def upsert_store(
    conn: sqlite3.Connection, chain_id: str, sub_chain_id: str, store_id: str
) -> int:
    # Prefer an existing row matched by (chain_id, store_id) regardless of sub_chain_id.
    # Old-format filenames default sub_chain_id to "001", but the XML header may differ
    # (e.g. יש stores = sub_chain 015, דיל = sub_chain 002). Using just store_id avoids
    # creating orphan rows with no store_name/city.
    row = conn.execute(
        "SELECT id FROM stores WHERE chain_id=? AND store_id=?",
        (chain_id, store_id),
    ).fetchone()
    if row:
        return row["id"]
    # Truly new store — insert it
    conn.execute(
        "INSERT OR IGNORE INTO stores (chain_id, sub_chain_id, store_id) VALUES (?, ?, ?)",
        (chain_id, sub_chain_id, store_id),
    )
    row = conn.execute(
        "SELECT id FROM stores WHERE chain_id=? AND store_id=?",
        (chain_id, store_id),
    ).fetchone()
    return row["id"]


def upsert_item(conn: sqlite3.Connection, item: dict) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO items
            (item_code, item_type, item_name, manufacturer_name,
             manufacture_country, unit_qty, quantity, is_weighted,
             unit_of_measure, qty_in_package)
        VALUES
            (:item_code, :item_type, :item_name, :manufacturer_name,
             :manufacture_country, :unit_qty, :quantity, :is_weighted,
             :unit_of_measure, :qty_in_package)
        """,
        item,
    )


def upsert_item_chain_name(conn: sqlite3.Connection, chain_id: str, item: dict) -> None:
    conn.execute(
        """
        INSERT INTO item_chain_names (item_code, chain_id, item_name, manufacturer_name)
        VALUES (:item_code, :chain_id, :item_name, :manufacturer_name)
        ON CONFLICT(item_code, chain_id) DO UPDATE SET
            item_name         = excluded.item_name,
            manufacturer_name = excluded.manufacturer_name
        """,
        {"chain_id": chain_id, **item},
    )


def upsert_price(conn: sqlite3.Connection, store_fk: int, item: dict) -> None:
    conn.execute(
        """
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
        """,
        {"store_fk": store_fk, **item},
    )
