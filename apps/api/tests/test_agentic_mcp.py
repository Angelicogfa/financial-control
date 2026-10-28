"""Unit and integration tests for Agentic Configuration & MCP Server (`fck_` keys and tools)."""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx2
import pytest
from alembic import command
from alembic.config import Config
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from sqlalchemy import create_engine, inspect

from controllers.agentic.requests import (
    AgentKeyCreateRequest,
    AgentKeyRenewRequest,
    AgentKeyUpdateRequest,
)
from core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from core.security import AuthenticationError
from domain.agentic.services.catalog import (
    CATALOG_BY_NAME,
    KNOWN_CONTEXTS,
    KNOWN_OPERATIONS,
    catalog,
    validate_grant,
)
from domain.agentic.services.use_cases import (
    KEY_PREFIX_TAG,
    VISIBLE_PREFIX_LEN,
    AgentKeyHandler,
    expiry_from_now,
    fingerprint,
    generate_raw_key,
)
from domain.shared.entities import AgentApiKeyEntity, AgentGrant, context_of
from infra.data import Base, SqlAlchemyUnitOfWork, build_engine, build_session_factory
from infra.mcp.server import INSTRUCTIONS

PERSISTENCE_DIR = Path(__file__).resolve().parents[1]

_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "0.1.0"},
    },
}
_ACCEPT_HEADERS = {"Accept": "application/json, text/event-stream"}
_CITED_TOOL = re.compile(r"`([a-z_]+(?:\.[a-z_]+){1,2})`")


# ---------------------------------------------------------------------------
# 1. Pure Domain & Catalog Unit Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_agent_grant_allows_context_module_and_explicit_operation() -> None:
    grant = AgentGrant(
        contexts=frozenset({"portfolio", "ledger.trades"}),
        operations=frozenset({"assets.get"}),
    )
    assert grant.allows("portfolio.report") is True
    assert grant.allows("portfolio.analytics") is True
    assert grant.allows("ledger.trades.create") is True
    assert grant.allows("ledger.earnings.list") is False
    assert grant.allows("assets.get") is True
    assert grant.allows("assets.create") is False

    # Round-trip serialization
    restored = AgentGrant.from_dict(grant.to_dict())
    assert restored == grant
    assert AgentGrant.from_dict(None) == AgentGrant()


@pytest.mark.unit
def test_agent_key_entity_validates_name_and_activity() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="cannot be empty"):
        AgentApiKeyEntity(
            name="   ",
            key_hash="h" * 64,
            prefix="fck_12345678",
            user_id="owner",
            expires_at=now + timedelta(days=30),
        )

    entity = AgentApiKeyEntity(
        name="  Claude Desktop  ",
        key_hash="h" * 64,
        prefix="fck_12345678",
        user_id="owner",
        expires_at=now + timedelta(days=30),
    )
    assert entity.name == "Claude Desktop"
    assert entity.is_active(now) is True
    assert entity.is_active(now + timedelta(days=31)) is False
    revoked = replace(entity, revoked_at=now)
    assert revoked.is_active(now) is False


@pytest.mark.unit
def test_catalog_completeness_and_grant_validation() -> None:
    ops = catalog()
    assert len(ops) >= 35
    assert "portfolio.report" in KNOWN_OPERATIONS
    assert "assets.create" in KNOWN_OPERATIONS
    assert "contributions.confirm" in KNOWN_OPERATIONS
    assert "ledger.trades.create" in KNOWN_OPERATIONS
    assert "ledger.earnings.create" in KNOWN_OPERATIONS
    assert "ledger.events.create" in KNOWN_OPERATIONS
    assert "ledger.imports.commit" in KNOWN_OPERATIONS
    assert "research.screener" in KNOWN_OPERATIONS
    assert "policy.update" in KNOWN_OPERATIONS
    assert "accounts.create" in KNOWN_OPERATIONS
    assert "alerts.dismiss" in KNOWN_OPERATIONS
    assert "market.series_status" in KNOWN_OPERATIONS

    # Every tool cited in INSTRUCTIONS must exist in CATALOG_BY_NAME
    cited = {
        m
        for m in _CITED_TOOL.findall(INSTRUCTIONS)
        if not m.endswith(".*") and context_of(m) in KNOWN_CONTEXTS
    }
    assert cited
    assert cited - set(CATALOG_BY_NAME) == set()

    with pytest.raises(ValidationError) as exc_empty:
        validate_grant(AgentGrant())
    assert exc_empty.value.code == "EMPTY_AGENT_GRANT"

    with pytest.raises(ValidationError) as exc_ctx:
        validate_grant(AgentGrant(contexts=frozenset({"nonexistent"})))
    assert exc_ctx.value.code == "UNKNOWN_AGENT_CONTEXT"

    with pytest.raises(ValidationError) as exc_op:
        validate_grant(AgentGrant(operations=frozenset({"assets.nonexistent"})))
    assert exc_op.value.code == "UNKNOWN_AGENT_OPERATION"


