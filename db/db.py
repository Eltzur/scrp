import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).parent / "schema.sql"
DEFAULT_DB = Path(__file__).parent.parent / "prices.db"


def connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()


def upsert_chain(conn: sqlite3.Connection, chain_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO chains (chain_id) VALUES (?)", (chain_id,)
    )


def upsert_store(
    conn: sqlite3.Connection, chain_id: str, sub_chain_id: str, store_id: str
) -> int:
    conn.execute(
        """
        INSERT OR IGNORE INTO stores (chain_id, sub_chain_id, store_id)
        VALUES (?, ?, ?)
        """,
        (chain_id, sub_chain_id, store_id),
    )
    row = conn.execute(
        """
        SELECT id FROM stores
        WHERE chain_id=? AND sub_chain_id=? AND store_id=?
        """,
        (chain_id, sub_chain_id, store_id),
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
