"""Use cases of the recommendation (Phase 45): read what the worker stored."""

from __future__ import annotations

from collections import Counter
from datetime import date

from controllers.recommendation.responses import (
    AssetLensesDTO,
    BacktestDTO,
    BacktestYearDTO,
    ClassComparisonDTO,
    ClassMatrixDTO,
    ConstructionDTO,
    ContributionComparisonDTO,
    CurvePointDTO,
    ExcludedAssetDTO,
    GateDTO,
    LensBoardDTO,
    LensDifferenceDTO,
    LensDTO,
    LensWeightDTO,
    MatrixBoardDTO,
    MatrixCellDTO,
    MatrixRowDTO,
    OrderLineDTO,
    RecommendationRunDTO,
    RowComparisonDTO,
    ScoreLineDTO,
    SelectedAssetDTO,
    SkippedAssetDTO,
)
from controllers.shared.dependencies import UoWFactory
from domain.policy.services.policy import current_policy
from domain.portfolio.services.consolidation import plan_contribution
from domain.portfolio.services.service import PortfolioApplicationService
from domain.recommendation.backtest import Backtest
from domain.recommendation.backtest_runs import RECOMMENDATION_BACKTEST
from domain.recommendation.combination import ClassMatrix, MatrixRow, compare_rows
from domain.recommendation.construction import ClassConstruction
from domain.recommendation.contribution import recommended_orders
from domain.recommendation.gates import GATE_LABELS, AssetGates
from domain.recommendation.keys import LENS_LABELS, OBJECTIVE_LABELS
from domain.recommendation.lenses import AssetLenses
from domain.shared.enums import INTEGER_QUANTITY_TYPES, AssetType
from domain.simulation.data import px_symbol


def _asset_dto(item: AssetLenses, gates: AssetGates | None) -> AssetLensesDTO:
    return AssetLensesDTO(
        ticker=item.ticker,
        source=item.source,  # type: ignore[arg-type]
        arca_class=item.arca_class,
        sector=item.sector,
        signal_ticker=item.signal_ticker,
        lenses=[
            LensDTO(
                lens=s.lens,  # type: ignore[arg-type]
                label=LENS_LABELS.get(s.lens, s.lens),
                value=s.value,
                normalized=s.normalized,
                confidence=s.confidence,
                note=s.note,
                flags=s.flags,
            )
            for s in item.lenses
        ],
        eligible=gates.eligible if gates is not None else None,
        gates=[
            GateDTO(
                gate=r.gate,  # type: ignore[arg-type]
                label=GATE_LABELS.get(r.gate, r.gate),
                status=r.status,  # type: ignore[arg-type]
                reason=r.reason,
            )
            for r in (gates.results if gates is not None else [])
        ],
    )


def _row_dto(row: MatrixRow) -> MatrixRowDTO:
    return MatrixRowDTO(
        ticker=row.ticker,
        source=row.source,  # type: ignore[arg-type]
        sector=row.sector,
        rank=row.rank,
        score=row.score,
        expected=row.expected,
        expected_low=row.expected_low,
        expected_high=row.expected_high,
        confidence=row.confidence,
        cells=[
            MatrixCellDTO(
                lens=c.lens,  # type: ignore[arg-type]
                value=c.value,
                weight=c.weight,
                contribution=c.contribution,
            )
            for c in row.cells
        ],
        gaussian_score=row.gaussian_score,
        gaussian_rank=row.gaussian_rank,
        flags=row.flags,
    )


def _construction_dto(c: ClassConstruction) -> ConstructionDTO:
    return ConstructionDTO(
        k=c.k,
        stop_reason=c.stop_reason,
        confidence=c.confidence,
        selected=[
            SelectedAssetDTO(
                ticker=s.ticker,
                sector=s.sector,
                group=s.group,
                weight=s.weight,
                score=s.score,
                expected=s.expected,
                confidence=s.confidence,
                reason=s.reason,
            )
            for s in c.selected
        ],
        skipped=[SkippedAssetDTO(ticker=s.ticker, reason=s.reason) for s in c.skipped],
        curve=[
            CurvePointDTO(k=p.k, added=p.added, expected=p.expected, risk=p.risk, utility=p.utility)
            for p in c.curve
        ],
        notes=c.notes,
    )


def _matrix_dto(m: ClassMatrix, construction: ClassConstruction | None = None) -> ClassMatrixDTO:
    return ClassMatrixDTO(
        arca_class=m.arca_class,
        objective=m.objective,  # type: ignore[arg-type]
        objective_label=OBJECTIVE_LABELS.get(m.objective, m.objective),
        consistency_ratio=m.consistency_ratio,
        scale_annual=m.scale_annual,
        weights=[
            LensWeightDTO(
                lens=lens,  # type: ignore[arg-type]
                label=LENS_LABELS.get(lens, lens),
                weight=w,
                gaussian_weight=m.gaussian_weights.get(lens, 0.0),
            )
            for lens, w in m.weights.items()
        ],
        rows=[_row_dto(r) for r in m.rows],
        excluded=[
            ExcludedAssetDTO(ticker=e.ticker, source=e.source, reasons=e.reasons)  # type: ignore[arg-type]
            for e in m.excluded
        ],
        construction=_construction_dto(construction) if construction is not None else None,
    )


