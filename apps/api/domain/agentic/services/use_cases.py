"""Use cases (command/query handlers) for the agentic configuration module.

Scope: lifecycle of personal MCP agent API keys (`fck_...`), permission scope validation,
and Bearer token resolution for the MCP server port.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import get_args

from controllers.agentic.requests import (
    AgentKeyCreateRequest,
    AgentKeyRenewRequest,
    AgentKeyUpdateRequest,
    KeyExpiryDays,
)
from controllers.agentic.responses import (
    AgentKeyCreatedDTO,
    AgentKeyDTO,
    GrantableContextDTO,
    GrantableOperationDTO,
    GrantOptionsDTO,
)
from controllers.shared.dependencies import UoWFactory
from core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from core.security import AuthenticationError
from domain.agentic.services.catalog import CONTEXT_LABELS, catalog, validate_grant
from domain.shared.entities import AgentApiKeyEntity, AgentGrant

KEY_PREFIX_TAG = "fck_"
KEY_ENTROPY_BYTES = 32
VISIBLE_PREFIX_LEN = 12
EXPIRY_OPTIONS: tuple[int, ...] = get_args(KeyExpiryDays)
DEFAULT_EXPIRY_DAYS = 90


def generate_raw_key() -> str:
    """Generate a high-entropy random agent key with the visible `fck_` prefix."""
    return f"{KEY_PREFIX_TAG}{secrets.token_urlsafe(KEY_ENTROPY_BYTES)}"


def fingerprint(raw_key: str) -> str:
    """Compute the SHA-256 hex digest stored in the database."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def expiry_from_now(days: int, *, now: datetime | None = None) -> datetime:
    """Calculate the expiration timestamp `days` from `now`."""
    if days not in EXPIRY_OPTIONS:
        raise ValidationError(
            f"Expiration days must be one of {EXPIRY_OPTIONS}",
            code="INVALID_EXPIRY_DAYS",
        )
    base = now or datetime.now(UTC)
    return base + timedelta(days=days)


def to_agent_key_dto(entity: AgentApiKeyEntity) -> AgentKeyDTO:
    """Serialize a domain `AgentApiKeyEntity` into a public `AgentKeyDTO`."""
    return AgentKeyDTO(
        id=entity.id or 0,
        name=entity.name,
        prefix=entity.prefix,
        user_id=entity.user_id,
        contexts=sorted(entity.grant.contexts),
        operations=sorted(entity.grant.operations),
        expires_at=entity.expires_at,
        last_used_at=entity.last_used_at,
        created_at=entity.created_at,
        revision=entity.revision,
    )


