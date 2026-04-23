"""FastAPI dependencies."""
from typing import Generator

from sqlalchemy.engine import Connection

from db.db import get_engine


def get_db() -> Generator[Connection, None, None]:
    """Yield one SQLAlchemy connection per request; close on completion."""
    with get_engine().connect() as conn:
        yield conn
