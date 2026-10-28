"""Side-by-side comparison of up to five assets of the same profile (Phase 27).

Indicators come in five groups (valuation, debt, efficiency, profitability, growth) from
the current fundamentals and the stored annual statements. Each row marks the best value
(lowest or highest, depending on the indicator); multiples where a negative number means a
loss (P/L, EV/EBITDA) only compete when positive. Mixing profiles (e.g. stocks and FIIs)
adds a warning, since their indicators do not mean the same thing.

The annual history (revenue, net income, ROE and DY) uses the statements; the yearly DY
divides the dividends paid by the market value at the last close of the year, estimating
the share count from today's market cap (constant share count).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from core.errors import ValidationError
from domain.assets.services.history import (
    STATEMENT_TYPES,
    FundamentalPeriod,
    FundamentalSnapshot,
    HistoricalMetrics,
)
from domain.market.entities import Fundamentals, PricePoint
from domain.shared.enums import AssetType, ChecklistProfile

MIN_ASSETS = 2
MAX_ASSETS = 5


class IndicatorGroup(StrEnum):
    VALUATION = "VALUATION"
    DEBT = "DEBT"
    EFFICIENCY = "EFFICIENCY"
    PROFITABILITY = "PROFITABILITY"
    GROWTH = "GROWTH"


class IndicatorUnit(StrEnum):
    FRACTION = "FRACTION"
    MULTIPLE = "MULTIPLE"


class Better(StrEnum):
    HIGHER = "HIGHER"
    LOWER = "LOWER"


GROUP_LABELS: dict[IndicatorGroup, str] = {
    IndicatorGroup.VALUATION: "Valuation",
    IndicatorGroup.DEBT: "Endividamento",
    IndicatorGroup.EFFICIENCY: "Eficiência",
    IndicatorGroup.PROFITABILITY: "Rentabilidade",
    IndicatorGroup.GROWTH: "Crescimento",
}

PROFILE_FAMILIES: dict[ChecklistProfile, str] = {
    ChecklistProfile.FII_BRICK: "FII",
    ChecklistProfile.FII_PAPER: "FII",
    ChecklistProfile.ETF: "ETF",
    ChecklistProfile.CRYPTO: "cripto",
    ChecklistProfile.FIXED_INCOME: "renda fixa",
}


@dataclass(frozen=True)
class IndicatorSpec:
    key: str
    label: str
    group: IndicatorGroup
    unit: IndicatorUnit
    better: Better
    positive_only: bool = False


INDICATORS: tuple[IndicatorSpec, ...] = (
    IndicatorSpec(
        "price_to_earnings",
        "P/L",
        IndicatorGroup.VALUATION,
        IndicatorUnit.MULTIPLE,
        Better.LOWER,
        True,
    ),
    IndicatorSpec(
        "price_to_book",
        "P/VP",
        IndicatorGroup.VALUATION,
        IndicatorUnit.MULTIPLE,
        Better.LOWER,
        True,
    ),
    IndicatorSpec(
        "ev_to_ebitda",
        "EV/EBITDA",
        IndicatorGroup.VALUATION,
        IndicatorUnit.MULTIPLE,
        Better.LOWER,
        True,
    ),
    IndicatorSpec(
        "dividend_yield",
        "Dividend yield",
        IndicatorGroup.VALUATION,
        IndicatorUnit.FRACTION,
        Better.HIGHER,
    ),
    IndicatorSpec(
        "margin_of_safety",
        "Margem de segurança",
        IndicatorGroup.VALUATION,
        IndicatorUnit.FRACTION,
        Better.HIGHER,
    ),
    IndicatorSpec(
        "debt_to_equity",
        "Dívida / patrimônio",
        IndicatorGroup.DEBT,
        IndicatorUnit.MULTIPLE,
        Better.LOWER,
    ),
    IndicatorSpec(
        "net_debt_to_ebitda",
        "Dívida líquida / EBITDA",
        IndicatorGroup.DEBT,
        IndicatorUnit.MULTIPLE,
        Better.LOWER,
    ),
    IndicatorSpec(
        "net_debt_to_equity",
        "Dívida líquida / patrimônio",
        IndicatorGroup.DEBT,
        IndicatorUnit.MULTIPLE,
        Better.LOWER,
    ),
    IndicatorSpec(
        "profit_margin",
        "Margem líquida",
        IndicatorGroup.EFFICIENCY,
        IndicatorUnit.FRACTION,
        Better.HIGHER,
    ),
    IndicatorSpec(
        "ebitda_margin",
        "Margem EBITDA",
        IndicatorGroup.EFFICIENCY,
        IndicatorUnit.FRACTION,
        Better.HIGHER,
    ),
    IndicatorSpec(
        "return_on_equity",
        "ROE",
        IndicatorGroup.PROFITABILITY,
        IndicatorUnit.FRACTION,
        Better.HIGHER,
    ),
    IndicatorSpec(
        "roe_average",
        "ROE médio (5 anos)",
        IndicatorGroup.PROFITABILITY,
        IndicatorUnit.FRACTION,
        Better.HIGHER,
    ),
    IndicatorSpec(
        "payout_average",
        "Payout médio",
        IndicatorGroup.PROFITABILITY,
        IndicatorUnit.FRACTION,
        Better.HIGHER,
    ),
    IndicatorSpec(
        "dividend_regularity",
        "Anos com proventos",
        IndicatorGroup.PROFITABILITY,
        IndicatorUnit.FRACTION,
        Better.HIGHER,
    ),
    IndicatorSpec(
        "revenue_growth",
        "Crescimento da receita (12m)",
        IndicatorGroup.GROWTH,
        IndicatorUnit.FRACTION,
        Better.HIGHER,
    ),
    IndicatorSpec(
        "earnings_growth",
        "Crescimento do lucro (12m)",
        IndicatorGroup.GROWTH,
        IndicatorUnit.FRACTION,
        Better.HIGHER,
    ),
    IndicatorSpec(
        "revenue_cagr",
        "CAGR da receita (5 anos)",
        IndicatorGroup.GROWTH,
        IndicatorUnit.FRACTION,
        Better.HIGHER,
    ),
    IndicatorSpec(
        "earnings_cagr",
        "CAGR do lucro (5 anos)",
        IndicatorGroup.GROWTH,
        IndicatorUnit.FRACTION,
        Better.HIGHER,
    ),
)
INDICATORS_BY_KEY: dict[str, IndicatorSpec] = {i.key: i for i in INDICATORS}


@dataclass(frozen=True)
class ComparedAsset:
    """Everything the comparison needs about one asset, already loaded by the caller."""

    ticker: str
    name: str
    asset_type: AssetType
    profile: ChecklistProfile
    asset_id: int | None = None
    currency: str | None = None
    price: float | None = None
    fundamentals: Fundamentals | None = None
    statements: Sequence[FundamentalSnapshot] = ()
    history: HistoricalMetrics | None = None
    prices: Sequence[PricePoint] = ()
    valuation_verdict: str | None = None
    fair_value: float | None = None
    margin_of_safety: float | None = None
    checklist_score: int | None = None
    checklist_max_score: int | None = None
    checklist_normalized_score: float | None = None
    checklist_coverage_pct: float | None = None
    checklist_recommendation: str | None = None


@dataclass(frozen=True)
class ComparisonRow:
    key: str
    label: str
    group: IndicatorGroup
    unit: IndicatorUnit
    better: Better
    values: dict[str, float | None]
    best: list[str]


@dataclass(frozen=True)
class HistoryPoint:
    year: int
    revenue: float | None = None
    net_income: float | None = None
    roe: float | None = None
    dividend_yield: float | None = None


@dataclass(frozen=True)
class AssetHistory:
    ticker: str
    points: list[HistoryPoint] = field(default_factory=list)


@dataclass(frozen=True)
class AssetComparison:
    assets: list[ComparedAsset]
    rows: list[ComparisonRow]
    history: list[AssetHistory]
    warnings: list[str]


def normalize_tickers(tickers: Sequence[str]) -> list[str]:
    """Upper-case, de-duplicated tickers in the given order (2 to 5)."""
    seen: list[str] = []
    for raw in tickers:
        for part in raw.split(","):
            ticker = part.strip().upper()
            if ticker and ticker not in seen:
                seen.append(ticker)
    if not MIN_ASSETS <= len(seen) <= MAX_ASSETS:
        raise ValidationError(
            f"Compare between {MIN_ASSETS} and {MAX_ASSETS} different assets",
            code="INVALID_COMPARISON_SIZE",
        )
    return seen


def select_indicators(keys: Sequence[str] | None) -> list[IndicatorSpec]:
    """Chosen indicators in catalog order (all of them when none is given)."""
    if not keys:
        return list(INDICATORS)
    wanted = {k.strip() for raw in keys for k in raw.split(",") if k.strip()}
    unknown = sorted(wanted - set(INDICATORS_BY_KEY))
    if unknown:
        raise ValidationError(
            f"Unknown indicator(s): {', '.join(unknown)}", code="UNKNOWN_INDICATOR"
        )
    return [i for i in INDICATORS if i.key in wanted]


def _latest_annual(statements: Sequence[FundamentalSnapshot]) -> FundamentalSnapshot | None:
    annual = [s for s in statements if s.period == FundamentalPeriod.ANNUAL]
    return max(annual, key=lambda s: s.reference_date) if annual else None


def _div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def indicator_value(asset: ComparedAsset, key: str) -> float | None:
    """Value of one indicator for one asset (None when the data is missing)."""
    fund = asset.fundamentals
    last = _latest_annual(asset.statements)
    history = asset.history

    def stmt(metric: str) -> float | None:
        return last.value(metric) if last else None

    if key == "margin_of_safety":
        return asset.margin_of_safety
    if key == "ev_to_ebitda":
        market_cap = fund.market_cap if fund else None
        debt, cash = stmt("total_debt"), stmt("cash")
        if market_cap is None or debt is None:
            return None
        return _div(market_cap + debt - (cash or 0.0), stmt("ebitda"))
    if key == "net_debt_to_equity":
        debt = stmt("total_debt")
        return _div(debt - (stmt("cash") or 0.0), stmt("equity")) if debt is not None else None
    if key == "ebitda_margin":
        return _div(stmt("ebitda"), stmt("revenue"))
    if key == "net_debt_to_ebitda":
        if fund and fund.net_debt_to_ebitda is not None:
            return fund.net_debt_to_ebitda
        debt = stmt("total_debt")
        return _div(debt - (stmt("cash") or 0.0), stmt("ebitda")) if debt is not None else None
    if key in ("roe_average", "payout_average", "revenue_cagr", "earnings_cagr"):
        return getattr(history, key) if history else None
    if key == "dividend_regularity":
        return history.dividend_regularity if history else None
    if fund is None:
        return None
    return getattr(fund, key, None)


def _best(spec: IndicatorSpec, values: Mapping[str, float | None]) -> list[str]:
    known = {t: v for t, v in values.items() if v is not None and (not spec.positive_only or v > 0)}
    if len(known) < 2:
        return []
    target = min(known.values()) if spec.better == Better.LOWER else max(known.values())
    return [t for t, v in known.items() if abs(v - target) <= 1e-12]


def build_rows(
    assets: Sequence[ComparedAsset], indicators: Sequence[IndicatorSpec]
) -> list[ComparisonRow]:
    rows: list[ComparisonRow] = []
    for spec in indicators:
        values = {a.ticker: _round(indicator_value(a, spec.key)) for a in assets}
        rows.append(
            ComparisonRow(
                key=spec.key,
                label=spec.label,
                group=spec.group,
                unit=spec.unit,
                better=spec.better,
                values=values,
                best=_best(spec, values),
            )
        )
    return rows


def _round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _year_end_close(prices: Sequence[PricePoint], year: int) -> float | None:
    closes = [p for p in prices if p.date.year == year and p.close > 0]
    return max(closes, key=lambda p: p.date).close if closes else None


def annual_history(asset: ComparedAsset) -> AssetHistory:
    """Revenue, net income, ROE and DY of each stored fiscal year, oldest first."""
    annual = sorted(
        (s for s in asset.statements if s.period == FundamentalPeriod.ANNUAL),
        key=lambda s: s.reference_date,
    )
    fund = asset.fundamentals
    shares = (
        _div(fund.market_cap, asset.price)
        if fund and fund.market_cap and asset.price and asset.price > 0
        else None
    )
    points: list[HistoryPoint] = []
    for snap in annual:
        year = snap.reference_date.year
        dividends = snap.value("dividends_paid")
        close = _year_end_close(asset.prices, year)
        dy = (
            _div(abs(dividends), shares * close)
            if dividends is not None and shares is not None and close is not None
            else None
        )
        points.append(
            HistoryPoint(
                year=year,
                revenue=snap.value("revenue"),
                net_income=snap.value("net_income"),
                roe=_round(_div(snap.value("net_income"), snap.value("equity"))),
                dividend_yield=_round(dy),
            )
        )
    return AssetHistory(ticker=asset.ticker, points=points)


def _family(profile: ChecklistProfile) -> str:
    return PROFILE_FAMILIES.get(profile, "ação")


def comparison_warnings(assets: Sequence[ComparedAsset]) -> list[str]:
    warnings: list[str] = []
    families = sorted({_family(a.profile) for a in assets})
    if len(families) > 1:
        warnings.append(
            f"Perfis diferentes ({' × '.join(families)}): os indicadores não significam a mesma "
            "coisa entre eles; compare preferencialmente ativos do mesmo perfil."
        )
    currencies = sorted({a.currency for a in assets if a.currency})
    if len(currencies) > 1:
        warnings.append(
            f"Moedas diferentes ({', '.join(currencies)}): preços e valores absolutos não são "
            "comparáveis; os múltiplos e percentuais são."
        )
    without = [a.ticker for a in assets if a.fundamentals is None]
    if without:
        warnings.append(
            f"Sem indicadores atuais do provedor para {', '.join(without)}; as linhas ficam em "
            "branco para esses ativos."
        )
    return warnings


def compare_assets(
    assets: Sequence[ComparedAsset], indicators: Sequence[IndicatorSpec]
) -> AssetComparison:
    return AssetComparison(
        assets=list(assets),
        rows=build_rows(assets, indicators),
        history=[annual_history(a) for a in assets],
        warnings=comparison_warnings(assets),
    )


def statements_missing(asset_type: AssetType, statements: Sequence[FundamentalSnapshot]) -> bool:
    """Whether a company has no stored annual statement yet (fetch on demand)."""
    return asset_type in STATEMENT_TYPES and not any(
        s.period == FundamentalPeriod.ANNUAL for s in statements
    )


__all__ = [
    "GROUP_LABELS",
    "INDICATORS",
    "MAX_ASSETS",
    "AssetComparison",
    "ComparedAsset",
    "IndicatorGroup",
    "compare_assets",
    "normalize_tickers",
    "select_indicators",
    "statements_missing",
]
