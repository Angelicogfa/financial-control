"""Domain entity to DTO serializers for the assets module.

Scope: asset registry, checklist and fundamentalist analysis.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from controllers.assets.requests import FixedIncomeTermPayload
from controllers.assets.responses import (
    AssetResponseDTO,
    AssetValuationDTO,
    ChecklistAnswerDTO,
    ChecklistAnswerHistoryDTO,
    ChecklistEvaluationRecordDTO,
    FundamentalSnapshotDTO,
    HistoricalMetricsDTO,
    MethodResultDTO,
)
from controllers.portfolio.serializers import to_risk_summary_dto, to_valued_position_dto
from controllers.shared.serializers import to_cerrado_dto
from domain.assets.services.history import HistoricalMetrics
from domain.assets.services.valuation import AssetValuation
from domain.shared.entities import (
    AssetEntity,
    ChecklistEvaluationRecord,
)
from domain.shared.enums import ArcaClass


def to_asset_dto(entity: AssetEntity) -> AssetResponseDTO:
    term_dto = None
    if entity.fixed_income_term is not None:
        t = entity.fixed_income_term
        term_dto = FixedIncomeTermPayload(
            instrument_kind=t.instrument_kind,
            indexer=t.indexer,
            contracted_rate=t.contracted_rate,
            issue_date=t.issue_date,
            maturity_date=t.maturity_date,
            tax_exempt=t.tax_exempt,
            liquidity=t.liquidity,
            issuer=t.issuer,
            semiannual_coupons=t.semiannual_coupons,
        )
    return AssetResponseDTO(
        id=entity.id or 0,
        ticker=entity.ticker,
        name=entity.name,
        asset_type=entity.asset_type,
        arca_class=entity.arca_class or ArcaClass.ACOES,
        currency=entity.currency or "BRL",
        manual_price=entity.manual_price,
        custom_class_weight=entity.custom_class_weight,
        use_cerrado=entity.use_cerrado,
        cerrado_answers={
            qid: a.as_bool for qid, a in entity.cerrado_answers.items() if a.as_bool is not None
        },
        checklist_profile=entity.profile,
        checklist_answers={
            qid: ChecklistAnswerDTO(
                value=a.value,
                source=a.source,
                evidence=a.evidence,
                answered_at=a.answered_at,
                checklist_version=a.checklist_version,
            )
            for qid, a in entity.cerrado_answers.items()
        },
        is_active=entity.is_active,
        notes=entity.notes,
        purpose=entity.purpose,
        fixed_income_term=term_dto,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def to_valuation_dto(valuation: AssetValuation) -> AssetValuationDTO:
    return AssetValuationDTO(
        profile=valuation.profile,
        applicable=valuation.applicable,
        price=valuation.price,
        methods=[MethodResultDTO(**{**asdict(m), "kind": m.kind.value}) for m in valuation.methods],
        fair_value=valuation.fair_value,
        margin=valuation.margin,
        verdict=valuation.verdict.value,
        reason=valuation.reason,
        suspicious_inputs=list(valuation.suspicious_inputs),
        extraordinary_dividends=valuation.extraordinary_dividends,
    )


def to_historical_metrics_dto(metrics: HistoricalMetrics) -> HistoricalMetricsDTO:
    return HistoricalMetricsDTO(
        **asdict(metrics),
        always_profitable=metrics.always_profitable,
        dividend_regularity=metrics.dividend_regularity,
    )


def to_checklist_record_dto(record: ChecklistEvaluationRecord) -> ChecklistEvaluationRecordDTO:
    return ChecklistEvaluationRecordDTO(
        evaluated_at=record.evaluated_at,
        profile=record.profile,
        checklist_version=record.checklist_version,
        score=record.score,
        normalized_score=record.normalized_score,
        coverage_pct=record.coverage_pct,
        answered=record.answered,
        applicable=record.applicable,
        recommendation=record.recommendation,
    )


def to_asset_analysis_dto(asset: AssetEntity, raw: dict[str, Any]) -> dict[str, Any]:
    metrics = raw["historical_metrics"]
    return {
        "asset": to_asset_dto(asset),
        "position": (
            to_valued_position_dto(raw["position"]) if raw["position"] is not None else None
        ),
        "fundamentals": raw["fundamentals"],
        "fundamental_history": [
            FundamentalSnapshotDTO(
                reference_date=s.reference_date,
                period=s.period.value,
                metrics=dict(s.metrics),
                source=s.source,
            )
            for s in raw["fundamental_history"]
        ],
        "historical_metrics": to_historical_metrics_dto(metrics) if metrics else None,
        "indicator_ratings": {
            key: {"status": r.status, "reference": r.reference}
            for key, r in raw.get("indicator_ratings", {}).items()
        },
        "valuation": to_valuation_dto(raw["valuation"]),
        "checklist": to_cerrado_dto(raw["checklist"]),
        "checklist_history": [to_checklist_record_dto(r) for r in raw["checklist_history"]],
        "answer_history": [
            ChecklistAnswerHistoryDTO(
                question_id=a.question_id,
                value=a.value,
                source=a.source,
                evidence=a.evidence,
                answered_at=a.answered_at,
                checklist_version=a.checklist_version,
            )
            for a in raw["answer_history"]
        ],
        "risk_return": to_risk_summary_dto(raw["risk_return"]),
        "benchmark": raw["benchmark"],
        "price_history": raw["price_history"],
    }
