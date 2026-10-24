"""Bidirectional mappers between SQLAlchemy ORM models and pure Domain Entities."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

from fincontrol_core.domain.entities import (
    AccountEntity,
    AssetEntity,
    ChecklistAnswer,
    ChecklistEvaluationRecord,
    EarningEntity,
    FixedIncomeTermEntity,
    JobRunEntity,
    MarketSeriesPoint,
    PortfolioSnapshotEntity,
    TransactionEntity,
)
from fincontrol_core.domain.enums import (
    AccountKind,
    AnswerSource,
    AnswerValue,
    ArcaClass,
    AssetPurpose,
    AssetType,
    ChecklistProfile,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
    IntraClassStrategy,
    JobRunStatus,
    SeriesUnit,
    TransactionKind,
)
from fincontrol_core.fundamentals.history import FundamentalPeriod, FundamentalSnapshot
from fincontrol_core.policy.assumptions import ProjectionAssumptions
from fincontrol_core.policy.models import (
    ArcaPolicy,
    ClassPolicy,
    EligibilityPolicy,
    InvestmentPolicy,
    ValuationPolicy,
)

from fincontrol_persistence.models import (
    AccountModel,
    AssetModel,
    ChecklistAnswerModel,
    ChecklistEvaluationModel,
    EarningModel,
    FixedIncomeTermModel,
    FundamentalSnapshotModel,
    InvestmentPolicyModel,
    JobRunModel,
    MarketSeriesModel,
    PortfolioSnapshotModel,
    TransactionModel,
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


def to_transaction_entity(model: TransactionModel) -> TransactionEntity:
    return TransactionEntity(
        id=model.id,
        asset_id=model.asset_id,
        kind=TransactionKind(model.kind),
        trade_date=model.trade_date,
        quantity=Decimal(model.quantity),
        unit_price=Decimal(model.unit_price),
        fees=Decimal(model.fees),
        fx_rate=Decimal(model.fx_rate),
        notes=model.notes,
        account_id=model.account_id,
        created_at=model.created_at,
    )


def to_earning_entity(model: EarningModel) -> EarningEntity:
    return EarningEntity(
        id=model.id,
        asset_id=model.asset_id,
        kind=EarningKind(model.kind),
        payment_date=model.payment_date,
        ex_date=model.ex_date,
        gross_amount=Decimal(model.gross_amount),
        withholding_tax=Decimal(model.withholding_tax),
        net_amount=Decimal(model.net_amount),
        fx_rate=Decimal(model.fx_rate),
        notes=model.notes,
        account_id=model.account_id,
        created_at=model.created_at,
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
    if include_children:
        txs = tuple(to_transaction_entity(t) for t in model.transactions)
        earnings = tuple(to_earning_entity(e) for e in model.earnings)

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
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def policy_payload(policy: InvestmentPolicy) -> dict[str, dict]:
    """JSON-serializable sections of a policy for storage."""
    return {
        "arca": {
            c.value: {
                "target_pct": p.target_pct,
                "band_pct": p.band_pct,
                "intra_class_strategy": p.intra_class_strategy.value,
            }
            for c, p in policy.arca.classes.items()
        },
        "eligibility": asdict(policy.eligibility),
        "valuation": {
            "bazin_required_yield": policy.valuation.bazin_required_yield,
            "graham_multiplier": policy.valuation.graham_multiplier,
            "projections": policy.valuation.projections.as_dict(),
        },
    }


def to_investment_policy(model: InvestmentPolicyModel) -> InvestmentPolicy:
    valuation = dict(model.valuation)
    projections = ProjectionAssumptions(**valuation.pop("projections", {}))
    return InvestmentPolicy(
        arca=ArcaPolicy(
            {
                ArcaClass(c): ClassPolicy(
                    target_pct=float(p["target_pct"]),
                    band_pct=float(p.get("band_pct", 5.0)),
                    intra_class_strategy=IntraClassStrategy(p["intra_class_strategy"]),
                )
                for c, p in model.arca.items()
            }
        ),
        eligibility=EligibilityPolicy(**model.eligibility),
        valuation=ValuationPolicy(projections=projections, **valuation),
        version=model.version,
        created_at=model.created_at,
    )


def to_market_series_point(model: MarketSeriesModel) -> MarketSeriesPoint:
    return MarketSeriesPoint(
        id=model.id,
        symbol=model.symbol,
        reference_date=model.reference_date,
        value=float(model.value),
        unit=SeriesUnit(model.unit),
    )


def to_portfolio_snapshot_entity(model: PortfolioSnapshotModel) -> PortfolioSnapshotEntity:
    return PortfolioSnapshotEntity(
        snapshot_date=model.snapshot_date,
        invested_value=float(model.invested_value),
        market_value=float(model.market_value),
        unrealized_pnl=float(model.unrealized_pnl),
        realized_pnl_cum=float(model.realized_pnl_cum),
        earnings_cum=float(model.earnings_cum),
        consolidated_pnl=float(model.consolidated_pnl),
        net_flow=float(model.net_flow),
        by_class=dict(model.by_class or {}),
    )


def to_job_run_entity(model: JobRunModel) -> JobRunEntity:
    return JobRunEntity(
        id=model.id,
        job_name=model.job_name,
        status=JobRunStatus(model.status),
        attempts=model.attempts,
        started_at=model.started_at,
        finished_at=model.finished_at,
        details=dict(model.details or {}),
        error=model.error,
    )


def to_account_entity(model: AccountModel) -> AccountEntity:
    return AccountEntity(
        id=model.id,
        name=model.name,
        institution=model.institution,
        kind=AccountKind(model.kind),
        is_active=bool(model.is_active),
        created_at=model.created_at,
    )


def to_fundamental_snapshot(model: FundamentalSnapshotModel) -> FundamentalSnapshot:
    return FundamentalSnapshot(
        id=model.id,
        ticker=model.ticker,
        reference_date=model.reference_date,
        period=FundamentalPeriod(model.period),
        metrics=dict(model.metrics or {}),
        source=model.source,
    )
