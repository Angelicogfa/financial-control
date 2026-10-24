"""Unit tests for ORM-to-Domain mappers and UnitOfWork transaction lifecycle."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fincontrol_core.domain import (
    ArcaClass,
    AssetEntity,
    AssetType,
    EarningEntity,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeTermEntity,
    TransactionEntity,
    TransactionKind,
)
from fincontrol_persistence import Base, SqlAlchemyUnitOfWork, build_engine, build_session_factory


@pytest.fixture()
def uow_factory():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    return lambda: SqlAlchemyUnitOfWork(session_factory)


@pytest.mark.unit
def test_uow_rolls_back_uncommitted_changes_on_exception(uow_factory) -> None:
    with pytest.raises(RuntimeError, match="simulated failure"), uow_factory() as uow:
        uow.assets.add(
            AssetEntity(
                ticker="PETR4",
                name="Petrobras PN",
                asset_type=AssetType.STOCK_BR,
            )
        )
        raise RuntimeError("simulated failure")

    with uow_factory() as uow:
        assert uow.assets.get_by_ticker("PETR4") is None


@pytest.mark.unit
def test_uow_persists_asset_with_fixed_income_term_and_returns_domain_entities(uow_factory) -> None:
    with uow_factory() as uow:
        created = uow.assets.add(
            AssetEntity(
                ticker="cdb-itau-110",
                name="CDB Itau 110% CDI",
                asset_type=AssetType.FIXED_INCOME,
                use_cerrado=False,
                fixed_income_term=FixedIncomeTermEntity(
                    instrument_kind=FixedIncomeInstrumentKind.CDB,
                    indexer=FixedIncomeIndexer.CDI,
                    contracted_rate=Decimal("1.10"),
                    issue_date=date(2025, 1, 2),
                    maturity_date=date(2028, 1, 2),
                    tax_exempt=False,
                    issuer="Banco Itau",
                ),
            )
        )
        assert created.id is not None
        asset_id = created.id
        uow.transactions.add(
            TransactionEntity(
                asset_id=asset_id,
                kind=TransactionKind.BUY,
                trade_date=date(2025, 1, 2),
                quantity=Decimal("1"),
                unit_price=Decimal("10000.00"),
            )
        )
        uow.earnings.add(
            EarningEntity(
                asset_id=asset_id,
                kind=EarningKind.FIXED_INCOME_COUPON,
                payment_date=date(2025, 7, 2),
                gross_amount=Decimal("500.00"),
                withholding_tax=Decimal("100.00"),
            )
        )
        uow.commit()

    with uow_factory() as uow:
        loaded = uow.assets.get_by_id(asset_id)
        assert loaded is not None
        assert isinstance(loaded, AssetEntity)
        assert loaded.ticker == "CDB-ITAU-110"
        assert loaded.arca_class == ArcaClass.CAIXA
        assert loaded.use_cerrado is False
        assert loaded.fixed_income_term is not None
        assert loaded.fixed_income_term.indexer == FixedIncomeIndexer.CDI
        assert loaded.fixed_income_term.contracted_rate == Decimal("1.10")
        assert len(loaded.transactions) == 1
        assert loaded.transactions[0].unit_price == Decimal("10000.00")
        assert len(loaded.earnings) == 1
        assert loaded.earnings[0].net_amount == Decimal("400.00")
