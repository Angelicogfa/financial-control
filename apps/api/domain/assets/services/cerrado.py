"""Checklist evaluation (Diagrama do Cerrado v2) and intra-class weight resolution.

Score = YES - NO over applicable questions (NA is excluded). `normalized_score` scales it to
[-1, 1] so assets with different questionnaires compare; `coverage_pct` is the share of
applicable questions answered (manually or automatically).
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from domain.assets.services.history import (
    FundamentalSnapshot,
    HistoricalMetrics,
    historical_metrics,
)
from domain.assets.services.questions import (
    CHECKLIST_VERSION,
    STATEMENT_PROFILES,
    EvidenceContext,
    questions_for,
    resolve_profile,
)
from domain.market.entities import Fundamentals
from domain.shared.entities import (
    AssetEntity,
    ChecklistAnswer,
    ChecklistEvaluationRecord,
)
from domain.shared.enums import (
    AnswerSource,
    AnswerValue,
    AssetType,
    ChecklistProfile,
    IntraClassStrategy,
)

if TYPE_CHECKING:
    from domain.shared.repositories import AbstractChecklistRepository


class Recommendation(StrEnum):
    APTO = "APTO"
    REVISAR = "REVISAR"
    INCOMPLETO = "INCOMPLETO"
    DESATIVADO = "DESATIVADO"


@dataclass(frozen=True)
class EvaluatedAnswer:
    question_id: str
    text: str
    category: str
    hint: str
    value: AnswerValue | None
    source: AnswerSource
    automatable: bool
    evidence: str | None = None
    answered_at: datetime | None = None

    @property
    def answer(self) -> bool | None:
        """YES/NO as a bool; None when pending or not applicable."""
        if self.value == AnswerValue.YES:
            return True
        if self.value == AnswerValue.NO:
            return False
        return None


@dataclass(frozen=True)
class CerradoEvaluation:
    profile: ChecklistProfile
    use_cerrado: bool
    answers: list[EvaluatedAnswer]
    yes: int
    no: int
    not_applicable: int
    recommendation: Recommendation
    checklist_version: int = CHECKLIST_VERSION

    @property
    def answered(self) -> int:
        return self.yes + self.no

    @property
    def applicable(self) -> int:
        return len(self.answers) - self.not_applicable

    @property
    def score(self) -> int:
        return self.yes - self.no

    @property
    def max_score(self) -> int:
        return self.applicable

    @property
    def pending(self) -> int:
        return self.applicable - self.answered

    @property
    def normalized_score(self) -> float | None:
        return self.score / self.applicable if self.applicable else None

    @property
    def coverage_pct(self) -> float:
        return self.answered / self.applicable * 100.0 if self.applicable else 0.0


def evaluate(
    profile_or_type: ChecklistProfile | AssetType,
    manual_answers: Mapping[str, object] | None = None,
    fundamentals: Fundamentals | None = None,
    *,
    use_cerrado: bool = True,
    history: HistoricalMetrics | None = None,
) -> CerradoEvaluation:
    """Evaluate a checklist: manual answers first, then auto rules with evidence."""
    profile = resolve_profile(profile_or_type)
    manual = {qid: ChecklistAnswer.coerce(qid, raw) for qid, raw in (manual_answers or {}).items()}
    context = EvidenceContext(fundamentals=fundamentals, history=history)
    evaluated: list[EvaluatedAnswer] = []
    counts = {AnswerValue.YES: 0, AnswerValue.NO: 0, AnswerValue.NA: 0}

    for q in questions_for(profile):
        value: AnswerValue | None = None
        source = AnswerSource.PENDING
        evidence: str | None = None
        answered_at: datetime | None = None
        stored = manual.get(q.id)
        if stored is not None and stored.value is not None:
            value, source = stored.value, stored.source
            evidence, answered_at = stored.evidence, stored.answered_at
        elif q.auto is not None:
            auto = q.auto(context)
            if auto is not None:
                value = AnswerValue.YES if auto.value else AnswerValue.NO
                source, evidence = AnswerSource.AUTO, auto.evidence
        if value is not None:
            counts[value] += 1
        evaluated.append(
            EvaluatedAnswer(
                q.id,
                q.text,
                q.category,
                q.hint,
                value,
                source,
                q.automatable,
                evidence,
                answered_at,
            )
        )

    yes, no = counts[AnswerValue.YES], counts[AnswerValue.NO]
    if not use_cerrado:
        recommendation = Recommendation.DESATIVADO
    elif yes + no == 0:
        recommendation = Recommendation.INCOMPLETO
    elif yes > no:
        recommendation = Recommendation.APTO
    else:
        recommendation = Recommendation.REVISAR

    return CerradoEvaluation(
        profile=profile,
        use_cerrado=use_cerrado,
        answers=evaluated,
        yes=yes,
        no=no,
        not_applicable=counts[AnswerValue.NA],
        recommendation=recommendation,
    )


def target_weights_from_scores[K: Hashable](scores: Mapping[K, int]) -> dict[K, float]:
    """Convert Cerrado scores into intra-class target weights (equal fallback if all <= 0)."""
    if not scores:
        return {}
    positives = {k: max(s, 0) for k, s in scores.items()}
    total = sum(positives.values())
    if total == 0:
        equal = 1.0 / len(scores)
        return {k: equal for k in scores}
    return {k: v / total for k, v in positives.items()}


def resolve_intra_class_weights[K: Hashable](
    strategy: IntraClassStrategy,
    asset_keys: list[K],
    *,
    cerrado_scores: Mapping[K, int] | None = None,
    cerrado_enabled: Mapping[K, bool] | None = None,
    manual_weights: Mapping[K, float | None] | None = None,
) -> dict[K, float]:
    """Resolve target weights inside an ARCA class (optional Cerrado, manual, or equal)."""
    if not asset_keys:
        return {}

    equal = {k: 1.0 / len(asset_keys) for k in asset_keys}

    if strategy == IntraClassStrategy.EQUAL_WEIGHT:
        return equal

    if strategy == IntraClassStrategy.MANUAL_WEIGHT and manual_weights:
        positive_manuals = {k: max(float(manual_weights.get(k) or 0.0), 0.0) for k in asset_keys}
        total_manual = sum(positive_manuals.values())
        if total_manual > 0:
            return {k: v / total_manual for k, v in positive_manuals.items()}
        return equal

    # Strategy == CERRADO: if use_cerrado is disabled for an asset, assign average positive score
    scores_map = cerrado_scores or {}
    enabled_map = cerrado_enabled or {}
    positive_scores = [
        max(scores_map.get(k, 0), 0)
        for k in asset_keys
        if enabled_map.get(k, True) and scores_map.get(k, 0) > 0
    ]
    default_non_cerrado_score = (
        int(round(sum(positive_scores) / len(positive_scores))) if positive_scores else 1
    )

    effective_scores: dict[K, int] = {}
    for k in asset_keys:
        if not enabled_map.get(k, True):
            effective_scores[k] = default_non_cerrado_score
        else:
            effective_scores[k] = scores_map.get(k, 0)

    return target_weights_from_scores(effective_scores)


def evaluation_record(
    asset_id: int, evaluation: CerradoEvaluation, evaluated_at: datetime
) -> ChecklistEvaluationRecord:
    """Persistable summary of an evaluation (item 11.4)."""
    return ChecklistEvaluationRecord(
        asset_id=asset_id,
        evaluated_at=evaluated_at,
        profile=evaluation.profile,
        score=evaluation.score,
        normalized_score=evaluation.normalized_score,
        coverage_pct=round(evaluation.coverage_pct, 2),
        answered=evaluation.answered,
        applicable=evaluation.applicable,
        recommendation=evaluation.recommendation.value,
        checklist_version=evaluation.checklist_version,
    )


def history_for_assets(
    assets: Iterable[AssetEntity], snapshots: Mapping[str, list[FundamentalSnapshot]]
) -> dict[str, HistoricalMetrics]:
    """Multi-year metrics of the assets whose checklist profile reads statements."""
    return {
        asset.ticker: historical_metrics(snapshots[asset.ticker])
        for asset in assets
        if asset.profile in STATEMENT_PROFILES and snapshots.get(asset.ticker)
    }


def record_if_changed(
    checklists: AbstractChecklistRepository, record: ChecklistEvaluationRecord
) -> bool:
    """Append an evaluation to the history only when its outcome changed."""
    latest = checklists.latest_evaluation(record.asset_id)
    if latest is not None and latest.same_result(record):
        return False
    checklists.record_evaluation(record)
    return True
