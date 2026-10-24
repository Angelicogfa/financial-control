"""FastAPI Controllers / Routers (strictly delegating to Application Handlers)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from fincontrol_core.domain.enums import AssetType
from fincontrol_core.domain.pagination import PaginationParams

from fincontrol_api.auth import SESSION_COOKIE
from fincontrol_api.dependencies import (
    get_account_handler,
    get_asset_handler,
    get_auth_handler,
    get_earning_handler,
    get_market_data_handler,
    get_policy_handler,
    get_portfolio_handler,
    get_system_handler,
    get_transaction_handler,
    require_user,
)
from fincontrol_api.handlers import (
    AssetHandler,
    EarningHandler,
    PortfolioHandler,
    TransactionHandler,
)
from fincontrol_api.handlers.account_handlers import AccountHandler
from fincontrol_api.handlers.auth_handlers import AuthHandler
from fincontrol_api.handlers.market_handlers import MarketDataHandler
from fincontrol_api.handlers.policy_handlers import PolicyHandler
from fincontrol_api.handlers.system_handlers import SystemHandler
from fincontrol_api.schemas import (
    AccountDTO,
    AccountRequest,
    ArcaSuggestionDTO,
    ArcaTargetItemDTO,
    ArcaTargetsUpdateRequest,
    AssetAnalysisResponseDTO,
    AssetCreateRequest,
    AssetResponseDTO,
    AssetUpdateRequest,
    CerradoUpdateRequest,
    ContributionPlanResponseDTO,
    ContributionSimulationRequest,
    CurrentUserDTO,
    EarningCreateRequest,
    EarningResponseDTO,
    EarningUpdateRequest,
    JobRunDTO,
    LoginRequest,
    PaginatedResponse,
    PolicyDTO,
    PolicyUpdateRequest,
    PortfolioAnalyticsResponseDTO,
    PortfolioReportResponseDTO,
    ReadinessDTO,
    SeriesStatusDTO,
    TransactionCreateRequest,
    TransactionResponseDTO,
    TransactionUpdateRequest,
)

health_router = APIRouter(tags=["Health"])
assets_router = APIRouter(prefix="/assets", tags=["Assets"])
transactions_router = APIRouter(prefix="/transactions", tags=["Transactions"])
earnings_router = APIRouter(prefix="/earnings", tags=["Earnings"])
portfolio_router = APIRouter(prefix="/portfolio", tags=["Portfolio & ARCA"])
settings_router = APIRouter(prefix="/settings", tags=["Settings"])
market_router = APIRouter(prefix="/market", tags=["Market Data"])
policy_router = APIRouter(prefix="/policy", tags=["Investment Policy"])
accounts_router = APIRouter(prefix="/accounts", tags=["Accounts"])
auth_router = APIRouter(prefix="/auth", tags=["Auth"])


def pagination_query(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=200),
    sort_by: str = Query(default="id"),
    sort_order: str = Query(default="asc"),
    sort_dir: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> PaginationParams:
    """Parse standardized pagination, sorting, and search query parameters."""
    order = (sort_dir or sort_order).lower()
    return PaginationParams(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=order,
        search=search,
    )


# ---------------------------------------------------------------------------
# Health Controller
# ---------------------------------------------------------------------------
@health_router.get("/health")
def get_health() -> dict[str, str]:
    """Liveness check: the process is up (no dependency is touched)."""
    return {"status": "ok", "service": "fincontrol-api"}


@health_router.get("/ready", response_model=ReadinessDTO)
def get_ready(
    response: Response,
    handler: SystemHandler = Depends(get_system_handler),
) -> ReadinessDTO:
    """Readiness check: database reachable and migrated (503 otherwise), cache status."""
    result = handler.readiness()
    if result.status == "not_ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


# ---------------------------------------------------------------------------
# Assets Controller
# ---------------------------------------------------------------------------
@assets_router.get("", response_model=PaginatedResponse[AssetResponseDTO])
def list_assets(
    params: PaginationParams = Depends(pagination_query),
    arca_class: str | None = Query(default=None),
    asset_type: str | None = Query(default=None),
    use_cerrado: bool | None = Query(default=None),
    active_only: bool = Query(default=True),
    handler: AssetHandler = Depends(get_asset_handler),
) -> PaginatedResponse[AssetResponseDTO]:
    return handler.list_paginated(
        params,
        arca_class=arca_class,
        asset_type=asset_type,
        use_cerrado=use_cerrado,
        active_only=active_only,
    )


@assets_router.post("", response_model=AssetResponseDTO, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreateRequest,
    handler: AssetHandler = Depends(get_asset_handler),
) -> AssetResponseDTO:
    return handler.create(payload)


@assets_router.get("/classification", response_model=ArcaSuggestionDTO)
def suggest_asset_classification(
    ticker: str = Query(..., min_length=1, max_length=32),
    asset_type: AssetType = Query(...),
    handler: AssetHandler = Depends(get_asset_handler),
) -> ArcaSuggestionDTO:
    """ARCA class suggested by what the instrument is exposed to (ETF catalog) or its type."""
    return handler.suggest_classification(ticker, asset_type)


@assets_router.get("/{asset_id}", response_model=AssetResponseDTO)
def get_asset(
    asset_id: int,
    handler: AssetHandler = Depends(get_asset_handler),
) -> AssetResponseDTO:
    return handler.get_by_id(asset_id)


@assets_router.put("/{asset_id}", response_model=AssetResponseDTO)
def update_asset(
    asset_id: int,
    payload: AssetUpdateRequest,
    handler: AssetHandler = Depends(get_asset_handler),
) -> AssetResponseDTO:
    return handler.update(asset_id, payload)


@assets_router.put("/{asset_id}/cerrado", response_model=AssetResponseDTO)
def update_asset_cerrado(
    asset_id: int,
    payload: CerradoUpdateRequest,
    handler: AssetHandler = Depends(get_asset_handler),
) -> AssetResponseDTO:
    return handler.update_cerrado(asset_id, payload)


@assets_router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: int,
    hard: bool = Query(default=False),
    handler: AssetHandler = Depends(get_asset_handler),
) -> Response:
    handler.delete(asset_id, hard=hard)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@assets_router.get("/{asset_id}/analysis", response_model=AssetAnalysisResponseDTO)
def get_asset_analysis(
    asset_id: int,
    handler: AssetHandler = Depends(get_asset_handler),
) -> AssetAnalysisResponseDTO:
    return handler.get_analysis(asset_id)


# ---------------------------------------------------------------------------
# Transactions Controller
# ---------------------------------------------------------------------------
@transactions_router.get("", response_model=PaginatedResponse[TransactionResponseDTO])
def list_transactions(
    params: PaginationParams = Depends(pagination_query),
    asset_id: int | None = Query(default=None),
    kind: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    account_id: int | None = Query(default=None),
    handler: TransactionHandler = Depends(get_transaction_handler),
) -> PaginatedResponse[TransactionResponseDTO]:
    return handler.list_paginated(
        params,
        asset_id=asset_id,
        kind=kind,
        date_from=date_from,
        date_to=date_to,
        account_id=account_id,
    )


@transactions_router.post(
    "", response_model=TransactionResponseDTO, status_code=status.HTTP_201_CREATED
)
def create_transaction(
    payload: TransactionCreateRequest,
    handler: TransactionHandler = Depends(get_transaction_handler),
) -> TransactionResponseDTO:
    return handler.create(payload)


@transactions_router.put("/{tx_id}", response_model=TransactionResponseDTO)
def update_transaction(
    tx_id: int,
    payload: TransactionUpdateRequest,
    handler: TransactionHandler = Depends(get_transaction_handler),
) -> TransactionResponseDTO:
    return handler.update(tx_id, payload)


@transactions_router.delete("/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    tx_id: int,
    handler: TransactionHandler = Depends(get_transaction_handler),
) -> Response:
    handler.delete(tx_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Earnings (Proventos) Controller
# ---------------------------------------------------------------------------
@earnings_router.get("", response_model=PaginatedResponse[EarningResponseDTO])
def list_earnings(
    params: PaginationParams = Depends(pagination_query),
    asset_id: int | None = Query(default=None),
    kind: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    account_id: int | None = Query(default=None),
    handler: EarningHandler = Depends(get_earning_handler),
) -> PaginatedResponse[EarningResponseDTO]:
    return handler.list_paginated(
        params,
        asset_id=asset_id,
        kind=kind,
        date_from=date_from,
        date_to=date_to,
        account_id=account_id,
    )


@earnings_router.post("", response_model=EarningResponseDTO, status_code=status.HTTP_201_CREATED)
def create_earning(
    payload: EarningCreateRequest,
    handler: EarningHandler = Depends(get_earning_handler),
) -> EarningResponseDTO:
    return handler.create(payload)


@earnings_router.put("/{earning_id}", response_model=EarningResponseDTO)
def update_earning(
    earning_id: int,
    payload: EarningUpdateRequest,
    handler: EarningHandler = Depends(get_earning_handler),
) -> EarningResponseDTO:
    return handler.update(earning_id, payload)


@earnings_router.delete("/{earning_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_earning(
    earning_id: int,
    handler: EarningHandler = Depends(get_earning_handler),
) -> Response:
    handler.delete(earning_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Portfolio, Consolidation, Contribution & Analytics Controller
# ---------------------------------------------------------------------------
@portfolio_router.get("", response_model=PortfolioReportResponseDTO)
def get_portfolio(
    as_of_date: date | None = Query(default=None),
    date_from: date | None = Query(default=None),
    account_id: int | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> PortfolioReportResponseDTO:
    return handler.get_portfolio_report(
        as_of_date=as_of_date, date_from=date_from, account_id=account_id
    )


@portfolio_router.get("/consolidated", response_model=PortfolioReportResponseDTO)
def get_consolidated_portfolio(
    as_of_date: date | None = Query(default=None),
    date_from: date | None = Query(default=None),
    account_id: int | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> PortfolioReportResponseDTO:
    return handler.get_portfolio_report(
        as_of_date=as_of_date, date_from=date_from, account_id=account_id
    )


@portfolio_router.post("/contribution", response_model=ContributionPlanResponseDTO)
def simulate_contribution(
    payload: ContributionSimulationRequest,
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> ContributionPlanResponseDTO:
    return handler.simulate_contribution(payload)


@portfolio_router.get("/analytics", response_model=PortfolioAnalyticsResponseDTO)
def get_portfolio_analytics(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> PortfolioAnalyticsResponseDTO:
    return handler.get_analytics(date_from=date_from, date_to=date_to)


# ---------------------------------------------------------------------------
# ARCA Target Settings Controller
# ---------------------------------------------------------------------------
@settings_router.get("/arca-targets", response_model=list[ArcaTargetItemDTO])
def get_arca_targets(
    handler: PolicyHandler = Depends(get_policy_handler),
) -> list[ArcaTargetItemDTO]:
    return handler.get_arca_targets()


@settings_router.put("/arca-targets", response_model=list[ArcaTargetItemDTO])
def update_arca_targets(
    payload: ArcaTargetsUpdateRequest,
    handler: PolicyHandler = Depends(get_policy_handler),
) -> list[ArcaTargetItemDTO]:
    return handler.update_arca_targets(payload)


# ---------------------------------------------------------------------------
# Investment Policy Controller (Estratégia)
# ---------------------------------------------------------------------------
@accounts_router.get("", response_model=list[AccountDTO])
def list_accounts(
    active_only: bool = Query(default=False),
    handler: AccountHandler = Depends(get_account_handler),
) -> list[AccountDTO]:
    return handler.list_all(active_only=active_only)


@accounts_router.post("", response_model=AccountDTO, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountRequest,
    handler: AccountHandler = Depends(get_account_handler),
) -> AccountDTO:
    return handler.create(payload)


@accounts_router.put("/{account_id}", response_model=AccountDTO)
def update_account(
    account_id: int,
    payload: AccountRequest,
    handler: AccountHandler = Depends(get_account_handler),
) -> AccountDTO:
    return handler.update(account_id, payload)


@policy_router.get("", response_model=PolicyDTO)
def get_policy(handler: PolicyHandler = Depends(get_policy_handler)) -> PolicyDTO:
    return handler.get_current()


@policy_router.put("", response_model=PolicyDTO)
def update_policy(
    payload: PolicyUpdateRequest,
    handler: PolicyHandler = Depends(get_policy_handler),
) -> PolicyDTO:
    return handler.update(payload)


@policy_router.get("/versions", response_model=list[PolicyDTO])
def list_policy_versions(
    limit: int = Query(default=20, ge=1, le=200),
    handler: PolicyHandler = Depends(get_policy_handler),
) -> list[PolicyDTO]:
    return handler.list_versions(limit)


# ---------------------------------------------------------------------------
# Market Data Diagnostics Controller
# ---------------------------------------------------------------------------
@market_router.get("/job-runs", response_model=list[JobRunDTO])
def get_job_runs(
    handler: MarketDataHandler = Depends(get_market_data_handler),
) -> list[JobRunDTO]:
    return handler.job_runs()


@market_router.get("/series-status", response_model=list[SeriesStatusDTO])
def get_series_status(
    handler: MarketDataHandler = Depends(get_market_data_handler),
) -> list[SeriesStatusDTO]:
    return handler.series_status()


# ---------------------------------------------------------------------------
# Authentication Controller (single user)
# ---------------------------------------------------------------------------
@auth_router.post("/login", response_model=CurrentUserDTO)
def login(
    payload: LoginRequest,
    response: Response,
    handler: AuthHandler = Depends(get_auth_handler),
) -> CurrentUserDTO:
    session = handler.login(payload)
    response.set_cookie(
        SESSION_COOKIE,
        session.token,
        max_age=handler.cookie_max_age_seconds,
        httponly=True,
        secure=handler.cookie_secure,
        samesite="strict",
        path="/",
    )
    return CurrentUserDTO(username=session.username, expires_at=session.expires_at)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@auth_router.get("/me", response_model=CurrentUserDTO)
def me(username: str = Depends(require_user)) -> CurrentUserDTO:
    return CurrentUserDTO(username=username)