@pytest.mark.unit
def test_key_generation_and_expiry_helpers() -> None:
    raw = generate_raw_key()
    assert raw.startswith(KEY_PREFIX_TAG)
    assert len(raw[:VISIBLE_PREFIX_LEN]) == VISIBLE_PREFIX_LEN
    assert len(fingerprint(raw)) == 64

    now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    assert expiry_from_now(30, now=now) == now + timedelta(days=30)
    with pytest.raises(ValidationError) as exc:
        expiry_from_now(45, now=now)
    assert exc.value.code == "INVALID_EXPIRY_DAYS"


# ---------------------------------------------------------------------------
# 2. Persistence & Migration (`script_00016`) Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_script_00016_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    db_url = f"sqlite:///{(tmp_path / 'mig16.db').as_posix()}"
    cfg = Config(str(PERSISTENCE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(PERSISTENCE_DIR / "infra" / "data" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    engine = create_engine(db_url, future=True)

    command.upgrade(cfg, "script_00015")
    assert "agent_api_keys" not in inspect(engine).get_table_names()

    command.upgrade(cfg, "script_00016")
    assert "agent_api_keys" in inspect(engine).get_table_names()

    command.downgrade(cfg, "script_00015")
    assert "agent_api_keys" not in inspect(engine).get_table_names()
    engine.dispose()


@pytest.mark.unit
def test_agent_key_repository_and_handler_lifecycle() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    uow_factory = lambda: SqlAlchemyUnitOfWork(session_factory)  # noqa: E731
    handler = AgentKeyHandler(uow_factory=uow_factory)

    options = handler.options()
    assert len(options.contexts) == len(KNOWN_CONTEXTS)

    created = handler.create_key(
        user_id="owner",
        req=AgentKeyCreateRequest(
            name="Cursor Agent",
            contexts=["portfolio"],
            operations=["assets.list"],
            expires_in_days=90,
        ),
    )
    assert created.key.startswith(KEY_PREFIX_TAG)
    assert created.prefix == created.key[:VISIBLE_PREFIX_LEN]
    assert created.contexts == ["portfolio"]
    assert created.operations == ["assets.list"]
    assert created.revision == 1

    # Authenticate with Bearer token
    authed = handler.authenticate_bearer(f"Bearer {created.key}")
    assert authed.id == created.id
    assert authed.last_used_at is not None

    # Update name and scope
    updated = handler.update_key(
        created.id,
        "owner",
        AgentKeyUpdateRequest(
            name="Cursor IDE",
            contexts=["portfolio", "accounts"],
            operations=[],
            expected_revision=1,
        ),
    )
    assert updated.name == "Cursor IDE"
    assert updated.contexts == ["accounts", "portfolio"]
    assert updated.revision == 2

    # Stale revision raises ConflictError
    with pytest.raises(ConflictError) as stale_exc:
        handler.update_key(
            created.id,
            "owner",
            AgentKeyUpdateRequest(
                name="Outdated",
                contexts=["portfolio"],
                operations=[],
                expected_revision=1,
            ),
        )
    assert stale_exc.value.code == "AGENT_KEY_STALE"

    # Another user cannot manage owner's personal key
    with pytest.raises(ForbiddenError) as forbidden_exc:
        handler.get_key(created.id, "other-user")
    assert forbidden_exc.value.code == "PERSONAL_KEY_OWNER_ONLY"

    # Renew key
    renewed = handler.renew_key(created.id, "owner", AgentKeyRenewRequest(expires_in_days=180))
    assert renewed.revision == 3
    assert renewed.expires_at > created.expires_at

    # Revoke key
    handler.revoke_key(created.id, "owner")
    assert handler.list_keys("owner") == []
    with pytest.raises(NotFoundError):
        handler.get_key(created.id, "owner")
    with pytest.raises(AuthenticationError):
        handler.authenticate_bearer(f"Bearer {created.key}")


# ---------------------------------------------------------------------------
# 3. REST API Endpoints (`/api/v1/agents/keys`) Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_agent_keys_rest_api_flow(api: SimpleNamespace) -> None:
    client = api.client

    opts_resp = client.get("/api/v1/agents/keys/options")
    assert opts_resp.status_code == 200
    opts = opts_resp.json()
    ctx_names = {c["name"] for c in opts["contexts"]}
    assert {"portfolio", "assets", "contributions", "ledger.trades", "accounts"} <= ctx_names

    create_resp = client.post(
        "/api/v1/agents/keys",
        json={
            "name": "Claude Desktop",
            "contexts": ["portfolio", "accounts"],
            "operations": ["assets.list"],
            "expires_in_days": 30,
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["key"].startswith("fck_")
    key_id = created["id"]

    # List keys never exposes the secret `key`
    list_resp = client.get("/api/v1/agents/keys")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert "key" not in items[0]
    assert items[0]["prefix"] == created["prefix"]

    # Get single key
    get_resp = client.get(f"/api/v1/agents/keys/{key_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Claude Desktop"

    # Update key
    put_resp = client.put(
        f"/api/v1/agents/keys/{key_id}",
        json={
            "name": "Claude Desktop Pro",
            "contexts": ["portfolio"],
            "operations": ["assets.list", "assets.get"],
            "expected_revision": 1,
        },
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["name"] == "Claude Desktop Pro"
    assert put_resp.json()["revision"] == 2

    # Renew key
    renew_resp = client.post(
        f"/api/v1/agents/keys/{key_id}/renew",
        json={"expires_in_days": 365},
    )
    assert renew_resp.status_code == 200
    assert renew_resp.json()["revision"] == 3

    # Revoke key
    del_resp = client.delete(f"/api/v1/agents/keys/{key_id}")
    assert del_resp.status_code == 204
    assert client.get("/api/v1/agents/keys").json() == []


# ---------------------------------------------------------------------------
# 4. MCP Server ASGI Port (`/api/v1/mcp`) End-to-End Protocol Tests
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _mcp_client(app, raw_key: str):
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    url = "http://testserver/api/v1/mcp"
    async with http, Client(streamable_http_client(url, http_client=http)) as client:
        yield client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_port_authentication_and_origin_guards(api: SimpleNamespace) -> None:
    created = api.client.post(
        "/api/v1/agents/keys",
        json={
            "name": "Guard Test Key",
            "contexts": ["portfolio"],
            "operations": [],
            "expires_in_days": 30,
        },
    ).json()
    raw_key = created["key"]

    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=api.app)) as http:
        # 1. Missing Authorization header -> 401
        r_no_auth = await http.post(
            "http://testserver/api/v1/mcp",
            json=_INITIALIZE,
            headers=_ACCEPT_HEADERS,
        )
        assert r_no_auth.status_code == 401
        assert r_no_auth.headers["www-authenticate"] == "Bearer"

        # 2. Invalid Bearer key -> 401
        r_bad_key = await http.post(
            "http://testserver/api/v1/mcp",
            json=_INITIALIZE,
            headers={**_ACCEPT_HEADERS, "Authorization": "Bearer fck_invalid_secret_key"},
        )
        assert r_bad_key.status_code == 401

        # 3. Foreign browser Origin -> 403
        r_bad_origin = await http.post(
            "http://testserver/api/v1/mcp",
            json=_INITIALIZE,
            headers={
                **_ACCEPT_HEADERS,
                "Authorization": f"Bearer {raw_key}",
                "Origin": "https://malicious.example.com",
            },
        )
        assert r_bad_origin.status_code == 403

        # 4. Valid key + valid same-origin -> 200 with INSTRUCTIONS
        r_ok = await http.post(
            "http://testserver/api/v1/mcp",
            json=_INITIALIZE,
            headers={
                **_ACCEPT_HEADERS,
                "Authorization": f"Bearer {raw_key}",
                "Origin": "http://testserver",
            },
        )
        assert r_ok.status_code == 200
        assert r_ok.json()["result"]["instructions"] == INSTRUCTIONS


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_tools_list_call_scoping_and_idempotency(api: SimpleNamespace) -> None:
    created = api.client.post(
        "/api/v1/agents/keys",
        json={
            "name": "Scoped Portfolio & Accounts Agent",
            "contexts": ["accounts", "portfolio"],
            "operations": ["assets.create", "assets.list"],
            "expires_in_days": 90,
        },
    ).json()
    raw_key = created["key"]

    async with _mcp_client(api.app, raw_key) as client:
        # 1. tools/list returns only granted operations
        listed = (await client.list_tools()).tools
        tool_map = {t.name: t for t in listed}
        assert {
            "accounts.list",
            "accounts.create",
            "accounts.update",
            "portfolio.report",
            "portfolio.analytics",
            "portfolio.snapshots",
            "portfolio.health",
            "portfolio.treasury_market",
            "portfolio.earnings_agenda",
            "assets.create",
            "assets.list",
        } == set(tool_map)
        assert "assets.archive" not in tool_map
        assert "policy.update" not in tool_map

        # Command tools advertise idempotency_key; query tools set read_only_hint
        assert "idempotency_key" in tool_map["accounts.create"].input_schema["properties"]
        assert "idempotency_key" not in tool_map["accounts.list"].input_schema.get("properties", {})
        assert tool_map["accounts.list"].annotations.read_only_hint is True

        # 2. Calling an operation outside the key's grant returns GRANT_NOT_ALLOWED
        denied = await client.call_tool("policy.get", {})
        assert denied.is_error is True
        assert json.loads(denied.content[0].text)["code"] == "GRANT_NOT_ALLOWED"

        # 3. Calling an unknown tool raises protocol MCPError
        with pytest.raises(MCPError):
            await client.call_tool("unknown.tool.name", {})

        # 4. Calling a tool with invalid schema returns INPUT_INVALID
        invalid = await client.call_tool("accounts.create", {"name": ""})
        assert invalid.is_error is True
        assert json.loads(invalid.content[0].text)["code"] == "INPUT_INVALID"

        # 5. Execute command with idempotency_key: creates account once
        acc_res = await client.call_tool(
            "accounts.create",
            {
                "name": "BTG Pactual",
                "institution": "BTG",
                "kind": "BROKER",
                "idempotency_key": "idem-acc-1",
            },
        )
        assert acc_res.is_error is False
        acc_payload = json.loads(acc_res.content[0].text)
        assert acc_payload["name"] == "BTG Pactual"

        # Repeating with the same idempotency_key and same input returns cached result
        acc_retry = await client.call_tool(
            "accounts.create",
            {
                "name": "BTG Pactual",
                "institution": "BTG",
                "kind": "BROKER",
                "idempotency_key": "idem-acc-1",
            },
        )
        assert acc_retry.is_error is False
        assert json.loads(acc_retry.content[0].text)["id"] == acc_payload["id"]

        # Repeating with the same idempotency_key and different input returns IDEMPOTENCY_CONFLICT
        acc_conflict = await client.call_tool(
            "accounts.create",
            {
                "name": "XP Investimentos",
                "institution": "XP",
                "kind": "BROKER",
                "idempotency_key": "idem-acc-1",
            },
        )
        assert acc_conflict.is_error is True
        assert json.loads(acc_conflict.content[0].text)["code"] == "IDEMPOTENCY_CONFLICT"

        # 6. Execute query tools (`accounts.list`, `portfolio.report`)
        list_acc = await client.call_tool("accounts.list", {"active_only": True})
        assert list_acc.is_error is False
        accounts = json.loads(list_acc.content[0].text)
        assert any(a["name"] == "BTG Pactual" for a in accounts)
        assert list_acc.structured_content == {"result": accounts}

        report_res = await client.call_tool("portfolio.report", {})
        assert report_res.is_error is False
        report = json.loads(report_res.content[0].text)
        assert "total_current_value_brl" in report
        assert len(report["allocations"]) == 4

    # 7. Verify `last_used_at` was recorded on the key
    key_meta = api.client.get(f"/api/v1/agents/keys/{created['id']}").json()
    assert key_meta["last_used_at"] is not None
