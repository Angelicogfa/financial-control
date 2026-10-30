"""Phase 43.2: the Garimpo's point-in-time signals."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from domain.disclosures.entities import IssuerTicker
from domain.disclosures.statements import (
    COMPANY,
    DEPRECIATION,
    DFP,
    DIVIDENDS_PAID,
    EBIT,
    EQUITY,
    NET_INCOME,
    REVENUE,
    SHARES,
    PitFundamentals,
    StatementFact,
)
from domain.forecast.valuation_model import CompanyInput, add_months
from domain.mining.signals import (
    IMPROVEMENT,
    MOMENTUM,
    QUALITY,
    VALUE,
    fundamentals_raw,
    mining_signals,
    momentum_raw,
)
from domain.recommendation.signals import INCOME, REGISTRY_SIGNALS, RISK
from domain.shared.entities import CatalogInstrument
from domain.shared.enums import AssetType, SeriesUnit
from domain.simulation.data import index_symbol, px_symbol, tr_symbol
from tests.conftest import offline_gateway
from worker.jobs import run_mining_job

NOW = datetime(2026, 10, 30, 20, 0, tzinfo=UTC)


def _snap(ref: date, income: float, *, revenue=1000.0, equity=500.0, ebit=150.0) -> PitFundamentals:
    return PitFundamentals(
        cnpj="1",
        as_of=ref + timedelta(days=40),
        reference_date=ref,
        delivered_on=ref + timedelta(days=40),
        doc_type="ITR",
        version=1,
        template=COMPANY,
        values={
            NET_INCOME: income,
            REVENUE: revenue,
            EQUITY: equity,
            EBIT: ebit,
            DEPRECIATION: 50.0,
            DIVIDENDS_PAID: 10.0,
            SHARES: 100.0,
            "debt_current": 100.0,
            "cash": 20.0,
        },
    )


def _quarters(start: date, incomes: list[float]) -> list[PitFundamentals]:
    out, ref = [], start
    for income in incomes:
        out.append(_snap(ref, income))
        month = add_months((ref.year, ref.month), 3)
        nxt = date(month[0] + (month[1] == 12), month[1] % 12 + 1, 1)
        ref = date.fromordinal(nxt.toordinal() - 1)
    return out


def test_fundamentals_raw_reads_quality_and_improvement() -> None:
    company = CompanyInput(
        ticker="AAAA3",
        sector="X",
        snapshots=_quarters(date(2022, 3, 31), [80, 90, 100, 100, 120, 130]),
        prices={},
    )
    raw = fundamentals_raw(company, (2023, 9))  # sees the 2023-06-30 statement (6th quarter)
    assert raw["roe"] == pytest.approx(130 / 500)
    assert raw["margin"] == pytest.approx(130 / 1000)
    assert raw["low_leverage"] == pytest.approx(-(100 - 20) / 200)
    assert raw["income_growth"] == pytest.approx((130 - 90) / 500)  # vs 2022-06-30
    assert raw["margin_change"] == pytest.approx((130 - 90) / 1000)
    assert raw["roe_stability"] < 0
    assert fundamentals_raw(company, (2022, 3)) == {}  # nothing delivered yet


def test_momentum_skips_the_last_month() -> None:
    alphas = {add_months((2020, 1), i): 0.01 for i in range(12)}
    alphas[(2020, 12)] = 0.5  # the last month does not count
    assert momentum_raw(alphas, (2020, 12)) == pytest.approx(0.11)
    assert momentum_raw(alphas, (2020, 6)) is None  # needs 11 earlier months


def _companies(n: int = 12):
    companies, alphas = {}, {}
    months = [add_months((2019, 1), i) for i in range(60)]
    for c in range(n):
        ticker = f"C{c:02d}3"
        incomes = [50 + 5 * c + q * c for q in range(20)]  # better and improving with c
        snaps = _quarters(date(2019, 3, 31), incomes)
        prices = {m: 10.0 + 0.02 * c * i for i, m in enumerate(months)}
        companies[ticker] = CompanyInput(ticker, "AB"[c % 2], snaps, prices)
        alphas[ticker] = {m: 0.001 * (c - n / 2) for m in months}
    return companies, alphas, months


def test_signals_order_the_companies() -> None:
    companies, alphas, months = _companies()
    panel = mining_signals(companies, alphas, months)
    month = (2023, 6)
    rows = {t: panel[t][month] for t in companies}
    best, worst = rows["C113"], rows["C003"]
    assert best[QUALITY] > worst[QUALITY]
    assert best[IMPROVEMENT] > worst[IMPROVEMENT]
    assert best[MOMENTUM] > worst[MOMENTUM]
    assert VALUE in best
    assert all(-3 <= z <= 3 for r in rows.values() for z in r.values())


def seed_panel(api: SimpleNamespace) -> dict[str, CompanyInput]:
    """Twelve liquid companies with statements and weekly prices, mapped to the CVM."""
    companies, _alphas, _months = _companies()
    days = [date(2019, 1, 2) + timedelta(days=7 * i) for i in range(270)]
    rng = np.random.default_rng(3)
    ibov = 100_000 * np.cumprod(1 + rng.normal(0.001, 0.02, len(days)))
    with api.uow_factory() as uow:
        uow.catalog.upsert(
            [
                CatalogInstrument(
                    ticker=t, name=t, asset_type=AssetType.STOCK_BR, sector=c.sector, volume_brl=5e6
                )
                for t, c in companies.items()
            ]
        )
        uow.cvm_issuers.replace_all(
            [IssuerTicker(t, f"{i:014d}", t) for i, t in enumerate(companies, start=1)]
        )
        facts = []
        for i, (t, c) in enumerate(companies.items(), start=1):
            for s in c.snapshots:
                for metric, value in s.values.items():
                    start = (
                        date(s.reference_date.year, 1, 1)
                        if metric in (NET_INCOME, REVENUE, EBIT, DEPRECIATION, DIVIDENDS_PAID)
                        else None
                    )
                    facts.append(
                        StatementFact(
                            f"{i:014d}",
                            DFP if s.reference_date.month == 12 else "ITR",
                            s.reference_date,
                            1,
                            s.delivered_on,
                            "CON",
                            COMPANY,
                            metric,
                            start,
                            s.reference_date,
                            value,
                        )
                    )
            path = 10 * np.cumprod(1 + rng.normal(0.002 * (i % 4), 0.03, len(days)))
            uow.market_series.upsert_points(
                px_symbol(t), list(zip(days, path, strict=True)), unit=SeriesUnit.PRICE
            )
            uow.market_series.upsert_points(
                tr_symbol(t), list(zip(days, path, strict=True)), unit=SeriesUnit.PRICE
            )
        uow.cvm_statements.add_many(facts)
        uow.market_series.upsert_points(
            index_symbol("IBOV"), list(zip(days, ibov, strict=True)), unit=SeriesUnit.INDEX_POINTS
        )
        uow.market_series.upsert_points(
            "CDI", [(d, 0.04) for d in days], unit=SeriesUnit.PERCENT_PER_DAY
        )
        uow.commit()
    return companies


def test_run_mining_stores_the_panel(api: SimpleNamespace) -> None:
    seed_panel(api)
    details = run_mining_job(api.uow_factory, offline_gateway(), now=NOW)
    assert details["universe"] == 12 and details["companies"] == 12 and details["signals"] > 0
    with api.uow_factory() as uow:
        last = uow.mining.latest_signal_month()
        own = uow.mining.signals_for("C113")
        priced = max(s.month for s in own if s.signal == MOMENTUM)  # synthetic prices end in 2024
        month = uow.mining.signals_of_month(priced)
        # The one register of point-in-time signals: the Garimpo's four and, from Phase 45.1,
        # the recommendation's income and risk.
        assert {s.signal for s in month} == set(REGISTRY_SIGNALS)
        assert {INCOME, RISK} <= {s.signal for s in own}
    assert details["last_month"] == last.isoformat()
    # Recomputing replaces the panel instead of piling it up.
    again = run_mining_job(api.uow_factory, offline_gateway(), now=NOW)
    assert again["signals"] == details["signals"]
