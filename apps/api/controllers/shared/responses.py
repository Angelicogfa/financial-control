"""Pydantic request/response DTOs for the shared module.

Scope: pieces shared by several modules.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from domain.shared.enums import (
    AnswerValue,
    ChecklistProfile,
)


class PageMetaDTO(BaseModel):
    """Standardized pagination metadata."""

    model_config = ConfigDict(from_attributes=True)

    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool
    sort_by: str
    sort_order: str


class PaginatedResponse[T](BaseModel):
    """Standardized paginated response envelope for all listing endpoints."""

    items: list[T]
    meta: PageMetaDTO


class EvaluatedAnswerDTO(BaseModel):
    question_id: str
    text: str
    category: str
    hint: str
    value: AnswerValue | None
    answer: bool | None
    source: str
    automatable: bool
    evidence: str | None = None
    answered_at: datetime | None = None
    stale_reason: str | None = None


class CerradoEvaluationDTO(BaseModel):
    profile: ChecklistProfile
    checklist_version: int
    use_cerrado: bool
    score: int
    max_score: int
    normalized_score: float | None
    coverage_pct: float
    answered: int
    applicable: int
    not_applicable: int
    pending: int
    recommendation: str
    stale: int = 0
    answers: list[EvaluatedAnswerDTO]
