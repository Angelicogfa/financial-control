"""SQLAlchemy repository of the recommendation (Phase 45).

It takes and returns pure domain entities and never commits
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from domain.recommendation.combination import ClassMatrix
from domain.recommendation.construction import ClassConstruction
from domain.recommendation.gates import GATES, AssetGates, GateResult
from domain.recommendation.keys import LENSES
from domain.recommendation.lenses import AssetLenses, LensScore
from domain.recommendation.repositories import (
    AbstractRecommendationRepository,
    RecommendationRun,
)
from infra.data.models.recommendation import (
    AssetGateModel,
    AssetLensModel,
    RecommendationMatrixModel,
    RecommendationRunModel,
)

CHUNK = 500


class SqlAlchemyRecommendationRepository(AbstractRecommendationRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_lenses(self, as_of: date, items: Sequence[AssetLenses]) -> int:
        self.session.execute(delete(AssetLensModel).where(AssetLensModel.as_of == as_of))
        rows = [
            {
                "as_of": as_of,
                "ticker": item.ticker,
                "lens": score.lens,
                "source": item.source,
                "arca_class": item.arca_class,
                "sector": item.sector,
                "signal_ticker": item.signal_ticker,
                "value": score.value,
                "normalized": score.normalized,
                "confidence": score.confidence,
                "note": score.note,
                "flags": list(score.flags),
            }
            for item in items
            for score in item.lenses
        ]
        for i in range(0, len(rows), CHUNK):
            self.session.execute(insert(AssetLensModel), rows[i : i + CHUNK])
        self.session.flush()
        return len(items)

    def latest_lens_date(self) -> date | None:
        return self.session.scalar(select(func.max(AssetLensModel.as_of)))

    def lenses(
        self, as_of: date | None = None, tickers: Sequence[str] | None = None
    ) -> list[AssetLenses]:
        day = as_of or self.latest_lens_date()
        if day is None:
            return []
        stmt = select(AssetLensModel).where(AssetLensModel.as_of == day)
        if tickers is not None:
            stmt = stmt.where(AssetLensModel.ticker.in_([t.strip().upper() for t in tickers]))
        by_ticker: dict[str, list[AssetLensModel]] = {}
        for m in self.session.scalars(stmt).all():
            by_ticker.setdefault(m.ticker, []).append(m)
        order = {lens: i for i, lens in enumerate(LENSES)}
        out = []
        for ticker in sorted(by_ticker):
            rows = sorted(by_ticker[ticker], key=lambda m: order.get(m.lens, len(order)))
            first = rows[0]
            out.append(
                AssetLenses(
                    ticker=ticker,
                    as_of=first.as_of,
                    source=first.source,
                    arca_class=first.arca_class,
                    sector=first.sector,
                    signal_ticker=first.signal_ticker,
                    lenses=[
                        LensScore(
                            lens=m.lens,
                            value=m.value,
                            normalized=m.normalized,
                            confidence=m.confidence,
                            note=m.note,
                            flags=list(m.flags or []),
                        )
                        for m in rows
                    ],
                )
            )
        return out

    def replace_gates(self, as_of: date, items: Sequence[AssetGates]) -> int:
        self.session.execute(delete(AssetGateModel).where(AssetGateModel.as_of == as_of))
        rows = [
            {
                "as_of": as_of,
                "ticker": item.ticker,
                "gate": r.gate,
                "status": r.status,
                "reason": r.reason,
            }
            for item in items
            for r in item.results
        ]
        for i in range(0, len(rows), CHUNK):
            self.session.execute(insert(AssetGateModel), rows[i : i + CHUNK])
        self.session.flush()
        return len(items)

    def gates(
        self, as_of: date | None = None, tickers: Sequence[str] | None = None
    ) -> list[AssetGates]:
        day = as_of or self.latest_lens_date()
        if day is None:
            return []
        stmt = select(AssetGateModel).where(AssetGateModel.as_of == day)
        if tickers is not None:
            stmt = stmt.where(AssetGateModel.ticker.in_([t.strip().upper() for t in tickers]))
        by_ticker: dict[str, list[AssetGateModel]] = {}
        for m in self.session.scalars(stmt).all():
            by_ticker.setdefault(m.ticker, []).append(m)
        order = {gate: i for i, gate in enumerate(GATES)}
        return [
            AssetGates(
                ticker,
                [
                    GateResult(m.gate, m.status, m.reason)
                    for m in sorted(by_ticker[ticker], key=lambda m: order.get(m.gate, len(order)))
                ],
            )
            for ticker in sorted(by_ticker)
        ]

    def replace_matrices(
        self,
        as_of: date,
        items: Sequence[ClassMatrix],
        constructions: Mapping[str, ClassConstruction] | None = None,
    ) -> int:
        self.session.execute(
            delete(RecommendationMatrixModel).where(RecommendationMatrixModel.as_of == as_of)
        )
        built = constructions or {}
        for item in items:
            construction = built.get(item.arca_class)
            self.session.add(
                RecommendationMatrixModel(
                    as_of=as_of,
                    arca_class=item.arca_class,
                    payload=item.to_dict(),
                    construction=construction.to_dict() if construction else None,
                )
            )
        self.session.flush()
        return len(items)

    def matrices(self, as_of: date | None = None) -> list[ClassMatrix]:
        day = as_of or self.latest_lens_date()
        if day is None:
            return []
        stmt = (
            select(RecommendationMatrixModel)
            .where(RecommendationMatrixModel.as_of == day)
            .order_by(RecommendationMatrixModel.arca_class)
        )
        return [ClassMatrix.from_dict(m.payload) for m in self.session.scalars(stmt).all()]

    def constructions(self, as_of: date | None = None) -> list[ClassConstruction]:
        day = as_of or self.latest_lens_date()
        if day is None:
            return []
        stmt = (
            select(RecommendationMatrixModel)
            .where(RecommendationMatrixModel.as_of == day)
            .order_by(RecommendationMatrixModel.arca_class)
        )
        return [
            ClassConstruction.from_dict(m.construction)
            for m in self.session.scalars(stmt).all()
            if m.construction
        ]

    def save_run(self, run: RecommendationRun) -> None:
        self.session.execute(
            delete(RecommendationRunModel).where(RecommendationRunModel.as_of == run.as_of)
        )
        self.session.add(
            RecommendationRunModel(
                as_of=run.as_of,
                policy_version=run.policy_version,
                signal_month=run.signal_month,
                assets=run.assets,
                eligible=run.eligible,
                selected=dict(run.selected),
            )
        )
        self.session.flush()

    def runs(self, limit: int = 52) -> list[RecommendationRun]:
        stmt = (
            select(RecommendationRunModel)
            .order_by(RecommendationRunModel.as_of.desc())
            .limit(limit)
        )
        return [
            RecommendationRun(
                as_of=m.as_of,
                policy_version=m.policy_version,
                signal_month=m.signal_month,
                assets=m.assets,
                eligible=m.eligible,
                selected={k: list(v) for k, v in (m.selected or {}).items()},
            )
            for m in self.session.scalars(stmt).all()
        ]
