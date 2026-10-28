"""Unit tests for the seven-pillar health engine, its input builders and the health policy."""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from core.errors import ValidationError
from domain.market.entities import PricePoint
from domain.policy.services.allocation import BAND_ABOVE, BAND_BELOW, BAND_WITHIN, ClassAllocation
from domain.policy.services.policy import HealthPolicy, InvestmentPolicy
from domain.portfolio.services.health import (
    BracketLot,
    HealthInputs,
    HealthPillar,
    HealthStatus,
    Holding,
    diagnose,
    issuer_of,
    worst,
)
from domain.portfolio.services.health_inputs import (
    asset_return_grid,
    checklist_age_days,
    policy_benchmark,
)
from domain.shared.entities import AssetEntity, ChecklistAnswer
from domain.shared.enums import (
    AnswerSource,
    AnswerValue,
    ArcaClass,
    AssetPurpose,
    AssetType,
)

AS_OF = date(2026, 10, 27)
POLICY = HealthPolicy()


def _holding(ticker: str, value: float, **kw: object) -> Holding:
    defaults: dict[str, object] = {
        "name": ticker,
        "asset_type": AssetType.STOCK_BR,
        "arca_class": ArcaClass.ACOES,
    }
    defaults.update(kw)
    return Holding(ticker=ticker, value_brl=value, **defaults)  # type: ignore[arg-type]


def _alloc(arca_class: ArcaClass, deviation: float, band: float = 5.0) -> ClassAllocation:
    status = BAND_WITHIN
    if deviation > band:
        status = BAND_ABOVE
    elif deviation < -band:
        status = BAND_BELOW
    return ClassAllocation(
        arca_class=arca_class,
        label=arca_class.value,
        invested_value=0.0,
        current_value=0.0,
        current_pct=25.0 + deviation,
        target_pct=25.0,
        deviation_pct=deviation,
        gap_value=0.0,
        band_pct=band,
        band_status=status,
    )


def _equal_portfolio(n: int = 10) -> list[Holding]:
    return [_holding(f"AAAA{i}", 1000.0, sector=f"Setor {i}") for i in range(n)]


def _pillar(report, pillar: HealthPillar):  # noqa: ANN001, ANN202
    return next(p for p in report.pillars if p.pillar == pillar)


def _check(report, key: str):  # noqa: ANN001, ANN202
    return next(c for p in report.pillars for c in p.checks if c.key == key)


def test_worst_ignores_insufficient_data_unless_nothing_was_evaluated() -> None:
    assert worst([HealthStatus.OK, HealthStatus.INSUFFICIENT_DATA]) == HealthStatus.OK
    assert worst([HealthStatus.OK, HealthStatus.CRITICAL]) == HealthStatus.CRITICAL
    assert worst([HealthStatus.INSUFFICIENT_DATA]) == HealthStatus.INSUFFICIENT_DATA


def test_empty_portfolio_has_no_data_to_judge() -> None:
    report = diagnose(HealthInputs(as_of=AS_OF, holdings=[]), POLICY)

    assert report.total_value_brl == 0.0
    assert len(report.pillars) == 7
    assert _check(report, "largest_asset").status == HealthStatus.INSUFFICIENT_DATA


def test_critical_pillar_comes_first_and_drives_the_overall_status() -> None:
    holdings = [_holding("PETR4", 9000.0, sector="Petróleo"), _holding("VALE3", 1000.0)]
    report = diagnose(HealthInputs(as_of=AS_OF, holdings=holdings), POLICY)

    assert report.status == HealthStatus.CRITICAL
    assert report.pillars[0].pillar == HealthPillar.CONCENTRATION
    assert report.pillars[0].status == HealthStatus.CRITICAL
    largest = _check(report, "largest_asset")
    assert largest.value == pytest.approx(0.9)
    assert "PETR4" in largest.explanation
    assert largest.action is not None


