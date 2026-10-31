"""Worker side of the backtest and the scoreboard of the recommendation (Phase 45.6).

The backtest reads the Garimpo's panel (the point-in-time signals, every month), the monthly
returns of the mining universe over the class and over the CDI, and the dated judicial recovery
announcements; the scoreboard reads the stored runs (45.5) and the stored prices after each one.
Both are stored together, weekly, as the RECOMMENDATION_BACKTEST model.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from domain.disclosures.events import RESTRUCTURING
from domain.mining.runs import mining_panel
from domain.mining.universe import MIN_DAILY_VOLUME, mining_universe
from domain.policy.services.policy import current_policy
from domain.recommendation.ahp import priority
from domain.recommendation.backtest import RunPortfolios, run_backtest, scoreboard
from domain.recommendation.keys import CERRADO
from domain.recommendation.lenses import CATALOG
from domain.recommendation.runs import monthly_returns
from domain.shared.enums import ArcaClass
from domain.shared.unit_of_work import AbstractUnitOfWork

RECOMMENDATION_BACKTEST = "RECOMMENDATION_BACKTEST"


def _run_portfolios(uow: AbstractUnitOfWork) -> list[RunPortfolios]:
    out = []
    for run in uow.recommendation.runs(limit=520):
        constructions = {c.arca_class: c for c in uow.recommendation.constructions(run.as_of)}
        lenses = {i.ticker: i for i in uow.recommendation.lenses(as_of=run.as_of)}
        for matrix in uow.recommendation.matrices(run.as_of):
            built = constructions.get(matrix.arca_class)
            eligible = [r.ticker for r in matrix.rows]
            cerrado = {}
            for r in matrix.rows:
                item = lenses.get(r.ticker)
                score = item.lens(CERRADO) if item is not None else None
                if r.source != CATALOG and score is not None and (score.value or 0) > 0:
                    cerrado[r.ticker] = float(score.value)
            out.append(
                RunPortfolios(
                    as_of=run.as_of,
                    recommended={s.ticker: s.weight for s in built.selected} if built else {},
                    eligible=eligible,
                    cerrado=cerrado,
                )
            )
    return out


def run_recommendation_backtest(
    uow: AbstractUnitOfWork,
    *,
    min_daily_volume: float = MIN_DAILY_VOLUME,
    today: date | None = None,
) -> dict[str, Any]:
    """Backtest the hierarchy on the Ações class and score the stored runs; store both."""
    as_of = today or date.today()
    policy = current_policy(uow.policies).recommendation
    objective = policy.objectives.get(ArcaClass.ACOES)
    weights = priority(policy.matrices[objective]).weights if objective else {}

    members = mining_universe(uow, min_daily_volume)
    companies, alphas, over_cdi = mining_panel(uow, members, as_of)
    panel: dict[tuple[int, int], dict[str, dict[str, float]]] = {}
    for s in uow.mining.all_signals():
        if s.ticker in companies:
            key = (s.month.year, s.month.month)
            panel.setdefault(key, {}).setdefault(s.ticker, {})[s.signal] = s.z
    first_month = {t: min(r) for t, r in over_cdi.items() if r}
    by_cnpj = {m.cnpj: m.ticker for m in members if m.ticker in companies}
    restructuring: dict[str, list[tuple[int, int]]] = {}
    for doc in uow.cvm_documents.events(sorted(by_cnpj)) if by_cnpj else []:
        if doc.event_class == RESTRUCTURING and doc.cnpj in by_cnpj:
            day = doc.delivery_date
            restructuring.setdefault(by_cnpj[doc.cnpj], []).append((day.year, day.month))
    found = run_backtest(
        as_of=as_of,
        panel=panel,
        alphas=alphas,
        returns=over_cdi,
        sectors={t: c.sector for t, c in companies.items()},
        first_month=first_month,
        restructuring=restructuring,
        weights=weights,
        params=policy.construction(),
        scale_annual=policy.score_scale_annual,
    )

    runs = _run_portfolios(uow)
    tickers = sorted({t for r in runs for t in (*r.recommended, *r.eligible, *r.cerrado)})
    returns = monthly_returns(uow, tickers, as_of)
    last = (as_of.year, as_of.month)
    lines = scoreboard(runs, returns, last)
    payload = {
        "backtest": found.to_dict(),
        "scoreboard": [line.__dict__ for line in lines],
    }
    uow.forecasts.save_model(RECOMMENDATION_BACKTEST, as_of, payload)
    return {
        "status": found.status,
        "passed": found.passed,
        "months": found.months,
        "probability": found.probability,
        "scored_runs": max((line.runs for line in lines), default=0),
    }
