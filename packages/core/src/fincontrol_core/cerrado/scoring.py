"""Optional Diagrama do Cerrado evaluation and intra-class weight resolution."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from fincontrol_core.cerrado.questions import questions_for
from fincontrol_core.domain.enums import AssetType, IntraClassStrategy
from fincontrol_core.market.models import Fundamentals


class AnswerSource(StrEnum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"
    PENDING = "PENDING"


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
    answer: bool | None
    source: AnswerSource
    automatable: bool


@dataclass(frozen=True)
class CerradoEvaluation:
    asset_type: AssetType
    use_cerrado: bool
    answers: list[EvaluatedAnswer]
    score: int
    max_score: int
    answered: int
    recommendation: Recommendation

    @property
    def pending(self) -> int:
        return len(self.answers) - self.answered


def evaluate(
    asset_type: AssetType,
    manual_answers: Mapping[str, bool] | None = None,
    fundamentals: Fundamentals | None = None,
    *,
    use_cerrado: bool = True,
) -> CerradoEvaluation:
    """Evaluate an asset's Diagrama do Cerrado questionnaire (or DESATIVADO if disabled)."""
    manual_answers = manual_answers or {}
    evaluated: list[EvaluatedAnswer] = []
    score = 0
    answered = 0

    for q in questions_for(asset_type):
        answer: bool | None = None
        source = AnswerSource.PENDING
        if q.id in manual_answers and manual_answers[q.id] is not None:
            answer, source = bool(manual_answers[q.id]), AnswerSource.MANUAL
        elif q.auto is not None and fundamentals is not None:
            auto_answer = q.auto(fundamentals)
            if auto_answer is not None:
                answer, source = auto_answer, AnswerSource.AUTO
        if answer is not None:
            answered += 1
            score += 1 if answer else -1
        evaluated.append(
            EvaluatedAnswer(q.id, q.text, q.category, q.hint, answer, source, q.automatable)
        )

    if not use_cerrado:
        recommendation = Recommendation.DESATIVADO
    elif answered == 0:
        recommendation = Recommendation.INCOMPLETO
    elif score > 0:
        recommendation = Recommendation.APTO
    else:
        recommendation = Recommendation.REVISAR

    return CerradoEvaluation(
        asset_type=asset_type,
        use_cerrado=use_cerrado,
        answers=evaluated,
        score=score,
        max_score=len(evaluated),
        answered=answered,
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
