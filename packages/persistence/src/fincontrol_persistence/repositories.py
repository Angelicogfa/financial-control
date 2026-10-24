"""Concrete SQLAlchemy implementations of AbstractRepository ports.

All repository methods accept and return pure Domain Entities from `fincontrol_core.domain.entities`
and never call `session.commit()` (transaction boundaries belong to `SqlAlchemyUnitOfWork`).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fincontrol_core.arca.allocation import InvalidTargetsError
from fincontrol_core.domain.entities import (
    ArcaTargetEntity,
    AssetEntity,
    EarningEntity,
    JobRunEntity,
    MarketSeriesPoint,
    PortfolioSnapshotEntity,
    TransactionEntity,
)
from fincontrol_core.domain.enums import ArcaClass, IntraClassStrategy, SeriesUnit
from fincontrol_core.domain.pagination import PageMeta, PaginatedResult, PaginationParams
from fincontrol_core.errors import NotFoundError, ValidationError
from fincontrol_core.ports.repositories import (
    AbstractArcaTargetRepository,
    AbstractAssetRepository,
    AbstractEarningRepository,
    AbstractJobRunRepository,
    AbstractMarketSeriesRepository,
    AbstractPortfolioSnapshotRepository,
    AbstractTransactionRepository,
)
from sqlalchemy import Select, asc, delete, desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from fincontrol_persistence.mappers import (
    to_arca_target_entity,
    to_asset_entity,
    to_earning_entity,
    to_fixed_income_term_model,
    to_job_run_entity,
    to_market_series_point,
    to_portfolio_snapshot_entity,
    to_transaction_entity,
)
from fincontrol_persistence.models import (
    ArcaTargetModel,
    AssetModel,
    EarningModel,
    FixedIncomeTermModel,
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
            cerrado_answers=asset.cerrado_answers,
            is_active=asset.is_active,
            notes=asset.notes,
        )
        if asset.fixed_income_term is not None:
            model.fixed_income_term = to_fixed_income_term_model(asset.fixed_income_term)
        self.session.add(model)
        self.session.flush()
        return to_asset_entity(model, include_children=False)

    def update(self, asset: AssetEntity) -> AssetEntity:
        if asset.id is None:
            raise ValidationError("Cannot update AssetEntity without id")
        stmt = (
            select(AssetModel)
            .options(selectinload(AssetModel.fixed_income_term))
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
        model.cerrado_answers = dict(asset.cerrado_answers)
        model.is_active = asset.is_active
        model.notes = asset.notes

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
        stmt = select(AssetModel).options(selectinload(AssetModel.fixed_income_term))
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
            items=[to_asset_entity(m, include_children=False) for m in rows],
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


class SqlAlchemyTransactionRepository(AbstractTransactionRepository):
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
    ) -> PaginatedResult[TransactionEntity]:
        stmt = select(TransactionModel).join(AssetModel)
        if asset_id is not None:
            stmt = stmt.where(TransactionModel.asset_id == asset_id)
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


class SqlAlchemyEarningRepository(AbstractEarningRepository):
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
    ) -> PaginatedResult[EarningEntity]:
        stmt = select(EarningModel).join(AssetModel)
        if asset_id is not None:
            stmt = stmt.where(EarningModel.asset_id == asset_id)
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


class SqlAlchemyArcaTargetRepository(AbstractArcaTargetRepository):
    """SQLAlchemy implementation of AbstractArcaTargetRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_all(self) -> list[ArcaTargetEntity]:
        stmt = select(ArcaTargetModel).order_by(ArcaTargetModel.arca_class.asc())
        rows = list(self.session.scalars(stmt).all())
        if not rows:
            return self.seed_defaults()
        return [to_arca_target_entity(r) for r in rows]

    def seed_defaults(self) -> list[ArcaTargetEntity]:
        rows: list[ArcaTargetModel] = []
        for arca_class in ArcaClass:
            row = ArcaTargetModel(
                arca_class=arca_class.value,
                target_pct=Decimal("25.00"),
                intra_class_strategy=IntraClassStrategy.CERRADO.value,
            )
            self.session.add(row)
            rows.append(row)
        self.session.flush()
        return [to_arca_target_entity(r) for r in rows]

    def upsert_targets(
        self,
        targets: dict[ArcaClass, Decimal],
        strategies: dict[ArcaClass, IntraClassStrategy] | None = None,
    ) -> list[ArcaTargetEntity]:
        total = sum(targets.values(), Decimal("0"))
        if abs(total - Decimal("100")) > Decimal("0.01"):
            raise InvalidTargetsError(f"ARCA target percentages must sum to 100 (got {total})")
        stmt = select(ArcaTargetModel)
        existing = {row.arca_class: row for row in self.session.scalars(stmt).all()}
        result: list[ArcaTargetModel] = []
        for arca_class, pct in targets.items():
            strategy = (
                strategies.get(arca_class, IntraClassStrategy.CERRADO)
                if strategies
                else IntraClassStrategy.CERRADO
            )
            row = existing.get(arca_class.value)
            if row is None:
                row = ArcaTargetModel(
                    arca_class=arca_class.value,
                    target_pct=pct,
                    intra_class_strategy=strategy.value,
                )
                self.session.add(row)
            else:
                row.target_pct = pct
                row.intra_class_strategy = strategy.value
            result.append(row)
        self.session.flush()
        return [to_arca_target_entity(r) for r in result]


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


# Backward-compatible aliases within persistence package
AssetRepository = SqlAlchemyAssetRepository
TransactionRepository = SqlAlchemyTransactionRepository
EarningRepository = SqlAlchemyEarningRepository
ArcaTargetRepository = SqlAlchemyArcaTargetRepository
MarketSeriesRepository = SqlAlchemyMarketSeriesRepository
PortfolioSnapshotRepository = SqlAlchemyPortfolioSnapshotRepository

__all__ = [
    "ArcaTargetRepository",
    "AssetRepository",
    "EarningRepository",
    "FixedIncomeTermModel",
    "MarketSeriesRepository",
    "PortfolioSnapshotRepository",
    "SqlAlchemyArcaTargetRepository",
    "SqlAlchemyAssetRepository",
    "SqlAlchemyEarningRepository",
    "SqlAlchemyMarketSeriesRepository",
    "SqlAlchemyPortfolioSnapshotRepository",
    "SqlAlchemyTransactionRepository",
    "TransactionRepository",
]