def test_equal_weights_are_healthy_concentration() -> None:
    report = diagnose(HealthInputs(as_of=AS_OF, holdings=_equal_portfolio()), POLICY)

    assert _check(report, "largest_asset").status == HealthStatus.OK
    assert _check(report, "effective_assets").value == pytest.approx(10.0)
    assert _check(report, "top5_assets").value == pytest.approx(0.5)
    asset = next(b for b in report.concentration if b.dimension == "ASSET")
    assert asset.hhi == pytest.approx(0.1)


def test_treasury_does_not_count_as_a_concentrated_asset() -> None:
    holdings = [
        _holding("TESOURO SELIC 2029", 9000.0, asset_type=AssetType.TREASURY),
        *_equal_portfolio(10),
    ]
    report = diagnose(HealthInputs(as_of=AS_OF, holdings=holdings), POLICY)

    assert _check(report, "largest_asset").status == HealthStatus.OK
    assert issuer_of(holdings[0]) == "TESOURO NACIONAL"


def test_issuer_groups_share_classes_of_the_same_company() -> None:
    assert issuer_of(_holding("PETR4", 1.0)) == "PETR"
    assert issuer_of(_holding("PETR3", 1.0)) == "PETR"
    assert issuer_of(_holding("CDB X", 1.0, issuer="Banco Inter")) == "BANCO INTER"


def test_sector_concentration_ignores_etfs_and_unknown_sectors() -> None:
    holdings = [
        _holding("ITUB4", 4000.0, sector="Bancos"),
        _holding("BBDC4", 4000.0, sector="Bancos"),
        _holding("WEGE3", 2000.0, sector="Indústria"),
        _holding("BOVA11", 50_000.0, asset_type=AssetType.ETF_BR),
        _holding("XXXX3", 1000.0),
    ]
    check = _check(diagnose(HealthInputs(as_of=AS_OF, holdings=holdings), POLICY), "largest_sector")

    assert check.status == HealthStatus.CRITICAL
    assert check.value == pytest.approx(8000 / 11000, abs=1e-4)
    assert "não tem setor" in check.explanation


def test_fgc_exposure_above_the_limit_is_critical() -> None:
    cdb = {"asset_type": AssetType.FIXED_INCOME, "arca_class": ArcaClass.CAIXA, "fgc_covered": True}
    holdings = [
        _holding("CDB A", 260_000.0, issuer="Banco A", **cdb),
        _holding("CDB B", 100_000.0, issuer="Banco B", **cdb),
        *_equal_portfolio(),
    ]
    report = diagnose(HealthInputs(as_of=AS_OF, holdings=holdings), POLICY)
    check = _check(report, "fgc_exposure")

    assert check.status == HealthStatus.CRITICAL
    assert report.institutions[0].issuer == "BANCO A"
    assert report.institutions[0].usage == pytest.approx(1.04)
    assert "BANCO A" in (check.action or "")


def test_fgc_without_issuer_warns() -> None:
    cdb = {"asset_type": AssetType.FIXED_INCOME, "arca_class": ArcaClass.CAIXA, "fgc_covered": True}
    holdings = [_holding("CDB A", 10_000.0, **cdb), *_equal_portfolio()]
    check = _check(diagnose(HealthInputs(as_of=AS_OF, holdings=holdings), POLICY), "fgc_exposure")

    assert check.status == HealthStatus.WARNING


def test_band_deviation_beyond_twice_the_band_is_critical() -> None:
    allocations = [
        _alloc(ArcaClass.ACOES, 12.0),
        _alloc(ArcaClass.CAIXA, -12.0),
        _alloc(ArcaClass.REAL_ESTATE, 0.0),
        _alloc(ArcaClass.ATIVOS_INTERNACIONAIS, 0.0),
    ]
    report = diagnose(
        HealthInputs(
            as_of=AS_OF,
            holdings=_equal_portfolio(),
            allocations=allocations,
            class_out_of_band_days={ArcaClass.ACOES: 40},
        ),
        POLICY,
    )
    check = _check(report, "band_adherence")

    assert check.status == HealthStatus.CRITICAL
    assert "há 40 dias" in check.explanation
    mild = diagnose(
        HealthInputs(
            as_of=AS_OF,
            holdings=_equal_portfolio(),
            allocations=[_alloc(ArcaClass.ACOES, 7.0), _alloc(ArcaClass.CAIXA, -7.0)],
        ),
        POLICY,
    )
    assert _check(mild, "band_adherence").status == HealthStatus.WARNING


