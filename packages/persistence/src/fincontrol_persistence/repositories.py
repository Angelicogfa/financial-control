"""Concrete SQLAlchemy implementations of AbstractRepository ports.

All repository methods accept and return pure Domain Entities from `fincontrol_core.domain.entities`
and never call `session.commit()` (transaction boundaries belong to `SqlAlchemyUnitOfWork`).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fincontrol_core.domain.entities import (
    AccountEntity,
    AssetEntity,
    CatalogInstrument,
    ChecklistAnswer,
    ChecklistEvaluationRecord,
    EarningEntity,
    JobRunEntity,
    MarketSeriesPoint,
    PortfolioSnapshotEntity,
    TransactionEntity,
)
from fincontrol_core.domain.enums import AnswerSource, ContributionPlanStatus, SeriesUnit
from fincontrol_core.domain.pagination import PageMeta, PaginatedResult, PaginationParams
from fincontrol_core.errors import NotFoundError, ValidationError
from fincontrol_core.fundamentals.history import FundamentalPeriod, FundamentalSnapshot
from fincontrol_core.policy.models import InvestmentPolicy
from fincontrol_core.portfolio.contribution_plans import SavedContributionPlan, plan_to_payload
from fincontrol_core.ports.repositories import (
    AbstractAccountRepository,
    AbstractAssetRepository,
    AbstractCatalogRepository,
    AbstractChecklistRepository,
    AbstractContributionPlanRepository,
    AbstractEarningRepository,
    AbstractFundamentalsRepository,
    AbstractJobRunRepository,
    AbstractMarketSeriesRepository,
    AbstractPolicyRepository,
    AbstractPortfolioSnapshotRepository,
    AbstractTransactionRepository,
)
from sqlalchemy import Select, asc, delete, desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from fincontrol_persistence.mappers import (
    current_answers,
    policy_payload,
    to_account_entity,
    to_asset_entity,
    to_catalog_instrument,
    to_checklist_answer,
    to_checklist_evaluation,
    to_earning_entity,
    to_fixed_income_term_model,
    to_fundamental_snapshot,
    to_investment_policy,
    to_job_run_entity,
    to_market_series_point,
    to_portfolio_snapshot_entity,
    to_saved_contribution_plan,
    to_transaction_entity,
)
from fincontrol_persistence.models import (
    AccountModel,
    AssetModel,
    ChecklistAnswerModel,
    ChecklistEvaluationModel,
    ContributionPlanModel,
    EarningModel,
    FixedIncomeTermModel,
    FundamentalSnapshotModel,
    InstrumentCatalogModel,
    InvestmentPolicyModel,
    JobRunModel,
    MarketSeriesModel,
    PortfolioSnapshotModel,
    TransactionModel,
)


def _money(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))


def _apply_sort_and_paginate(
    session: Session,
    stmt: Select[Any],
    params: PaginationParams,
    allowed_sort_columns: dict[str, Any],
    default_column: Any,
    tie_breaker: Any,
) -> tuple[list[Any], PageMeta]:
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total_items = int(session.scalar(count_stmt) or 0)

    sort_col = allowed_sort_columns.get(params.sort_by, default_column)
    direction = desc if params.is_descending else asc
    # The primary key breaks ties so equal sort values never shuffle between pages (D-04).
    paginated_stmt = (
        stmt.order_by(direction(sort_col), direction(tie_breaker))
        .offset(params.offset)
        .limit(params.page_size)
    )
    items = list(session.scalars(paginated_stmt).all())
    meta = PageMeta.build(params, total_items)
    return items, meta


def _append_changed_answers(model: AssetModel, answers: Mapping[str, ChecklistAnswer]) -> None:
    """Append a row for every answer that differs from the stored one (append-only, 11.4).

    Questions answered before and missing from `answers` get a cleared (NULL) row.
    """
    current = current_answers(model.checklist_answers)
    now = datetime.now(UTC)
    for qid in sorted(set(current) | set(answers)):
        new = answers.get(qid)
        old = current.get(qid)
        if new is None and old is None:
            continue
        if (
            new is not None
            and old is not None
            and new.value == old.value
            and new.evidence in (None, old.evidence)
        ):
            continue
        model.checklist_answers.append(
            ChecklistAnswerModel(
                question_id=qid,
                value=new.value.value if new is not None and new.value else None,
                source=(new.source if new is not None else AnswerSource.MANUAL).value,
                evidence=new.evidence if new is not None else None,
                answered_at=(new.answered_at if new is not None and new.answered_at else now),
                checklist_version=new.checklist_version if new is not None else 2,
            )
        )


class SqlAlchemyAssetRepository(AbstractAssetRepository):
    """SQLAlchemy implementation of AbstractAssetRepository."""

    SORT_COLUMNS = {
        "id": AssetModel.id,
        "ticker": AssetModel.ticker,
        "name": AssetModel.name,
        "asset_type": AssetModel.asset_type,
        "arca_class": AssetModel.arca_class,
        "created_at": AssetModel.created_at,
    }

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, asset: AssetEntity) -> AssetEntity:
        model = AssetModel.create(
            ticker=asset.ticker,
            name=asset.name,
            asset_type=asset.asset_type,
            arca_class=asset.arca_class,
            currency=asset.currency,
            manual_price=asset.manual_price,
            custom_class_weight=asset.custom_class_weight,
            use_cerrado=asset.use_cerrado,
            is_active=asset.is_active,
            notes=asset.notes,
        )
        model.purpose = asset.purpose.value
        model.checklist_profile = asset.checklist_profile.value if asset.checklist_profile else None
        if asset.fixed_income_term is not None:
            model.fixed_income_term = to_fixed_income_term_model(asset.fixed_income_term)
        self.session.add(model)
        self.session.flush()
        _append_changed_answers(model, asset.cerrado_answers)
        self.session.flush()
        return to_asset_entity(model, include_children=False)

    def update(self, asset: AssetEntity) -> AssetEntity:
        if asset.id is None:
            raise ValidationError("Cannot update AssetEntity without id")
        stmt = (
            select(AssetModel)
            .options(
                selectinload(AssetModel.fixed_income_term),
                selectinload(AssetModel.checklist_answers),
            )
            .where(AssetModel.id == asset.id)
        )
        model = self.session.scalar(stmt)
        if model is None:
            raise NotFoundError(f"Asset id={asset.id} not found")

        model.ticker = asset.ticker
        model.name = asset.name
        model.asset_type = asset.asset_type.value
        model.arca_class = asset.arca_class.value if asset.arca_class else model.arca_class
        model.currency = asset.currency or model.currency
        model.manual_price = asset.manual_price
        model.custom_class_weight = asset.custom_class_weight
        model.use_cerrado = asset.use_cerrado
        model.checklist_profile = asset.checklist_profile.value if asset.checklist_profile else None
        _append_changed_answers(model, asset.cerrado_answers)
        model.is_active = asset.is_active
        model.notes = asset.notes
        model.purpose = asset.purpose.value

        if asset.fixed_income_term is not None:
            term = asset.fixed_income_term
            if model.fixed_income_term is None:
                model.fixed_income_term = to_fixed_income_term_model(term)
            else:
                model.fixed_income_term.instrument_kind = term.instrument_kind.value
                model.fixed_income_term.indexer = term.indexer.value
                model.fixed_income_term.contracted_rate = term.contracted_rate
                model.fixed_income_term.issue_date = term.issue_date
                model.fixed_income_term.maturity_date = term.maturity_date
                model.fixed_income_term.tax_exempt = term.tax_exempt
                model.fixed_income_term.liquidity = term.liquidity.value
                model.fixed_income_term.issuer = term.issuer
        elif model.fixed_income_term is not None:
            model.fixed_income_term = None

        self.session.flush()
        return to_asset_entity(model, include_children=False)

    def get_by_id(self, asset_id: int) -> AssetEntity | None:
        stmt = (
            select(AssetModel)
            .options(
                selectinload(AssetModel.fixed_income_term),
                selectinload(AssetModel.transactions),
                selectinload(AssetModel.earnings),
                selectinload(AssetModel.checklist_answers),
            )
            .where(AssetModel.id == asset_id)
        )
        model = self.session.scalar(stmt)
        return to_asset_entity(model, include_children=True) if model else None

    def get_by_ticker(self, ticker: str) -> AssetEntity | None:
        stmt = (
            select(AssetModel)
            .options(
                selectinload(AssetModel.fixed_income_term),
                selectinload(AssetModel.transactions),
                selectinload(AssetModel.earnings),
                selectinload(AssetModel.checklist_answers),
            )
            .where(AssetModel.ticker == ticker.strip().upper())
        )
        model = self.session.scalar(stmt)
        return to_asset_entity(model, include_children=True) if model else None

    def list_all(self, *, active_only: bool = True) -> list[AssetEntity]:
        stmt = select(AssetModel).options(
            selectinload(AssetModel.fixed_income_term),
            selectinload(AssetModel.transactions),
            selectinload(AssetModel.earnings),
            selectinload(AssetModel.checklist_answers),
        )
        if active_only:
            stmt = stmt.where(AssetModel.is_active.is_(True))
        stmt = stmt.order_by(AssetModel.ticker.asc())
        models = list(self.session.scalars(stmt).all())
        return [to_asset_entity(m, include_children=True) for m in models]

    def list_paginated(
        self,
        params: PaginationParams,
        *,
        arca_class: str | None = None,
        asset_type: str | None = None,
        use_cerrado: bool | None = None,
        active_only: bool = True,
    ) -> PaginatedResult[AssetEntity]:
        stmt = select(AssetModel).options(
            selectinload(AssetModel.fixed_income_term),
            selectinload(AssetModel.transactions),
            selectinload(AssetModel.earnings),
            selectinload(AssetModel.checklist_answers),
        )
        if active_only:
            stmt = stmt.where(AssetModel.is_active.is_(True))
        if arca_class:
            stmt = stmt.where(AssetModel.arca_class == arca_class.upper())
        if asset_type:
            stmt = stmt.where(AssetModel.asset_type == asset_type.upper())
        if use_cerrado is not None:
            stmt = stmt.where(AssetModel.use_cerrado.is_(use_cerrado))
        if params.search:
            pattern = f"%{params.search.strip()}%"
            stmt = stmt.where(or_(AssetModel.ticker.ilike(pattern), AssetModel.name.ilike(pattern)))

        rows, meta = _apply_sort_and_paginate(
            self.session, stmt, params, self.SORT_COLUMNS, AssetModel.ticker, AssetModel.id
        )
        return PaginatedResult(
            items=[to_asset_entity(m, include_children=True) for m in rows],
            meta=meta,
        )

    def delete(self, asset_id: int, *, hard: bool = False) -> bool:
        model = self.session.get(AssetModel, asset_id)
        if model is None:
            return False
        if hard:
            self.session.delete(model)
        else:
            model.is_active = False
        self.session.flush()
        return True


def _default_account_id(session: Session) -> int:
    stmt = (
        select(AccountModel.id)
        .where(AccountModel.is_active.is_(True))
        .order_by(AccountModel.id.asc())
        .limit(1)
    )
    account_id = session.scalar(stmt)
    if account_id is None:
        raise ValidationError("Create an account before recording trades", code="NO_ACCOUNT")
    return int(account_id)


class _AccountDefaultMixin:
    session: Session

    def _account_id(self, account_id: int | None) -> int:
        return account_id if account_id is not None else _default_account_id(self.session)


class SqlAlchemyTransactionRepository(_AccountDefaultMixin, AbstractTransactionRepository):
    """SQLAlchemy implementation of AbstractTransactionRepository."""

    SORT_COLUMNS = {
        "id": TransactionModel.id,
        "trade_date": TransactionModel.trade_date,
        "kind": TransactionModel.kind,
        "quantity": TransactionModel.quantity,
        "unit_price": TransactionModel.unit_price,
    }

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, transaction: TransactionEntity) -> TransactionEntity:
        model = TransactionModel(
            asset_id=transaction.asset_id,
            kind=transaction.kind.value,
            trade_date=transaction.trade_date,
            quantity=transaction.quantity,
            unit_price=transaction.unit_price,
            fees=transaction.fees,
            fx_rate=transaction.fx_rate,
            notes=transaction.notes,
            account_id=self._account_id(transaction.account_id),
        )
        self.session.add(model)
        self.session.flush()
        return to_transaction_entity(model)

    def get_by_id(self, transaction_id: int) -> TransactionEntity | None:
        model = self.session.get(TransactionModel, transaction_id)
        return to_transaction_entity(model) if model else None

    def update(self, transaction: TransactionEntity) -> TransactionEntity:
        model = self.session.get(TransactionModel, transaction.id) if transaction.id else None
        if model is None:
            raise NotFoundError(f"Transaction id={transaction.id} not found")
        model.kind = transaction.kind.value
        model.trade_date = transaction.trade_date
        model.quantity = transaction.quantity
        model.unit_price = transaction.unit_price
        model.fees = transaction.fees
        model.fx_rate = transaction.fx_rate
        model.notes = transaction.notes
        model.account_id = self._account_id(transaction.account_id)
        self.session.flush()
        return to_transaction_entity(model)

    def delete(self, transaction_id: int) -> bool:
        model = self.session.get(TransactionModel, transaction_id)
        if model is None:
            return False
        self.session.delete(model)
        self.session.flush()
        return True

    def list_for_asset(self, asset_id: int) -> list[TransactionEntity]:
        stmt = (
            select(TransactionModel)
            .where(TransactionModel.asset_id == asset_id)
            .order_by(TransactionModel.trade_date.asc(), TransactionModel.id.asc())
        )
        return [to_transaction_entity(m) for m in self.session.scalars(stmt).all()]

    def list_paginated(
        self,
        params: PaginationParams,
        *,
        asset_id: int | None = None,
        kind: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        account_id: int | None = None,
    ) -> PaginatedResult[TransactionEntity]:
        stmt = select(TransactionModel).join(AssetModel)
        if asset_id is not None:
            stmt = stmt.where(TransactionModel.asset_id == asset_id)
        if account_id is not None:
            stmt = stmt.where(TransactionModel.account_id == account_id)
        if kind:
            stmt = stmt.where(TransactionModel.kind == kind.upper())
        if date_from is not None:
            stmt = stmt.where(TransactionModel.trade_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(TransactionModel.trade_date <= date_to)
        if params.search:
            pattern = f"%{params.search.strip()}%"
            stmt = stmt.where(
                or_(
                    AssetModel.ticker.ilike(pattern),
                    AssetModel.name.ilike(pattern),
                    TransactionModel.notes.ilike(pattern),
                )
            )

        rows, meta = _apply_sort_and_paginate(
            self.session,
            stmt,
            params,
            self.SORT_COLUMNS,
            TransactionModel.trade_date,
            TransactionModel.id,
        )
        return PaginatedResult(items=[to_transaction_entity(m) for m in rows], meta=meta)


class SqlAlchemyEarningRepository(_AccountDefaultMixin, AbstractEarningRepository):
    """SQLAlchemy implementation of AbstractEarningRepository."""

    SORT_COLUMNS = {
        "id": EarningModel.id,
        "payment_date": EarningModel.payment_date,
        "kind": EarningModel.kind,
        "gross_amount": EarningModel.gross_amount,
        "net_amount": EarningModel.net_amount,
    }

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, earning: EarningEntity) -> EarningEntity:
        model = EarningModel(
            asset_id=earning.asset_id,
            kind=earning.kind.value,
            payment_date=earning.payment_date,
            ex_date=earning.ex_date,
            gross_amount=earning.gross_amount,
            withholding_tax=earning.withholding_tax,
            net_amount=earning.net_amount or (earning.gross_amount - earning.withholding_tax),
            fx_rate=earning.fx_rate,
            notes=earning.notes,
            account_id=self._account_id(earning.account_id),
        )
        self.session.add(model)
        self.session.flush()
        return to_earning_entity(model)

    def get_by_id(self, earning_id: int) -> EarningEntity | None:
        model = self.session.get(EarningModel, earning_id)
        return to_earning_entity(model) if model else None

    def update(self, earning: EarningEntity) -> EarningEntity:
        model = self.session.get(EarningModel, earning.id) if earning.id else None
        if model is None:
            raise NotFoundError(f"Earning id={earning.id} not found")
        model.kind = earning.kind.value
        model.payment_date = earning.payment_date
        model.ex_date = earning.ex_date
        model.gross_amount = earning.gross_amount
        model.withholding_tax = earning.withholding_tax
        model.net_amount = earning.net_amount or (earning.gross_amount - earning.withholding_tax)
        model.fx_rate = earning.fx_rate
        model.notes = earning.notes
        model.account_id = self._account_id(earning.account_id)
        self.session.flush()
        return to_earning_entity(model)

    def delete(self, earning_id: int) -> bool:
        model = self.session.get(EarningModel, earning_id)
        if model is None:
            return False
        self.session.delete(model)
        self.session.flush()
        return True

    def list_for_asset(self, asset_id: int) -> list[EarningEntity]:
        stmt = (
            select(EarningModel)
            .where(EarningModel.asset_id == asset_id)
            .order_by(EarningModel.payment_date.asc(), EarningModel.id.asc())
        )
        return [to_earning_entity(m) for m in self.session.scalars(stmt).all()]

    def list_paginated(
        self,
        params: PaginationParams,
        *,
        asset_id: int | None = None,
        kind: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        account_id: int | None = None,
    ) -> PaginatedResult[EarningEntity]:
        stmt = select(EarningModel).join(AssetModel)
        if asset_id is not None:
            stmt = stmt.where(EarningModel.asset_id == asset_id)
        if account_id is not None:
            stmt = stmt.where(EarningModel.account_id == account_id)
        if kind:
            stmt = stmt.where(EarningModel.kind == kind.upper())
        if date_from is not None:
            stmt = stmt.where(EarningModel.payment_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(EarningModel.payment_date <= date_to)
        if params.search:
            pattern = f"%{params.search.strip()}%"
            stmt = stmt.where(
                or_(
                    AssetModel.ticker.ilike(pattern),
                    AssetModel.name.ilike(pattern),
                    EarningModel.notes.ilike(pattern),
                )
            )

        rows, meta = _apply_sort_and_paginate(
            self.session,
            stmt,
            params,
            self.SORT_COLUMNS,
            EarningModel.payment_date,
            EarningModel.id,
        )
        return PaginatedResult(items=[to_earning_entity(m) for m in rows], meta=meta)


class SqlAlchemyPolicyRepository(AbstractPolicyRepository):
    """SQLAlchemy implementation of AbstractPolicyRepository (append-only versions)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_current(self) -> InvestmentPolicy | None:
        stmt = select(InvestmentPolicyModel).order_by(InvestmentPolicyModel.version.desc())
        model = self.session.scalars(stmt.limit(1)).first()
        return to_investment_policy(model) if model else None

    def add(self, policy: InvestmentPolicy) -> InvestmentPolicy:
        model = InvestmentPolicyModel(**policy_payload(policy))
        self.session.add(model)
        self.session.flush()
        return to_investment_policy(model)

    def list_versions(self, limit: int = 20) -> list[InvestmentPolicy]:
        stmt = (
            select(InvestmentPolicyModel)
            .order_by(InvestmentPolicyModel.version.desc())
            .limit(limit)
        )
        return [to_investment_policy(m) for m in self.session.scalars(stmt).all()]


