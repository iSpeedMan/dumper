"""
database.py — SQLAlchemy engine and session factory.
All models import Base from here; all routes use get_db() as a dependency.
"""

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

DB_PATH = Path(settings.database.path).resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,  # Required for SQLite + multithreading
        "timeout": 30,               # Wait up to 30s on locked DB
    },
    pool_pre_ping=True,
    echo=settings.app.debug,
)


# Enable WAL mode for better concurrent read/write performance
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ---------------------------------------------------------------------------
# Base class for all ORM models
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """Yield a database session, ensuring it is closed after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_schema(engine) -> None:
    """Add columns that were added after initial DB creation."""
    with engine.connect() as conn:
        # notification_webhooks.send_diff (added in v1.1)
        try:
            conn.execute(text(
                "ALTER TABLE notification_webhooks ADD COLUMN send_diff BOOLEAN NOT NULL DEFAULT 0"
            ))
            conn.commit()
        except Exception:
            pass  # Column already exists

        # devices.retention_days (added in v1.2)
        try:
            conn.execute(text(
                "ALTER TABLE devices ADD COLUMN retention_days INTEGER"
            ))
            conn.commit()
        except Exception:
            pass  # Column already exists


def init_db() -> None:
    """Create all tables and run lightweight schema migrations."""
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _migrate_schema(engine)
