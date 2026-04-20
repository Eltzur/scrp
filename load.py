"""Pipeline: parse an XML price file and load it into SQLite."""
import sys
from pathlib import Path

from db.db import connect, init_db, upsert_chain, upsert_store, upsert_item, upsert_price
from parser.price_parser import parse_file


def load(xml_path: Path, db_path: Path = None) -> int:
    from db.db import DEFAULT_DB
    db_path = db_path or DEFAULT_DB

    conn = connect(db_path)
    init_db(conn)

    header, items = parse_file(xml_path)
    chain_id     = header["chain_id"]
    sub_chain_id = header["sub_chain_id"]
    store_id     = header["store_id"]

    print(f"Chain: {chain_id}  SubChain: {sub_chain_id}  Store: {store_id}")

    upsert_chain(conn, chain_id)
    store_fk = upsert_store(conn, chain_id, sub_chain_id, store_id)

    count = 0
    for item in items:
        if not item["item_code"] or item["item_price"] is None:
            continue
        upsert_item(conn, item)
        upsert_price(conn, store_fk, item)
        count += 1
        if count % 500 == 0:
            conn.commit()
            print(f"  {count} items loaded...", end="\r")

    conn.commit()
    conn.close()
    print(f"\nDone. {count} items loaded into {db_path}")
    return count


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python load.py <xml_file> [db_file]")
        sys.exit(1)
    xml = Path(sys.argv[1])
    db  = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    load(xml, db)