class AgentKeyHandler:
    """Application handler for managing personal MCP agent API keys."""

    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def options(self) -> GrantOptionsDTO:
        """Return all grantable contexts and operations for the ScopePicker UI."""
        by_context: dict[str, list[GrantableOperationDTO]] = {}
        for op in catalog():
            by_context.setdefault(op.context, []).append(
                GrantableOperationDTO(
                    name=op.name,
                    kind=op.kind,
                    description=op.description,
                    grantable=True,
                )
            )
        return GrantOptionsDTO(
            contexts=[
                GrantableContextDTO(
                    name=ctx,
                    label=CONTEXT_LABELS.get(ctx, ctx),
                    grantable=True,
                    operations=ops,
                )
                for ctx, ops in by_context.items()
            ]
        )

    def list_keys(self, user_id: str) -> list[AgentKeyDTO]:
        """List all non-revoked agent keys belonging to `user_id`."""
        with self.uow_factory() as uow:
            keys = uow.agent_keys.list_active(user_id=user_id)
            return [to_agent_key_dto(k) for k in keys]

    def get_key(self, key_id: int, user_id: str) -> AgentKeyDTO:
        """Get a single non-revoked agent key owned by `user_id`."""
        with self.uow_factory() as uow:
            entity = self._require_owned_key(uow.agent_keys.get_by_id(key_id), key_id, user_id)
            return to_agent_key_dto(entity)

    def create_key(self, user_id: str, req: AgentKeyCreateRequest) -> AgentKeyCreatedDTO:
        """Create a new personal agent key and return its cleartext value once."""
        grant = AgentGrant(
            contexts=frozenset(req.contexts),
            operations=frozenset(req.operations),
        )
        validate_grant(grant)
        raw_key = generate_raw_key()
        now = datetime.now(UTC)
        entity = AgentApiKeyEntity(
            name=req.name,
            key_hash=fingerprint(raw_key),
            prefix=raw_key[:VISIBLE_PREFIX_LEN],
            user_id=user_id,
            grant=grant,
            expires_at=expiry_from_now(req.expires_in_days, now=now),
            created_at=now,
            updated_at=now,
            revision=1,
        )
        with self.uow_factory() as uow:
            saved = uow.agent_keys.add(entity)
            uow.commit()
            dto = to_agent_key_dto(saved)
            return AgentKeyCreatedDTO(**dto.model_dump(), key=raw_key)

    def update_key(
        self, key_id: int, user_id: str, req: AgentKeyUpdateRequest
    ) -> AgentKeyDTO:
        """Update the name and permission scope of an existing personal agent key."""
        grant = AgentGrant(
            contexts=frozenset(req.contexts),
            operations=frozenset(req.operations),
        )
        validate_grant(grant)
        with self.uow_factory() as uow:
            current = self._require_owned_key(uow.agent_keys.get_by_id(key_id), key_id, user_id)
            if current.revision != req.expected_revision:
                raise ConflictError(
                    "The agent key was modified since it was loaded; reload and try again",
                    code="AGENT_KEY_STALE",
                )
            updated = uow.agent_keys.update(
                replace(
                    current,
                    name=req.name.strip(),
                    grant=grant,
                    revision=current.revision + 1,
                )
            )
            uow.commit()
            return to_agent_key_dto(updated)

    def renew_key(
        self, key_id: int, user_id: str, req: AgentKeyRenewRequest
    ) -> AgentKeyDTO:
        """Extend the expiration date of an existing personal agent key from today."""
        with self.uow_factory() as uow:
            current = self._require_owned_key(uow.agent_keys.get_by_id(key_id), key_id, user_id)
            validate_grant(current.grant)
            updated = uow.agent_keys.update(
                replace(
                    current,
                    expires_at=expiry_from_now(req.expires_in_days),
                    revision=current.revision + 1,
                )
            )
            uow.commit()
            return to_agent_key_dto(updated)

    def revoke_key(self, key_id: int, user_id: str) -> None:
        """Revoke an existing personal agent key so it can no longer authenticate."""
        with self.uow_factory() as uow:
            current = self._require_owned_key(uow.agent_keys.get_by_id(key_id), key_id, user_id)
            uow.agent_keys.update(replace(current, revoked_at=datetime.now(UTC)))
            uow.commit()

    def authenticate_bearer(self, authorization_header: str) -> AgentApiKeyEntity:
        """Resolve and validate an `Authorization: Bearer fck_...` header for MCP requests."""
        header = (authorization_header or "").strip()
        if not header.lower().startswith("bearer "):
            raise AuthenticationError("Bearer agent API key required")
        raw_key = header[7:].strip()
        if not raw_key.startswith(KEY_PREFIX_TAG):
            raise AuthenticationError("Invalid agent API key")

        expected_hash = fingerprint(raw_key)
        now = datetime.now(UTC)
        with self.uow_factory() as uow:
            entity = uow.agent_keys.get_by_hash(expected_hash)
            if entity is None or not hmac.compare_digest(entity.key_hash, expected_hash):
                raise AuthenticationError("Invalid agent API key")
            if entity.revoked_at is not None:
                raise AuthenticationError("Agent API key has been revoked")
            if entity.expires_at <= now:
                raise AuthenticationError("Agent API key has expired")
            if entity.id is not None:
                uow.agent_keys.touch_last_used(entity.id, now)
                uow.commit()
            return replace(entity, last_used_at=now)

    @staticmethod
    def _require_owned_key(
        entity: AgentApiKeyEntity | None, key_id: int, user_id: str
    ) -> AgentApiKeyEntity:
        if entity is None or entity.revoked_at is not None:
            raise NotFoundError(f"Agent API key id={key_id} not found", code="AGENT_KEY_NOT_FOUND")
        if entity.user_id != user_id:
            raise ForbiddenError(
                "Personal agent key can only be managed by its owner",
                code="PERSONAL_KEY_OWNER_ONLY",
            )
        return entity
