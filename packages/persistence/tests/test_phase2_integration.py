"""Phase 2 integration tests: SqlAlchemyUnitOfWork + Pure Domain Consolidation & Rebalancing."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from fincontrol_core.arca.allocation import ArcaTargets
from fincontrol_core.domain.entities import (
    AssetEntity,
    EarningEntity,
    FixedIncomeTermEntity,
    TransactionEntity,
)
from fincontrol_core.domain.enums import (
    ArcaClass,
    AssetType,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    IntraClassStrategy,
    TransactionKind,
)
from fincontrol_core.market.models import Quote
from fincontrol_core.portfolio.consolidation import (
    consolidate_portfolio,
    plan_contribution,
)
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_uow_and_domain_consolidation_end_to_end(tmp_path: Path, monkeypatch) -> None:
    db_file = tmp_path / "phase2_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    persistence_dir = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(persistence_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(persistence_dir / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    with SqlAlchemyUnitOfWork(session_factory=factory) as uow:
        stock = uow.assets.add(
            AssetEntity(
                ticker="BBAS3",
                name="Banco do Brasil",
                asset_type=AssetType.STOCK_BR,
                arca_class=ArcaClass.ACOES,
                cerrado_answers={"roe": True, "dividends": True},
            )
        )
        rf = uow.assets.add(
            AssetEntity(
                ticker="TESOURO-SELIC-2029",
                name="Tesouro Selic 2029",
                asset_type=AssetType.TREASURY,
                arca_class=ArcaClass.CAIXA,
                fixed_income_term=FixedIncomeTermEntity(
                    instrument_kind=FixedIncomeInstrumentKind.TESOURO_SELIC,
                    indexer=FixedIncomeIndexer.SELIC,
                    contracted_rate=Decimal("100"),
                    issue_date=date(2024, 3, 10),
                ),
            )
        )
        assert stock.id is not None
        assert rf.id is not None

        uow.transactions.add(
            TransactionEntity(
                asset_id=stock.id,
                kind=TransactionKind.BUY,
                trade_date=date(2024, 3, 10),
                quantity=Decimal("200"),
                unit_price=Decimal("25.00"),
            )
        )
        uow.transactions.add(
            TransactionEntity(
                asset_id=rf.id,
                kind=TransactionKind.BUY,
                trade_date=date(2024, 3, 10),
                quantity=Decimal("1"),
                unit_price=Decimal("5000.00"),
            )
        )
        uow.earnings.add(
            EarningEntity(
                asset_id=stock.id,
                kind=EarningKind.DIVIDEND,
                payment_date=date(2024, 8, 20),
                gross_amount=Decimal("280.00"),
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory=factory) as uow:
        assets = uow.assets.list_all()

    report = consolidate_portfolio(
        assets=assets,
        targets=ArcaTargets.default(),
        quotes={"BBAS3": Quote(symbol="BBAS3", price=29.00, currency="BRL")},
        as_of_date=date(2025, 1, 10),
    )

    assert report.total_invested_brl == 10000.00
    assert report.total_received_earnings_brl == 280.00
    assert report.total_consolidated_pnl_brl > 1080.00

    contribution = plan_contribution(
        report=report,
        targets=ArcaTargets.default(),
        amount_brl=1500.00,
        strategy_override=IntraClassStrategy.EQUAL_WEIGHT,
    )
    assert contribution.contribution_amount_brl == 1500.00
    engine.dispose()
