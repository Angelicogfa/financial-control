"""Worker side of the live scoreboard (Phase 45.8a): build and update the comparison portfolios.

Every day, after the snapshot, the routine reads the real ARCA trades and the stored series and:
- rebuilds your portfolio from the trades (it is the reference, never frozen: a trade
  registered late changes it, as it should);
- creates each comparison portfolio the first time, rebuilding its past from your first
  contribution (retroactive, labelled) - the recommendation from its first stored run, with
  your ARCA patrimony of that day as its first money in (decision 10.1.8);
- after that, only adds the new days to each one, from its stored book: the prospective record
  is never rewritten. Money from a trade registered after its day enters on the next new day.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date, timedelta
from functools import cache
from typing import Any

from domain.comparison.engine import Book, Market, replay_actual, run_strategy, valuation_days
from domain.comparison.flow import arca_flows, arca_trades
from domain.comparison.points import Point
from domain.comparison.repositories import ComparisonPortfolio
from domain.comparison.strategies import (
    LABELS,
    OPTIMIZED,
    RANDOM_PORTFOLIOS,
    WITH_CERRADO,
    WITHOUT_CERRADO,
    YOURS,
    AllCdi,
    Candidate,
    CerradoRule,
    EqualWeights,
    Holdings,
    IndexArca,
    RandomPicks,
    RecommendationRuns,
    Strategy,
)
from domain.policy.services.policy import current_policy
from domain.recommendation.optimizer import optimized_of
from domain.shared.entities import AssetEntity, ChecklistAnswer
from domain.shared.enums import AnswerValue, ArcaClass, AssetPurpose, AssetType
from domain.shared.enums import Market as Venue
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.simulation.data import build_market_history, px_symbol
from domain.simulation.market import PriceSeries

CERRADO_HALF = 5.0  # a 0-10 score: 5 x (net share of yes + 1) x coverage, as the L0 lens
HISTORY_MARGIN_DAYS = 10


def cerrado_score(answers: Iterable[ChecklistAnswer], day: date, applicable: int) -> float | None:
    """The Cerrado score with the answers in force at the close of `day` (None: not analysed).

    The same rule as the L0 lens, without the decay of stale answers (the answers of each date
    were fresh then); the applicable questions are those ever answered for the asset.
    """
    current: dict[str, AnswerValue] = {}
    for answer in sorted(
        (a for a in answers if a.answered_at is not None),
        key=lambda a: a.answered_at,  # type: ignore[arg-type,return-value]
    ):
        if answer.answered_at.date() > day:  # type: ignore[union-attr]
            break
        if answer.value is None:
            current.pop(answer.question_id, None)
        else:
            current[answer.question_id] = answer.value
    yes = sum(1 for v in current.values() if v == AnswerValue.YES)
    no = sum(1 for v in current.values() if v == AnswerValue.NO)
    if yes + no == 0:
        return None
    coverage = min((yes + no) / max(applicable, 1), 1.0)
    return round(CERRADO_HALF * ((yes - no) / (yes + no) + 1.0) * coverage, 2)


def _scores(
    histories: Mapping[str, Sequence[ChecklistAnswer]],
) -> Callable[[date], dict[str, float]]:
    applicable = {
        t: len({a.question_id for a in h if a.value not in (None, AnswerValue.NA)})
        for t, h in histories.items()
    }

    @cache
    def on(day: date) -> dict[str, float]:
        out = {}
        for ticker, history in histories.items():
            score = cerrado_score(history, day, applicable[ticker])
            if score is not None:
                out[ticker] = score
        return out

    return on


def _traded(asset: AssetEntity) -> bool:
    return asset.market not in (Venue.MANUAL, Venue.FIXED_INCOME_CURVE)


def recommendation_runs(uow: AbstractUnitOfWork) -> list[tuple[date, Holdings]]:
    """The targets of every stored weekly run, class by class."""
    out = []
    for run in uow.recommendation.runs(limit=520):
        holdings: Holdings = {}
        for built in uow.recommendation.constructions(run.as_of):
            if built.selected:
                holdings[ArcaClass(built.arca_class)] = {s.ticker: s.weight for s in built.selected}
        if holdings:
            out.append((run.as_of, holdings))
    return sorted(out, key=lambda r: r[0])


def variant_runs(uow: AbstractUnitOfWork, variant: str) -> list[tuple[date, Holdings]]:
    """The construction's weights with or without the Cerrado lens of every stored run."""
    out = []
    for run in uow.recommendation.runs(limit=520):
        holdings: Holdings = {}
        for built in uow.recommendation.constructions(run.as_of):
            weights = (built.cerrado_variants or {}).get(variant)
            if weights:
                holdings[ArcaClass(built.arca_class)] = dict(weights)
        if holdings:
            out.append((run.as_of, holdings))
    return sorted(out, key=lambda r: r[0])


