"""SQLAlchemy repositories: transactions, earnings, corporate events and B3 import dedup.

They take and return pure domain entities and never commit
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from core.errors import NotFoundError, ValidationError
from core.helpers.pagination import PaginatedResult, PaginationParams
from domain.shared.entities import (
    CorporateEventEntity,
    EarningEntity,
    TransactionEntity,
)
from domain.shared.repositories import (
    AbstractCorporateEventRepository,
    AbstractEarningRepository,
    AbstractLedgerImportRepository,
    AbstractTransactionRepository,
)
from infra.data.mappers.ledger import (
    to_corporate_event,
    to_earning_entity,
    to_transaction_entity,
)
from infra.data.models.accounts import AccountModel
from infra.data.models.assets import AssetModel
from infra.data.models.ledger import CorporateEventModel, EarningModel, TransactionModel
from infra.data.repositories.common import apply_sort_and_paginate


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
            import_hash=transaction.import_hash,
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

        rows, meta = apply_sort_and_paginate(
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
            import_hash=earning.import_hash,
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

        rows, meta = apply_sort_and_paginate(
            self.session,
            stmt,
            params,
            self.SORT_COLUMNS,
            EarningModel.payment_date,
            EarningModel.id,
        )
        return PaginatedResult(items=[to_earning_entity(m) for m in rows], meta=meta)


class SqlAlchemyCorporateEventRepository(AbstractCorporateEventRepository):
    """SQLAlchemy implementation of AbstractCorporateEventRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, event: CorporateEventEntity) -> CorporateEventEntity:
        model = CorporateEventModel(
            asset_id=event.asset_id,
            kind=event.kind.value,
            ex_date=event.ex_date,
            factor=event.factor,
            unit_cost=event.unit_cost,
            notes=event.notes,
            import_hash=event.import_hash,
        )
        self.session.add(model)
        self.session.flush()
        return to_corporate_event(model)

    def get(self, event_id: int) -> CorporateEventEntity | None:
        model = self.session.get(CorporateEventModel, event_id)
        return to_corporate_event(model) if model else None

    def delete(self, event_id: int) -> bool:
        model = self.session.get(CorporateEventModel, event_id)
        if model is None:
            return False
        self.session.delete(model)
        self.session.flush()
        return True

    def list_all(self, *, asset_id: int | None = None) -> list[CorporateEventEntity]:
        stmt = select(CorporateEventModel).order_by(
            CorporateEventModel.ex_date.asc(), CorporateEventModel.id.asc()
        )
        if asset_id is not None:
            stmt = stmt.where(CorporateEventModel.asset_id == asset_id)
        return [to_corporate_event(m) for m in self.session.scalars(stmt).all()]


class SqlAlchemyLedgerImportRepository(AbstractLedgerImportRepository):
    """Looks up import hashes across trades, earnings and corporate events."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def existing_hashes(self, hashes: list[str]) -> set[str]:
        wanted = sorted(set(hashes))
        found: set[str] = set()
        for start in range(0, len(wanted), 500):
            chunk = wanted[start : start + 500]
            for column in (
                TransactionModel.import_hash,
                EarningModel.import_hash,
                CorporateEventModel.import_hash,
            ):
                found.update(self.session.scalars(select(column).where(column.in_(chunk))))
        return found
