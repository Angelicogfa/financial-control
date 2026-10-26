"""SQLAlchemy repositories: brokers, banks and exchanges.

They take and return pure domain entities and never commit
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import NotFoundError
from domain.shared.entities import (
    AccountEntity,
)
from domain.shared.repositories import (
    AbstractAccountRepository,
)
from infra.data.mappers.accounts import to_account_entity
from infra.data.models.accounts import AccountModel


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
