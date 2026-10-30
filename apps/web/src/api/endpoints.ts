/** Typed calls to the API, one group per operation context (ADR 0005). */

import { request } from "./http";
import type {
  AccountDTO,
  AccountRequest,
  AgentKeyCreatedDTO,
  AgentKeyCreateRequest,
  AgentKeyDTO,
  AgentKeyUpdateRequest,
  AlertDismissRequest,
  AlertsResponseDTO,
  ArcaClass,
  ArcaSuggestionDTO,
  AssetAnalysisResponseDTO,
  AssetForecastDTO,
  AssetPriceHistoryDTO,
  AssetComparisonDTO,
  AssetCreateRequest,
  AssetResponseDTO,
  AssetTaxStatusDTO,
  AssetType,
  AssetUpdateRequest,
  BacktestRequest,
  CalibrationDTO,
  CandidatesDTO,
  CandidatesRequest,
  DisclosureFeedDTO,
  LabDTO,
  MarkReadRequest,
  MarkReadResultDTO,
  CerradoUpdateRequest,
  ContributionConfirmRequest,
  ContributionPlanStatus,
  ContributionSimulationRequest,
  CorporateEventDTO,
  CorporateEventRequest,
  EarningsAgendaDTO,
  EarningCreateRequest,
  EarningResponseDTO,
  EarningUpdateRequest,
  FixedIncomeCompareRequest,
  FixedIncomeComparisonDTO,
  FixedIncomeIndexer,
  ForecastQualityDTO,
  GrantOptionsDTO,
  ImportCommitDTO,
  ImportFixedIncomeTermDTO,
  ImportPreviewDTO,
  JobRunDTO,
  KeyExpiryDays,
  PaginatedResponse_AssetResponseDTO_,
  PaginatedResponse_EarningResponseDTO_,
  PaginatedResponse_TransactionResponseDTO_,
  PolicyDTO,
  PolicyUpdateRequest,
  PortfolioAnalyticsResponseDTO,
  PortfolioHealthDTO,
  PortfolioReportResponseDTO,
  SavedContributionPlanDTO,
  ProjectionDTO,
  QuoteStatusDTO,
  ProjectionRequest,
  RobustnessDTO,
  ScreenerResponseDTO,
  SeriesStatusDTO,
  SimulationKind,
  SimulationRunDetailDTO,
  SimulationRunDTO,
  SnapshotPointDTO,
  StudyComparisonDTO,
  StudyDTO,
  StudyRequest,
  StudySummaryDTO,
  StudyVariationRequest,
  StudyVersionDTO,
  TaxRuleDTO,
  TransactionCreateRequest,
  TransactionResponseDTO,
  TransactionUpdateRequest,
  TreasuryMarketDTO,
  TreasurySearchResponseDTO,
  WatchlistAddRequest,
  WatchlistItemDTO,
  WealthByAccountDTO,
  WorkerErrorsResponseDTO,
} from "./types";

/**
 * Mirrors the backend `ImportNewAssetRequest`: it travels as JSON inside the multipart
 * `new_assets` field, so it is not one of the generated OpenAPI schemas.
 */
export interface ImportNewAssetRequest {
  ticker: string;
  asset_type?: AssetType | null;
  arca_class?: ArcaClass | null;
  /** Treasury bonds and bank securities: name and terms, with the contracted rate (ADR 0006). */
  name?: string | null;
  fixed_income_term?: (Omit<ImportFixedIncomeTermDTO, "contracted_rate"> & { contracted_rate: number }) | null;
}

export interface LedgerFilters {
  page?: number;
  page_size?: number;
  asset_id?: number;
  account_id?: number;
  date_from?: string;
  date_to?: string;
  kind?: string;
}

export interface ScreenerFilters {
  q?: string;
  asset_type?: AssetType[];
  arca_class?: ArcaClass[];
  sector?: string[];
  min_volume_brl?: number;
  max_pe?: number;
  max_pb?: number;
  min_dy?: number;
  min_roe?: number;
  below_band?: boolean;
  exclude_registered?: boolean;
  /** Page size. */
  limit?: number;
  /** One-based page of the matches; the reply's `total` says how many there are. */
  page?: number;
}

export interface TreasuryFilters {
  q?: string;
  indexer?: FixedIncomeIndexer;
  coupon_type?: "zero" | "semestral";
}

const newestFirst = { sort_by: "id", sort_order: "desc" };

