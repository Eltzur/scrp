"""FastAPI dependencies."""
import sqlite3
from typing import Generator
from db.db import connect, DEFAULT_DB


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Yield one SQLite connection per request; close on completion."""
    conn = connect(DEFAULT_DB)
    try:
        yield conn
    finally:
        conn.close()
