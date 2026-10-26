"""SQLAlchemy repositories: versioned investment policy.

They take and return pure domain entities and never commit
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from fincontrol_core.policy.models import InvestmentPolicy
from fincontrol_core.ports.repositories import (
    AbstractPolicyRepository,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from fincontrol_persistence.mappers.policy import policy_payload, to_investment_policy
from fincontrol_persistence.models.policy import InvestmentPolicyModel


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
