"""Unit tests for the persistence ports' contract and the rate curve loader."""

from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal

import pytest

from domain.portfolio.services.curves import earliest_fixed_income_start, load_rate_curves
from domain.shared import repositories
from domain.shared.entities import (
    AssetEntity,
    FixedIncomeTermEntity,
    MarketSeriesPoint,
    TransactionEntity,
)
from domain.shared.enums import (
    AssetType,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    SeriesUnit,
    TransactionKind,
)
from domain.shared.unit_of_work import AbstractUnitOfWork


class _UoW(AbstractUnitOfWork):
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_unit_of_work_rolls_back_only_on_errors() -> None:
    with _UoW() as uow:
        uow.commit()
    assert uow.committed and not uow.rolled_back

    failing = _UoW()
    with pytest.raises(RuntimeError), failing:
        raise RuntimeError("boom")
    assert failing.rolled_back


PORTS = [
    cls
    for _, cls in inspect.getmembers(repositories, inspect.isclass)
    if cls.__module__ == repositories.__name__ and cls.__name__.startswith("Abstract")
]


@pytest.mark.parametrize("port", PORTS, ids=lambda p: p.__name__)
def test_every_port_method_is_abstract(port: type) -> None:
    """Ports declare the contract only: each method must be implemented by the adapter."""
    assert port.__abstractmethods__, port
    with pytest.raises(TypeError):
        port()
    concrete = type(f"Bare{port.__name__}", (port,), {})
    concrete.__abstractmethods__ = frozenset()
    instance = concrete()
    for name in port.__abstractmethods__:
        method = getattr(instance, name)
        args, kwargs = [], {}
        for param in inspect.signature(method).parameters.values():
            if param.default is not inspect.Parameter.empty:
                continue
            if param.kind is inspect.Parameter.KEYWORD_ONLY:
                kwargs[param.name] = None
            else:
                args.append(None)
        with pytest.raises(NotImplementedError):
            method(*args, **kwargs)


class _Series:
    def __init__(self, points: dict[str, list[MarketSeriesPoint]]) -> None:
        self.points = points
        self.asked: list[tuple[str, date | None]] = []

    def list_series(
        self, symbol: str, *, date_from: date | None = None, date_to: date | None = None
    ):
        self.asked.append((symbol, date_from))
        return self.points.get(symbol, [])


def _point(symbol: str, day: date, value: float, unit: SeriesUnit) -> MarketSeriesPoint:
    return MarketSeriesPoint(symbol=symbol, reference_date=day, value=value, unit=unit)


def test_rate_curves_read_daily_and_monthly_series_as_fractions() -> None:
    series = _Series(
        {
            "CDI": [_point("CDI", date(2025, 3, 10), 0.05, SeriesUnit.PERCENT_PER_DAY)],
            "SELIC": [_point("SELIC", date(2025, 3, 10), 0.051, SeriesUnit.PERCENT_PER_DAY)],
            "IPCA": [_point("IPCA", date(2025, 3, 1), 0.4, SeriesUnit.PERCENT_PER_MONTH)],
        }
    )
    curves = load_rate_curves(
        series,
        date_from=date(2025, 3, 10),
        date_to=date(2025, 3, 31),
        annual_cdi_rate=0.14,
        annual_ipca_rate=0.05,
    )
    assert curves.cdi_daily[date(2025, 3, 10)] == pytest.approx(0.0005)
    assert curves.selic_daily[date(2025, 3, 10)] == pytest.approx(0.00051)
    assert list(curves.ipca_monthly.values()) == [pytest.approx(0.004)]
    assert ("IPCA", date(2000, 7, 1)) in series.asked  # IPCA since the VNA base (July 2000)

    empty = load_rate_curves(
        series,
        date_from=None,
        date_to=date(2025, 3, 31),
        annual_cdi_rate=0.14,
        annual_ipca_rate=0.05,
    )
    assert empty.annual_cdi_rate == 0.14 and not empty.cdi_daily


def test_earliest_fixed_income_start_is_the_first_purchase() -> None:
    term = FixedIncomeTermEntity(
        instrument_kind=FixedIncomeInstrumentKind.CDB,
        indexer=FixedIncomeIndexer.CDI,
        contracted_rate=Decimal("1.1"),
        issue_date=date(2025, 2, 1),
    )
    buy = TransactionEntity(
        asset_id=1,
        kind=TransactionKind.BUY,
        trade_date=date(2025, 1, 15),
        quantity=Decimal("1"),
        unit_price=Decimal("1000"),
    )
    cdb = AssetEntity(
        ticker="CDB",
        name="CDB",
        asset_type=AssetType.FIXED_INCOME,
        fixed_income_term=term,
        transactions=(buy,),
    )
    stock = AssetEntity(ticker="X3", name="X", asset_type=AssetType.STOCK_BR, transactions=(buy,))
    assert earliest_fixed_income_start([cdb, stock]) == date(2025, 1, 15)
    assert earliest_fixed_income_start([stock]) is None
