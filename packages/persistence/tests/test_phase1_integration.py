"""Integration tests for Phase 1: Alembic migration `script_00001` and standardized repositories."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fincontrol_core.domain import (
    ArcaClass,
    AssetEntity,
    AssetType,
    EarningEntity,
    EarningKind,
    IntraClassStrategy,
    PaginationParams,
    PortfolioSnapshotEntity,
    SeriesUnit,
    TransactionEntity,
    TransactionKind,
)
from fincontrol_persistence import SqlAlchemyUnitOfWork, build_engine, build_session_factory
from sqlalchemy import inspect

PERSISTENCE_ROOT = Path(__file__).resolve().parents[1]


def _make_alembic_config(db_url: str) -> Config:
    cfg = Config(str(PERSISTENCE_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PERSISTENCE_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


@pytest.mark.integration
def test_alembic_migration_script_00001_upgrade_and_downgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "phase1_migration.db"
    db_url = f"sqlite+pysqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    cfg = _make_alembic_config(db_url)

    command.upgrade(cfg, "head")

    engine = build_engine(db_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected_tables = {
        "assets",
        "fixed_income_terms",
        "transactions",
        "earnings",
        "arca_targets",
        "market_series",
        "portfolio_snapshots",
        "alembic_version",
    }
    assert expected_tables.issubset(tables)

    session_factory = build_session_factory(engine)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        seeded_targets = uow.arca_targets.get_all()
        assert len(seeded_targets) == 4
        assert sum(t.target_pct for t in seeded_targets) == Decimal("100.00")

    command.downgrade(cfg, "base")
    inspector_after = inspect(engine)
    remaining = set(inspector_after.get_table_names()) - {"alembic_version"}
    assert remaining == set()
    engine.dispose()


@pytest.mark.integration
def test_repositories_standardized_pagination_sorting_and_filtering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "phase1_repos.db"
    db_url = f"sqlite+pysqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    cfg = _make_alembic_config(db_url)
    command.upgrade(cfg, "head")

    engine = build_engine(db_url)
    session_factory = build_session_factory(engine)

    sample_assets = [
        ("WEGE3", "WEG S.A.", AssetType.STOCK_BR),
        ("ITUB4", "Itau Unibanco", AssetType.STOCK_BR),
        ("VALE3", "Vale S.A.", AssetType.STOCK_BR),
        ("HGLG11", "CSHG Logistica FII", AssetType.FII),
        ("KNRI11", "Kinea Renda FII", AssetType.FII),
        ("VOO", "Vanguard S&P 500 ETF", AssetType.ETF_INTL),
        ("BTC", "Bitcoin", AssetType.CRYPTO),
    ]

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        for ticker, name, asset_type in sample_assets:
            created = uow.assets.add(
                AssetEntity(ticker=ticker, name=name, asset_type=asset_type)
            )
            assert created.id is not None
            uow.transactions.add(
                TransactionEntity(
                    asset_id=created.id,
                    kind=TransactionKind.BUY,
                    trade_date=date(2026, 1, 15),
                    quantity=Decimal("10"),
                    unit_price=Decimal("100.00"),
                )
            )
            uow.earnings.add(
                EarningEntity(
                    asset_id=created.id,
                    kind=EarningKind.DIVIDEND,
                    payment_date=date(2026, 2, 15),
                    gross_amount=Decimal("25.00"),
                )
            )

        uow.arca_targets.upsert_targets(
            {
                ArcaClass.ACOES: Decimal("30.00"),
                ArcaClass.REAL_ESTATE: Decimal("25.00"),
                ArcaClass.CAIXA: Decimal("25.00"),
                ArcaClass.ATIVOS_INTERNACIONAIS: Decimal("20.00"),
            },
            {ArcaClass.CAIXA: IntraClassStrategy.EQUAL_WEIGHT},
        )
        uow.market_series.upsert_points(
            "^BVSP",
            [(date(2026, 1, 2), 128000.0), (date(2026, 1, 3), 129500.0)],
            unit=SeriesUnit.INDEX_POINTS,
        )
        uow.snapshots.upsert(
            PortfolioSnapshotEntity(
                snapshot_date=date(2026, 1, 15),
                invested_value=7000.0,
                market_value=7500.0,
                unrealized_pnl=500.0,
                consolidated_pnl=675.0,
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        page1 = uow.assets.list_paginated(
            PaginationParams(page=1, page_size=3, sort_by="ticker", sort_order="asc")
        )
        assert [a.ticker for a in page1.items] == ["BTC", "HGLG11", "ITUB4"]
        assert page1.meta.total_items == 7
        assert page1.meta.total_pages == 3
        assert page1.meta.has_prev is False
        assert page1.meta.has_next is True

        fii_filtered = uow.assets.list_paginated(
            PaginationParams(page=1, page_size=10, sort_by="ticker", sort_order="desc"),
            arca_class="REAL_ESTATE",
        )
        assert [a.ticker for a in fii_filtered.items] == ["KNRI11", "HGLG11"]

        tx_search = uow.transactions.list_paginated(
            PaginationParams(page=1, page_size=5, search="WEG")
        )
        assert tx_search.meta.total_items == 1

        earn_page = uow.earnings.list_paginated(PaginationParams(page=1, page_size=4))
        assert len(earn_page.items) == 4
        assert earn_page.meta.total_items == 7

        ibov_series = uow.market_series.list_series("^BVSP")
        assert len(ibov_series) == 2

        snaps = uow.snapshots.list_range()
        assert len(snaps) == 1
        assert snaps[0].consolidated_pnl == 675.0

    engine.dispose()
