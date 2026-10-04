"""
database.py — Engine/session setup with PyInstaller-aware DB path resolution.

The DB must live OUTSIDE the PyInstaller temp extraction directory so it persists
across runs and app updates. Resolution order:
  1. ENV var  APP_DB_PATH  (absolute path)
  2. Next to the running exe  (sys.executable parent when frozen)
  3. Next to this source file  (dev mode)
"""

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase


def _resolve_db_path() -> Path:
    env_path = os.environ.get("APP_DB_PATH")
    if env_path:
        return Path(env_path)

    if getattr(sys, "frozen", False):
        # Running inside a PyInstaller bundle — exe lives at sys.executable
        base = Path(sys.executable).parent
    else:
        # Dev mode — put DB next to this file
        base = Path(__file__).parent

    return base / "app.db"


DB_PATH = _resolve_db_path()
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _record):
    # SQLite ignores foreign keys unless this is switched on per connection.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