def test_ineligible_holdings_with_weight_warn() -> None:
    holdings = [_holding("OIBR3", 1000.0, eligible=False), *_equal_portfolio()]
    check = _check(
        diagnose(HealthInputs(as_of=AS_OF, holdings=holdings), POLICY), "ineligible_weight"
    )

    assert check.status == HealthStatus.WARNING
    assert "OIBR3" in check.explanation


def _returns(n: int, seed: int, drift: float = 0.0005, scale: float = 0.01) -> list[float]:
    rng = random.Random(seed)
    return [drift + rng.gauss(0.0, scale) for _ in range(n)]


def _dates(n: int) -> list[date]:
    return [AS_OF - timedelta(days=n - i) for i in range(n)]


def test_short_history_reports_insufficient_data_with_the_minimum_window() -> None:
    report = diagnose(
        HealthInputs(
            as_of=AS_OF,
            holdings=_equal_portfolio(),
            portfolio_dates=_dates(10),
            portfolio_returns=_returns(10, 1),
        ),
        POLICY,
    )
    volatility = _check(report, "volatility")

    assert volatility.status == HealthStatus.INSUFFICIENT_DATA
    assert volatility.observations == 10
    assert volatility.min_observations == POLICY.min_observations
    assert _check(report, "rolling_sharpe").status == HealthStatus.INSUFFICIENT_DATA
    assert _pillar(report, HealthPillar.DIVERSIFICATION).status == HealthStatus.INSUFFICIENT_DATA


def test_long_history_evaluates_risk_and_performance() -> None:
    n = 400
    returns = _returns(n, 2)
    report = diagnose(
        HealthInputs(
            as_of=AS_OF,
            holdings=_equal_portfolio(),
            portfolio_dates=_dates(n),
            portfolio_returns=returns,
            benchmark_returns=_returns(n, 3),
            cdi_returns=[0.0004] * n,
        ),
        POLICY,
    )

    assert _check(report, "volatility").status != HealthStatus.INSUFFICIENT_DATA
    assert report.risk.volatility == pytest.approx(0.1587, abs=0.02)
    assert _check(report, "information_ratio").value is not None
    assert _check(report, "cdi_consistency").observations >= 6
    assert report.performance.rolling
    assert report.performance.sharpe_interval is not None
    interval = report.performance.sharpe_interval
    assert interval.low <= report.performance.sharpe <= interval.high


def test_deep_drawdown_is_critical() -> None:
    returns = [0.001] * 30 + [-0.02] * 15
    check = _check(
        diagnose(
            HealthInputs(
                as_of=AS_OF,
                holdings=_equal_portfolio(),
                portfolio_dates=_dates(45),
                portfolio_returns=returns,
            ),
            POLICY,
        ),
        "current_drawdown",
    )

    assert check.status == HealthStatus.CRITICAL
    assert check.value == pytest.approx(1 - 0.98**15, abs=1e-4)
    assert "15 pregões" in check.explanation


def test_diversification_with_twin_assets_flags_the_pair() -> None:
    n = 200
    base = _returns(n, 4)
    holdings = [_holding("ITUB4", 5000.0), _holding("ITSA4", 5000.0), _holding("WEGE3", 5000.0)]
    report = diagnose(
        HealthInputs(
            as_of=AS_OF,
            holdings=holdings,
            asset_dates=_dates(n),
            asset_returns={
                "ITUB4": base,
                "ITSA4": [x * 1.05 for x in base],
                "WEGE3": _returns(n, 5),
            },
        ),
        POLICY,
    )

    pairs = _check(report, "correlated_pairs")
    assert pairs.status == HealthStatus.WARNING
    assert "ITUB4 × ITSA4" in pairs.explanation
    assert report.diversification.diversification_ratio is not None
    assert sum(s.risk_share for s in report.diversification.by_asset) == pytest.approx(1, abs=1e-3)
    assert _check(report, "historical_stress").status != HealthStatus.INSUFFICIENT_DATA


