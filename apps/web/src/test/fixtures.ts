/** Typed sample payloads for page tests. */

import type {
  AlertsResponseDTO,
  AssetAnalysisResponseDTO,
  AssetResponseDTO,
  CerradoEvaluationDTO,
  ClassAllocationDTO,
  PortfolioAnalyticsResponseDTO,
  PortfolioReportResponseDTO,
  RiskReturnSummaryDTO,
  SavedContributionPlanDTO,
  ValuedPositionDTO,
} from "../api/types";

export function evaluation(overrides: Partial<CerradoEvaluationDTO> = {}): CerradoEvaluationDTO {
  return {
    profile: "STOCK",
    checklist_version: 2,
    use_cerrado: true,
    score: 2,
    max_score: 12,
    normalized_score: 0.17,
    coverage_pct: 33.3,
    answered: 4,
    applicable: 12,
    not_applicable: 0,
    pending: 8,
    recommendation: "APTO",
    answers: [
      {
        question_id: "roe",
        text: "ROE historicamente acima de 5%?",
        category: "Rentabilidade",
        hint: "",
        value: "YES",
        answer: true,
        source: "AUTO",
        automatable: true,
        evidence: "ROE médio 18,0% em 5 anos (2020-2024)",
      },
      {
        question_id: "governance",
        text: "Tem boa governança?",
        category: "Governança",
        hint: "",
        value: null,
        answer: null,
        source: "PENDING",
        automatable: false,
      },
    ],
    ...overrides,
  };
}

export function position(overrides: Partial<ValuedPositionDTO> = {}): ValuedPositionDTO {
  return {
    asset_id: 1,
    ticker: "WEGE3",
    name: "WEG",
    asset_type: "STOCK_BR",
    arca_class: "ACOES",
    currency: "BRL",
    quantity: 100,
    average_price: 40,
    current_unit_price: 50,
    fx_rate: 1,
    price_freshness: "LIVE",
    invested_value_brl: 4000,
    gross_current_value_brl: 5000,
    estimated_tax_brl: 0,
    current_value_brl: 5000,
    unrealized_pnl_brl: 1000,
    unrealized_pnl_pct: 25,
    realized_pnl_brl: 0,
    received_earnings_brl: 120,
    earnings_12m_brl: 120,
    yield_on_cost_pct: 3,
    estimated_yield_to_date_brl: 0,
    estimated_yield_to_date_pct: 0,
    estimated_yield_basis: "",
    projected_12m_yield_brl: 0,
    consolidated_pnl_brl: 1120,
    consolidated_return_pct: 28,
    cerrado_evaluation: evaluation(),
    class_target_weight_pct: 100,
    class_current_weight_pct: 100,
    lifecycle_status: "HELD",
    ...overrides,
  };
}

export function allocation(overrides: Partial<ClassAllocationDTO> = {}): ClassAllocationDTO {
  return {
    arca_class: "ACOES",
    label: "Ações",
    invested_value: 4000,
    current_value: 5000,
    current_pct: 100,
    target_pct: 25,
    deviation_pct: 75,
    gap_value: -3750,
    consolidated_pnl: 1120,
    band_pct: 5,
    band_status: "ABOVE",
    ...overrides,
  };
}

export function report(overrides: Partial<PortfolioReportResponseDTO> = {}): PortfolioReportResponseDTO {
  return {
    as_of_date: "2026-03-10",
    total_invested_brl: 4000,
    total_gross_value_brl: 5000,
    total_estimated_tax_brl: 0,
    total_current_value_brl: 5000,
    total_unrealized_pnl_brl: 1000,
    total_unrealized_pnl_pct: 25,
    total_realized_pnl_brl: 0,
    total_received_earnings_brl: 120,
    total_earnings_12m_brl: 120,
    portfolio_yield_on_cost_pct: 3,
    total_estimated_yield_to_date_brl: 0,
    total_projected_12m_yield_brl: 0,
    total_projected_12m_value_brl: 5000,
    total_consolidated_pnl_brl: 1120,
    total_consolidated_return_pct: 28,
    allocations: [
      allocation(),
      allocation({
        arca_class: "REAL_ESTATE",
        label: "Real Estate",
        invested_value: 0,
        current_value: 0,
        current_pct: 0,
        target_pct: 25,
        consolidated_pnl: 0,
        band_status: "BELOW",
      }),
    ],
    positions: [position()],
    earnings_by_month: { "2026-02": 120 },
    value_by_purpose_brl: { ARCA: 5000 },
    ...overrides,
  };
}

export function riskSummary(overrides: Partial<RiskReturnSummaryDTO> = {}): RiskReturnSummaryDTO {
  return {
    observations: 3,
    cumulative_return: 0.05,
    cagr: 0.05,
    real_return_vs_ipca: 0.01,
    annualized_volatility: 0.12,
    sharpe_ratio: 0.8,
    sortino_ratio: 1.1,
    max_drawdown: -0.04,
    calmar_ratio: 1,
    var_95_historical: -0.02,
    var_95_parametric: -0.02,
    cvar_95: -0.03,
    benchmarks: [
      { benchmark: "IBOV", benchmark_return: 0.03, excess_return: 0.02, beta: 0.9, correlation: 0.8 },
    ],
    drawdown_curve: [0, -0.01, -0.04],
    ...overrides,
  };
}

