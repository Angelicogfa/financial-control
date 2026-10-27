"""Unit tests for API controllers, handlers, and architectural layer isolation."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from controllers.policy.requests import ArcaTargetItemDTO, ArcaTargetsUpdateRequest
from domain.policy.services.allocation import InvalidTargetsError
from domain.policy.services.use_cases import PolicyHandler
from domain.shared.enums import ArcaClass
from domain.shared.unit_of_work import AbstractUnitOfWork

API_ROOT = Path(__file__).resolve().parents[1]
ROUTERS = sorted((API_ROOT / "controllers").glob("*/router.py"))


def test_policy_handler_rejects_non_100_targets_without_committing() -> None:
    mock_uow = MagicMock(spec=AbstractUnitOfWork)
    mock_uow.__enter__.return_value = mock_uow
    mock_uow.policies = MagicMock()
    mock_uow.policies.get_current.return_value = None

    handler = PolicyHandler(uow_factory=lambda: mock_uow)
    bad_req = ArcaTargetsUpdateRequest(
        targets=[
            ArcaTargetItemDTO(arca_class=ArcaClass.ACOES, target_pct=50.0),
            ArcaTargetItemDTO(arca_class=ArcaClass.REAL_ESTATE, target_pct=20.0),
            ArcaTargetItemDTO(arca_class=ArcaClass.CAIXA, target_pct=20.0),
            ArcaTargetItemDTO(arca_class=ArcaClass.ATIVOS_INTERNACIONAIS, target_pct=20.0),
        ]
    )
    with pytest.raises(InvalidTargetsError):
        handler.update_arca_targets(bad_req)
    mock_uow.commit.assert_not_called()


def test_every_feature_router_is_checked() -> None:
    assert len(ROUTERS) == 13


@pytest.mark.parametrize("router_path", ROUTERS, ids=lambda p: p.parent.name)
def test_controllers_strictly_isolated_from_orm_and_repositories(router_path: Path) -> None:
    """Rule #8: Controllers MUST NEVER import SQLAlchemy sessions, ORM models, or Repositories."""
    tree = ast.parse(router_path.read_text(encoding="utf-8"))

    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.add(node.module)
            for alias in node.names:
                imported_names.add(alias.name)

    forbidden = {
        "sqlalchemy",
        "infra.data",
        "Session",
        "AssetModel",
        "TransactionModel",
        "EarningModel",
        "ArcaTargetModel",
        "AgentApiKeyModel",
        "SqlAlchemyAssetRepository",
        "SqlAlchemyTransactionRepository",
        "SqlAlchemyEarningRepository",
        "SqlAlchemyAgentKeyRepository",
        "SqlAlchemyUnitOfWork",
        "uow_factory",
    }
    violations = {
        imp
        for imp in imported_names
        if imp in forbidden or any(imp.startswith(f"{f}.") for f in forbidden)
    }
    assert not violations, f"Controller layer isolation violated in {router_path}: {violations}"
