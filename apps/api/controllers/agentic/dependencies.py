"""FastAPI dependency providers for the agentic configuration module.

Scope: personal MCP agent API keys and scoped tool execution.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from controllers.portfolio.dependencies import get_portfolio_service
from controllers.shared.dependencies import UoWFactory
from domain.agentic.services.catalog import AgenticRuntimeHandlers
from domain.agentic.services.use_cases import AgentKeyHandler
from domain.portfolio.services.service import PortfolioApplicationService


def get_agent_key_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> AgentKeyHandler:
    """Provide the AgentKeyHandler instance."""
    return AgentKeyHandler(uow_factory=uow_factory)


def get_agentic_runtime_handlers(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> AgenticRuntimeHandlers:
    """Provide the bundle of domain handlers used by MCP tool executions."""
    return AgenticRuntimeHandlers(
        uow_factory=uow_factory,
        portfolio_service=portfolio_service,
    )
