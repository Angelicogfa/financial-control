/** Typed calls to the API, one group per operation context (ADR 0005). */

import { request } from "./http";
import type {
  AccountDTO,
  AccountRequest,
  AlertDismissRequest,
  AlertsResponseDTO,
  ArcaSuggestionDTO,
  AssetAnalysisResponseDTO,
  AssetCreateRequest,
  AssetResponseDTO,
  AssetType,
  AssetUpdateRequest,
  CerradoUpdateRequest,
  ContributionConfirmRequest,
  ContributionPlanStatus,
  ContributionSimulationRequest,
  CorporateEventDTO,
  CorporateEventRequest,
  EarningCreateRequest,
  EarningResponseDTO,
  EarningUpdateRequest,
  ImportCommitDTO,
  ImportPreviewDTO,
  JobRunDTO,
  PaginatedResponse_AssetResponseDTO_,
  PaginatedResponse_EarningResponseDTO_,
  PaginatedResponse_TransactionResponseDTO_,
  PolicyDTO,
  PolicyUpdateRequest,
  PortfolioAnalyticsResponseDTO,
  PortfolioReportResponseDTO,
  SavedContributionPlanDTO,
  ScreenerResponseDTO,
  SeriesStatusDTO,
  SnapshotPointDTO,
  TransactionCreateRequest,
  TransactionResponseDTO,
  TransactionUpdateRequest,
  WatchlistAddRequest,
  WatchlistItemDTO,
} from "./types";

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
  sector?: string[];
  min_volume_brl?: number;
  max_pe?: number;
  max_pb?: number;
  min_dy?: number;
  min_roe?: number;
  below_band?: boolean;
  exclude_registered?: boolean;
  limit?: number;
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
  research: {
    screener: (filters: ScreenerFilters) =>
      request<ScreenerResponseDTO>("/research/screener", { query: { ...filters } }),
    watchlist: () => request<WatchlistItemDTO[]>("/research/watchlist"),
    follow: (body: WatchlistAddRequest) =>
      request<WatchlistItemDTO>("/research/watchlist", { method: "POST", body }),
    unfollow: (assetId: number) =>
      request<void>(`/research/watchlist/${assetId}`, { method: "DELETE" }),
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
    previewImport: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return request<ImportPreviewDTO>("/imports/b3/preview", { method: "POST", form });
    },
    commitImport: (file: File, accountId: number | null, createTickers: string[]) => {
      const form = new FormData();
      form.append("file", file);
      if (accountId !== null) form.append("account_id", String(accountId));
      form.append("create_tickers", createTickers.join(","));
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
    jobs: () => request<JobRunDTO[]>("/market/job-runs"),
  },
};
