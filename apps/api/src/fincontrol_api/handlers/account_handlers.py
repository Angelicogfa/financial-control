"""Custody account commands and queries (item 10.5)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from fincontrol_core.domain.entities import AccountEntity
from fincontrol_core.errors import ConflictError, NotFoundError, ValidationError
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork

from fincontrol_api.schemas import AccountDTO, AccountRequest

UoWFactory = Callable[[], AbstractUnitOfWork]


def to_account_dto(account: AccountEntity) -> AccountDTO:
    return AccountDTO(
        id=account.id or 0,
        name=account.name,
        institution=account.institution,
        kind=account.kind,
        is_active=account.is_active,
        created_at=account.created_at,
    )


def resolve_account_id(uow: AbstractUnitOfWork, account_id: int | None) -> int | None:
    """Validate an explicit account (None lets the repository use the default account)."""
    if account_id is None:
        return None
    account = uow.accounts.get_by_id(account_id)
    if account is None:
        raise NotFoundError(f"Account id={account_id} not found")
    if not account.is_active:
        raise ValidationError(f"Account '{account.name}' is inactive", code="INACTIVE_ACCOUNT")
    return account_id


class AccountHandler:
    """Application handler for custody accounts."""

    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def list_all(self, *, active_only: bool = False) -> list[AccountDTO]:
        with self.uow_factory() as uow:
            return [to_account_dto(a) for a in uow.accounts.list_all(active_only=active_only)]

    def create(self, req: AccountRequest) -> AccountDTO:
        with self.uow_factory() as uow:
            if any(a.name == req.name.strip() for a in uow.accounts.list_all()):
                raise ConflictError(
                    f"Account '{req.name.strip()}' already exists", code="DUPLICATE_ACCOUNT"
                )
            saved = uow.accounts.add(
                AccountEntity(
                    name=req.name,
                    institution=req.institution,
                    kind=req.kind,
                    is_active=req.is_active,
                )
            )
            uow.commit()
            return to_account_dto(saved)

    def update(self, account_id: int, req: AccountRequest) -> AccountDTO:
        with self.uow_factory() as uow:
            current = uow.accounts.get_by_id(account_id)
            if current is None:
                raise NotFoundError(f"Account id={account_id} not found")
            if not req.is_active and current.is_active:
                active = [a for a in uow.accounts.list_all(active_only=True) if a.id != account_id]
                if not active:
                    raise ValidationError(
                        "At least one account must stay active", code="LAST_ACTIVE_ACCOUNT"
                    )
            saved = uow.accounts.update(
                replace(
                    current,
                    name=req.name.strip(),
                    institution=req.institution,
                    kind=req.kind,
                    is_active=req.is_active,
                )
            )
            uow.commit()
            return to_account_dto(saved)
