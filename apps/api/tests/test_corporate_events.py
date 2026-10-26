"""Unit tests for corporate events in the position engine (item 12.4)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.errors import ValidationError
from domain.ledger.services.ledger import LedgerConflictError, validate_ledger_change
from domain.policy.services.lifecycle import has_position
from domain.portfolio.services.positions import InsufficientQuantityError, build_position
from domain.shared.entities import AssetEntity, CorporateEventEntity, TransactionEntity
from domain.shared.enums import AssetType, CorporateEventKind, TransactionKind


def _tx(kind: TransactionKind, day: date, qty: str, price: str) -> TransactionEntity:
    return TransactionEntity(
        asset_id=1, kind=kind, trade_date=day, quantity=Decimal(qty), unit_price=Decimal(price)
    )


def _event(
    kind: CorporateEventKind, day: date, factor: str, cost: str = "0"
) -> CorporateEventEntity:
    return CorporateEventEntity(
        asset_id=1, kind=kind, ex_date=day, factor=Decimal(factor), unit_cost=Decimal(cost)
    )


BUY = _tx(TransactionKind.BUY, date(2024, 1, 2), "100", "40")
SPLIT = _event(CorporateEventKind.SPLIT, date(2024, 6, 3), "2")


def test_split_doubles_quantity_and_keeps_cost() -> None:
    pos = build_position([BUY], events=[SPLIT])
    assert pos.quantity == Decimal("200")
    assert pos.total_cost == Decimal("4000")
    assert pos.average_price == Decimal("20")
    before = build_position([BUY], events=[SPLIT], up_to_date=date(2024, 6, 2))
    assert before.quantity == Decimal("100")


def test_sell_after_split_uses_post_event_quantity() -> None:
    sell = _tx(TransactionKind.SELL, date(2024, 6, 3), "150", "25")
    pos = build_position([BUY, sell], events=[SPLIT])
    assert pos.quantity == Decimal("50")
    assert pos.realized_pnl == Decimal("750")  # 150 x (25 - 20)
    with pytest.raises(InsufficientQuantityError):
        build_position([BUY, sell])


def test_reverse_split_and_bonus_with_attributed_cost() -> None:
    reverse = _event(CorporateEventKind.REVERSE_SPLIT, date(2024, 3, 1), "0.1")
    bonus = _event(CorporateEventKind.BONUS, date(2024, 9, 2), "1.1", cost="5")
    pos = build_position([BUY], events=[bonus, reverse])
    assert pos.quantity == Decimal("11")
    assert pos.total_cost == Decimal("4005")  # one bonus share at R$ 5


def test_events_before_any_position_are_ignored() -> None:
    early = _event(CorporateEventKind.SPLIT, date(2023, 1, 2), "3")
    assert build_position([BUY], events=[early]).quantity == Decimal("100")


def test_adjust_through_expresses_past_quantity_in_later_share_terms() -> None:
    past = build_position(
        [BUY], events=[SPLIT], up_to_date=date(2024, 3, 1), adjust_through=date(2024, 12, 31)
    )
    assert past.quantity == Decimal("200")
    assert past.total_cost == Decimal("4000")
    not_yet = build_position(
        [BUY], events=[SPLIT], up_to_date=date(2024, 3, 1), adjust_through=date(2024, 5, 1)
    )
    assert not_yet.quantity == Decimal("100")


def test_event_validation_rules() -> None:
    with pytest.raises(ValidationError):
        _event(CorporateEventKind.SPLIT, date(2024, 1, 1), "0.5")
    with pytest.raises(ValidationError):
        _event(CorporateEventKind.REVERSE_SPLIT, date(2024, 1, 1), "2")
    with pytest.raises(ValidationError):
        _event(CorporateEventKind.SPLIT, date(2024, 1, 1), "2", cost="1")
    with pytest.raises(ValidationError):
        _event(CorporateEventKind.BONUS, date(2024, 1, 1), "0")


def test_ledger_and_lifecycle_see_events() -> None:
    sell = _tx(TransactionKind.SELL, date(2024, 7, 1), "150", "25")
    asset = AssetEntity(
        ticker="X", name="X", asset_type=AssetType.STOCK_BR, corporate_events=(SPLIT,)
    )
    validate_ledger_change(asset, [BUY, sell])
    with pytest.raises(LedgerConflictError):
        validate_ledger_change(asset, [BUY, sell], events=[])
    assert has_position([BUY, sell], fixed_income=False, events=[SPLIT])
    # Without the split the ledger oversells; plain sums report no position.
    assert not has_position([BUY, sell], fixed_income=False)