def optimized_runs(uow: AbstractUnitOfWork) -> list[tuple[date, Holdings]]:
    """The optimizer's weights of every stored weekly run that has them (Phase 45.8b)."""
    out = []
    for run in uow.recommendation.runs(limit=520):
        holdings: Holdings = {}
        for built in uow.recommendation.constructions(run.as_of):
            found = optimized_of(built)
            if found is not None and found.assets:
                holdings[ArcaClass(built.arca_class)] = found.weights
        if holdings:
            out.append((run.as_of, holdings))
    return sorted(out, key=lambda r: r[0])


def universe(
    assets: Sequence[AssetEntity], runs: Sequence[tuple[date, Holdings]]
) -> list[Candidate]:
    """What the references may buy: your ARCA assets traded on a market (portfolio and
    watchlist) plus the catalog stocks the recommendation has chosen."""
    out: dict[str, Candidate] = {}
    for a in assets:
        if a.is_active and a.purpose == AssetPurpose.ARCA and a.arca_class and _traded(a):
            out[a.ticker] = Candidate(a.ticker, a.arca_class, a.asset_type)
    for _, holdings in runs:
        for arca_class, weights in holdings.items():
            for ticker in weights:
                out.setdefault(ticker, Candidate(ticker, arca_class, AssetType.STOCK_BR))
    return sorted(out.values(), key=lambda c: c.symbol)


def _market(
    uow: AbstractUnitOfWork,
    assets: Sequence[AssetEntity],
    tickers: Sequence[str],
    types: Mapping[str, AssetType],
    start: date,
    end: date,
) -> Market:
    currencies = {a.ticker: a.currency or "BRL" for a in assets}
    history = build_market_history(
        uow.market_series, tickers, start=start, end=end, currency_by_ticker=currencies
    )
    lots = {}
    for ticker in tickers:
        if currencies.get(ticker, "BRL") != "BRL":
            continue
        points = uow.market_series.list_series(px_symbol(ticker), date_from=start, date_to=end)
        if points:
            lots[ticker] = PriceSeries.from_points([(p.reference_date, p.value) for p in points])
    return Market(history=history, lot_prices=lots, asset_types=dict(types))


def _strategies(
    assets: Sequence[AssetEntity],
    runs: Sequence[tuple[date, Holdings]],
    optimized: Sequence[tuple[date, Holdings]],
    variants: Mapping[str, Sequence[tuple[date, Holdings]]],
    members: Sequence[Candidate],
    uow: AbstractUnitOfWork,
) -> list[tuple[int, Strategy]]:
    registered = [c for c in members if any(a.ticker == c.symbol for a in assets)]
    histories = {
        a.ticker: uow.checklists.answer_history(a.id)
        for a in assets
        if a.id is not None and a.use_cerrado and any(c.symbol == a.ticker for c in registered)
    }
    fixed: list[tuple[int, Strategy]] = [
        (0, RecommendationRuns(runs)),
        (0, RecommendationRuns(optimized, key=OPTIMIZED, label=LABELS[OPTIMIZED])),
        *(
            (0, RecommendationRuns(runs_of, key=key, label=LABELS[key]))
            for key, runs_of in variants.items()
        ),
        (0, CerradoRule(registered, _scores(histories))),
        (0, EqualWeights(members)),
        (0, IndexArca()),
        (0, AllCdi()),
    ]
    return fixed + [(i, RandomPicks(members, index=i)) for i in range(RANDOM_PORTFOLIOS)]


