"""ORM model <-> domain entity mappers.

Scope: assets, fixed income terms and checklist answers/evaluations.
"""

from __future__ import annotations

from decimal import Decimal

from fincontrol_core.domain.entities import (
    AssetEntity,
    ChecklistAnswer,
    ChecklistEvaluationRecord,
    CorporateEventEntity,
    EarningEntity,
    FixedIncomeTermEntity,
    TransactionEntity,
)
from fincontrol_core.domain.enums import (
    AnswerSource,
    AnswerValue,
    ArcaClass,
    AssetPurpose,
    AssetType,
    ChecklistProfile,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
)

from fincontrol_persistence.mappers.ledger import (
    to_corporate_event,
    to_earning_entity,
    to_transaction_entity,
)
from fincontrol_persistence.models.assets import (
    AssetModel,
    ChecklistAnswerModel,
    ChecklistEvaluationModel,
    FixedIncomeTermModel,
)


def to_fixed_income_term_entity(model: FixedIncomeTermModel) -> FixedIncomeTermEntity:
    return FixedIncomeTermEntity(
        id=model.id,
        asset_id=model.asset_id,
        instrument_kind=FixedIncomeInstrumentKind(model.instrument_kind),
        indexer=FixedIncomeIndexer(model.indexer),
        contracted_rate=Decimal(model.contracted_rate),
        issue_date=model.issue_date,
        maturity_date=model.maturity_date,
        tax_exempt=bool(model.tax_exempt),
        liquidity=FixedIncomeLiquidity(model.liquidity),
        issuer=model.issuer,
    )


def to_fixed_income_term_model(entity: FixedIncomeTermEntity) -> FixedIncomeTermModel:
    return FixedIncomeTermModel(
        instrument_kind=entity.instrument_kind.value,
        indexer=entity.indexer.value,
        contracted_rate=entity.contracted_rate,
        issue_date=entity.issue_date,
        maturity_date=entity.maturity_date,
        tax_exempt=entity.tax_exempt,
        liquidity=entity.liquidity.value,
        issuer=entity.issuer,
    )


def to_checklist_answer(model: ChecklistAnswerModel) -> ChecklistAnswer:
    return ChecklistAnswer(
        id=model.id,
        question_id=model.question_id,
        value=AnswerValue(model.value) if model.value else None,
        source=AnswerSource(model.source),
        evidence=model.evidence,
        answered_at=model.answered_at,
        checklist_version=model.checklist_version,
    )


def current_answers(rows: list[ChecklistAnswerModel]) -> dict[str, ChecklistAnswer]:
    """Latest answer per question (rows are ordered oldest first); cleared answers drop out."""
    latest: dict[str, ChecklistAnswer] = {}
    for row in rows:
        latest[row.question_id] = to_checklist_answer(row)
    return {qid: answer for qid, answer in latest.items() if answer.value is not None}


def to_checklist_evaluation(model: ChecklistEvaluationModel) -> ChecklistEvaluationRecord:
    return ChecklistEvaluationRecord(
        id=model.id,
        asset_id=model.asset_id,
        evaluated_at=model.evaluated_at,
        profile=ChecklistProfile(model.profile),
        score=model.score,
        normalized_score=model.normalized_score,
        coverage_pct=model.coverage_pct,
        answered=model.answered,
        applicable=model.applicable,
        recommendation=model.recommendation,
        checklist_version=model.checklist_version,
    )


def to_asset_entity(
    model: AssetModel,
    *,
    include_children: bool = True,
) -> AssetEntity:
    fi_term = (
        to_fixed_income_term_entity(model.fixed_income_term)
        if model.fixed_income_term is not None
        else None
    )
    txs: tuple[TransactionEntity, ...] = ()
    earnings: tuple[EarningEntity, ...] = ()
    events: tuple[CorporateEventEntity, ...] = ()
    if include_children:
        txs = tuple(to_transaction_entity(t) for t in model.transactions)
        earnings = tuple(to_earning_entity(e) for e in model.earnings)
        events = tuple(to_corporate_event(e) for e in model.corporate_events)

    return AssetEntity(
        id=model.id,
        ticker=model.ticker,
        name=model.name,
        asset_type=AssetType(model.asset_type),
        arca_class=ArcaClass(model.arca_class),
        currency=model.currency,
        manual_price=Decimal(model.manual_price) if model.manual_price is not None else None,
        custom_class_weight=(
            Decimal(model.custom_class_weight) if model.custom_class_weight is not None else None
        ),
        use_cerrado=bool(model.use_cerrado),
        cerrado_answers=current_answers(model.checklist_answers),
        checklist_profile=(
            ChecklistProfile(model.checklist_profile) if model.checklist_profile else None
        ),
        is_active=bool(model.is_active),
        notes=model.notes,
        purpose=AssetPurpose(model.purpose),
        fixed_income_term=fi_term,
        transactions=txs,
        earnings=earnings,
        corporate_events=events,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
