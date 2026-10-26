"""Integration tests for the phase 8 data migrations (script_00002 onwards)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

PERSISTENCE_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def db(tmp_path: Path) -> tuple[Config, Engine]:
    db_url = f"sqlite:///{(tmp_path / 'phase8_migrations.db').as_posix()}"
    cfg = Config(str(PERSISTENCE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(PERSISTENCE_DIR / "infra" / "data" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    engine = create_engine(db_url, future=True)
    yield cfg, engine
    engine.dispose()


def test_script_00002_tags_existing_series_with_units(db: tuple[Config, Engine]) -> None:
    cfg, engine = db
    command.upgrade(cfg, "script_00001")
    with engine.begin() as conn:
        for symbol, value in (
            ("CDI", 0.0393),
            ("SELIC", 0.0393),
            ("IPCA", 0.16),
            ("IBOV", 120000.0),
            ("WEGE3", 52.0),
        ):
            conn.execute(
                text(
                    "INSERT INTO market_series (symbol, reference_date, value) "
                    "VALUES (:s, '2025-01-02', :v)"
                ),
                {"s": symbol, "v": value},
            )

    command.upgrade(cfg, "script_00002")

    with engine.connect() as conn:
        units = dict(conn.execute(text("SELECT symbol, unit FROM market_series")).all())
    assert units == {
        "CDI": "PERCENT_PER_DAY",
        "SELIC": "PERCENT_PER_DAY",
        "IPCA": "PERCENT_PER_MONTH",
        "IBOV": "INDEX_POINTS",
        "WEGE3": "PRICE",
    }

    command.downgrade(cfg, "script_00001")
    with engine.connect() as conn:
        columns = [row[1] for row in conn.execute(text("PRAGMA table_info(market_series)"))]
    assert "unit" not in columns


def test_script_00003_normalizes_percent_scaled_contracted_rates(
    db: tuple[Config, Engine],
) -> None:
    cfg, engine = db
    command.upgrade(cfg, "script_00002")
    rows = [
        (1, "CDI", 110.0),
        (2, "CDI", 1.10),
        (3, "SELIC", 100.0),
        (4, "IPCA", 6.5),
        (5, "IPCA", 0.065),
        (6, "PRE", 12.0),
    ]
    with engine.begin() as conn:
        for asset_id, indexer, rate in rows:
            conn.execute(
                text(
                    "INSERT INTO assets (id, ticker, name, asset_type, arca_class, currency, "
                    "cerrado_answers, created_at, updated_at) VALUES (:id, :t, :t, "
                    "'FIXED_INCOME', 'CAIXA', 'BRL', '{}', '2025-01-01', '2025-01-01')"
                ),
                {"id": asset_id, "t": f"RF-{asset_id}"},
            )
            conn.execute(
                text(
                    "INSERT INTO fixed_income_terms (asset_id, instrument_kind, indexer, "
                    "contracted_rate, issue_date, tax_exempt, liquidity) VALUES "
                    "(:id, 'CDB', :ix, :rate, '2025-01-02', 0, 'AT_MATURITY')"
                ),
                {"id": asset_id, "ix": indexer, "rate": rate},
            )

    command.upgrade(cfg, "script_00003")

    with engine.connect() as conn:
        rates = {
            asset_id: float(rate)
            for asset_id, rate in conn.execute(
                text("SELECT asset_id, contracted_rate FROM fixed_income_terms")
            )
        }
    assert rates == {
        1: pytest.approx(1.10),
        2: pytest.approx(1.10),
        3: pytest.approx(1.00),
        4: pytest.approx(0.065),
        5: pytest.approx(0.065),
        6: pytest.approx(0.12),
    }


def test_script_00004_adds_earning_fx_rate_with_default(db: tuple[Config, Engine]) -> None:
    cfg, engine = db
    command.upgrade(cfg, "script_00003")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO assets (id, ticker, name, asset_type, arca_class, currency, "
                "cerrado_answers, created_at, updated_at) VALUES (1, 'AAPL', 'Apple', "
                "'STOCK_INTL', 'ATIVOS_INTERNACIONAIS', 'USD', '{}', '2025-01-01', '2025-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO earnings (asset_id, kind, payment_date, gross_amount, "
                "withholding_tax, net_amount, created_at) VALUES "
                "(1, 'DIVIDEND', '2025-03-01', 10, 3, 7, '2025-03-01')"
            )
        )

    command.upgrade(cfg, "script_00004")

    with engine.connect() as conn:
        (fx_rate,) = conn.execute(text("SELECT fx_rate FROM earnings")).one()
    assert float(fx_rate) == 1.0


def test_script_00005_keeps_snapshot_values_as_numeric(db: tuple[Config, Engine]) -> None:
    cfg, engine = db
    command.upgrade(cfg, "script_00004")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO portfolio_snapshots (snapshot_date, invested_value, market_value, "
                "unrealized_pnl, realized_pnl_cum, earnings_cum, consolidated_pnl, net_flow, "
                "by_class) VALUES ('2025-01-02', 1000.1, 1100.25, 100.15, 0, 0, 100.15, 0, '{}')"
            )
        )

    command.upgrade(cfg, "head")

    from sqlalchemy.orm import sessionmaker

    from domain.shared.entities import PortfolioSnapshotEntity
    from infra.data.unit_of_work import SqlAlchemyUnitOfWork

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with SqlAlchemyUnitOfWork(session_factory=factory) as uow:
        (legacy,) = uow.snapshots.list_range()
        assert legacy.market_value == 1100.25
        uow.snapshots.upsert(
            PortfolioSnapshotEntity(
                snapshot_date=legacy.snapshot_date,
                invested_value=0.1 + 0.2,
                market_value=1100.255,
                unrealized_pnl=0.0,
            )
        )
        uow.commit()
    with SqlAlchemyUnitOfWork(session_factory=factory) as uow:
        (saved,) = uow.snapshots.list_range()
    assert saved.invested_value == 0.3
    assert saved.market_value in (1100.25, 1100.26)

    command.downgrade(cfg, "script_00004")


def test_pagination_breaks_ties_by_id(db: tuple[Config, Engine]) -> None:
    cfg, engine = db
    command.upgrade(cfg, "head")

    from datetime import date
    from decimal import Decimal

    from sqlalchemy.orm import sessionmaker

    from domain.shared import (
        AssetEntity,
        AssetType,
        PaginationParams,
        TransactionEntity,
        TransactionKind,
    )
    from infra.data.unit_of_work import SqlAlchemyUnitOfWork

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with SqlAlchemyUnitOfWork(session_factory=factory) as uow:
        asset = uow.assets.add(AssetEntity(ticker="X", name="X", asset_type=AssetType.STOCK_BR))
        assert asset.id is not None
        for _ in range(5):
            uow.transactions.add(
                TransactionEntity(
                    asset_id=asset.id,
                    kind=TransactionKind.BUY,
                    trade_date=date(2025, 1, 2),
                    quantity=Decimal("1"),
                    unit_price=Decimal("1"),
                )
            )
        uow.commit()

        pages = [
            uow.transactions.list_paginated(
                PaginationParams(page=page, page_size=2, sort_by="trade_date", sort_order="desc")
            ).items
            for page in (1, 2, 3)
        ]
    ids = [tx.id for page in pages for tx in page]
    assert ids == [5, 4, 3, 2, 1]


def test_script_00007_turns_arca_targets_into_policy_version(db: tuple[Config, Engine]) -> None:
    cfg, engine = db
    command.upgrade(cfg, "script_00006")
    with engine.begin() as conn:
        conn.execute(text("UPDATE arca_targets SET target_pct = 35 WHERE arca_class = 'ACOES'"))
        conn.execute(text("UPDATE arca_targets SET target_pct = 15 WHERE arca_class = 'CAIXA'"))
        conn.execute(
            text(
                "UPDATE arca_targets SET intra_class_strategy = 'EQUAL_WEIGHT' "
                "WHERE arca_class = 'REAL_ESTATE'"
            )
        )

    command.upgrade(cfg, "script_00007")

    from sqlalchemy.orm import sessionmaker

    from domain.shared.enums import ArcaClass, IntraClassStrategy
    from infra.data.unit_of_work import SqlAlchemyUnitOfWork

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with SqlAlchemyUnitOfWork(session_factory=factory) as uow:
        policy = uow.policies.get_current()
    assert policy is not None and policy.version == 1
    assert policy.arca.classes[ArcaClass.ACOES].target_pct == 35.0
    assert policy.arca.classes[ArcaClass.CAIXA].target_pct == 15.0
    assert (
        policy.arca.classes[ArcaClass.REAL_ESTATE].intra_class_strategy
        == IntraClassStrategy.EQUAL_WEIGHT
    )

    command.downgrade(cfg, "script_00006")
    with engine.connect() as conn:
        rows = dict(conn.execute(text("SELECT arca_class, target_pct FROM arca_targets")).all())
    assert float(rows["ACOES"]) == 35.0


def test_script_00009_assigns_existing_ledger_to_principal(db: tuple[Config, Engine]) -> None:
    cfg, engine = db
    command.upgrade(cfg, "script_00008")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO assets (id, ticker, name, asset_type, arca_class, currency, "
                "cerrado_answers, created_at, updated_at) VALUES (1, 'WEGE3', 'WEG', "
                "'STOCK_BR', 'ACOES', 'BRL', '{}', '2025-01-01', '2025-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO transactions (asset_id, kind, trade_date, quantity, unit_price, "
                "fees, fx_rate, created_at) VALUES (1, 'BUY', '2025-01-02', 10, 40, 0, 1, "
                "'2025-01-02')"
            )
        )

    command.upgrade(cfg, "script_00009")

    with engine.connect() as conn:
        assert conn.execute(text("SELECT account_id FROM transactions")).scalar() == 1
        assert conn.execute(text("SELECT name FROM accounts")).scalar() == "Principal"

    command.downgrade(cfg, "script_00008")
    with engine.connect() as conn:
        columns = [row[1] for row in conn.execute(text("PRAGMA table_info(transactions)"))]
    assert "account_id" not in columns
