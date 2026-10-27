"""ORM model <-> domain entity mappers: MCP agent API keys."""

from __future__ import annotations

from datetime import UTC, datetime

from domain.shared.entities import AgentApiKeyEntity, AgentGrant
from infra.data.models.agent_keys import AgentApiKeyModel


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def to_agent_key_entity(model: AgentApiKeyModel) -> AgentApiKeyEntity:
    expires_at = _ensure_utc(model.expires_at)
    assert expires_at is not None
    return AgentApiKeyEntity(
        id=model.id,
        name=model.name,
        key_hash=model.key_hash,
        prefix=model.prefix,
        user_id=model.user_id,
        grant=AgentGrant.from_dict(model.grant_scope),
        expires_at=expires_at,
        last_used_at=_ensure_utc(model.last_used_at),
        revoked_at=_ensure_utc(model.revoked_at),
        revision=model.revision,
        created_at=_ensure_utc(model.created_at),
        updated_at=_ensure_utc(model.updated_at),
    )
