"""Persistence layer for Financial Control (SQLAlchemy 2.0, Alembic, Repositories, UnitOfWork).

Layout:
    core/          engine/session factory, SqlAlchemyUnitOfWork, database health
    models/        ORM models, one module per feature
    repositories/  repositories returning pure domain entities, one module per feature
    mappers/       ORM model <-> domain entity conversion, one module per feature
"""

from fincontrol_persistence.core.db import Base, build_engine, build_session_factory
from fincontrol_persistence.core.unit_of_work import SqlAlchemyUnitOfWork

__all__ = [
    "Base",
    "SqlAlchemyUnitOfWork",
    "build_engine",
    "build_session_factory",
]
