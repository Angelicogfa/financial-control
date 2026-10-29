"""MCP ASGI server port exposing Financial Control catalog operations as agent tools.

Follows the same architecture as `dynamic-research/apps/api/app/ports/mcp_server.py`,
adapted for Financial Control's single-user personal portfolio model:
1. Origin check against DNS rebinding.
2. Personal `fck_...` Bearer key authentication on every request.
3. Scoped `tools/list` returning only operations reachable by the key's `AgentGrant`.
4. `tools/call` with Pydantic input validation, command idempotency, structured output,
   and domain error translation (`isError=True`).
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import types as pytypes
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from composition import get_market_gateway, get_uow_factory
from controllers.portfolio.dependencies import get_portfolio_service
from controllers.shared.dependencies import UoWFactory
from core.errors import ConflictError, DomainError
from core.http_errors import error_body
from core.security import AuthenticationError
from core.settings import get_settings
from domain.agentic.services.catalog import (
    CATALOG_BY_NAME,
    AgenticRuntimeHandlers,
    OperationSpec,
    catalog,
    reaches,
)
from domain.agentic.services.use_cases import AgentKeyHandler
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.entities import AgentApiKeyEntity

logger = logging.getLogger("fincontrol_api")

SERVER_NAME = "financial-control"
_STATE_KEY = "mcp_agent_key"
IDEMPOTENCY_ARGUMENT = "idempotency_key"
_MAX_IDEMPOTENCY_ENTRIES = 512

INSTRUCTIONS = """\
Cada ferramenta corresponde a uma operação da plataforma Financial Control, com o mesmo nome \
e as mesmas regras de negócio da interface web. Você enxerga em `tools/list` apenas as \
operações concedidas a esta chave; chamar uma operação fora do escopo retorna erro com código \
`GRANT_NOT_ALLOWED`.

Visão Geral e Carteira:
- Chame `portfolio.report` para consultar posições atuais, preços, rentabilidade, alocação nos \
quatro quadrantes ARCA (Ações, Real Estate, Caixa, Ativos Internacionais) e desvios das bandas.
- Use `portfolio.analytics` para métricas de risco e retorno (TWR, CAGR, Sharpe, Sortino, \
drawdown e comparação com CDI, IPCA e IBOV) e `portfolio.snapshots` para a evolução diária.

Ativos e Análise Fundamentalista:
- Use `assets.list` para buscar ativos cadastrados e `assets.get` para detalhes de um ativo.
- Chame `assets.analysis` para ver múltiplos fundamentalistas históricos, valuation (Graham, \
Bazin, P/VP) e avaliação do Diagrama do Cerrado; `assets.prices` dá os fechamentos de 6 \
meses, 1, 2 ou 5 anos, ou de todo o histórico.
- Use `assets.create`, `assets.update`, `assets.checklist` e `assets.archive` para gerenciar o \
cadastro e o checklist fundamentalista.

Aportes e Rebalanceamento:
- Use `contributions.simulate` para simular como distribuir um novo aporte em R$ respeitando as \
bandas ARCA.
- Para salvar e efetivar um aporte, use `contributions.draft` seguido de `contributions.confirm`.

Lançamentos (Ledger) e Extrato B3:
- Negociações de compra/venda: `ledger.trades.list`, `ledger.trades.get`, `ledger.trades.create`, \
`ledger.trades.update`, `ledger.trades.delete`.
- Proventos (dividendos, JCP, rendimentos): `ledger.earnings.list`, `ledger.earnings.get`, \
`ledger.earnings.create`, `ledger.earnings.update`, `ledger.earnings.delete`.
- Eventos corporativos (desdobramentos, grupamentos, bonificações): `ledger.events.list`, \
`ledger.events.create`, `ledger.events.delete`.
- Importação de extrato B3: envie o conteúdo para `ledger.imports.preview` antes de confirmar \
com `ledger.imports.commit`.

