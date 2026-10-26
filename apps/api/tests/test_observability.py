"""Tests for request ids, structured logs and readiness (item 9.6)."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from fastapi.testclient import TestClient
from fincontrol_api.composition import get_database_probe
from fincontrol_api.modules.assets.dependencies import get_asset_handler
from fincontrol_config.logging import JsonFormatter, request_id_var
from fincontrol_persistence.core.health import DatabaseStatus, check_database, head_revision


def test_request_id_is_echoed_or_generated(api: SimpleNamespace) -> None:
    given = api.client.get("/api/v1/health", headers={"X-Request-ID": "abc123"})
    generated = api.client.get("/api/v1/health")

    assert given.headers["X-Request-ID"] == "abc123"
    assert len(generated.headers["X-Request-ID"]) == 32


def test_internal_error_returns_request_id(api: SimpleNamespace) -> None:
    def boom(_asset_id: int) -> None:
        raise RuntimeError("bug")

    api.app.dependency_overrides[get_asset_handler] = lambda: SimpleNamespace(get_by_id=boom)
    client = TestClient(api.app, raise_server_exceptions=False)

    resp = client.get("/api/v1/assets/1", headers={"X-Request-ID": "req-1"})

    assert resp.status_code == 500
    assert resp.json()["request_id"] == "req-1"


def test_ready_when_database_is_migrated(api: SimpleNamespace) -> None:
    body = api.client.get("/api/v1/ready").json()

    assert body["status"] == "ready"
    assert body["checks"]["migrations"]["ok"] is True
    assert body["checks"]["cache"]["detail"] == "memory"


def test_not_ready_returns_503(api: SimpleNamespace) -> None:
    api.app.dependency_overrides[get_database_probe] = lambda: (
        lambda: DatabaseStatus(False, None, head_revision(), error="OperationalError")
    )

    resp = api.client.get("/api/v1/ready")

    assert resp.status_code == 503
    assert resp.json()["checks"]["database"] == {"ok": False, "detail": "OperationalError"}


def test_check_database_reports_unreachable_database() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    broken = sessionmaker(bind=create_engine("sqlite:///file:missing?mode=ro&uri=true"))
    status = check_database(broken)
    assert not status.reachable and not status.migrated
    assert status.head_revision == head_revision()


def test_json_formatter_includes_request_id_and_extras() -> None:
    token = request_id_var.set("rid-9")
    try:
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello %s", ("w",), None)
        record.duration_ms = 12.5
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)

    assert payload["message"] == "hello w"
    assert payload["request_id"] == "rid-9"
    assert payload["duration_ms"] == 12.5
