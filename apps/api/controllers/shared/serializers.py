"""Domain entity to DTO serializers for the shared module.

Scope: pieces shared by several modules.
"""

from __future__ import annotations

from controllers.shared.responses import (
    CerradoEvaluationDTO,
    EvaluatedAnswerDTO,
    PageMetaDTO,
)
from core.helpers.pagination import PageMeta
from domain.assets.services.cerrado import CerradoEvaluation


def to_page_meta_dto(meta: PageMeta) -> PageMetaDTO:
    return PageMetaDTO(
        page=meta.page,
        page_size=meta.page_size,
        total_items=meta.total_items,
        total_pages=meta.total_pages,
        has_next=meta.has_next,
        has_prev=meta.has_prev,
        sort_by=meta.sort_by,
        sort_order=meta.sort_order,
    )


def to_cerrado_dto(eval_obj: CerradoEvaluation) -> CerradoEvaluationDTO:
    return CerradoEvaluationDTO(
        profile=eval_obj.profile,
        checklist_version=eval_obj.checklist_version,
        use_cerrado=eval_obj.use_cerrado,
        score=eval_obj.score,
        max_score=eval_obj.max_score,
        normalized_score=eval_obj.normalized_score,
        coverage_pct=round(eval_obj.coverage_pct, 2),
        answered=eval_obj.answered,
        applicable=eval_obj.applicable,
        not_applicable=eval_obj.not_applicable,
        pending=eval_obj.pending,
        recommendation=eval_obj.recommendation.value,
        answers=[
            EvaluatedAnswerDTO(
                question_id=a.question_id,
                text=a.text,
                category=a.category,
                hint=a.hint,
                value=a.value,
                answer=a.answer,
                source=a.source.value,
                automatable=a.automatable,
                evidence=a.evidence,
                answered_at=a.answered_at,
            )
            for a in eval_obj.answers
        ],
    )