def test_quality_uses_weighted_checklist_and_stale_answers() -> None:
    holdings = [
        _holding("WEGE3", 3000.0, checklist_ratio=1.0, checklist_age_days=30),
        _holding("OIBR3", 7000.0, checklist_ratio=-0.5, checklist_age_days=500),
    ]
    report = diagnose(HealthInputs(as_of=AS_OF, holdings=holdings), POLICY)

    quality = _check(report, "checklist_quality")
    assert quality.value == pytest.approx(0.3 * 1.0 + 0.7 * -0.5)
    assert quality.status == HealthStatus.CRITICAL
    stale = _check(report, "stale_checklist")
    assert stale.status == HealthStatus.WARNING
    assert stale.value == pytest.approx(0.7)
    assert _check(report, "accounting_scores").status == HealthStatus.INSUFFICIENT_DATA


def test_accounting_scores_flag_fragile_companies() -> None:
    holdings = [
        _holding("WEGE3", 5000.0, f_score=8, z_score=4.0),
        _holding("AMER3", 5000.0, z_score=0.5),
    ]
    check = _check(
        diagnose(HealthInputs(as_of=AS_OF, holdings=holdings), POLICY), "accounting_scores"
    )

    assert check.status == HealthStatus.WARNING
    assert "AMER3" in check.explanation


def test_liquidity_reserve_maturities_and_brackets() -> None:
    policy = replace(POLICY, monthly_expenses_brl=5000.0)
    holdings = [
        _holding(
            "CDB RESERVA",
            20_000.0,
            asset_type=AssetType.FIXED_INCOME,
            arca_class=ArcaClass.CAIXA,
            purpose=AssetPurpose.EMERGENCY_RESERVE,
            maturity_date=AS_OF + timedelta(days=100),
        ),
        _holding(
            "LCI",
            10_000.0,
            asset_type=AssetType.FIXED_INCOME,
            arca_class=ArcaClass.CAIXA,
            liquid_d2=False,
            tax_exempt=True,
        ),
    ]
    lot = BracketLot(
        "CDB RESERVA",
        AS_OF - timedelta(days=700),
        AS_OF + timedelta(days=21),
        21,
        0.175,
        0.15,
        42.0,
    )
    report = diagnose(
        HealthInputs(as_of=AS_OF, holdings=holdings, earnings_12m_brl=1200.0, bracket_lots=[lot]),
        policy,
    )

    reserve = _check(report, "emergency_reserve")
    assert reserve.value == pytest.approx(4.0)
    assert reserve.status == HealthStatus.WARNING
    assert _check(report, "liquid_weight").value == pytest.approx(2 / 3, abs=1e-4)
    assert report.liquidity.maturities_12m[0].ticker == "CDB RESERVA"
    assert report.liquidity.exempt_weight == pytest.approx(1 / 3, abs=1e-4)
    brackets = _check(report, "tax_brackets")
    assert brackets.status == HealthStatus.WARNING
    assert "R$ 42,00" in brackets.explanation
    assert _check(report, "passive_income").value == 1200.0


def test_reserve_without_monthly_cost_has_no_data() -> None:
    report = diagnose(HealthInputs(as_of=AS_OF, holdings=_equal_portfolio()), POLICY)
    assert _check(report, "emergency_reserve").status == HealthStatus.INSUFFICIENT_DATA


# --- input builders -------------------------------------------------------------------------