class SqlAlchemyMarketSeriesRepository(AbstractMarketSeriesRepository):
    """SQLAlchemy implementation of AbstractMarketSeriesRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_points(
        self, symbol: str, points: list[tuple[date, float]], *, unit: SeriesUnit
    ) -> int:
        if not points:
            return 0
        normalized = symbol.strip().upper()
        dates = [ref_date for ref_date, _ in points]
        existing_rows = {
            row.reference_date: row
            for row in self.session.scalars(
                select(MarketSeriesModel).where(
                    MarketSeriesModel.symbol == normalized,
                    MarketSeriesModel.reference_date >= min(dates),
                    MarketSeriesModel.reference_date <= max(dates),
                )
            ).all()
        }
        for ref_date, value in points:
            row = existing_rows.get(ref_date)
            if row is not None:
                row.value = float(value)
                row.unit = unit.value
            else:
                row = MarketSeriesModel(
                    symbol=normalized,
                    reference_date=ref_date,
                    value=float(value),
                    unit=unit.value,
                )
                self.session.add(row)
                existing_rows[ref_date] = row
        self.session.flush()
        return len(points)

    def date_range(self, symbol: str) -> tuple[date, date] | None:
        stmt = select(
            func.min(MarketSeriesModel.reference_date),
            func.max(MarketSeriesModel.reference_date),
        ).where(MarketSeriesModel.symbol == symbol.strip().upper())
        first, last = self.session.execute(stmt).one()
        if first is None or last is None:
            return None
        return first, last

    def list_series(
        self,
        symbol: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[MarketSeriesPoint]:
        stmt = select(MarketSeriesModel).where(MarketSeriesModel.symbol == symbol.strip().upper())
        if date_from is not None:
            stmt = stmt.where(MarketSeriesModel.reference_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(MarketSeriesModel.reference_date <= date_to)
        stmt = stmt.order_by(MarketSeriesModel.reference_date.asc())
        return [to_market_series_point(m) for m in self.session.scalars(stmt).all()]


class SqlAlchemyPortfolioSnapshotRepository(AbstractPortfolioSnapshotRepository):
    """SQLAlchemy implementation of AbstractPortfolioSnapshotRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, snapshot: PortfolioSnapshotEntity) -> PortfolioSnapshotEntity:
        model = PortfolioSnapshotModel(
            snapshot_date=snapshot.snapshot_date,
            invested_value=_money(snapshot.invested_value),
            market_value=_money(snapshot.market_value),
            unrealized_pnl=_money(snapshot.unrealized_pnl),
            realized_pnl_cum=_money(snapshot.realized_pnl_cum),
            earnings_cum=_money(snapshot.earnings_cum),
            consolidated_pnl=_money(snapshot.consolidated_pnl),
            net_flow=_money(snapshot.net_flow),
            by_class=snapshot.by_class,
        )
        merged = self.session.merge(model)
        self.session.flush()
        return to_portfolio_snapshot_entity(merged)

    def list_range(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[PortfolioSnapshotEntity]:
        stmt = select(PortfolioSnapshotModel)
        if date_from is not None:
            stmt = stmt.where(PortfolioSnapshotModel.snapshot_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(PortfolioSnapshotModel.snapshot_date <= date_to)
        stmt = stmt.order_by(PortfolioSnapshotModel.snapshot_date.asc())
        return [to_portfolio_snapshot_entity(m) for m in self.session.scalars(stmt).all()]

    def latest_before(self, snapshot_date: date) -> PortfolioSnapshotEntity | None:
        stmt = (
            select(PortfolioSnapshotModel)
            .where(PortfolioSnapshotModel.snapshot_date < snapshot_date)
            .order_by(PortfolioSnapshotModel.snapshot_date.desc())
            .limit(1)
        )
        model = self.session.scalar(stmt)
        return to_portfolio_snapshot_entity(model) if model else None

    def delete_range(self, *, date_from: date | None = None, date_to: date | None = None) -> int:
        stmt = delete(PortfolioSnapshotModel)
        if date_from is not None:
            stmt = stmt.where(PortfolioSnapshotModel.snapshot_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(PortfolioSnapshotModel.snapshot_date <= date_to)
        result = self.session.execute(stmt)
        self.session.flush()
        return int(result.rowcount or 0)


class SqlAlchemyJobRunRepository(AbstractJobRunRepository):
    """SQLAlchemy implementation of AbstractJobRunRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, run: JobRunEntity) -> JobRunEntity:
        model = JobRunModel(
            job_name=run.job_name,
            status=run.status.value,
            attempts=run.attempts,
            started_at=run.started_at,
            finished_at=run.finished_at,
            details=dict(run.details),
            error=run.error,
        )
        self.session.add(model)
        self.session.flush()
        return to_job_run_entity(model)

    def update(self, run: JobRunEntity) -> JobRunEntity:
        model = self.session.get(JobRunModel, run.id) if run.id else None
        if model is None:
            raise NotFoundError(f"Job run id={run.id} not found")
        model.status = run.status.value
        model.attempts = run.attempts
        model.finished_at = run.finished_at
        model.details = dict(run.details)
        model.error = run.error
        self.session.flush()
        return to_job_run_entity(model)

    def latest_per_job(self) -> list[JobRunEntity]:
        latest = (
            select(JobRunModel.job_name, func.max(JobRunModel.id).label("max_id"))
            .group_by(JobRunModel.job_name)
            .subquery()
        )
        stmt = (
            select(JobRunModel)
            .join(latest, JobRunModel.id == latest.c.max_id)
            .order_by(JobRunModel.job_name.asc())
        )
        return [to_job_run_entity(m) for m in self.session.scalars(stmt).all()]


class SqlAlchemyAccountRepository(AbstractAccountRepository):
    """SQLAlchemy implementation of AbstractAccountRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, account: AccountEntity) -> AccountEntity:
        model = AccountModel(
            name=account.name,
            institution=account.institution,
            kind=account.kind.value,
            is_active=account.is_active,
        )
        self.session.add(model)
        self.session.flush()
        return to_account_entity(model)

    def update(self, account: AccountEntity) -> AccountEntity:
        model = self.session.get(AccountModel, account.id) if account.id else None
        if model is None:
            raise NotFoundError(f"Account id={account.id} not found")
        model.name = account.name
        model.institution = account.institution
        model.kind = account.kind.value
        model.is_active = account.is_active
        self.session.flush()
        return to_account_entity(model)

    def get_by_id(self, account_id: int) -> AccountEntity | None:
        model = self.session.get(AccountModel, account_id)
        return to_account_entity(model) if model else None

    def get_by_name(self, name: str) -> AccountEntity | None:
        model = self.session.scalar(select(AccountModel).where(AccountModel.name == name.strip()))
        return to_account_entity(model) if model else None

    def list_all(self, *, active_only: bool = False) -> list[AccountEntity]:
        stmt = select(AccountModel).order_by(AccountModel.id.asc())
        if active_only:
            stmt = stmt.where(AccountModel.is_active.is_(True))
        return [to_account_entity(m) for m in self.session.scalars(stmt).all()]

    def get_default(self) -> AccountEntity | None:
        stmt = (
            select(AccountModel)
            .where(AccountModel.is_active.is_(True))
            .order_by(AccountModel.id.asc())
            .limit(1)
        )
        model = self.session.scalar(stmt)
        return to_account_entity(model) if model else None


class SqlAlchemyFundamentalsRepository(AbstractFundamentalsRepository):
    """SQLAlchemy implementation of AbstractFundamentalsRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, snapshots: list[FundamentalSnapshot]) -> int:
        for snapshot in snapshots:
            ticker = snapshot.ticker.strip().upper()
            model = self.session.scalar(
                select(FundamentalSnapshotModel).where(
                    FundamentalSnapshotModel.ticker == ticker,
                    FundamentalSnapshotModel.reference_date == snapshot.reference_date,
                    FundamentalSnapshotModel.period == snapshot.period.value,
                )
            )
            if model is None:
                model = FundamentalSnapshotModel(
                    ticker=ticker,
                    reference_date=snapshot.reference_date,
                    period=snapshot.period.value,
                )
                self.session.add(model)
            model.metrics = dict(snapshot.metrics)
            model.source = snapshot.source
            model.fetched_at = datetime.now(UTC)
        self.session.flush()
        return len(snapshots)

    def list_for(
        self, ticker: str, *, period: FundamentalPeriod = FundamentalPeriod.ANNUAL
    ) -> list[FundamentalSnapshot]:
        return self.list_for_many([ticker], period=period).get(ticker.strip().upper(), [])

    def list_for_many(
        self, tickers: list[str], *, period: FundamentalPeriod = FundamentalPeriod.ANNUAL
    ) -> dict[str, list[FundamentalSnapshot]]:
        normalized = sorted({t.strip().upper() for t in tickers})
        if not normalized:
            return {}
        stmt = (
            select(FundamentalSnapshotModel)
            .where(
                FundamentalSnapshotModel.ticker.in_(normalized),
                FundamentalSnapshotModel.period == period.value,
            )
            .order_by(FundamentalSnapshotModel.reference_date.asc())
        )
        result: dict[str, list[FundamentalSnapshot]] = {}
        for model in self.session.scalars(stmt).all():
            result.setdefault(model.ticker, []).append(to_fundamental_snapshot(model))
        return result


class SqlAlchemyChecklistRepository(AbstractChecklistRepository):
    """SQLAlchemy implementation of AbstractChecklistRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def answer_history(self, asset_id: int) -> list[ChecklistAnswer]:
        stmt = (
            select(ChecklistAnswerModel)
            .where(ChecklistAnswerModel.asset_id == asset_id)
            .order_by(ChecklistAnswerModel.answered_at.desc(), ChecklistAnswerModel.id.desc())
        )
        return [to_checklist_answer(m) for m in self.session.scalars(stmt).all()]

    def record_evaluation(self, record: ChecklistEvaluationRecord) -> ChecklistEvaluationRecord:
        model = ChecklistEvaluationModel(
            asset_id=record.asset_id,
            evaluated_at=record.evaluated_at,
            profile=record.profile.value,
            checklist_version=record.checklist_version,
            score=record.score,
            normalized_score=record.normalized_score,
            coverage_pct=record.coverage_pct,
            answered=record.answered,
            applicable=record.applicable,
            recommendation=record.recommendation,
        )
        self.session.add(model)
        self.session.flush()
        return to_checklist_evaluation(model)

    def latest_evaluation(self, asset_id: int) -> ChecklistEvaluationRecord | None:
        history = self.evaluation_history(asset_id, limit=1)
        return history[-1] if history else None

    def evaluation_history(
        self, asset_id: int, *, limit: int = 104
    ) -> list[ChecklistEvaluationRecord]:
        stmt = (
            select(ChecklistEvaluationModel)
            .where(ChecklistEvaluationModel.asset_id == asset_id)
            .order_by(
                ChecklistEvaluationModel.evaluated_at.desc(), ChecklistEvaluationModel.id.desc()
            )
            .limit(limit)
        )
        rows = [to_checklist_evaluation(m) for m in self.session.scalars(stmt).all()]
        return rows[::-1]


class SqlAlchemyCatalogRepository(AbstractCatalogRepository):
    """SQLAlchemy implementation of AbstractCatalogRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, instruments: list[CatalogInstrument]) -> int:
        existing = {m.ticker: m for m in self.session.scalars(select(InstrumentCatalogModel))}
        for item in instruments:
            model = existing.get(item.ticker)
            if model is None:
                model = InstrumentCatalogModel(ticker=item.ticker)
                self.session.add(model)
                existing[item.ticker] = model
            model.name = item.name[:160]
            model.asset_type = item.asset_type.value if item.asset_type else None
            model.sector = item.sector[:80] if item.sector else None
            model.close = item.close
            model.change_pct = item.change_pct
            model.volume_brl = item.volume_brl
            model.market_cap = item.market_cap
            model.logo_url = item.logo_url[:255] if item.logo_url else None
            model.updated_at = item.updated_at or datetime.now(UTC)
        self.session.flush()
        return len(instruments)

    def get(self, ticker: str) -> CatalogInstrument | None:
        model = self.session.get(InstrumentCatalogModel, ticker.strip().upper())
        return to_catalog_instrument(model) if model else None

    def list_all(self) -> list[CatalogInstrument]:
        stmt = select(InstrumentCatalogModel).order_by(
            InstrumentCatalogModel.volume_brl.desc().nulls_last(),
            InstrumentCatalogModel.ticker.asc(),
        )
        return [to_catalog_instrument(m) for m in self.session.scalars(stmt).all()]


class SqlAlchemyContributionPlanRepository(AbstractContributionPlanRepository):
    """SQLAlchemy implementation of AbstractContributionPlanRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _apply(model: ContributionPlanModel, saved: SavedContributionPlan) -> None:
        model.status = saved.status.value
        model.amount_brl = Decimal(str(saved.plan.contribution_amount_brl))
        model.strategy_override = saved.strategy_override.value if saved.strategy_override else None
        model.policy_version = saved.policy_version
        model.account_id = saved.account_id
        model.payload = plan_to_payload(saved.plan)
        model.transaction_ids = list(saved.transaction_ids)
        model.confirmed_at = saved.confirmed_at
        model.discarded_at = saved.discarded_at

    def add(self, saved: SavedContributionPlan) -> SavedContributionPlan:
        model = ContributionPlanModel(created_at=saved.created_at or datetime.now(UTC))
        self._apply(model, saved)
        self.session.add(model)
        self.session.flush()
        return to_saved_contribution_plan(model)

    def update(self, saved: SavedContributionPlan) -> SavedContributionPlan:
        model = self.session.get(ContributionPlanModel, saved.id) if saved.id else None
        if model is None:
            raise NotFoundError(f"Contribution plan id={saved.id} not found")
        self._apply(model, saved)
        self.session.flush()
        return to_saved_contribution_plan(model)

    def get(self, plan_id: int) -> SavedContributionPlan | None:
        model = self.session.get(ContributionPlanModel, plan_id)
        return to_saved_contribution_plan(model) if model else None

    def list_recent(
        self, *, status: ContributionPlanStatus | None = None, limit: int = 20
    ) -> list[SavedContributionPlan]:
        stmt = select(ContributionPlanModel).order_by(ContributionPlanModel.id.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(ContributionPlanModel.status == status.value)
        return [to_saved_contribution_plan(m) for m in self.session.scalars(stmt).all()]


# Backward-compatible aliases within persistence package
AssetRepository = SqlAlchemyAssetRepository
TransactionRepository = SqlAlchemyTransactionRepository
EarningRepository = SqlAlchemyEarningRepository
PolicyRepository = SqlAlchemyPolicyRepository
MarketSeriesRepository = SqlAlchemyMarketSeriesRepository
PortfolioSnapshotRepository = SqlAlchemyPortfolioSnapshotRepository

__all__ = [
    "AssetRepository",
    "EarningRepository",
    "FixedIncomeTermModel",
    "MarketSeriesRepository",
    "PolicyRepository",
    "PortfolioSnapshotRepository",
    "SqlAlchemyAssetRepository",
    "SqlAlchemyEarningRepository",
    "SqlAlchemyMarketSeriesRepository",
    "SqlAlchemyPolicyRepository",
    "SqlAlchemyPortfolioSnapshotRepository",
    "SqlAlchemyTransactionRepository",
    "TransactionRepository",
]
