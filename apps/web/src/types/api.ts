/** TypeScript interfaces matching the FastAPI backend DTO contracts. */

export type ArcaClass =
  | "ACOES"
  | "REAL_ESTATE"
  | "CAIXA"
  | "ATIVOS_INTERNACIONAIS";

export type AssetType =
  | "STOCK_BR"
  | "ETF_BR"
  | "FII"
  | "BDR"
  | "STOCK_INTL"
  | "ETF_INTL"
  | "REIT"
  | "CRYPTO"
  | "FIXED_INCOME"
  | "TREASURY"
  | "CASH";

export type IntraClassStrategy = "CERRADO" | "MANUAL_WEIGHT" | "EQUAL_WEIGHT";

export type TransactionKind = "BUY" | "SELL";

export type EarningKind =
  | "DIVIDEND"
  | "JCP"
  | "FII_YIELD"
  | "FIXED_INCOME_COUPON"
  | "RESTITUTION";

export type FixedIncomeIndexer = "CDI" | "SELIC" | "IPCA" | "PRE";

export type FixedIncomeInstrumentKind =
  | "CDB"
  | "LCI"
  | "LCA"
  | "CRI"
  | "CRA"
  | "DEBENTURE"
  | "TESOURO_SELIC"
  | "TESOURO_IPCA"
  | "TESOURO_PRE"
  | "SAVINGS_BOX";

export interface PageMetaDTO {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
  sort_by: string;
  sort_order: "asc" | "desc";
}

export interface PaginatedResponse<T> {
  items: T[];
  meta: PageMetaDTO;
}

export interface FixedIncomeTermPayload {
  instrument_kind: FixedIncomeInstrumentKind;
  indexer: FixedIncomeIndexer;
  contracted_rate: number | string;
  issue_date: string;
  maturity_date?: string | null;
  tax_exempt: boolean;
  liquidity: "DAILY" | "AT_MATURITY";
  issuer?: string | null;
}

export interface AssetCreatePayload {
  ticker: string;
  name: string;
  asset_type: AssetType;
  arca_class?: ArcaClass | null;
  currency?: string | null;
  manual_price?: number | null;
  custom_class_weight?: number | null;
  use_cerrado: boolean;
  cerrado_answers?: Record<string, boolean>;
  notes?: string | null;
  fixed_income_term?: FixedIncomeTermPayload | null;
}

export interface CerradoUpdatePayload {
  use_cerrado: boolean;
  cerrado_answers?: Record<string, boolean>;
  custom_class_weight?: number | null;
}

export interface AssetDTO {
  id: number;
  ticker: string;
  name: string;
  asset_type: AssetType;
  arca_class: ArcaClass;
  currency: string;
  manual_price?: number | null;
  custom_class_weight?: number | null;
  use_cerrado: boolean;
  cerrado_answers: Record<string, boolean>;
  is_active: boolean;
  notes?: string | null;
  fixed_income_term?: FixedIncomeTermPayload | null;
}

export interface EvaluatedAnswerDTO {
  question_id: string;
  text: string;
  category: string;
  hint: string;
  answer: boolean | null;
  source: string;
  automatable: boolean;
}

export interface CerradoEvaluationDTO {
  asset_type: AssetType;
  use_cerrado: boolean;
  score: number;
  max_score: number;
  answered: number;
  pending: number;
  recommendation: string;
  answers?: EvaluatedAnswerDTO[];
}

export interface ValuedPositionDTO {
  asset_id: number;
  ticker: string;
  name: string;
  asset_type: AssetType;
  arca_class: ArcaClass;
  currency: string;
  quantity: number;
  average_price: number;
  current_unit_price: number;
  fx_rate: number;
  price_freshness: string;
  invested_value_brl: number;
  gross_current_value_brl: number;
  estimated_tax_brl: number;
  current_value_brl: number;
  unrealized_pnl_brl: number;
  unrealized_pnl_pct: number;
  realized_pnl_brl: number;
  received_earnings_brl: number;
  earnings_12m_brl: number;
  yield_on_cost_pct: number;
  estimated_yield_to_date_brl: number;
  estimated_yield_to_date_pct: number;
  estimated_yield_basis: string;
  projected_12m_yield_brl: number;
  consolidated_pnl_brl: number;
  consolidated_return_pct: number;
  cerrado_evaluation: CerradoEvaluationDTO;
  class_target_weight_pct: number;
  class_current_weight_pct: number;
  fx_pnl_brl?: number;
  custom_class_weight?: number | null;
  ledger_status?: "VALID" | "INVALID";
  ledger_message?: string | null;
}