export function analytics(overrides: Partial<PortfolioAnalyticsResponseDTO> = {}): PortfolioAnalyticsResponseDTO {
  return {
    status: "OK",
    available_points: 4,
    summary: riskSummary(),
    correlation_matrix: {},
    curves: {
      PORTFOLIO: [
        { date: "2026-03-01", value: 100 },
        { date: "2026-03-02", value: 101 },
        { date: "2026-03-03", value: 103 },
        { date: "2026-03-04", value: 105 },
      ],
      CDI: [
        { date: "2026-03-01", value: 100 },
        { date: "2026-03-02", value: 100.04 },
        { date: "2026-03-03", value: 100.08 },
        { date: "2026-03-04", value: 100.12 },
      ],
    },
    ...overrides,
  };
}

export function alerts(overrides: Partial<AlertsResponseDTO> = {}): AlertsResponseDTO {
  return {
    alerts: [
      {
        key: "band:REAL_ESTATE:BELOW",
        kind: "CLASS_OUT_OF_BAND",
        severity: "WARNING",
        title: "Real Estate abaixo da banda",
        detail: "Peso atual 0,0% contra meta 25,0% ± 5,0%.",
        subject: "REAL_ESTATE",
        route: "/contribute",
      },
    ],
    dismissed: 0,
    generated_at: "2026-03-10T12:00:00Z",
    ...overrides,
  };
}

export function asset(overrides: Partial<AssetResponseDTO> = {}): AssetResponseDTO {
  return {
    id: 1,
    ticker: "WEGE3",
    name: "WEG",
    asset_type: "STOCK_BR",
    arca_class: "ACOES",
    currency: "BRL",
    use_cerrado: true,
    cerrado_answers: {},
    checklist_profile: "STOCK",
    checklist_answers: {},
    is_active: true,
    purpose: "ARCA",
    ...overrides,
  };
}

export function analysis(overrides: Partial<AssetAnalysisResponseDTO> = {}): AssetAnalysisResponseDTO {
  return {
    asset: asset(),
    position: position(),
    fundamentals: { price_to_earnings: 25, dividend_yield: 0.015, return_on_equity: 0.3 },
    fundamental_history: [
      { reference_date: "2023-12-31", period: "ANNUAL", metrics: { revenue: 100, net_income: 10 } },
      { reference_date: "2024-12-31", period: "ANNUAL", metrics: { revenue: 120, net_income: 14 } },
    ],
    historical_metrics: {
      years: 2,
      first_year: 2023,
      last_year: 2024,
      roe_average: 0.18,
      revenue_cagr: 0.2,
      earnings_cagr: 0.4,
      profitable_years: 2,
      dividend_years: 2,
      payout_average: 0.5,
      always_profitable: true,
      dividend_regularity: 1,
    },
    valuation: {
      profile: "STOCK",
      applicable: true,
      price: 50,
      methods: [
        { method: "GRAHAM", label: "Preço justo de Graham", kind: "PRICE", value: 60, passes: true, margin: 0.17, note: "" },
        { method: "PE", label: "P/L", kind: "MULTIPLE", value: 25, threshold: 15, passes: false, note: "" },
      ],
      fair_value: 60,
      margin: 0.17,
      verdict: "DISCOUNTED",
      reason: "",
    },
    checklist: evaluation(),
    checklist_history: [
      {
        evaluated_at: "2026-03-01T10:00:00Z",
        profile: "STOCK",
        checklist_version: 2,
        score: 2,
        normalized_score: 0.17,
        coverage_pct: 33.3,
        answered: 4,
        applicable: 12,
        recommendation: "APTO",
      },
    ],
    answer_history: [],
    risk_return: riskSummary(),
    benchmark: "IBOV",
    price_history: [
      { date: "2026-03-01", close: 48 },
      { date: "2026-03-02", close: 50 },
    ],
    ...overrides,
  };
}

export function savedPlan(overrides: Partial<SavedContributionPlanDTO> = {}): SavedContributionPlanDTO {
  return {
    id: 7,
    status: "DRAFT",
    created_at: "2026-03-10T12:00:00Z",
    transaction_ids: [],
    plan: {
      contribution_amount_brl: 1000,
      executed_total_brl: 960,
      unallocated_cash_brl: 40,
      by_class_allocated_brl: { REAL_ESTATE: 1000 },
      orders: [
        {
          asset_id: 3,
          ticker: "HGLG11",
          name: "CSHG",
          asset_type: "FII",
          arca_class: "REAL_ESTATE",
          cerrado_score: 1,
          cerrado_recommendation: "APTO",
          intra_class_target_weight_pct: 100,
          allocated_amount_brl: 1000,
          unit_price_brl: 160,
          recommended_quantity: 6,
          executed_amount_brl: 960,
          projected_value_brl: 960,
        },
      ],
      projected_allocations: [
        allocation({ current_pct: 83.9, band_status: "ABOVE" }),
        allocation({ arca_class: "REAL_ESTATE", label: "Real Estate", current_pct: 16.1, band_status: "BELOW" }),
      ],
    },
    ...overrides,
  };
}
