"""Database engine, declarative Base, and session factory utilities."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models."""


def get_database_url(override_url: str | None = None) -> str:
    """Resolve DATABASE_URL from argument or environment variable."""
    url = override_url or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    return url


def build_engine(database_url: str | None = None, **kwargs: Any) -> Engine:
    """Create a SQLAlchemy Engine with foreign-key enforcement on SQLite for tests."""
    url = get_database_url(database_url)
    engine = create_engine(url, future=True, pool_pre_ping=True, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_sqlite_fk(dbapi_connection: Any, _connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a configured sessionmaker bound to the provided engine."""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@lru_cache(maxsize=1)
def get_default_session_factory() -> sessionmaker[Session]:
    """Return a singleton session factory bound to the default DATABASE_URL engine."""
    return build_session_factory(build_engine())