export interface ClassAllocationDTO {
  arca_class: ArcaClass;
  label: string;
  invested_value: number;
  current_value: number;
  current_pct: number;
  target_pct: number;
  deviation_pct: number;
  gap_value: number;
  consolidated_pnl: number;
}

export interface PortfolioReportDTO {
  as_of_date: string;
  total_invested_brl: number;
  total_gross_value_brl: number;
  total_estimated_tax_brl: number;
  total_current_value_brl: number;
  total_unrealized_pnl_brl: number;
  total_unrealized_pnl_pct: number;
  total_realized_pnl_brl: number;
  total_received_earnings_brl: number;
  total_earnings_12m_brl: number;
  portfolio_yield_on_cost_pct: number;
  total_estimated_yield_to_date_brl: number;
  total_projected_12m_yield_brl: number;
  total_projected_12m_value_brl: number;
  total_consolidated_pnl_brl: number;
  total_consolidated_return_pct: number;
  allocations: ClassAllocationDTO[];
  positions: ValuedPositionDTO[];
  earnings_by_month: Record<string, number>;
  total_fx_pnl_brl?: number;
  projection_assumptions?: Record<string, number>;
}

export interface AssetContributionOrderDTO {
  asset_id: number;
  ticker: string;
  name: string;
  asset_type: AssetType;
  arca_class: ArcaClass;
  cerrado_score: number;
  cerrado_recommendation: string;
  intra_class_target_weight_pct: number;
  allocated_amount_brl: number;
  unit_price_brl: number;
  recommended_quantity: number;
  executed_amount_brl: number;
  projected_value_brl: number;
}

export interface ContributionPlanDTO {
  contribution_amount_brl: number;
  executed_total_brl: number;
  unallocated_cash_brl: number;
  by_class_allocated_brl: Record<ArcaClass, number>;
  orders: AssetContributionOrderDTO[];
  projected_allocations: ClassAllocationDTO[];
}

export interface TransactionCreatePayload {
  asset_id: number;
  kind: TransactionKind;
  trade_date: string;
  quantity: number;
  unit_price: number;
  fees?: number;
  fx_rate?: number;
  notes?: string | null;
}

export interface TransactionDTO {
  id: number;
  asset_id: number;
  ticker?: string | null;
  kind: TransactionKind;
  trade_date: string;
  quantity: number;
  unit_price: number;
  fees: number;
  fx_rate: number;
  total_brl: number;
  notes?: string | null;
}

export interface EarningCreatePayload {
  asset_id: number;
  kind: EarningKind;
  payment_date: string;
  gross_amount: number;
  withholding_tax?: number;
  net_amount?: number | null;
  ex_date?: string | null;
  notes?: string | null;
  fx_rate?: number;
}

export interface EarningDTO {
  id: number;
  asset_id: number;
  ticker?: string | null;
  kind: EarningKind;
  payment_date: string;
  ex_date?: string | null;
  gross_amount: number;
  withholding_tax: number;
  net_amount: number;
  fx_rate?: number;
  net_amount_brl?: number;
  notes?: string | null;
}

export interface ArcaTargetItemDTO {
  arca_class: ArcaClass;
  target_pct: number;
  intra_class_strategy: IntraClassStrategy;
}

export interface BenchmarkComparisonDTO {
  benchmark: string;
  benchmark_return: number;
  excess_return: number;
  beta?: number | null;
  alpha_annual?: number | null;
  correlation?: number | null;
}

export interface PortfolioAnalyticsDTO {
  status?: "OK" | "INSUFFICIENT_HISTORY";
  available_points?: number;
  summary: {
    observations: number;
    cumulative_return: number;
    cagr: number;
    real_return_vs_ipca: number;
    annualized_volatility: number;
    sharpe_ratio: number;
    sortino_ratio: number;
    max_drawdown: number;
    calmar_ratio: number;
    var_95_historical: number;
    var_95_parametric: number;
    cvar_95: number;
    benchmarks: BenchmarkComparisonDTO[];
    drawdown_curve: number[];
  };
  correlation_matrix: Record<string, Record<string, number>>;
}