export const api = {
  portfolio: {
    report: (accountId?: number) =>
      request<PortfolioReportResponseDTO>("/portfolio/consolidated", {
        query: { account_id: accountId },
      }),
    analytics: (dateFrom?: string) =>
      request<PortfolioAnalyticsResponseDTO>("/portfolio/analytics", { query: { date_from: dateFrom } }),
    snapshots: (dateFrom?: string) =>
      request<SnapshotPointDTO[]>("/portfolio/snapshots", { query: { date_from: dateFrom } }),
    health: () => request<PortfolioHealthDTO>("/portfolio/health"),
    treasuryMarket: () => request<TreasuryMarketDTO[]>("/portfolio/treasury-market"),
    treasuryMarketDetail: (assetId: number) =>
      request<TreasuryMarketDTO>(`/portfolio/treasury-market/${assetId}`),
    earningsAgenda: () => request<EarningsAgendaDTO>("/portfolio/earnings-agenda"),
    byAccount: () => request<WealthByAccountDTO>("/portfolio/by-account"),
  },
  alerts: {
    list: () => request<AlertsResponseDTO>("/alerts"),
    dismiss: (body: AlertDismissRequest) =>
      request<void>("/alerts/dismissals", { method: "POST", body }),
    restore: (key: string) =>
      request<void>("/alerts/dismissals", { method: "DELETE", query: { key } }),
  },
  assets: {
    list: (activeOnly = true) =>
      request<PaginatedResponse_AssetResponseDTO_>("/assets", {
        query: { page_size: 200, active_only: activeOnly, sort_by: "ticker" },
      }),
    get: (id: number) => request<AssetResponseDTO>(`/assets/${id}`),
    analysis: (id: number) => request<AssetAnalysisResponseDTO>(`/assets/${id}/analysis`),
    prices: (id: number, range: AssetPriceHistoryDTO["range"]) =>
      request<AssetPriceHistoryDTO>(`/assets/${id}/prices`, { query: { range } }),
    forecast: (id: number) => request<AssetForecastDTO>(`/assets/${id}/forecast`),
    create: (body: AssetCreateRequest) => request<AssetResponseDTO>("/assets", { method: "POST", body }),
    update: (id: number, body: AssetUpdateRequest) =>
      request<AssetResponseDTO>(`/assets/${id}`, { method: "PUT", body }),
    archive: (id: number) => request<void>(`/assets/${id}`, { method: "DELETE" }),
    checklist: (id: number, body: CerradoUpdateRequest) =>
      request<AssetResponseDTO>(`/assets/${id}/checklist`, { method: "PUT", body }),
    classify: (ticker: string, assetType: AssetType) =>
      request<ArcaSuggestionDTO>("/assets/classification", {
        query: { ticker, asset_type: assetType },
      }),
  },
  disclosures: {
    feed: (params: { assetId?: number; category?: string; unread?: boolean; limit?: number } = {}) =>
      request<DisclosureFeedDTO>("/disclosures", {
        query: { asset_id: params.assetId, category: params.category, unread: params.unread, limit: params.limit },
      }),
    markRead: (body: MarkReadRequest) =>
      request<MarkReadResultDTO>("/disclosures/read", { method: "POST", body }),
  },
  simulations: {
    list: (limit = 20, kind?: SimulationKind) =>
      request<SimulationRunDTO[]>("/simulations", { query: { limit, kind } }),
    get: (id: number) => request<SimulationRunDetailDTO>(`/simulations/${id}`),
    remove: (id: number) => request<void>(`/simulations/${id}`, { method: "DELETE" }),
    robustness: (id: number) => request<RobustnessDTO>(`/simulations/${id}/robustness`),
    projection: (id: number) => request<ProjectionDTO>(`/simulations/${id}/projection`),
    calibration: (runId?: number) =>
      request<CalibrationDTO>("/simulations/calibration", { query: { run_id: runId } }),
    submitCalibration: () => request<SimulationRunDTO>("/simulations/calibrations", { method: "POST" }),
    submitBacktest: (body: BacktestRequest) =>
      request<SimulationRunDTO>("/simulations/backtests", { method: "POST", body }),
    candidates: (id: number) => request<CandidatesDTO>(`/simulations/${id}/candidates`),
    lab: (runId?: number) => request<LabDTO>("/simulations/lab", { query: { run_id: runId } }),
    submitLab: () => request<SimulationRunDTO>("/simulations/lab", { method: "POST" }),
    submitCandidates: (body: CandidatesRequest) =>
      request<SimulationRunDTO>("/simulations/candidates", { method: "POST", body }),
    submitProjection: (body: ProjectionRequest) =>
      request<SimulationRunDTO>("/simulations/projections", { method: "POST", body }),
  },
  studies: {
    list: (limit = 50) => request<StudySummaryDTO[]>("/studies", { query: { limit } }),
    get: (id: number) => request<StudyDTO>(`/studies/${id}`),
    create: (body: StudyRequest) => request<StudyDTO>("/studies", { method: "POST", body }),
    refresh: (id: number) => request<StudyDTO>(`/studies/${id}/refresh`, { method: "POST" }),
    variation: (id: number, body: StudyVariationRequest) =>
      request<StudyDTO>(`/studies/${id}/variations`, { method: "POST", body }),
    versions: (id: number) => request<StudyVersionDTO[]>(`/studies/${id}/versions`),
    compare: (a: number, b: number) => request<StudyComparisonDTO>("/studies/compare", { query: { a, b } }),
    remove: (id: number) => request<void>(`/studies/${id}`, { method: "DELETE" }),
  },
  tax: {
    rules: () => request<TaxRuleDTO[]>("/tax/rules"),
    assetStatus: (id: number) => request<AssetTaxStatusDTO>(`/tax/assets/${id}/status`),
    compare: (body: FixedIncomeCompareRequest) =>
      request<FixedIncomeComparisonDTO>("/tax/fixed-income/compare", { method: "POST", body }),
  },
  research: {
    screener: (filters: ScreenerFilters) =>
      request<ScreenerResponseDTO>("/research/screener", { query: { ...filters } }),
    sectors: () => request<string[]>("/research/sectors"),
    treasury: (filters: TreasuryFilters = {}) =>
      request<TreasurySearchResponseDTO>("/research/treasury", { query: { ...filters } }),
    watchlist: () => request<WatchlistItemDTO[]>("/research/watchlist"),
    compare: (tickers: string[], indicators: string[] = []) =>
      request<AssetComparisonDTO>("/research/compare", {
        query: { tickers: tickers.join(","), indicators: indicators.length ? indicators.join(",") : undefined },
      }),
    follow: (body: WatchlistAddRequest) =>
      request<WatchlistItemDTO>("/research/watchlist", { method: "POST", body }),
    unfollow: (assetId: number) =>
      request<void>(`/research/watchlist/${assetId}`, { method: "DELETE" }),
    classify: (assetId: number, arcaClass: ArcaClass) =>
      request<WatchlistItemDTO>(`/research/watchlist/${assetId}/classification`, {
        method: "PUT",
        body: { arca_class: arcaClass },
      }),
  },
  contributions: {
    list: (status?: ContributionPlanStatus) =>
      request<SavedContributionPlanDTO[]>("/contributions", { query: { status } }),
    get: (id: number) => request<SavedContributionPlanDTO>(`/contributions/${id}`),
    draft: (body: ContributionSimulationRequest) =>
      request<SavedContributionPlanDTO>("/contributions", { method: "POST", body }),
    confirm: (id: number, body: ContributionConfirmRequest) =>
      request<SavedContributionPlanDTO>(`/contributions/${id}/confirm`, { method: "POST", body }),
    discard: (id: number) =>
      request<SavedContributionPlanDTO>(`/contributions/${id}/discard`, { method: "POST" }),
  },
  ledger: {
    trades: (filters: LedgerFilters = {}) =>
      request<PaginatedResponse_TransactionResponseDTO_>("/transactions", {
        query: { page_size: 50, ...newestFirst, ...filters },
      }),
    trade: (id: number) => request<TransactionResponseDTO>(`/transactions/${id}`),
    createTrade: (body: TransactionCreateRequest) =>
      request<TransactionResponseDTO>("/transactions", { method: "POST", body }),
    updateTrade: (id: number, body: TransactionUpdateRequest) =>
      request<TransactionResponseDTO>(`/transactions/${id}`, { method: "PUT", body }),
    deleteTrade: (id: number) => request<void>(`/transactions/${id}`, { method: "DELETE" }),
    earnings: (filters: LedgerFilters = {}) =>
      request<PaginatedResponse_EarningResponseDTO_>("/earnings", {
        query: { page_size: 50, ...newestFirst, ...filters },
      }),
    earning: (id: number) => request<EarningResponseDTO>(`/earnings/${id}`),
    createEarning: (body: EarningCreateRequest) =>
      request<EarningResponseDTO>("/earnings", { method: "POST", body }),
    updateEarning: (id: number, body: EarningUpdateRequest) =>
      request<EarningResponseDTO>(`/earnings/${id}`, { method: "PUT", body }),
    deleteEarning: (id: number) => request<void>(`/earnings/${id}`, { method: "DELETE" }),
    events: (assetId?: number) =>
      request<CorporateEventDTO[]>("/corporate-events", { query: { asset_id: assetId } }),
    createEvent: (body: CorporateEventRequest) =>
      request<CorporateEventDTO>("/corporate-events", { method: "POST", body }),
    deleteEvent: (id: number) => request<void>(`/corporate-events/${id}`, { method: "DELETE" }),
    /** `skipLines`: statement line numbers left out of the import. */
    previewImport: (file: File, skipLines: number[] = []) => {
      const form = new FormData();
      form.append("file", file);
      if (skipLines.length > 0) form.append("skip_lines", skipLines.join(","));
      return request<ImportPreviewDTO>("/imports/b3/preview", { method: "POST", form });
    },
    /** `newAssets`: unknown tickers to register, with the type and ARCA quadrant chosen. */
    commitImport: (
      file: File,
      accountId: number | null,
      newAssets: ImportNewAssetRequest[],
      skipLines: number[] = [],
    ) => {
      const form = new FormData();
      form.append("file", file);
      if (accountId !== null) form.append("account_id", String(accountId));
      form.append("new_assets", JSON.stringify(newAssets));
      if (skipLines.length > 0) form.append("skip_lines", skipLines.join(","));
      return request<ImportCommitDTO>("/imports/b3/commit", { method: "POST", form });
    },
  },
  policy: {
    current: () => request<PolicyDTO>("/policy"),
    versions: () => request<PolicyDTO[]>("/policy/versions"),
    save: (body: PolicyUpdateRequest) => request<PolicyDTO>("/policy", { method: "PUT", body }),
  },
  accounts: {
    list: () => request<AccountDTO[]>("/accounts"),
    create: (body: AccountRequest) => request<AccountDTO>("/accounts", { method: "POST", body }),
    update: (id: number, body: AccountRequest) =>
      request<AccountDTO>(`/accounts/${id}`, { method: "PUT", body }),
  },
  market: {
    series: () => request<SeriesStatusDTO[]>("/market/series-status"),
    forecastQuality: () => request<ForecastQualityDTO>("/market/forecast-quality"),
    jobs: () => request<JobRunDTO[]>("/market/job-runs"),
    quoteStatus: () => request<QuoteStatusDTO>("/market/quotes/status"),
    requestJob: (name: string) =>
      request<JobRunDTO>(`/market/job-runs/${encodeURIComponent(name)}/request`, { method: "POST" }),
    workerErrors: (includeResolved = false) =>
      request<WorkerErrorsResponseDTO>("/market/worker-errors", {
        query: { include_resolved: includeResolved },
      }),
    resolveWorkerError: (errorId: number) =>
      request<void>(`/market/worker-errors/${errorId}`, { method: "DELETE" }),
    resolveAllWorkerErrors: () =>
      request<void>("/market/worker-errors", { method: "DELETE" }),
  },
  agents: {
    options: () => request<GrantOptionsDTO>("/agents/keys/options"),
    list: () => request<AgentKeyDTO[]>("/agents/keys"),
    get: (id: number) => request<AgentKeyDTO>(`/agents/keys/${id}`),
    create: (body: AgentKeyCreateRequest) =>
      request<AgentKeyCreatedDTO>("/agents/keys", { method: "POST", body }),
    update: (id: number, body: AgentKeyUpdateRequest) =>
      request<AgentKeyDTO>(`/agents/keys/${id}`, { method: "PUT", body }),
    renew: (id: number, expiresInDays: KeyExpiryDays) =>
      request<AgentKeyDTO>(`/agents/keys/${id}/renew`, {
        method: "POST",
        body: { expires_in_days: expiresInDays },
      }),
    revoke: (id: number) => request<void>(`/agents/keys/${id}`, { method: "DELETE" }),
  },
};
