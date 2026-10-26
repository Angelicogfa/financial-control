"""Unit tests for snapshot helpers: external flows, history windows and price lookup."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fincontrol_core.domain.entities import AssetEntity, TransactionEntity
from fincontrol_core.domain.enums import AssetType, TransactionKind
from fincontrol_core.portfolio.snapshots import (
    PriceLookup,
    external_flow_brl,
    first_trade_date,
    history_range_for,
    history_start,
    net_flow_between,
)


def _tx(kind: TransactionKind, on: date, fx: str = "1") -> TransactionEntity:
    return TransactionEntity(
        asset_id=1,
        kind=kind,
        trade_date=on,
        quantity=Decimal("10"),
        unit_price=Decimal("20"),
        fees=Decimal("2"),
        fx_rate=Decimal(fx),
    )


def test_external_flows_include_fees_and_fx() -> None:
    assert external_flow_brl(_tx(TransactionKind.BUY, date(2025, 1, 2))) == 202.0
    assert external_flow_brl(_tx(TransactionKind.SELL, date(2025, 1, 2), fx="5")) == -990.0


def test_net_flow_between_is_half_open() -> None:
    asset = AssetEntity(
        id=1,
        ticker="X",
        name="X",
        asset_type=AssetType.STOCK_BR,
        transactions=(
            _tx(TransactionKind.BUY, date(2025, 1, 2)),
            _tx(TransactionKind.BUY, date(2025, 1, 3)),
            _tx(TransactionKind.SELL, date(2025, 1, 6)),
        ),
    )
    assert net_flow_between([asset], after=date(2025, 1, 2), up_to=date(2025, 1, 6)) == 4.0
    assert net_flow_between([asset], after=None, up_to=date(2025, 1, 2)) == 202.0
    assert first_trade_date([asset]) == date(2025, 1, 2)
    assert first_trade_date([]) is None


@pytest.mark.parametrize(
    ("start", "expected"),
    [
        (date(2024, 7, 1), "1y"),
        (date(2023, 7, 1), "2y"),
        (date(2021, 1, 1), "5y"),
        (date(2016, 1, 1), "10y"),
        (date(2000, 1, 1), "max"),
    ],
)
def test_history_range_for(start: date, expected: str) -> None:
    assert history_range_for(start, date(2025, 6, 30)) == expected


def test_history_start_defaults_to_one_year_and_caps_at_ten() -> None:
    end = date(2025, 6, 30)
    assert history_start(end) == date(2024, 6, 30)
    assert history_start(end, date(2022, 1, 3), None) == date(2022, 1, 3)
    assert history_start(end, date(1990, 1, 1)) == date(2015, 7, 3)


def test_price_lookup_carries_last_close() -> None:
    lookup = PriceLookup([(date(2025, 1, 3), 11.0), (date(2025, 1, 2), 10.0)])
    assert lookup.on(date(2025, 1, 1)) is None
    assert lookup.on(date(2025, 1, 2)) == 10.0
    assert lookup.on(date(2025, 1, 5)) == 11.0
    assert not PriceLookup([])