class RecommendationHandler:
    def __init__(
        self,
        uow_factory: UoWFactory,
        portfolio_service: PortfolioApplicationService | None = None,
    ) -> None:
        self.uow_factory = uow_factory
        self.portfolio_service = portfolio_service

    def lenses(
        self,
        *,
        arca_class: str | None = None,
        source: str | None = None,
        ticker: str | None = None,
        eligible: bool | None = None,
        as_of: date | None = None,
    ) -> LensBoardDTO:
        """The latest lenses and gates, optionally of one class, source, ticker or eligibility."""
        tickers = [ticker] if ticker else None
        with self.uow_factory() as uow:
            items = uow.recommendation.lenses(as_of=as_of, tickers=tickers)
            gates = {g.ticker: g for g in uow.recommendation.gates(as_of=as_of, tickers=tickers)}
        if not items:
            return LensBoardDTO(status="NOT_COMPUTED")
        chosen = [
            i
            for i in items
            if (arca_class is None or i.arca_class == arca_class)
            and (source is None or i.source == source)
            and (eligible is None or (i.ticker in gates and gates[i.ticker].eligible == eligible))
        ]
        return LensBoardDTO(
            status="OK",
            as_of=items[0].as_of,
            assets=[_asset_dto(i, gates.get(i.ticker)) for i in chosen],
            counts=dict(Counter(i.source for i in chosen)),
            eligible=sum(1 for i in chosen if i.ticker in gates and gates[i.ticker].eligible),
        )

    def matrix(self, *, arca_class: str | None = None, as_of: date | None = None) -> MatrixBoardDTO:
        """The decision matrix of each class (or of one class), of the latest run or of `as_of`."""
        with self.uow_factory() as uow:
            found = uow.recommendation.matrices(as_of)
            built = {c.arca_class: c for c in uow.recommendation.constructions(as_of)}
        if not found:
            return MatrixBoardDTO(status="NOT_COMPUTED")
        return MatrixBoardDTO(
            status="OK",
            as_of=found[0].as_of,
            classes=[
                _matrix_dto(m, built.get(m.arca_class))
                for m in found
                if arca_class is None or m.arca_class == arca_class
            ],
        )

    def compare(self, a: str, b: str) -> RowComparisonDTO:
        """'A and not B': the two rows of the same class, lens by lens."""
        ta, tb = a.strip().upper(), b.strip().upper()
        with self.uow_factory() as uow:
            found = uow.recommendation.matrices()
        if not found:
            return RowComparisonDTO(status="NOT_COMPUTED")
        rows = {r.ticker: (m, r) for m in found for r in m.rows}
        excluded = {e.ticker: e for m in found for e in m.excluded}
        for ticker in (ta, tb):
            if ticker not in rows:
                reason = (
                    f"{ticker} não passou nos portões: {' '.join(excluded[ticker].reasons)}"
                    if ticker in excluded
                    else f"{ticker} não está no universo da recomendação."
                )
                return RowComparisonDTO(status="NOT_COMPARABLE", reason=reason)
        (ma, ra), (mb, rb) = rows[ta], rows[tb]
        if ma.arca_class != mb.arca_class:
            return RowComparisonDTO(
                status="NOT_COMPARABLE",
                reason="Os dois ativos são de classes ARCA diferentes, com objetivos e pesos "
                "diferentes; compare dentro da mesma classe.",
            )
        return RowComparisonDTO(
            status="OK",
            a=_row_dto(ra),
            b=_row_dto(rb),
            differences=[
                LensDifferenceDTO(
                    lens=d.lens,  # type: ignore[arg-type]
                    label=LENS_LABELS.get(d.lens, d.lens),
                    a=d.a,
                    b=d.b,
                    weight=d.weight,
                    difference=d.difference,
                )
                for d in compare_rows(ra, rb)
            ],
        )

    def backtest(self) -> BacktestDTO:
        """The latest backtest of the hierarchy and the scoreboard of the runs."""
        with self.uow_factory() as uow:
            stored = uow.forecasts.latest_model(RECOMMENDATION_BACKTEST)
        if stored is None:
            return BacktestDTO(status="NOT_COMPUTED")
        found = Backtest.from_dict(stored.payload["backtest"])
        return BacktestDTO(
            status=found.status,  # type: ignore[arg-type]
            as_of=found.as_of,
            passed=found.passed,
            reason=found.reason,
            first_month=found.first_month,
            last_month=found.last_month,
            months=found.months,
            rebalances=found.rebalances,
            average_k=found.average_k,
            strategy_annual=found.strategy_annual,
            equal_annual=found.equal_annual,
            difference_annual=found.difference_annual,
            hit_rate=found.hit_rate,
            probability=found.probability,
            years=[BacktestYearDTO(**y.__dict__) for y in found.years],
            weights=found.weights,
            notes=found.notes,
            scoreboard=[ScoreLineDTO(**line) for line in stored.payload.get("scoreboard", [])],
        )

    def runs(self, limit: int = 52) -> list[RecommendationRunDTO]:
        """The history of the weekly runs, newest first."""
        return list_runs(self, limit)

    def contribution(self, amount_brl: float) -> ContributionComparisonDTO:
        """The current rule's contribution next to the recommendation's (nothing saved)."""
        if self.portfolio_service is None:
            raise RuntimeError("the contribution comparison needs the portfolio service")
        service = self.portfolio_service
        with self.uow_factory() as uow:
            built = {c.arca_class: c for c in uow.recommendation.constructions()}
            if not built:
                return ContributionComparisonDTO(status="NOT_COMPUTED", amount=amount_brl)
            as_of = uow.recommendation.latest_lens_date()
            report = service.build_portfolio_report(uow)
            policy = current_policy(uow.policies)
            plan = plan_contribution(
                report=report,
                targets=policy.arca.targets,
                amount_brl=amount_brl,
                class_strategies=policy.arca.strategies,
            )
            wanted = {s.ticker for c in built.values() for s in c.selected}
            held = {p.ticker for p in report.positions if p.current_value_brl > 0}
            registered = {a.ticker.upper(): a for a in uow.assets.list_all(active_only=True)}
            prices: dict[str, float] = {
                p.ticker: p.current_unit_price * p.fx_rate
                for p in report.positions
                if p.current_unit_price > 0
            }
            missing = sorted(wanted - set(prices))
            quotes = uow.market_data.get_many(missing)
            for ticker in missing:
                data = quotes.get(ticker)
                if data is not None and data.quote is not None and data.quote.price > 0:
                    prices[ticker] = data.quote.price
                else:
                    points = uow.market_series.list_series(px_symbol(ticker))
                    if points:
                        prices[ticker] = points[-1].value
        whole = {t: _whole_units(t, report, registered) for t in wanted | held}
        classes = []
        # The class's share by the ARCA rule (level 1), even when the current rule could not
        # spend it for lack of an eligible asset in the portfolio.
        shares = {r.arca_class: r.first_level_brl for r in plan.class_rationale}
        for arca_class in plan.by_class_allocated_brl:
            budget = shares.get(arca_class, plan.by_class_allocated_brl[arca_class])
            current = [o for o in plan.orders if o.arca_class == arca_class]
            line = ClassComparisonDTO(
                arca_class=arca_class.value,
                budget=round(budget, 2),
                covered=arca_class.value in built,
                current_orders=[
                    OrderLineDTO(
                        ticker=o.ticker,
                        amount=round(o.executed_amount_brl, 2),
                        quantity=o.recommended_quantity,
                        unit_price=o.unit_price_brl,
                        target_weight=round(o.intra_class_target_weight_pct / 100.0, 6),
                        current_weight=round(o.class_current_weight_pct / 100.0, 6),
                    )
                    for o in current
                    if o.executed_amount_brl > 0
                ],
            )
            construction = built.get(arca_class.value)
            if construction is None or not construction.selected:
                line.note = (
                    "A recomendação não cobre esta classe (Caixa ou sem ativos aptos): segue a "
                    "regra atual."
                )
                classes.append(line)
                continue
            values = {
                p.ticker: p.current_value_brl
                for p in report.positions
                if p.arca_class == arca_class
            }
            found = recommended_orders(
                budget,
                construction,
                values,
                prices,
                whole,
                policy.recommendation.min_lot_brl,
            )
            line.confidence = construction.confidence
            line.recommended_leftover = found.leftover
            line.recommended_orders = [
                OrderLineDTO(
                    ticker=o.ticker,
                    amount=o.amount,
                    quantity=o.quantity,
                    unit_price=o.unit_price,
                    target_weight=o.target_weight,
                    current_weight=o.current_weight,
                    new=o.ticker not in held,
                    reason=o.reason,
                )
                for o in found.orders
            ]
            classes.append(line)
        return ContributionComparisonDTO(
            status="OK", as_of=as_of, amount=amount_brl, classes=classes
        )


def _whole_units(ticker: str, report: object, registered: dict) -> bool:
    position = next((p for p in report.positions if p.ticker == ticker), None)  # type: ignore[attr-defined]
    if position is not None:
        return position.asset_type in INTEGER_QUANTITY_TYPES
    asset = registered.get(ticker)
    kind = asset.asset_type if asset is not None else AssetType.STOCK_BR  # catalog: B3 stocks
    return kind in INTEGER_QUANTITY_TYPES


def _run_dto(run) -> RecommendationRunDTO:  # type: ignore[no-untyped-def]
    return RecommendationRunDTO(
        as_of=run.as_of,
        policy_version=run.policy_version,
        signal_month=run.signal_month,
        assets=run.assets,
        eligible=run.eligible,
        selected=run.selected,
    )


def list_runs(handler: RecommendationHandler, limit: int = 52) -> list[RecommendationRunDTO]:
    with handler.uow_factory() as uow:
        return [_run_dto(r) for r in uow.recommendation.runs(limit)]
