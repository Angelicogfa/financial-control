"""Integration tests for phase 12 persistence: events, import hashes and their migration."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from domain.shared.entities import (
    AssetEntity,
    CorporateEventEntity,
    EarningEntity,
    TransactionEntity,
)
from domain.shared.enums import (
    AssetType,
    CorporateEventKind,
    EarningKind,
    TransactionKind,
)
from infra.data.unit_of_work import SqlAlchemyUnitOfWork

PERSISTENCE_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def db(tmp_path: Path) -> Iterator[tuple[Config, Engine]]:
    db_url = f"sqlite:///{(tmp_path / 'phase12.db').as_posix()}"
    cfg = Config(str(PERSISTENCE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(PERSISTENCE_DIR / "infra" / "data" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    engine = create_engine(db_url, future=True)
    command.upgrade(cfg, "head")
    yield cfg, engine
    engine.dispose()


def test_events_load_with_assets_and_hashes_deduplicate(db: tuple[Config, Engine]) -> None:
    _cfg, engine = db
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with SqlAlchemyUnitOfWork(session_factory=factory) as uow:
        asset = uow.assets.add(
            AssetEntity(ticker="WEGE3", name="WEG", asset_type=AssetType.STOCK_BR)
        )
        uow.transactions.add(
            TransactionEntity(
                asset_id=asset.id or 0,
                kind=TransactionKind.BUY,
                trade_date=date(2024, 1, 2),
                quantity=Decimal("10"),
                unit_price=Decimal("40"),
                import_hash="t" * 64,
            )
        )
        uow.earnings.add(
            EarningEntity(
                asset_id=asset.id or 0,
                kind=EarningKind.DIVIDEND,
                payment_date=date(2024, 3, 1),
                gross_amount=Decimal("5"),
                import_hash="e" * 64,
            )
        )
        uow.corporate_events.add(
            CorporateEventEntity(
                asset_id=asset.id or 0,
                kind=CorporateEventKind.SPLIT,
                ex_date=date(2024, 6, 3),
                factor=Decimal("2"),
                import_hash="c" * 64,
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory=factory) as uow:
        loaded = uow.assets.get_by_ticker("WEGE3")
        assert loaded is not None
        assert [e.factor for e in loaded.corporate_events] == [Decimal("2")]
        assert loaded.transactions[0].import_hash == "t" * 64
        assert uow.ledger_imports.existing_hashes(["t" * 64, "e" * 64, "c" * 64, "x" * 64]) == {
            "t" * 64,
            "e" * 64,
            "c" * 64,
        }
        assert uow.ledger_imports.existing_hashes([]) == set()

    duplicate = TransactionEntity(
        asset_id=loaded.id or 0,
        kind=TransactionKind.BUY,
        trade_date=date(2024, 1, 3),
        quantity=Decimal("1"),
        unit_price=Decimal("1"),
        import_hash="t" * 64,
    )
    with SqlAlchemyUnitOfWork(session_factory=factory) as uow, pytest.raises(IntegrityError):
        uow.transactions.add(duplicate)


def test_script_00014_downgrade_and_upgrade(db: tuple[Config, Engine]) -> None:
    cfg, engine = db
    command.downgrade(cfg, "script_00013")
    with engine.connect() as conn:
        columns = [row[1] for row in conn.execute(text("PRAGMA table_info(transactions)"))]
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master"))}
    assert "import_hash" not in columns
    assert "corporate_events" not in tables
    command.upgrade(cfg, "head")


def test_pagination_is_stable_when_sort_values_tie(db: tuple[Config, Engine]) -> None:
    """D-04: the primary key breaks ties, so pages never repeat or skip rows."""
    from core.helpers.pagination import PaginationParams

    _cfg, engine = db
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with SqlAlchemyUnitOfWork(session_factory=factory) as uow:
        for ticker in ("CCC3", "AAA3", "BBB3", "DDD3"):
            uow.assets.add(AssetEntity(ticker=ticker, name=ticker, asset_type=AssetType.STOCK_BR))
        uow.commit()
    seen: list[str] = []
    with SqlAlchemyUnitOfWork(session_factory=factory) as uow:
        for page in (1, 2, 3, 4):
            result = uow.assets.list_paginated(
                PaginationParams(page=page, page_size=1, sort_by="asset_type", sort_order="asc")
            )
            seen.extend(a.ticker for a in result.items)
    assert sorted(seen) == ["AAA3", "BBB3", "CCC3", "DDD3"]
