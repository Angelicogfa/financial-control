"""Unit tests for API Handlers, Services, DTO serialization, and strict layering rules."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import fincontrol_api
import pytest
from fincontrol_api.modules.assets.serializers import to_asset_dto
from fincontrol_api.modules.ledger.serializers import to_transaction_dto
from fincontrol_api.modules.policy.schemas import ArcaTargetItemDTO, ArcaTargetsUpdateRequest
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

PACKAGE = Path(fincontrol_api.__file__).parent
ROUTERS = sorted(PACKAGE.glob("modules/**/router.py"))


def test_every_module_has_a_router() -> None:
    assert len(ROUTERS) == 11


@pytest.mark.parametrize("router", ROUTERS, ids=lambda p: p.parent.name)
def test_controllers_strictly_isolated_from_orm_and_repositories(router: Path) -> None:
    """Enforce Rule #8: Controllers never import SQLAlchemy Session, Models, or Repos."""
    source = router.read_text(encoding="utf-8")
    forbidden = [
        "sqlalchemy",
        "fincontrol_persistence",
        "Session",
        "AssetModel",
        "TransactionModel",
        "EarningModel",
        "SqlAlchemyAssetRepository",
        "SqlAlchemyTransactionRepository",
        "SqlAlchemyUnitOfWork",
        "uow_factory",
    ]
    for token in forbidden:
        assert token not in source, f"Forbidden persistence symbol '{token}' found in {router}"


def test_only_the_composition_root_picks_the_unit_of_work() -> None:
    """Use cases depend on the abstract UoW; the SQLAlchemy one is chosen in one place."""
    offenders = [
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*.py")
        if path.name != "composition.py"
        and (
            "SqlAlchemyUnitOfWork" in (text := path.read_text(encoding="utf-8"))
            or "import sqlalchemy" in text
            or "from sqlalchemy" in text
        )
    ]
    assert offenders == []


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

    from fincontrol_api.modules.policy.use_cases import PolicyHandler

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