def test_checklist_age_uses_the_oldest_manual_answer() -> None:
    asset = AssetEntity(
        ticker="WEGE3",
        name="WEG",
        asset_type=AssetType.STOCK_BR,
        cerrado_answers={
            "q1": ChecklistAnswer(
                "q1", AnswerValue.YES, AnswerSource.MANUAL, None, datetime(2026, 1, 1, tzinfo=UTC)
            ),
            "q2": ChecklistAnswer(
                "q2", AnswerValue.NO, AnswerSource.MANUAL, None, datetime(2026, 6, 1, tzinfo=UTC)
            ),
            "q3": ChecklistAnswer(
                "q3", AnswerValue.YES, AnswerSource.AUTO, None, datetime(2020, 1, 1, tzinfo=UTC)
            ),
        },
    )
    assert checklist_age_days(asset, AS_OF) == (AS_OF - date(2026, 1, 1)).days
    assert checklist_age_days(replace(asset, cerrado_answers={}), AS_OF) is None


def test_policy_benchmark_weights_indexes_by_targets_and_renormalizes_gaps() -> None:
    base = [date(2026, 1, 2), date(2026, 1, 5)]
    series = {
        "IBOV": ([date(2026, 1, 2), date(2026, 1, 5)], [0.02, 0.01]),
        "CDI": ([date(2026, 1, 5)], [0.001]),
    }
    targets = {ArcaClass.ACOES: 50.0, ArcaClass.CAIXA: 50.0}

    out = policy_benchmark(base, targets, series)

    assert out[0] == pytest.approx(0.02)
    assert out[1] == pytest.approx(0.5 * 0.01 + 0.5 * 0.001)
    assert policy_benchmark(base, {ArcaClass.REAL_ESTATE: 100.0}, series) == [None, None]


def test_asset_return_grid_puts_fixed_income_on_the_cdi() -> None:
    days = [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6)]
    holdings = [
        _holding("WEGE3", 1.0),
        _holding("CDB", 1.0, asset_type=AssetType.FIXED_INCOME, arca_class=ArcaClass.CAIXA),
        _holding("SEMHIST3", 1.0),
    ]
    histories = {"WEGE3": [PricePoint(d, c) for d, c in zip(days, [10.0, 11.0, 11.0], strict=True)]}
    cdi = (days, [0.0004, 0.0004, 0.0004])

    grid, series = asset_return_grid(holdings, histories, cdi, date_from=date(2026, 1, 1))

    assert grid == days
    assert series["WEGE3"] == [None, pytest.approx(0.1), 0.0]
    assert series["CDB"] == pytest.approx([0.0004, 0.0004, 0.0004])
    assert "SEMHIST3" not in series


# --- policy ---------------------------------------------------------------------------------


def test_health_policy_defaults_are_part_of_the_investment_policy() -> None:
    assert InvestmentPolicy().health == HealthPolicy()
    assert HealthPolicy().as_dict()["fgc_limit_brl"] == 250_000.0


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_asset_weight_warning": 0.30, "max_asset_weight_critical": 0.20},
        {"min_reserve_months_warning": 2.0, "min_reserve_months_critical": 3.0},
        {"high_correlation": 1.5},
        {"fgc_limit_brl": 0.0},
        {"monthly_expenses_brl": -1.0},
        {"min_observations": 0},
    ],
)
def test_health_policy_rejects_inconsistent_limits(overrides: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        HealthPolicy(**overrides)


def test_custom_limits_change_the_verdict() -> None:
    holdings = [_holding("PETR4", 2000.0), *_equal_portfolio(8)]
    strict = HealthPolicy(max_asset_weight_warning=0.05, max_asset_weight_critical=0.10)

    assert (
        _check(
            diagnose(HealthInputs(as_of=AS_OF, holdings=holdings), POLICY), "largest_asset"
        ).status
        == HealthStatus.WARNING
    )
    assert (
        _check(
            diagnose(HealthInputs(as_of=AS_OF, holdings=holdings), strict), "largest_asset"
        ).status
        == HealthStatus.CRITICAL
    )
