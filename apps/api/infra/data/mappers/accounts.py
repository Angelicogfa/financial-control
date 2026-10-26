"""ORM model <-> domain entity mappers: brokers, banks and exchanges."""

from __future__ import annotations

from domain.shared.entities import (
    AccountEntity,
)
from domain.shared.enums import (
    AccountKind,
)
from infra.data.models.accounts import AccountModel


def to_account_entity(model: AccountModel) -> AccountEntity:
    return AccountEntity(
        id=model.id,
        name=model.name,
        institution=model.institution,
        kind=AccountKind(model.kind),
        is_active=bool(model.is_active),
        created_at=model.created_at,
    )
