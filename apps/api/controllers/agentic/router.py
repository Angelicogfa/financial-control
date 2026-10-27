"""HTTP controllers (routers) of the agentic module; they only delegate to use cases.

Scope: management of personal MCP agent API keys and grantable operation options.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from controllers.agentic.dependencies import get_agent_key_handler
from controllers.agentic.requests import (
    AgentKeyCreateRequest,
    AgentKeyRenewRequest,
    AgentKeyUpdateRequest,
)
from controllers.agentic.responses import (
    AgentKeyCreatedDTO,
    AgentKeyDTO,
    GrantOptionsDTO,
)
from controllers.auth.dependencies import require_user
from domain.agentic.services.use_cases import AgentKeyHandler

agentic_router = APIRouter(prefix="/agents/keys", tags=["Agentic & MCP"])


@agentic_router.get("/options", response_model=GrantOptionsDTO)
def get_agent_key_options(
    _user: str = Depends(require_user),
    handler: AgentKeyHandler = Depends(get_agent_key_handler),
) -> GrantOptionsDTO:
    return handler.options()


@agentic_router.get("", response_model=list[AgentKeyDTO])
def list_agent_keys(
    user: str = Depends(require_user),
    handler: AgentKeyHandler = Depends(get_agent_key_handler),
) -> list[AgentKeyDTO]:
    return handler.list_keys(user_id=user)


@agentic_router.post(
    "", response_model=AgentKeyCreatedDTO, status_code=status.HTTP_201_CREATED
)
def create_agent_key(
    payload: AgentKeyCreateRequest,
    user: str = Depends(require_user),
    handler: AgentKeyHandler = Depends(get_agent_key_handler),
) -> AgentKeyCreatedDTO:
    return handler.create_key(user_id=user, req=payload)


@agentic_router.get("/{key_id}", response_model=AgentKeyDTO)
def get_agent_key(
    key_id: int,
    user: str = Depends(require_user),
    handler: AgentKeyHandler = Depends(get_agent_key_handler),
) -> AgentKeyDTO:
    return handler.get_key(key_id=key_id, user_id=user)


@agentic_router.put("/{key_id}", response_model=AgentKeyDTO)
def update_agent_key(
    key_id: int,
    payload: AgentKeyUpdateRequest,
    user: str = Depends(require_user),
    handler: AgentKeyHandler = Depends(get_agent_key_handler),
) -> AgentKeyDTO:
    return handler.update_key(key_id=key_id, user_id=user, req=payload)


@agentic_router.post("/{key_id}/renew", response_model=AgentKeyDTO)
def renew_agent_key(
    key_id: int,
    payload: AgentKeyRenewRequest,
    user: str = Depends(require_user),
    handler: AgentKeyHandler = Depends(get_agent_key_handler),
) -> AgentKeyDTO:
    return handler.renew_key(key_id=key_id, user_id=user, req=payload)


@agentic_router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_agent_key(
    key_id: int,
    user: str = Depends(require_user),
    handler: AgentKeyHandler = Depends(get_agent_key_handler),
) -> Response:
    handler.revoke_key(key_id=key_id, user_id=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
