"""Unit tests for API Handlers, Services, DTO serialization, and strict layering rules."""

from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal

import pytest
from fincontrol_api import controllers
from fincontrol_api.handlers.serializers import to_asset_dto, to_transaction_dto
from fincontrol_api.schemas import (
    ArcaTargetItemDTO,
    ArcaTargetsUpdateRequest,
)
from fincontrol_core.arca.allocation import InvalidTargetsError
from fincontrol_core.domain.entities import (
    AssetEntity,
    FixedIncomeTermEntity,
    TransactionEntity,
)
from fincontrol_core.domain.enums import (
    ArcaClass,
    AssetType,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    IntraClassStrategy,
    TransactionKind,
)


def test_controllers_strictly_isolated_from_orm_and_repositories() -> None:
    """Enforce Rule #8: Controllers never import SQLAlchemy Session, Models, or Repos."""
    source = inspect.getsource(controllers)
    forbidden = [
        "sqlalchemy",
        "Session",
        "AssetModel",
        "TransactionModel",
        "EarningModel",
        "SqlAlchemyAssetRepository",
        "SqlAlchemyTransactionRepository",
        "SqlAlchemyUnitOfWork",
    ]
    for token in forbidden:
        assert token not in source, (
            f"Forbidden persistence symbol '{token}' found in controllers.py"
        )


def test_dto_serializers_for_asset_and_transaction() -> None:
    asset = AssetEntity(
        id=7,
        ticker="CDB-BANCO-INTER",
        name="CDB 112% CDI",
        asset_type=AssetType.FIXED_INCOME,
        arca_class=ArcaClass.CAIXA,
        use_cerrado=False,
        fixed_income_term=FixedIncomeTermEntity(
            instrument_kind=FixedIncomeInstrumentKind.CDB,
            indexer=FixedIncomeIndexer.CDI,
            contracted_rate=Decimal("1.12"),
            issue_date=date(2024, 5, 1),
        ),
    )
    dto = to_asset_dto(asset)
    assert dto.id == 7
    assert dto.use_cerrado is False
    assert dto.fixed_income_term is not None
    assert dto.fixed_income_term.contracted_rate == Decimal("1.12")

    tx = TransactionEntity(
        id=15,
        asset_id=7,
        kind=TransactionKind.BUY,
        trade_date=date(2024, 5, 1),
        quantity=Decimal("10"),
        unit_price=Decimal("100.00"),
        fees=Decimal("2.50"),
        fx_rate=Decimal("1.00"),
    )
    tx_dto = to_transaction_dto(tx, ticker="CDB-BANCO-INTER")
    assert tx_dto.total_brl == 1002.50
    assert tx_dto.ticker == "CDB-BANCO-INTER"


def test_arca_targets_update_validation_rejects_sum_not_100() -> None:
    from types import SimpleNamespace

    from fincontrol_api.handlers.policy_handlers import PolicyHandler

    class _UoW(SimpleNamespace):
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_exc):  # type: ignore[no-untyped-def]
            return None

    uow = _UoW(policies=SimpleNamespace(get_current=lambda: None))
    handler = PolicyHandler(uow_factory=lambda: uow)  # type: ignore[arg-type]

    bad_req = ArcaTargetsUpdateRequest(
        targets=[
            ArcaTargetItemDTO(
                arca_class=ArcaClass.ACOES,
                target_pct=40.0,
                intra_class_strategy=IntraClassStrategy.CERRADO,
            ),
            ArcaTargetItemDTO(
                arca_class=ArcaClass.REAL_ESTATE,
                target_pct=25.0,
                intra_class_strategy=IntraClassStrategy.CERRADO,
            ),
            ArcaTargetItemDTO(
                arca_class=ArcaClass.CAIXA,
                target_pct=25.0,
                intra_class_strategy=IntraClassStrategy.CERRADO,
            ),
            ArcaTargetItemDTO(
                arca_class=ArcaClass.ATIVOS_INTERNACIONAIS,
                target_pct=25.0,
                intra_class_strategy=IntraClassStrategy.CERRADO,
            ),
        ]
    )
    with pytest.raises(InvalidTargetsError):
        handler.update_arca_targets(bad_req)
