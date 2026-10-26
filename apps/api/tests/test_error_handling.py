"""Unit tests for the translation of domain errors into HTTP responses (finding I-05)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from fincontrol_api.main import create_app
from fincontrol_api.modules.assets.dependencies import get_asset_handler
from fincontrol_api.modules.auth.dependencies import require_user
from fincontrol_core.arca.allocation import InvalidTargetsError
from fincontrol_core.errors import ConflictError, NotFoundError, ValidationError
from fincontrol_core.portfolio.positions import InsufficientQuantityError


def _client_raising(exc: BaseException) -> TestClient:
    def boom(_asset_id: int) -> None:
        raise exc

    app = create_app()
    app.dependency_overrides[require_user] = lambda: "tester"
    app.dependency_overrides[get_asset_handler] = lambda: SimpleNamespace(get_by_id=boom)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (NotFoundError("Asset id=1 not found"), 404, "NOT_FOUND"),
        (ValidationError("bad input"), 400, "VALIDATION_ERROR"),
        (InsufficientQuantityError("oversell"), 400, "INSUFFICIENT_QUANTITY"),
        (InvalidTargetsError("sum != 100"), 400, "INVALID_ARCA_TARGETS"),
        (ConflictError("duplicate", code="DUPLICATE_TICKER"), 409, "DUPLICATE_TICKER"),
    ],
)
def test_domain_errors_map_to_http_status_and_code(
    exc: BaseException, status: int, code: str
) -> None:
    resp = _client_raising(exc).get("/api/v1/assets/1")

    assert resp.status_code == status
    assert resp.json() == {"detail": str(exc), "code": code}


@pytest.mark.parametrize("exc", [KeyError("x"), ValueError("x"), LookupError("x")])
def test_non_domain_errors_are_internal_server_errors(exc: BaseException) -> None:
    resp = _client_raising(exc).get("/api/v1/assets/1")

    assert resp.status_code == 500
    assert resp.json()["code"] == "INTERNAL_ERROR"
