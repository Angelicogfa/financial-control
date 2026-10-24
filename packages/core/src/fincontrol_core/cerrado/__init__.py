"""Fundamentalist checklist (Diagrama do Cerrado v2) and intra-class weight resolution."""

from fincontrol_core.cerrado.questions import (
    CHECKLIST_VERSION,
    STATEMENT_PROFILES,
    AutoAnswer,
    CerradoQuestion,
    EvidenceContext,
    questions_for,
    resolve_profile,
)
from fincontrol_core.cerrado.scoring import (
    CerradoEvaluation,
    EvaluatedAnswer,
    Recommendation,
    evaluate,
    evaluation_record,
    history_for_assets,
    record_if_changed,
    resolve_intra_class_weights,
    target_weights_from_scores,
)
from fincontrol_core.domain.enums import AnswerSource, AnswerValue, ChecklistProfile

__all__ = [
    "CHECKLIST_VERSION",
    "STATEMENT_PROFILES",
    "AnswerSource",
    "AnswerValue",
    "AutoAnswer",
    "CerradoEvaluation",
    "CerradoQuestion",
    "ChecklistProfile",
    "EvaluatedAnswer",
    "EvidenceContext",
    "Recommendation",
    "evaluate",
    "evaluation_record",
    "history_for_assets",
    "record_if_changed",
    "questions_for",
    "resolve_profile",
    "resolve_intra_class_weights",
    "target_weights_from_scores",
]