def _late_flow(flows: Mapping[date, float], state: Mapping[str, Any], book: Book) -> float:
    """Money of trades registered after their day was already recorded."""
    if book.day is None:
        return 0.0
    seen = float(state.get("seen_flow", 0.0))
    return round(sum(v for d, v in flows.items() if d <= book.day) - seen, 2)


def _opening(points: Sequence[Point], day: date) -> float:
    """Your ARCA patrimony at the close before `day` (the start of the recommendation)."""
    before = [p for p in points if p.day < day]
    return before[-1].value if before else 0.0


def update_comparison_portfolios(
    uow: AbstractUnitOfWork, *, today: date | None = None
) -> dict[str, Any]:
    """Rebuild your portfolio and add the new days to every comparison portfolio."""
    as_of = today or date.today()
    assets = uow.assets.list_all(active_only=False)
    flows = arca_flows(assets)
    trades = arca_trades(assets)
    if not flows:
        return {"status": "NO_FLOW", "portfolios": 0}
    first = min(flows)
    runs = recommendation_runs(uow)
    optimized = optimized_runs(uow)
    variants = {key: variant_runs(uow, key) for key in (WITH_CERRADO, WITHOUT_CERRADO)}
    members = universe(assets, [*runs, *optimized, *(r for v in variants.values() for r in v)])
    types = {c.symbol: c.asset_type for c in members} | {t.ticker: t.asset_type for t in trades}
    tickers = sorted(types)
    market = _market(
        uow, assets, tickers, types, first - timedelta(days=HISTORY_MARGIN_DAYS), as_of
    )
    targets = {c: p.target_pct for c, p in current_policy(uow.policies).arca.classes.items()}
    days = valuation_days([*flows, as_of], first, as_of)

    yours_points, _, _ = replay_actual(trades, market, days)
    yours = uow.comparison.get(YOURS) or ComparisonPortfolio(
        key=YOURS, variant=0, label=LABELS[YOURS], created_on=as_of
    )
    yours.points = yours_points
    uow.comparison.save(yours)

    created = updated = 0
    for variant, strategy in _strategies(assets, runs, optimized, variants, members, uow):
        start = getattr(strategy, "first_day", None)
        if isinstance(strategy, RecommendationRuns) and start is None:
            continue  # the recommendation has not run yet: it starts with its first run
        row = uow.comparison.get(strategy.key, variant)
        initial = 0.0
        strategy_days = [d for d in days if start is None or d >= start]
        if row is None:
            row = ComparisonPortfolio(
                key=strategy.key, variant=variant, label=strategy.label, created_on=as_of
            )
            book = Book()
            if start is not None and strategy_days:
                initial = _opening(yours_points, strategy_days[0])
            created += 1
        else:
            book = Book.from_dict(row.state.get("book", {}))
            updated += 1
        step_flows = dict(flows)
        late = _late_flow(flows, row.state, book)
        if late:
            upcoming = [d for d in strategy_days if book.day is None or d > book.day]
            if upcoming:
                step_flows[upcoming[0]] = step_flows.get(upcoming[0], 0.0) + late
        new_points, book = run_strategy(
            strategy, market, step_flows, strategy_days, targets, book=book, initial=initial
        )
        row.points = [*row.points, *new_points]
        seen = sum(v for d, v in flows.items() if book.day is not None and d <= book.day)
        row.state = {"book": book.to_dict(), "seen_flow": round(seen, 2)}
        uow.comparison.save(row)
    return {
        "status": "OK",
        "first_flow": first.isoformat(),
        "created": created,
        "updated": updated,
        "days": len(days),
    }
