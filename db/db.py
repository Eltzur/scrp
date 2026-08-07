import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

# Rows per INSERT statement for bulk operations.
# 1000 reduces ~7000 per-row round-trips to ~7 statements per store.
# PostgreSQL limit: 65535 positional params; 1000 rows × 10 cols = 10000 — well within bounds.
PRICE_INSERT_BATCH_SIZE = 1000

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is not None:
        return _engine
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set!")
    _engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=10,
    )
    return _engine


def connect() -> Connection:
    return get_engine().connect()


def init_db(conn: Connection) -> None:
    """Create tables not covered by schema_postgres.sql (idempotent)."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS promos (
            id            SERIAL PRIMARY KEY,
            store_fk      INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
            item_code     TEXT NOT NULL,
            promo_id      TEXT,
            promo_description TEXT,
            promo_type    INTEGER,
            allow_multiple_discounts BOOLEAN,
            min_qty       NUMERIC,
            reward_type   INTEGER,
            discount_rate NUMERIC,
            discount_price NUMERIC,
            min_purchase_amount NUMERIC,
            promo_start   TIMESTAMP,
            promo_end     TIMESTAMP,
            created_at    TIMESTAMP DEFAULT NOW(),
            UNIQUE (store_fk, item_code, promo_id)
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_promos_store_fk ON promos(store_fk)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_promos_item_code ON promos(item_code)"))
    conn.commit()


def upsert_chain(conn: Connection, chain_id: str, name: str = "") -> None:
    conn.execute(text("""
        INSERT INTO chains (chain_id, name) VALUES (:chain_id, :name)
        ON CONFLICT(chain_id) DO UPDATE SET
            name = CASE WHEN excluded.name != '' THEN excluded.name ELSE chains.name END
    """), {"chain_id": chain_id, "name": name})


def _pad_store_id(store_id: str) -> str:
    """Canonical store_id format: zero-padded 3-digit when numeric."""
    s = str(store_id).strip()
    return s.zfill(3) if s.isdigit() else s


def upsert_store(conn: Connection, chain_id: str, sub_chain_id: str, store_id: str) -> int:
    store_id = _pad_store_id(store_id)
    sub_chain_id = _pad_store_id(sub_chain_id)
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


def bulk_insert_promos(conn: Connection, store_fk: int, promo_items: list[dict]) -> int:
    """
    Bulk-insert promo rows in batches.
    ON CONFLICT (store_fk, item_code, promo_id) DO UPDATE refreshes all promo fields.
    Returns count of rows inserted/updated.
    """
    if not promo_items:
        return 0
    # Deduplicate by conflict key before upsert — some portals (e.g. Victory)
    # emit the same (item_code, promo_id) pair twice in one file, which causes
    # a CardinalityViolation when both rows land in the same INSERT batch.
    # store_fk is constant per call so keying on (item_code, promo_id) suffices.
    promo_items = list(
        {(item.get("item_code"), item.get("promo_id")): item for item in promo_items}.values()
    )
    # Column order must match param binding order exactly.
    cols = (
        "store_fk", "item_code", "promo_id", "promo_description",
        "promo_type", "allow_multiple_discounts", "min_qty", "reward_type",
        "discount_rate", "discount_price", "min_purchase_amount",
        "promo_start", "promo_end", "club_id", "max_qty", "gift_count",
    )
    conflict_clause = (
        " ON CONFLICT (store_fk, item_code, promo_id) DO UPDATE SET"
        " promo_description=excluded.promo_description,"
        " promo_type=excluded.promo_type,"
        " allow_multiple_discounts=excluded.allow_multiple_discounts,"
        " min_qty=excluded.min_qty,"
        " reward_type=excluded.reward_type,"
        " discount_rate=excluded.discount_rate,"
        " discount_price=excluded.discount_price,"
        " min_purchase_amount=excluded.min_purchase_amount,"
        " promo_start=excluded.promo_start,"
        " promo_end=excluded.promo_end,"
        " club_id=excluded.club_id,"
        " max_qty=excluded.max_qty,"
        " gift_count=excluded.gift_count"
    )
    total = 0
    for i0 in range(0, len(promo_items), PRICE_INSERT_BATCH_SIZE):
        batch = promo_items[i0: i0 + PRICE_INSERT_BATCH_SIZE]
        placeholders, params = [], {}
        for j, item in enumerate(batch):
            # Underscore separator prevents key collisions when j>=11 and n>=10
            # e.g. j=1,n=10 → "p1_10"; j=11,n=0 → "p11_0" — unambiguous.
            placeholders.append(
                f"(:p{j}_0,:p{j}_1,:p{j}_2,:p{j}_3,:p{j}_4,"
                f":p{j}_5,:p{j}_6,:p{j}_7,:p{j}_8,:p{j}_9,:p{j}_10,:p{j}_11,:p{j}_12,"
                f":p{j}_13,:p{j}_14,:p{j}_15)"
            )
            params.update({
                f"p{j}_0":  store_fk,
                f"p{j}_1":  item.get("item_code"),
                f"p{j}_2":  item.get("promo_id"),
                f"p{j}_3":  item.get("promo_description"),
                f"p{j}_4":  item.get("promo_type"),
                f"p{j}_5":  bool(item.get("allow_multiple_discounts")) if item.get("allow_multiple_discounts") is not None else None,
                f"p{j}_6":  item.get("min_qty"),
                f"p{j}_7":  item.get("reward_type"),
                f"p{j}_8":  item.get("discount_rate"),
                f"p{j}_9":  item.get("discount_price"),
                f"p{j}_10": item.get("min_purchase_amount"),
                f"p{j}_11": item.get("promo_start"),
                f"p{j}_12": item.get("promo_end"),
                f"p{j}_13": item.get("club_id"),
                f"p{j}_14": item.get("max_qty"),
                f"p{j}_15": item.get("gift_count"),
            })
        conn.execute(text(
            f"INSERT INTO promos ({','.join(cols)})"
            f" VALUES {','.join(placeholders)}{conflict_clause}"
        ), params)
        total += len(batch)
    return total


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