Pesquisa B3, Estratégia, Contas e Alertas:
- Screener e Watchlist B3: `research.screener`, `research.watchlist`, `research.follow`, \
`research.classify`, `research.unfollow`.
- Política de investimentos e metas ARCA: `policy.get`, `policy.update`, `policy.versions`, \
`policy.get_arca_targets`, `policy.update_arca_targets`.
- Contas de custódia e alertas: `accounts.list`, `accounts.create`, `accounts.update`, \
`alerts.list`, `alerts.dismiss`, `alerts.restore`.

Tributação:
- `assets.tax_status` mostra a faixa de IR de cada lote de renda fixa, a data da próxima queda \
e o IR estimado resgatando hoje × na próxima faixa; para renda variável, o regime do tipo.
- `tools.fixed_income_compare` compara títulos tributados e isentos (valor e taxa líquidos, \
taxas equivalentes por faixa, ponto de empate); `tools.tax_rules` lista as alíquotas com vigência.

Repetição segura (Idempotência):
- Ferramentas de comando aceitam `idempotency_key` opcional. Após um timeout de rede, repita \
com a mesma `idempotency_key` e a mesma entrada para receber o resultado já gravado sem \
duplicar lançamentos.\
"""


@dataclass(frozen=True)
class ToolEntry:
    """An operation specification adapted into an MCP `types.Tool` definition."""

    spec: OperationSpec
    tool: types.Tool
    input_adapter: TypeAdapter[Any]
    output_adapter: TypeAdapter[Any] | None
    wraps_output: bool


def _is_object_schema(schema: dict[str, Any]) -> bool:
    return schema.get("type") == "object"


def _wrap_output_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Wrap non-object schemas (such as lists) in `{"result": ...}` keeping `$defs` at root."""
    body = dict(schema)
    defs = body.pop("$defs", None)
    wrapped: dict[str, Any] = {
        "type": "object",
        "properties": {"result": body},
        "required": ["result"],
    }
    if defs:
        wrapped["$defs"] = defs
    return wrapped


def build_tool_entry(spec: OperationSpec) -> ToolEntry:
    """Build an MCP `ToolEntry` from an `OperationSpec`."""
    input_adapter: TypeAdapter[Any] = TypeAdapter(spec.input_model)
    input_schema = copy.deepcopy(input_adapter.json_schema())
    if spec.kind == "command":
        input_schema.setdefault("properties", {})[IDEMPOTENCY_ARGUMENT] = {
            "type": "string",
            "maxLength": 200,
            "description": (
                "Opcional. A mesma chave com a mesma entrada devolve o resultado já gravado, "
                "sem executar de novo; com entrada diferente, é recusada."
            ),
        }

    no_output = spec.output_type is None or spec.output_type is pytypes.NoneType
    if no_output:
        output_adapter = None
        output_schema = None
        wraps = False
    else:
        output_adapter = TypeAdapter(spec.output_type)
        raw_out_schema = output_adapter.json_schema()
        wraps = not _is_object_schema(raw_out_schema)
        output_schema = _wrap_output_schema(raw_out_schema) if wraps else raw_out_schema

    read_only = spec.kind == "query"
    tool = types.Tool(
        name=spec.name,
        description=spec.description,
        input_schema=input_schema,
        output_schema=output_schema,
        annotations=types.ToolAnnotations(
            read_only_hint=read_only,
            destructive_hint=False if read_only else None,
        ),
    )
    return ToolEntry(
        spec=spec,
        tool=tool,
        input_adapter=input_adapter,
        output_adapter=output_adapter,
        wraps_output=wraps,
    )


def build_tool_entries() -> dict[str, ToolEntry]:
    """Build MCP tool entries for all catalog operations."""
    return {spec.name: build_tool_entry(spec) for spec in catalog()}


def _error_result(body: dict[str, Any]) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(text=json.dumps(body, ensure_ascii=False))],
        is_error=True,
    )


def _invalid_input_body(exc: PydanticValidationError) -> dict[str, Any]:
    return {
        "detail": "Input arguments do not match the tool schema",
        "code": "INPUT_INVALID",
        "errors": [
            {
                "key": ".".join(str(part) for part in err["loc"]),
                "message": err["msg"],
                "code": f"input.{err['type']}",
            }
            for err in exc.errors(include_url=False)
        ],
    }


