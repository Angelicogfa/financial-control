"""Catalog of application operations exposed as MCP tools (1:1 with UI screens).

Every tool maps directly to an application handler method, shares the same Pydantic validation
and domain rules as the HTTP routers, and respects the grant scope configured on the user's
personal agent key.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from controllers.accounts.requests import AccountRequest
from controllers.accounts.responses import AccountDTO
from controllers.alerts.requests import AlertDismissRequest
from controllers.alerts.responses import AlertsResponseDTO
from controllers.assets.requests import (
    AssetCreateRequest,
    AssetUpdateRequest,
    CerradoUpdateRequest,
)
from controllers.assets.responses import (
    ArcaSuggestionDTO,
    AssetAnalysisResponseDTO,
    AssetResponseDTO,
)
from controllers.contributions.requests import ContributionConfirmRequest
from controllers.contributions.responses import SavedContributionPlanDTO
from controllers.ledger.requests import (
    CorporateEventRequest,
    EarningCreateRequest,
    EarningUpdateRequest,
    ImportNewAssetRequest,
    TransactionCreateRequest,
    TransactionUpdateRequest,
)
from controllers.ledger.responses import (
    CorporateEventDTO,
    EarningResponseDTO,
    ImportCommitDTO,
    ImportPreviewDTO,
    TransactionResponseDTO,
)
from controllers.market.responses import (
    JobRunDTO,
    SeriesStatusDTO,
    WorkerErrorsResponseDTO,
)
from controllers.policy.requests import (
    ArcaTargetItemDTO,
    ArcaTargetsUpdateRequest,
    PolicyUpdateRequest,
)
from controllers.policy.responses import PolicyDTO
from controllers.portfolio.requests import ContributionSimulationRequest
from controllers.portfolio.responses import (
    ContributionPlanResponseDTO,
    EarningsAgendaDTO,
    PortfolioAnalyticsResponseDTO,
    PortfolioHealthDTO,
    PortfolioReportResponseDTO,
    SnapshotPointDTO,
    TreasuryMarketDTO,
)
from controllers.research.requests import WatchlistAddRequest
from controllers.research.responses import (
    AssetComparisonDTO,
    ScreenerResponseDTO,
    WatchlistItemDTO,
)
from controllers.shared.dependencies import UoWFactory
from controllers.shared.responses import PaginatedResponse
from controllers.simulation.requests import BacktestRequest
from controllers.simulation.responses import (
    CoverageReportDTO,
    SimulationRunDetailDTO,
    SimulationRunDTO,
)
from controllers.tax.requests import FixedIncomeCompareRequest
from controllers.tax.responses import AssetTaxStatusDTO, FixedIncomeComparisonDTO, TaxRuleDTO
from core.errors import ValidationError
from core.helpers.pagination import PaginationParams
from domain.accounts.services.use_cases import AccountHandler
from domain.alerts.services.use_cases import AlertHandler
from domain.assets.services.use_cases import AssetHandler
from domain.contributions.services.use_cases import ContributionHandler
from domain.ledger.services.use_cases.b3_import import ImportHandler
from domain.ledger.services.use_cases.corporate_events import CorporateEventHandler
from domain.ledger.services.use_cases.earnings import EarningHandler
from domain.ledger.services.use_cases.transactions import TransactionHandler
from domain.market.services.use_cases import MarketDataHandler
from domain.policy.services.use_cases import PolicyHandler
from domain.portfolio.services.service import PortfolioApplicationService
from domain.portfolio.services.use_cases import PortfolioHandler
from domain.research.services.screener import ScreenerCriteria
from domain.research.services.use_cases import ResearchHandler
from domain.shared.entities import AgentGrant, context_of
from domain.shared.enums import ArcaClass, AssetType, ContributionPlanStatus
from domain.simulation.services.use_cases import SimulationHandler
from domain.tax.services.use_cases import TaxHandler

OperationKind = Literal["query", "command"]

CONTEXT_LABELS: dict[str, str] = {
    "portfolio": "Carteira & Desempenho",
    "assets": "Ativos & Checklist",
    "contributions": "Aportes & Rebalanceamento",
    "ledger.trades": "Lançamentos · Negociações",
    "ledger.earnings": "Lançamentos · Proventos",
    "ledger.events": "Lançamentos · Eventos Corporativos",
    "ledger.imports": "Lançamentos · Importação B3",
    "research": "Pesquisa & Watchlist B3",
    "policy": "Estratégia & Política ARCA",
    "accounts": "Contas & Custódia",
    "alerts": "Alertas",
    "market": "Dados de Mercado",
    "tools": "Ferramentas · Tributação",
    "simulation": "Simulação de carteira",
}


class EmptyInput(BaseModel):
    """Input model for operations that take no parameters."""


class PortfolioReportInput(BaseModel):
    as_of_date: date | None = None
    date_from: date | None = None
    account_id: int | None = None


class CompareInput(BaseModel):
    tickers: list[str] = Field(..., min_length=2, max_length=5)
    indicators: list[str] = Field(default_factory=list)


class TreasuryMarketInput(BaseModel):
    as_of_date: date | None = None
    asset_id: int | None = None


class CoveragePeriodInput(BaseModel):
    start: date | None = None
    end: date | None = None


class SimulationIdInput(BaseModel):
    run_id: int


class SimulationListInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


class AsOfDateInput(BaseModel):
    as_of_date: date | None = None


class DateRangeInput(BaseModel):
    date_from: date | None = None
    date_to: date | None = None


class AssetListInput(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    sort_by: str = "ticker"
    sort_order: Literal["asc", "desc"] = "asc"
    arca_class: str | None = None
    asset_type: str | None = None
    use_cerrado: bool | None = None
    active_only: bool = True


class AssetIdInput(BaseModel):
    asset_id: int


class AssetTaxStatusInput(BaseModel):
    asset_id: int
    as_of_date: date | None = None


class AssetUpdateToolInput(BaseModel):
    asset_id: int
    data: AssetUpdateRequest


class AssetChecklistToolInput(BaseModel):
    asset_id: int
    data: CerradoUpdateRequest


class AssetArchiveToolInput(BaseModel):
    asset_id: int
    hard: bool = False


class AssetClassifyInput(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=32)
    asset_type: AssetType


class ContributionListInput(BaseModel):
    status: ContributionPlanStatus | None = None
    limit: int = Field(default=20, ge=1, le=100)


class ContributionIdInput(BaseModel):
    plan_id: int


class ContributionConfirmToolInput(BaseModel):
    plan_id: int
    data: ContributionConfirmRequest


class LedgerListInput(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    sort_by: str = "id"
    sort_order: Literal["asc", "desc"] = "desc"
    asset_id: int | None = None
    account_id: int | None = None
    kind: str | None = None
    date_from: date | None = None
    date_to: date | None = None


class TransactionIdInput(BaseModel):
    tx_id: int


class TransactionUpdateToolInput(BaseModel):
    tx_id: int
    data: TransactionUpdateRequest


class EarningIdInput(BaseModel):
    earning_id: int


class EarningUpdateToolInput(BaseModel):
    earning_id: int
    data: EarningUpdateRequest


class CorporateEventListInput(BaseModel):
    asset_id: int | None = None


class CorporateEventIdInput(BaseModel):
    event_id: int


class B3ImportPreviewToolInput(BaseModel):
    filename: str = Field(
        default="statement.csv",
        description="Statement filename ending in .csv or .xlsx",
    )
    csv_text: str | None = Field(
        default=None,
        description="UTF-8 CSV text of the B3 statement (use this or content_base64)",
    )
    content_base64: str | None = Field(
        default=None,
        description="Base64-encoded bytes of the .xlsx or .csv B3 statement",
    )
    skip_lines: list[int] = Field(
        default_factory=list,
        description="Statement line numbers (line_no in the preview) to leave out",
    )


class B3ImportCommitToolInput(B3ImportPreviewToolInput):
    account_id: int | None = None
    create_tickers: list[str] = Field(default_factory=list)
    new_assets: list[ImportNewAssetRequest] = Field(default_factory=list)


class ScreenerToolInput(BaseModel):
    asset_type: list[AssetType] = Field(default_factory=list)
    arca_class: list[ArcaClass] = Field(default_factory=list)
    sector: list[str] = Field(default_factory=list)
    q: str | None = Field(default=None, max_length=60)
    min_volume_brl: float | None = Field(default=None, ge=0)
    min_market_cap: float | None = Field(default=None, ge=0)
    max_pe: float | None = Field(default=None, gt=0)
    max_pb: float | None = Field(default=None, gt=0)
    min_dy: float | None = Field(default=None, ge=0)
    min_roe: float | None = None
    below_band: bool = False
    exclude_registered: bool = False
    limit: int = Field(default=30, ge=1, le=100)


class WatchlistClassifyToolInput(BaseModel):
    asset_id: int
    arca_class: ArcaClass


class PolicyVersionsInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=200)


class AccountListInput(BaseModel):
    active_only: bool = False


class AccountUpdateToolInput(BaseModel):
    account_id: int
    data: AccountRequest


class AlertRestoreInput(BaseModel):
    key: str = Field(..., min_length=1, max_length=160)


class WorkerErrorsListInput(BaseModel):
    include_resolved: bool = False
    limit: int = Field(default=100, ge=1, le=500)


class WorkerErrorIdInput(BaseModel):
    error_id: int


class OperationStatusDTO(BaseModel):
    """Standard acknowledgement for operations that return HTTP 204 in REST."""

    ok: bool = True


def _decode_statement_bytes(payload: B3ImportPreviewToolInput) -> bytes:
    if payload.content_base64:
        try:
            return base64.b64decode(payload.content_base64)
        except Exception as exc:
            raise ValidationError("Invalid base64 statement content", code="INVALID_FILE") from exc
    if payload.csv_text is not None:
        return payload.csv_text.encode("utf-8")
    raise ValidationError(
        "Provide either `csv_text` or `content_base64` for the B3 statement",
        code="INVALID_FILE",
    )


@dataclass(frozen=True)
class AgenticRuntimeHandlers:
    """Bundle of application handlers used by MCP tool executions."""

    uow_factory: UoWFactory
    portfolio_service: PortfolioApplicationService

    @property
    def accounts(self) -> AccountHandler:
        return AccountHandler(uow_factory=self.uow_factory)

    @property
    def alerts(self) -> AlertHandler:
        return AlertHandler(uow_factory=self.uow_factory, portfolio_service=self.portfolio_service)

    @property
    def assets(self) -> AssetHandler:
        return AssetHandler(uow_factory=self.uow_factory, portfolio_service=self.portfolio_service)

    @property
    def contributions(self) -> ContributionHandler:
        return ContributionHandler(
            uow_factory=self.uow_factory, portfolio_service=self.portfolio_service
        )

    @property
    def transactions(self) -> TransactionHandler:
        return TransactionHandler(
            uow_factory=self.uow_factory, portfolio_service=self.portfolio_service
        )

    @property
    def earnings(self) -> EarningHandler:
        return EarningHandler(uow_factory=self.uow_factory)

    @property
    def events(self) -> CorporateEventHandler:
        return CorporateEventHandler(uow_factory=self.uow_factory)

    @property
    def imports(self) -> ImportHandler:
        gateway = self.portfolio_service.gateway
        return ImportHandler(
            uow_factory=self.uow_factory,
            distributions=lambda ticker, asset_type: gateway.get_distributions(
                ticker, asset_type=asset_type
            ),
        )

    @property
    def market(self) -> MarketDataHandler:
        return MarketDataHandler(uow_factory=self.uow_factory)

    @property
    def policy(self) -> PolicyHandler:
        return PolicyHandler(uow_factory=self.uow_factory)

    @property
    def portfolio(self) -> PortfolioHandler:
        return PortfolioHandler(
            uow_factory=self.uow_factory, portfolio_service=self.portfolio_service
        )

    @property
    def tax(self) -> TaxHandler:
        return TaxHandler(uow_factory=self.uow_factory, portfolio_service=self.portfolio_service)

    @property
    def simulation(self) -> SimulationHandler:
        return SimulationHandler(uow_factory=self.uow_factory)

    @property
    def research(self) -> ResearchHandler:
        return ResearchHandler(
            uow_factory=self.uow_factory, portfolio_service=self.portfolio_service
        )


@dataclass(frozen=True)
class OperationSpec:
    """Declarative specification of an application operation exposed via MCP."""

    name: str
    kind: OperationKind
    description: str
    input_model: type[BaseModel]
    output_type: Any
    invoke: Callable[[AgenticRuntimeHandlers, Any], Any]

    @property
    def context(self) -> str:
        return context_of(self.name)


OPERATIONS: tuple[OperationSpec, ...] = (
    # 1. Portfolio & ARCA
    OperationSpec(
        name="portfolio.report",
        kind="query",
        description=(
            "Relatório consolidado da carteira: posições valorizadas, alocação ARCA atual, "
            "desvios em relação às bandas e patrimônio total."
        ),
        input_model=PortfolioReportInput,
        output_type=PortfolioReportResponseDTO,
        invoke=lambda h, p: h.portfolio.get_portfolio_report(
            as_of_date=p.as_of_date, date_from=p.date_from, account_id=p.account_id
        ),
    ),
    OperationSpec(
        name="portfolio.analytics",
        kind="query",
        description=(
            "Métricas de desempenho e risco da carteira: TWR, CAGR, volatilidade, Sharpe, "
            "Sortino, drawdown, correlação e comparação com benchmarks (CDI, IPCA, IBOV)."
        ),
        input_model=DateRangeInput,
        output_type=PortfolioAnalyticsResponseDTO,
        invoke=lambda h, p: h.portfolio.get_analytics(date_from=p.date_from, date_to=p.date_to),
    ),
    OperationSpec(
        name="portfolio.snapshots",
        kind="query",
        description="Série histórica de snapshots diários de patrimônio e resultado da carteira.",
        input_model=DateRangeInput,
        output_type=list[SnapshotPointDTO],
        invoke=lambda h, p: h.portfolio.list_snapshots(date_from=p.date_from, date_to=p.date_to),
    ),
    OperationSpec(
        name="portfolio.treasury_market",
        kind="query",
        description=(
            "Tesouro Direto a mercado: valor na curva (taxa da compra) contra o PU de venda do "
            "dia, diferença (prêmio), rentabilidade realizada vendendo hoje contra a da curva, "
            "taxa de reinvestimento de empate até o vencimento e sinal de oportunidade de venda "
            "antecipada (status OPPORTUNITY). Com `asset_id`, inclui o histórico curva × mercado."
        ),
        input_model=TreasuryMarketInput,
        output_type=list[TreasuryMarketDTO],
        invoke=lambda h, p: h.portfolio.treasury_market(
            as_of_date=p.as_of_date, asset_id=p.asset_id, with_history=p.asset_id is not None
        ),
    ),
    OperationSpec(
        name="portfolio.earnings_agenda",
        kind="query",
        description=(
            "Agenda de proventos anunciados (dividendos, JCP e rendimentos de FII) das ações, "
            "BDRs e FIIs da carteira e da watchlist, pela página de empresas listadas da B3: "
            "data com, data ex, pagamento, valor por cota e, para quem tem posição, valor bruto, "
            "IR retido estimado e líquido. Mostra só o que ainda não foi pago."
        ),
        input_model=AsOfDateInput,
        output_type=EarningsAgendaDTO,
        invoke=lambda h, p: h.portfolio.earnings_agenda(as_of_date=p.as_of_date),
    ),
    OperationSpec(
        name="portfolio.health",
        kind="query",
        description=(
            "Saúde da carteira em sete pilares (aderência à política, concentração, "
            "diversificação de risco, risco, desempenho, qualidade dos ativos e liquidez, renda "
            "e tributos). Cada checagem traz estado (OK, WARNING, CRITICAL ou "
            "INSUFFICIENT_DATA), valor, limites da política, explicação e ação sugerida; os "
            "pilares vêm do pior para o melhor. Frações seguem a ADR 0006 (0.15 = 15%)."
        ),
        input_model=AsOfDateInput,
        output_type=PortfolioHealthDTO,
        invoke=lambda h, p: h.portfolio.get_health(as_of_date=p.as_of_date),
    ),
    # 2. Assets & Checklist
    OperationSpec(
        name="assets.list",
        kind="query",
        description="Lista paginada de ativos cadastrados com filtros por quadrante ARCA e tipo.",
        input_model=AssetListInput,
        output_type=PaginatedResponse[AssetResponseDTO],
        invoke=lambda h, p: h.assets.list_paginated(
            PaginationParams(
                page=p.page,
                page_size=p.page_size,
                sort_by=p.sort_by,
                sort_order=p.sort_order,
            ),
            arca_class=p.arca_class,
            asset_type=p.asset_type,
            use_cerrado=p.use_cerrado,
            active_only=p.active_only,
        ),
    ),
    OperationSpec(
        name="assets.get",
        kind="query",
        description="Consulta os detalhes cadastrais e respostas do checklist de um ativo pelo ID.",
        input_model=AssetIdInput,
        output_type=AssetResponseDTO,
        invoke=lambda h, p: h.assets.get_by_id(p.asset_id),
    ),
    OperationSpec(
        name="assets.analysis",
        kind="query",
        description=(
            "Análise fundamentalista completa de um ativo: posição atual, múltiplos históricos, "
            "valuation (Graham, Bazin, P/VP), nota do Diagrama do Cerrado e risco-retorno."
        ),
        input_model=AssetIdInput,
        output_type=AssetAnalysisResponseDTO,
        invoke=lambda h, p: h.assets.get_analysis(p.asset_id),
    ),
    OperationSpec(
        name="assets.tax_status",
        kind="query",
        description=(
            "Situação tributária de um ativo: para renda fixa, por lote, a alíquota de IR "
            "atual, o IOF ainda devido, a data e os dias até a próxima faixa regressiva e o "
            "IR estimado resgatando hoje × na próxima faixa (ganho de esperar); para renda "
            "variável, o regime informativo do tipo de ativo (ações, FII, JCP, exterior)."
        ),
        input_model=AssetTaxStatusInput,
        output_type=AssetTaxStatusDTO,
        invoke=lambda h, p: h.tax.asset_tax_status(p.asset_id, as_of_date=p.as_of_date),
    ),
    OperationSpec(
        name="assets.create",
        kind="command",
        description="Cadastra um novo ativo de investimento na carteira.",
        input_model=AssetCreateRequest,
        output_type=AssetResponseDTO,
        invoke=lambda h, p: h.assets.create(p),
    ),
    OperationSpec(
        name="assets.update",
        kind="command",
        description="Atualiza os dados cadastrais ou termos de renda fixa de um ativo existente.",
        input_model=AssetUpdateToolInput,
        output_type=AssetResponseDTO,
        invoke=lambda h, p: h.assets.update(p.asset_id, p.data),
    ),
    OperationSpec(
        name="assets.checklist",
        kind="command",
        description=(
            "Atualiza as respostas e evidências do Checklist Fundamentalista "
            "(Diagrama do Cerrado) de um ativo."
        ),
        input_model=AssetChecklistToolInput,
        output_type=AssetResponseDTO,
        invoke=lambda h, p: h.assets.update_cerrado(p.asset_id, p.data),
    ),
    OperationSpec(
        name="assets.archive",
        kind="command",
        description="Arquiva (inativa) ou remove permanentemente um ativo pelo ID.",
        input_model=AssetArchiveToolInput,
        output_type=OperationStatusDTO,
        invoke=lambda h, p: (h.assets.delete(p.asset_id, hard=p.hard), OperationStatusDTO())[1],
    ),
    OperationSpec(
        name="assets.classify",
        kind="query",
        description="Sugere o quadrante ARCA adequado para um ticker e tipo de ativo.",
        input_model=AssetClassifyInput,
        output_type=ArcaSuggestionDTO,
        invoke=lambda h, p: h.assets.suggest_classification(p.ticker, p.asset_type),
    ),
    # 3. Contributions
    OperationSpec(
        name="contributions.simulate",
        kind="query",
        description=(
            "Simula a distribuição ótima de um novo aporte em R$ entre os quadrantes ARCA e "
            "ativos elegíveis, sem persistir rascunho."
        ),
        input_model=ContributionSimulationRequest,
        output_type=ContributionPlanResponseDTO,
        invoke=lambda h, p: h.portfolio.simulate_contribution(p),
    ),
    OperationSpec(
        name="contributions.draft",
        kind="command",
        description="Cria e salva um plano de aporte como rascunho (DRAFT).",
        input_model=ContributionSimulationRequest,
        output_type=SavedContributionPlanDTO,
        invoke=lambda h, p: h.contributions.create_draft(p),
    ),
    OperationSpec(
        name="contributions.list",
        kind="query",
        description="Lista os planos de aporte salvos (rascunhos, confirmados ou descartados).",
        input_model=ContributionListInput,
        output_type=list[SavedContributionPlanDTO],
        invoke=lambda h, p: h.contributions.list_recent(status=p.status, limit=p.limit),
    ),
    OperationSpec(
        name="contributions.get",
        kind="query",
        description="Consulta um plano de aporte salvo pelo ID.",
        input_model=ContributionIdInput,
        output_type=SavedContributionPlanDTO,
        invoke=lambda h, p: h.contributions.get(p.plan_id),
    ),
    OperationSpec(
        name="contributions.confirm",
        kind="command",
        description=(
            "Confirma um plano de aporte e registra automaticamente as transações de compra "
            "correspondentes no livro de lançamentos."
        ),
        input_model=ContributionConfirmToolInput,
        output_type=SavedContributionPlanDTO,
        invoke=lambda h, p: h.contributions.confirm(p.plan_id, p.data),
    ),
    OperationSpec(
        name="contributions.discard",
        kind="command",
        description="Descarta um rascunho de plano de aporte.",
        input_model=ContributionIdInput,
        output_type=SavedContributionPlanDTO,
        invoke=lambda h, p: h.contributions.discard(p.plan_id),
    ),
    # 4. Ledger: Trades
    OperationSpec(
        name="ledger.trades.list",
        kind="query",
        description="Lista paginada de lançamentos de compra e venda com filtros.",
        input_model=LedgerListInput,
        output_type=PaginatedResponse[TransactionResponseDTO],
        invoke=lambda h, p: h.transactions.list_paginated(
            PaginationParams(
                page=p.page,
                page_size=p.page_size,
                sort_by=p.sort_by,
                sort_order=p.sort_order,
            ),
            asset_id=p.asset_id,
            kind=p.kind,
            date_from=p.date_from,
            date_to=p.date_to,
            account_id=p.account_id,
        ),
    ),
    OperationSpec(
        name="ledger.trades.get",
        kind="query",
        description="Consulta uma transação de compra ou venda pelo ID.",
        input_model=TransactionIdInput,
        output_type=TransactionResponseDTO,
        invoke=lambda h, p: h.transactions.get(p.tx_id),
    ),
    OperationSpec(
        name="ledger.trades.create",
        kind="command",
        description="Registra uma nova transação de compra (BUY) ou venda (SELL).",
        input_model=TransactionCreateRequest,
        output_type=TransactionResponseDTO,
        invoke=lambda h, p: h.transactions.create(p),
    ),
    OperationSpec(
        name="ledger.trades.update",
        kind="command",
        description="Corrige os dados de uma transação de compra ou venda existente.",
        input_model=TransactionUpdateToolInput,
        output_type=TransactionResponseDTO,
        invoke=lambda h, p: h.transactions.update(p.tx_id, p.data),
    ),
    OperationSpec(
        name="ledger.trades.delete",
        kind="command",
        description="Exclui uma transação de compra ou venda pelo ID.",
        input_model=TransactionIdInput,
        output_type=OperationStatusDTO,
        invoke=lambda h, p: (h.transactions.delete(p.tx_id), OperationStatusDTO())[1],
    ),
    # 5. Ledger: Earnings
    OperationSpec(
        name="ledger.earnings.list",
        kind="query",
        description="Lista paginada de proventos recebidos (dividendos, JCP, rendimentos, cupons).",
        input_model=LedgerListInput,
        output_type=PaginatedResponse[EarningResponseDTO],
        invoke=lambda h, p: h.earnings.list_paginated(
            PaginationParams(
                page=p.page,
                page_size=p.page_size,
                sort_by=p.sort_by,
                sort_order=p.sort_order,
            ),
            asset_id=p.asset_id,
            kind=p.kind,
            date_from=p.date_from,
            date_to=p.date_to,
            account_id=p.account_id,
        ),
    ),
    OperationSpec(
        name="ledger.earnings.get",
        kind="query",
        description="Consulta um lançamento de provento pelo ID.",
        input_model=EarningIdInput,
        output_type=EarningResponseDTO,
        invoke=lambda h, p: h.earnings.get(p.earning_id),
    ),
    OperationSpec(
        name="ledger.earnings.create",
        kind="command",
        description="Registra um novo provento recebido (dividendo, JCP, rendimento FII, cupom).",
        input_model=EarningCreateRequest,
        output_type=EarningResponseDTO,
        invoke=lambda h, p: h.earnings.create(p),
    ),
    OperationSpec(
        name="ledger.earnings.update",
        kind="command",
        description="Atualiza os dados de um provento registrado.",
        input_model=EarningUpdateToolInput,
        output_type=EarningResponseDTO,
        invoke=lambda h, p: h.earnings.update(p.earning_id, p.data),
    ),
    OperationSpec(
        name="ledger.earnings.delete",
        kind="command",
        description="Exclui um registro de provento pelo ID.",
        input_model=EarningIdInput,
        output_type=OperationStatusDTO,
        invoke=lambda h, p: (h.earnings.delete(p.earning_id), OperationStatusDTO())[1],
    ),
    # 6. Ledger: Corporate Events
    OperationSpec(
        name="ledger.events.list",
        kind="query",
        description="Lista eventos corporativos (desdobramentos, grupamentos, bonificações).",
        input_model=CorporateEventListInput,
        output_type=list[CorporateEventDTO],
        invoke=lambda h, p: h.events.list_all(asset_id=p.asset_id),
    ),
    OperationSpec(
        name="ledger.events.create",
        kind="command",
        description="Registra um evento corporativo (SPLIT, REVERSE_SPLIT, BONUS).",
        input_model=CorporateEventRequest,
        output_type=CorporateEventDTO,
        invoke=lambda h, p: h.events.create(p),
    ),
    OperationSpec(
        name="ledger.events.delete",
        kind="command",
        description="Remove um evento corporativo pelo ID.",
        input_model=CorporateEventIdInput,
        output_type=OperationStatusDTO,
        invoke=lambda h, p: (h.events.delete(p.event_id), OperationStatusDTO())[1],
    ),
    # 7. Ledger: B3 Imports
    OperationSpec(
        name="ledger.imports.preview",
        kind="query",
        description=(
            "Analisa e pré-visualiza um extrato de movimentação ou negociação da B3 "
            "(.csv ou .xlsx) sem gravar, identificando linhas novas, duplicadas e tickers novos."
        ),
        input_model=B3ImportPreviewToolInput,
        output_type=ImportPreviewDTO,
        invoke=lambda h, p: h.imports.preview(
            p.filename, _decode_statement_bytes(p), skip_lines=p.skip_lines
        ),
    ),
    OperationSpec(
        name="ledger.imports.commit",
        kind="command",
        description=(
            "Importa e grava as linhas novas de um extrato da B3 (.csv ou .xlsx), "
            "cadastrando opcionalmente os novos tickers informados."
        ),
        input_model=B3ImportCommitToolInput,
        output_type=ImportCommitDTO,
        invoke=lambda h, p: h.imports.commit(
            p.filename,
            _decode_statement_bytes(p),
            account_id=p.account_id,
            create_tickers=p.create_tickers,
            new_assets=p.new_assets,
            skip_lines=p.skip_lines,
        ),
    ),
    # 8. Research & Watchlist
    OperationSpec(
        name="research.screener",
        kind="query",
        description=(
            "Executa o screener fundamentalista no catálogo da B3 filtrando por tipo, "
            "quadrante ARCA, setor, liquidez, P/L, P/VP, Dividend Yield e ROE."
        ),
        input_model=ScreenerToolInput,
        output_type=ScreenerResponseDTO,
        invoke=lambda h, p: h.research.screener(
            ScreenerCriteria(
                asset_types=frozenset(p.asset_type),
                arca_classes=frozenset(p.arca_class),
                sectors=frozenset(p.sector),
                query=p.q,
                min_volume_brl=p.min_volume_brl,
                min_market_cap=p.min_market_cap,
                max_pe=p.max_pe,
                max_pb=p.max_pb,
                min_dy=p.min_dy,
                min_roe=p.min_roe,
                exclude_registered=p.exclude_registered,
                limit=p.limit,
            ),
            below_band=p.below_band,
        ),
    ),
    OperationSpec(
        name="research.compare",
        kind="query",
        description=(
            "Compara de 2 a 5 ativos lado a lado (cadastrados ou do catálogo B3): indicadores "
            "em cinco grupos (valuation, endividamento, eficiência, rentabilidade, "
            "crescimento) com o melhor de cada linha em `best`, histórico anual (receita, "
            "lucro, ROE, DY), veredito de valuation e nota do checklist. `indicators` escolhe "
            "as linhas (todas quando vazio). Busca sob demanda os demonstrativos que faltarem."
        ),
        input_model=CompareInput,
        output_type=AssetComparisonDTO,
        invoke=lambda h, p: h.research.compare(p.tickers, p.indicators or None),
    ),
    OperationSpec(
        name="research.watchlist",
        kind="query",
        description="Lista os ativos em observação (watchlist) com avaliação e valuation.",
        input_model=EmptyInput,
        output_type=list[WatchlistItemDTO],
        invoke=lambda h, _p: h.research.watchlist(),
    ),
    OperationSpec(
        name="research.follow",
        kind="command",
        description="Adiciona um ticker da B3 à watchlist para acompanhamento e análise.",
        input_model=WatchlistAddRequest,
        output_type=WatchlistItemDTO,
        invoke=lambda h, p: h.research.add(p),
    ),
    OperationSpec(
        name="research.classify",
        kind="command",
        description="Altera o quadrante ARCA de um ativo acompanhado na watchlist.",
        input_model=WatchlistClassifyToolInput,
        output_type=WatchlistItemDTO,
        invoke=lambda h, p: h.research.classify(p.asset_id, p),
    ),
    OperationSpec(
        name="research.unfollow",
        kind="command",
        description="Remove um ativo sem posição da watchlist.",
        input_model=AssetIdInput,
        output_type=OperationStatusDTO,
        invoke=lambda h, p: (h.research.remove(p.asset_id), OperationStatusDTO())[1],
    ),
    # 9. Policy & Strategy
    OperationSpec(
        name="policy.get",
        kind="query",
        description=(
            "Consulta a política de investimentos vigente (alocações ARCA, bandas, "
            "critérios de elegibilidade e premissas de valuation)."
        ),
        input_model=EmptyInput,
        output_type=PolicyDTO,
        invoke=lambda h, _p: h.policy.get_current(),
    ),
    OperationSpec(
        name="policy.update",
        kind="command",
        description="Salva uma nova versão da política de investimentos completa.",
        input_model=PolicyUpdateRequest,
        output_type=PolicyDTO,
        invoke=lambda h, p: h.policy.update(p),
    ),
    OperationSpec(
        name="policy.versions",
        kind="query",
        description="Lista o histórico de versões da política de investimentos.",
        input_model=PolicyVersionsInput,
        output_type=list[PolicyDTO],
        invoke=lambda h, p: h.policy.list_versions(p.limit),
    ),
    OperationSpec(
        name="policy.get_arca_targets",
        kind="query",
        description="Consulta os percentuais-alvo e estratégias intra-classe dos quadrantes ARCA.",
        input_model=EmptyInput,
        output_type=list[ArcaTargetItemDTO],
        invoke=lambda h, _p: h.policy.get_arca_targets(),
    ),
    OperationSpec(
        name="policy.update_arca_targets",
        kind="command",
        description="Atualiza os percentuais-alvo dos 4 quadrantes ARCA (soma deve ser 100%).",
        input_model=ArcaTargetsUpdateRequest,
        output_type=list[ArcaTargetItemDTO],
        invoke=lambda h, p: h.policy.update_arca_targets(p),
    ),
    # 10. Accounts
    OperationSpec(
        name="accounts.list",
        kind="query",
        description="Lista as contas de custódia (corretoras, bancos, exchanges).",
        input_model=AccountListInput,
        output_type=list[AccountDTO],
        invoke=lambda h, p: h.accounts.list_all(active_only=p.active_only),
    ),
    OperationSpec(
        name="accounts.create",
        kind="command",
        description="Cadastra uma nova conta de custódia (corretora, banco ou exchange).",
        input_model=AccountRequest,
        output_type=AccountDTO,
        invoke=lambda h, p: h.accounts.create(p),
    ),
    OperationSpec(
        name="accounts.update",
        kind="command",
        description="Atualiza os dados ou status ativo de uma conta de custódia.",
        input_model=AccountUpdateToolInput,
        output_type=AccountDTO,
        invoke=lambda h, p: h.accounts.update(p.account_id, p.data),
    ),
    # 11. Alerts
    OperationSpec(
        name="alerts.list",
        kind="query",
        description="Lista os alertas ativos da carteira (rebalanceamento, valuation, dados).",
        input_model=EmptyInput,
        output_type=AlertsResponseDTO,
        invoke=lambda h, _p: h.alerts.list_alerts(),
    ),
    OperationSpec(
        name="alerts.dismiss",
        kind="command",
        description="Oculta/descarta um alerta pela chave por um número de dias ou enquanto durar.",
        input_model=AlertDismissRequest,
        output_type=OperationStatusDTO,
        invoke=lambda h, p: (h.alerts.dismiss(p), OperationStatusDTO())[1],
    ),
    OperationSpec(
        name="alerts.restore",
        kind="command",
        description="Restaura um alerta previamente ocultado pela chave.",
        input_model=AlertRestoreInput,
        output_type=OperationStatusDTO,
        invoke=lambda h, p: (h.alerts.restore(p.key), OperationStatusDTO())[1],
    ),
    # 12. Market Data
    OperationSpec(
        name="market.series_status",
        kind="query",
        description="Consulta o status de atualização e cobertura das séries de mercado.",
        input_model=EmptyInput,
        output_type=list[SeriesStatusDTO],
        invoke=lambda h, _p: h.market.series_status(),
    ),
    OperationSpec(
        name="market.job_runs",
        kind="query",
        description="Lista as execuções recentes dos jobs em segundo plano de dados de mercado.",
        input_model=EmptyInput,
        output_type=list[JobRunDTO],
        invoke=lambda h, _p: h.market.job_runs(),
    ),
    OperationSpec(
        name="market.worker_errors",
        kind="query",
        description=(
            "Lista o log detalhado de erros de requisição dos provedores externos ocorridos nas "
            "buscas do worker e a quantidade de notificações pendentes."
        ),
        input_model=WorkerErrorsListInput,
        output_type=WorkerErrorsResponseDTO,
        invoke=lambda h, p: h.market.worker_errors(
            include_resolved=p.include_resolved, limit=p.limit
        ),
    ),
    OperationSpec(
        name="market.resolve_worker_error",
        kind="command",
        description="Marca um erro de requisição do worker como resolvido pelo ID.",
        input_model=WorkerErrorIdInput,
        output_type=OperationStatusDTO,
        invoke=lambda h, p: (h.market.resolve_worker_error(p.error_id), OperationStatusDTO())[1],
    ),
    OperationSpec(
        name="market.resolve_all_worker_errors",
        kind="command",
        description=(
            "Limpa/resolve todas as notificações pendentes de erro de requisição do worker."
        ),
        input_model=EmptyInput,
        output_type=OperationStatusDTO,
        invoke=lambda h, _p: (h.market.resolve_all_worker_errors(), OperationStatusDTO())[1],
    ),
    # 13. Tools
    OperationSpec(
        name="tools.fixed_income_compare",
        kind="query",
        description=(
            "Compara dois ou mais títulos de renda fixa tributados e isentos (% do CDI, "
            "CDI + spread, IPCA+ ou prefixado), informados à mão ou pelo asset_id da "
            "carteira: valor e taxa líquidos no vencimento e na janela comum, IR sobre o "
            "ganho acumulado, taxas equivalentes por faixa e ponto de empate em dias, nos "
            "cenários das premissas da política. `rate`: multiplicador para CDI_PERCENT "
            "(1.10 = 110%) e fração anual para os demais (0.065 = 6,5% a.a.)."
        ),
        input_model=FixedIncomeCompareRequest,
        output_type=FixedIncomeComparisonDTO,
        invoke=lambda h, p: h.tax.compare_fixed_income(p),
    ),
    OperationSpec(
        name="tools.tax_rules",
        kind="query",
        description=(
            "Tabela de alíquotas de IR e IOF com vigência (renda fixa regressiva, isentos, "
            "ações, ETFs/BDRs, FIIs, dividendos, JCP, exterior e cripto) e base legal."
        ),
        input_model=EmptyInput,
        output_type=list[TaxRuleDTO],
        invoke=lambda h, _p: h.tax.list_rules(),
    ),
    # 14. Simulation
    OperationSpec(
        name="simulation.coverage",
        kind="query",
        description=(
            "Cobertura das séries históricas que a simulação de carteira usa (ativos da "
            "carteira, da watchlist e os mais negociados do catálogo, Ibovespa, IFIX, "
            "S&P 500, dólar, CDI e IPCA): primeira e última data, meses cobertos, maior "
            "intervalo sem dados e status OK, PARTIAL ou MISSING."
        ),
        input_model=CoveragePeriodInput,
        output_type=CoverageReportDTO,
        invoke=lambda h, p: h.simulation.coverage(start=p.start, end=p.end),
    ),
    OperationSpec(
        name="simulation.backtest",
        kind="command",
        description=(
            "Agenda um backtest da estratégia: as regras reais de aporte (metas, bandas ARCA, "
            "checklist e política) reaplicadas mês a mês sobre o histórico, com taxas, IR na "
            "venda e comparação com CDI, Ibovespa, IFIX ou S&P 500 em reais. Roda no worker; "
            "acompanhe com simulation.get."
        ),
        input_model=BacktestRequest,
        output_type=SimulationRunDTO,
        invoke=lambda h, p: h.simulation.submit_backtest(p),
    ),
    OperationSpec(
        name="simulation.get",
        kind="query",
        description=(
            "Status e resultados de uma simulação: resumo (valor final, TIR, TWR, "
            "volatilidade, drawdown, taxas e IR), série mensal e hashes de reprodutibilidade."
        ),
        input_model=SimulationIdInput,
        output_type=SimulationRunDetailDTO,
        invoke=lambda h, p: h.simulation.get_run(p.run_id),
    ),
    OperationSpec(
        name="simulation.list",
        kind="query",
        description="Simulações solicitadas, mais recentes primeiro, com status e parâmetros.",
        input_model=SimulationListInput,
        output_type=list[SimulationRunDTO],
        invoke=lambda h, p: h.simulation.list_runs(p.limit),
    ),
)

CATALOG_BY_NAME: dict[str, OperationSpec] = {op.name: op for op in OPERATIONS}
KNOWN_CONTEXTS: frozenset[str] = frozenset(op.context for op in OPERATIONS)
KNOWN_OPERATIONS: frozenset[str] = frozenset(CATALOG_BY_NAME)


def catalog() -> tuple[OperationSpec, ...]:
    """Return all registered MCP operation specifications in display order."""
    return OPERATIONS


def reaches(grant: AgentGrant | None, operation: str) -> bool:
    """Whether `grant` allows executing `operation` (None means full user session)."""
    if operation not in CATALOG_BY_NAME:
        return False
    if grant is None:
        return True
    return grant.allows(operation)


def validate_grant(grant: AgentGrant) -> None:
    """Validate that `grant` is non-empty and references only known contexts and operations."""
    if not grant.contexts and not grant.operations:
        raise ValidationError(
            "An agent key must grant at least one context or operation",
            code="EMPTY_AGENT_GRANT",
        )
    unknown_contexts = sorted(grant.contexts - KNOWN_CONTEXTS)
    if unknown_contexts:
        raise ValidationError(
            f"Unknown operation context(s): {', '.join(unknown_contexts)}",
            code="UNKNOWN_AGENT_CONTEXT",
        )
    unknown_ops = sorted(grant.operations - KNOWN_OPERATIONS)
    if unknown_ops:
        raise ValidationError(
            f"Unknown operation(s): {', '.join(unknown_ops)}",
            code="UNKNOWN_AGENT_OPERATION",
        )
