"""Pure builders that turn consolidated positions and stored series into `HealthInputs`.

The application service loads the data (report, histories, statements, snapshots, tax lots)
and these functions shape it: one `Holding` per valued position, asset returns on a common
date grid (fixed income follows the daily CDI), and the policy benchmark that weights IBOV,
IFIX, S&P 500 and CDI by the ARCA targets.

Approximations: international assets use returns in their own currency, and every fixed
income position follows the CDI (there is no mark-to-market yet, TD-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime

from domain.assets.services.history import STATEMENT_TYPES, FundamentalSnapshot
from domain.assets.services.scores import accounting_scores
from domain.market.entities import Fundamentals, PricePoint
from domain.portfolio.services.analytics import align_to_base, dated_simple_returns
from domain.portfolio.services.consolidation import LEDGER_VALID, ValuedAssetPosition
from domain.portfolio.services.health import BracketLot, Holding
from domain.shared.entities import AssetEntity, MarketSeriesPoint
from domain.shared.enums import (
    AnswerSource,
    ArcaClass,
    AssetType,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
)
from domain.tax.services.status import AssetTaxStatus

# Instruments covered by the Fundo Garantidor de Créditos (R$ 250 mil per institution).
FGC_KINDS = frozenset(
    {
        FixedIncomeInstrumentKind.CDB,
        FixedIncomeInstrumentKind.LCI,
        FixedIncomeInstrumentKind.LCA,
        FixedIncomeInstrumentKind.SAVINGS_BOX,
    }
)
CDI_LIKE_TYPES = frozenset({AssetType.FIXED_INCOME, AssetType.TREASURY, AssetType.CASH})
LIQUID_DAYS = 2

CLASS_BENCHMARKS: dict[ArcaClass, str] = {
    ArcaClass.ACOES: "IBOV",
    ArcaClass.REAL_ESTATE: "IFIX",
    ArcaClass.ATIVOS_INTERNACIONAIS: "SP500",
    ArcaClass.CAIXA: "CDI",
}


def checklist_age_days(asset: AssetEntity, as_of: date) -> int | None:
    """Days since the oldest current manual answer (None without manual answers)."""
    dates: list[date] = []
    for answer in asset.cerrado_answers.values():
        if answer.source != AnswerSource.MANUAL or answer.value is None:
            continue
        if answer.answered_at is None:
            continue
        stamp = answer.answered_at
        dates.append(stamp.date() if isinstance(stamp, datetime) else stamp)
    if not dates:
        return None
    return max(0, (as_of - min(dates)).days)


def _liquid_d2(asset: AssetEntity, as_of: date) -> bool:
    term = asset.fixed_income_term
    if term is None or asset.asset_type == AssetType.TREASURY:
        return True
    if term.liquidity == FixedIncomeLiquidity.DAILY:
        return True
    return term.maturity_date is not None and (term.maturity_date - as_of).days <= LIQUID_DAYS


def build_holding(
    position: ValuedAssetPosition,
    asset: AssetEntity,
    *,
    as_of: date,
    fundamentals: Fundamentals | None = None,
    statements: Sequence[FundamentalSnapshot] = (),
) -> Holding:
    term = asset.fixed_income_term
    evaluation = position.cerrado_evaluation
    ratio = (
        evaluation.score / evaluation.applicable
        if evaluation.use_cerrado and evaluation.answered > 0 and evaluation.applicable > 0
        else None
    )
    scores = (
        accounting_scores(statements)
        if asset.asset_type in STATEMENT_TYPES and statements
        else None
    )
    sector = fundamentals.sector if fundamentals and fundamentals.sector else None
    return Holding(
        ticker=position.ticker,
        name=position.name,
        asset_type=position.asset_type,
        arca_class=position.arca_class,
        value_brl=position.current_value_brl,
        purpose=position.purpose,
        sector=sector,
        issuer=term.issuer if term else None,
        fgc_covered=(
            asset.asset_type == AssetType.FIXED_INCOME
            and term is not None
            and term.instrument_kind in FGC_KINDS
        ),
        liquid_d2=_liquid_d2(asset, as_of),
        maturity_date=term.maturity_date if term else None,
        tax_exempt=bool(term and term.tax_exempt),
        eligible=position.eligible,
        checklist_ratio=round(ratio, 4) if ratio is not None else None,
        checklist_age_days=checklist_age_days(asset, as_of),
        checklist_stale=evaluation.stale > 0,
        suspicious_data=bool(fundamentals and fundamentals.suspicious),
        f_score=scores.f_score if scores else None,
        z_score=scores.z_score if scores else None,
    )


def build_holdings(
    positions: Sequence[ValuedAssetPosition],
    assets_by_id: Mapping[int, AssetEntity],
    *,
    as_of: date,
    fundamentals: Mapping[str, Fundamentals],
    statements: Mapping[str, Sequence[FundamentalSnapshot]],
) -> list[Holding]:
    """One holding per valid position with value (invalid ledgers stay out of the diagnosis)."""
    holdings: list[Holding] = []
    for position in positions:
        asset = assets_by_id.get(position.asset_id)
        if asset is None or position.ledger_status != LEDGER_VALID:
            continue
        if position.current_value_brl <= 0:
            continue
        holdings.append(
            build_holding(
                position,
                asset,
                as_of=as_of,
                fundamentals=fundamentals.get(position.ticker),
                statements=statements.get(position.ticker, ()),
            )
        )
    return holdings


def cdi_returns(points: Sequence[MarketSeriesPoint]) -> tuple[list[date], list[float]]:
    """Daily CDI rates (% per day) as dated returns."""
    ordered = sorted(points, key=lambda p: p.reference_date)
    return [p.reference_date for p in ordered], [p.value / 100.0 for p in ordered]


def asset_return_grid(
    holdings: Sequence[Holding],
    histories: Mapping[str, Sequence[PricePoint]],
    cdi: tuple[Sequence[date], Sequence[float]],
    *,
    date_from: date,
) -> tuple[list[date], dict[str, list[float | None]]]:
    """Asset returns re-expressed on the union of their dates (fixed income follows the CDI)."""
    dated: dict[str, tuple[list[date], list[float]]] = {}
    for h in holdings:
        if h.asset_type in CDI_LIKE_TYPES:
            if cdi[0]:
                dated[h.ticker] = (list(cdi[0]), list(cdi[1]))
            continue
        points = [p for p in histories.get(h.ticker, ()) if p.close > 0]
        if len(points) < 2:
            continue
        dated[h.ticker] = dated_simple_returns([p.date for p in points], [p.close for p in points])
    grid = sorted({d for dates, _ in dated.values() for d in dates if d > date_from})
    if not grid:
        return [], {}
    return grid, {t: align_to_base(grid, dates, rets) for t, (dates, rets) in dated.items()}


def policy_benchmark(
    base_dates: Sequence[date],
    targets: Mapping[ArcaClass, float],
    series: Mapping[str, tuple[Sequence[date], Sequence[float]]],
) -> list[float | None]:
    """ARCA-target-weighted index returns on the portfolio periods.

    A class whose index has no return in a period is left out and the others are
    renormalized; a period with no index at all is None.
    """
    aligned: dict[ArcaClass, list[float | None]] = {}
    for arca_class, symbol in CLASS_BENCHMARKS.items():
        if targets.get(arca_class, 0.0) <= 0 or symbol not in series:
            continue
        dates, rets = series[symbol]
        aligned[arca_class] = align_to_base(base_dates, dates, rets)
    out: list[float | None] = []
    for i in range(len(base_dates)):
        weighted = 0.0
        weight = 0.0
        for arca_class, values in aligned.items():
            r = values[i]
            if r is None:
                continue
            w = targets[arca_class]
            weighted += w * r
            weight += w
        out.append(weighted / weight if weight > 0 else None)
    return out


def bracket_lots(statuses: Sequence[AssetTaxStatus]) -> list[BracketLot]:
    """Open lots with a lower income tax bracket ahead and a tax saving by waiting."""
    lots: list[BracketLot] = []
    for status in statuses:
        for lot in status.lots:
            if (
                lot.next_bracket_date is None
                or lot.days_to_next_bracket is None
                or lot.next_income_tax_rate is None
                or (lot.tax_saving_by_waiting or 0.0) <= 0
            ):
                continue
            lots.append(
                BracketLot(
                    ticker=status.ticker,
                    start_date=lot.start_date,
                    next_bracket_date=lot.next_bracket_date,
                    days_to_next_bracket=lot.days_to_next_bracket,
                    current_rate=lot.income_tax_rate,
                    next_rate=lot.next_income_tax_rate,
                    tax_saving_by_waiting=lot.tax_saving_by_waiting or 0.0,
                )
            )
    return lots
