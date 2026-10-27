"""SQLAlchemy repository: MCP agent API keys.

Takes and returns pure domain entities and never commits
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import NotFoundError
from domain.shared.entities import AgentApiKeyEntity
from domain.shared.repositories import AbstractAgentKeyRepository
from infra.data.mappers.agent_keys import to_agent_key_entity
from infra.data.models.agent_keys import AgentApiKeyModel
from infra.data.models.common import utc_now


class SqlAlchemyAgentKeyRepository(AbstractAgentKeyRepository):
    """SQLAlchemy implementation of AbstractAgentKeyRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, key: AgentApiKeyEntity) -> AgentApiKeyEntity:
        now = utc_now()
        model = AgentApiKeyModel(
            name=key.name,
            key_hash=key.key_hash,
            prefix=key.prefix,
            user_id=key.user_id,
            grant_scope=key.grant.to_dict(),
            expires_at=key.expires_at,
            last_used_at=key.last_used_at,
            revoked_at=key.revoked_at,
            revision=key.revision,
            created_at=key.created_at or now,
            updated_at=key.updated_at or now,
        )
        self.session.add(model)
        self.session.flush()
        return to_agent_key_entity(model)

    def update(self, key: AgentApiKeyEntity) -> AgentApiKeyEntity:
        model = self.session.get(AgentApiKeyModel, key.id) if key.id else None
        if model is None:
            raise NotFoundError(f"Agent API key id={key.id} not found")
        model.name = key.name
        model.grant_scope = key.grant.to_dict()
        model.expires_at = key.expires_at
        model.last_used_at = key.last_used_at
        model.revoked_at = key.revoked_at
        model.revision = key.revision
        model.updated_at = utc_now()
        self.session.flush()
        return to_agent_key_entity(model)

    def get_by_id(self, key_id: int) -> AgentApiKeyEntity | None:
        model = self.session.get(AgentApiKeyModel, key_id)
        return to_agent_key_entity(model) if model else None

    def get_by_hash(self, key_hash: str) -> AgentApiKeyEntity | None:
        stmt = select(AgentApiKeyModel).where(AgentApiKeyModel.key_hash == key_hash)
        model = self.session.scalar(stmt)
        return to_agent_key_entity(model) if model else None

    def list_active(self, *, user_id: str | None = None) -> list[AgentApiKeyEntity]:
        stmt = (
            select(AgentApiKeyModel)
            .where(AgentApiKeyModel.revoked_at.is_(None))
            .order_by(AgentApiKeyModel.created_at.desc(), AgentApiKeyModel.id.desc())
        )
        if user_id is not None:
            stmt = stmt.where(AgentApiKeyModel.user_id == user_id)
        return [to_agent_key_entity(m) for m in self.session.scalars(stmt).all()]

    def touch_last_used(self, key_id: int, used_at: datetime) -> None:
        model = self.session.get(AgentApiKeyModel, key_id)
        if model is not None:
            model.last_used_at = used_at
            self.session.flush()
