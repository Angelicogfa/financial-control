"""Unit tests for the research service: shared asset registration and statement refresh."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fincontrol_api.modules.research.service import (
    StatementRefresher,
    register_researched_asset,
    suggested_arca_class,
)
from fincontrol_core.domain.enums import ArcaClass, AssetType
from fincontrol_core.errors import ValidationError
from fincontrol_core.fundamentals.history import FundamentalPeriod, FundamentalSnapshot


class _Gateway:
    """Statements for ITUB4; WEGE3 fails like a provider outage; anything else has none."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def get_annual_statements(self, symbol, *, asset_type=None, bypass_cache=False):  # type: ignore[no-untyped-def]
        self.asked.append(symbol)
        if symbol == "WEGE3":
            raise RuntimeError("provider down")
        if symbol != "ITUB4":
            return []
        return [
            FundamentalSnapshot(
                ticker="ITUB4",
                period=FundamentalPeriod.ANNUAL,
                reference_date=date(2024, 12, 31),
                metrics={"net_income": 40e9},
            )
        ]


def test_register_uses_the_chosen_quadrant_or_the_suggestion(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        chosen = register_researched_asset(
            uow, " itsa4 ", asset_type=AssetType.STOCK_BR, arca_class=ArcaClass.CAIXA
        )
        suggested = register_researched_asset(uow, "HGLG11", asset_type=AssetType.FII)
        uow.commit()
    assert (chosen.ticker, chosen.name, chosen.arca_class) == ("ITSA4", "ITSA4", ArcaClass.CAIXA)
    assert suggested.arca_class == suggested_arca_class("HGLG11", AssetType.FII)
    assert suggested.arca_class == ArcaClass.REAL_ESTATE


def test_register_requires_a_type_outside_the_catalog(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow, pytest.raises(ValidationError) as err:
        register_researched_asset(uow, "XPTO3")
    assert err.value.code == "UNKNOWN_INSTRUMENT"


def test_refresh_stores_statements_and_survives_provider_failures(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        for ticker, asset_type in (
            ("ITUB4", AssetType.STOCK_BR),
            ("WEGE3", AssetType.STOCK_BR),
            ("BBAS3", AssetType.STOCK_BR),
            ("HGLG11", AssetType.FII),  # funds publish no statements: not asked
        ):
            register_researched_asset(uow, ticker, asset_type=asset_type)
        uow.commit()
    gateway = _Gateway()
    refresher = StatementRefresher(uow_factory=api.uow_factory, gateway=gateway)  # type: ignore[arg-type]

    stored = refresher.refresh(["itub4", "WEGE3", "BBAS3", "HGLG11", "NOPE3", " "])

    assert stored == {"BBAS3": 0, "ITUB4": 1, "WEGE3": 0}
    assert sorted(gateway.asked) == ["BBAS3", "ITUB4", "WEGE3"]
    with api.uow_factory() as uow:
        assert len(uow.fundamentals.list_for_many(["ITUB4"])["ITUB4"]) == 1
    assert refresher.refresh([]) == {}
