"""Readiness probe for the relational database and its Alembic schema version (item 9.6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from infra.data.db import get_default_session_factory

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


@dataclass(frozen=True)
class DatabaseStatus:
    reachable: bool
    current_revision: str | None
    head_revision: str | None
    error: str | None = None

    @property
    def migrated(self) -> bool:
        return self.reachable and self.current_revision == self.head_revision


def head_revision() -> str | None:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(cfg).get_current_head()


def check_database(session_factory: sessionmaker[Session] | None = None) -> DatabaseStatus:
    """Ping the database and compare its Alembic revision with the code's head."""
    head = head_revision()
    factory = session_factory or get_default_session_factory()
    try:
        with factory() as session:
            session.execute(text("SELECT 1"))
            current = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:  # any driver/connection error means "not ready"
        return DatabaseStatus(False, None, head, error=type(exc).__name__)
    return DatabaseStatus(True, current, head)