def _unauthenticated_response() -> JSONResponse:
    return JSONResponse(
        {"detail": "Authentication required", "code": "UNAUTHENTICATED"},
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


class McpPort:
    """ASGI endpoint mounted at `/api/v1/mcp` serving the MCP Streamable HTTP protocol."""

    def __init__(self) -> None:
        self._manager: StreamableHTTPSessionManager | None = None
        self._entries: dict[str, ToolEntry] | None = None
        self._idempotency_cache: OrderedDict[
            tuple[int, str, str], tuple[str, types.CallToolResult]
        ] = OrderedDict()
        self.server = Server(
            SERVER_NAME,
            title="Financial Control",
            instructions=INSTRUCTIONS,
            on_list_tools=self._list_tools,
            on_call_tool=self._call_tool,
        )

    @property
    def entries(self) -> dict[str, ToolEntry]:
        if self._entries is None:
            self._entries = build_tool_entries()
        return self._entries

    def _new_manager(self) -> StreamableHTTPSessionManager:
        return StreamableHTTPSessionManager(
            app=self.server,
            json_response=True,
            stateless=True,
            security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )

    @asynccontextmanager
    async def running(self) -> AsyncIterator[None]:
        manager = self._new_manager()
        async with manager.run():
            self._manager = manager
            try:
                yield
            finally:
                self._manager = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive)

        rejection = self._foreign_origin(request)
        if rejection is None:
            rejection = await self._authenticate(request)
        if rejection is not None:
            await rejection(scope, receive, send)
            return

        if self._manager is not None:
            await self._manager.handle_request(scope, receive, send)
            return

        # Fallback when invoked in tests without entering FastAPI lifespan:
        transient = self._new_manager()
        async with transient.run():
            await transient.handle_request(scope, receive, send)

    @staticmethod
    def _foreign_origin(request: Request) -> JSONResponse | None:
        """Reject browser requests from a foreign Origin; non-browser MCP clients omit Origin."""
        origin = request.headers.get("origin")
        if not origin:
            return None
        settings = get_settings()
        host = request.headers.get("host", "")
        scheme = "https" if settings.auth_cookie_secure else "http"
        if origin == f"{scheme}://{host}":
            return None
        if origin in settings.cors_origins:
            return None
        return JSONResponse(
            {"detail": "Origin not allowed", "code": "FORBIDDEN_ORIGIN"},
            status_code=403,
        )

    @staticmethod
    def _resolve_uow_factory(request: Request | None) -> UoWFactory:
        app = getattr(request, "app", None) if request is not None else None
        overrides = getattr(app, "dependency_overrides", {}) if app is not None else {}
        provider = overrides.get(get_uow_factory, get_uow_factory)
        return provider()

    @classmethod
    def _resolve_runtime_handlers(cls, request: Request | None) -> AgenticRuntimeHandlers:
        uow_factory = cls._resolve_uow_factory(request)
        app = getattr(request, "app", None) if request is not None else None
        overrides = getattr(app, "dependency_overrides", {}) if app is not None else {}
        if get_portfolio_service in overrides:
            portfolio_service = overrides[get_portfolio_service]()
        else:
            settings = get_settings()
            if get_market_gateway in overrides:
                gateway = overrides[get_market_gateway]()
            else:
                gateway = get_market_gateway(settings)
            portfolio_service = PortfolioApplicationService(
                gateway=gateway,
                fetch_workers=settings.market_fetch_workers,
                fetch_timeout_seconds=settings.market_fetch_timeout_seconds,
            )
        return AgenticRuntimeHandlers(
            uow_factory=uow_factory,
            portfolio_service=portfolio_service,
        )

    async def _authenticate(self, request: Request) -> JSONResponse | None:
        uow_factory = self._resolve_uow_factory(request)
        key_handler = AgentKeyHandler(uow_factory=uow_factory)
        auth_header = request.headers.get("authorization", "")
        try:
            agent_key = await anyio.to_thread.run_sync(key_handler.authenticate_bearer, auth_header)
        except AuthenticationError:
            return _unauthenticated_response()
        except DomainError as exc:
            return JSONResponse(error_body(exc), status_code=403)

        setattr(request.state, _STATE_KEY, agent_key)
        return None

    @staticmethod
    def _agent_key(ctx: Any) -> AgentApiKeyEntity:
        request: Request | None = getattr(ctx, "request", None)
        agent_key = getattr(request.state, _STATE_KEY, None) if request is not None else None
        if agent_key is None:
            raise MCPError(types.INVALID_REQUEST, "Unauthenticated MCP request")
        return agent_key

    async def _list_tools(
        self, ctx: Any, _params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        agent_key = self._agent_key(ctx)
        return types.ListToolsResult(
            tools=[
                entry.tool for name, entry in self.entries.items() if reaches(agent_key.grant, name)
            ]
        )

    async def _call_tool(
        self, ctx: Any, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        agent_key = self._agent_key(ctx)
        entry = self.entries.get(params.name)
        if entry is None or params.name not in CATALOG_BY_NAME:
            raise MCPError(types.INVALID_PARAMS, f"Unknown tool: {params.name}")

        if not reaches(agent_key.grant, params.name):
            return _error_result(
                {
                    "detail": (
                        f"Operation '{params.name}' is not granted to agent key '{agent_key.name}'"
                    ),
                    "code": "GRANT_NOT_ALLOWED",
                }
            )

        raw_args = dict(params.arguments or {})
        idem_key: str | None = None
        if entry.spec.kind == "command":
            raw_idem = raw_args.pop(IDEMPOTENCY_ARGUMENT, None)
            if raw_idem is not None:
                idem_key = str(raw_idem).strip() or None

        try:
            validated_input = entry.input_adapter.validate_python(raw_args)
        except PydanticValidationError as exc:
            return _error_result(_invalid_input_body(exc))

        args_digest = hashlib.sha256(
            json.dumps(
                entry.input_adapter.dump_python(validated_input, mode="json"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        cache_slot = (agent_key.id or 0, params.name, idem_key) if idem_key else None
        if cache_slot is not None and cache_slot in self._idempotency_cache:
            prev_digest, prev_result = self._idempotency_cache[cache_slot]
            if prev_digest != args_digest:
                return _error_result(
                    error_body(
                        ConflictError(
                            "Idempotency key was already used with different arguments",
                            code="IDEMPOTENCY_CONFLICT",
                        )
                    )
                )
            return prev_result

        request: Request | None = getattr(ctx, "request", None)
        handlers = self._resolve_runtime_handlers(request)
        try:
            raw_output = await anyio.to_thread.run_sync(
                entry.spec.invoke, handlers, validated_input
            )
        except DomainError as exc:
            return _error_result(error_body(exc))
        except Exception:
            request_id = getattr(getattr(request, "state", None), "request_id", None)
            logger.exception("Unexpected failure executing MCP tool %s", entry.tool.name)
            return _error_result(
                {
                    "detail": "Unexpected internal error while executing MCP tool",
                    "code": "INTERNAL_ERROR",
                    "request_id": request_id,
                }
            )

        if entry.output_adapter is None:
            result = types.CallToolResult(content=[types.TextContent(text="null")])
        else:
            serialized = entry.output_adapter.dump_python(raw_output, mode="json")
            structured = {"result": serialized} if entry.wraps_output else serialized
            result = types.CallToolResult(
                content=[types.TextContent(text=json.dumps(serialized, ensure_ascii=False))],
                structured_content=structured,
            )

        if cache_slot is not None:
            self._idempotency_cache[cache_slot] = (args_digest, result)
            while len(self._idempotency_cache) > _MAX_IDEMPOTENCY_ENTRIES:
                self._idempotency_cache.popitem(last=False)

        return result


mcp_port = McpPort()
