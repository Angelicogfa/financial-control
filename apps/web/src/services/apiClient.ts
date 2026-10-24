/** API Client for communicating with the FastAPI backend (/api/v1) with clean empty initial state. */

import type {
  ArcaTargetItemDTO,
  AssetCreatePayload,
  AssetDTO,
  CerradoUpdatePayload,
  ContributionPlanDTO,
  EarningCreatePayload,
  EarningDTO,
  IntraClassStrategy,
  PaginatedResponse,
  PortfolioAnalyticsDTO,
  PortfolioReportDTO,
  TransactionCreatePayload,
  TransactionDTO,
} from "../types/api";

export const EMPTY_PORTFOLIO_REPORT: PortfolioReportDTO = {
  as_of_date: new Date().toISOString().slice(0, 10),
  total_invested_brl: 0.0,
  total_gross_value_brl: 0.0,
  total_estimated_tax_brl: 0.0,
  total_current_value_brl: 0.0,
  total_unrealized_pnl_brl: 0.0,
  total_unrealized_pnl_pct: 0.0,
  total_realized_pnl_brl: 0.0,
  total_received_earnings_brl: 0.0,
  total_earnings_12m_brl: 0.0,
  portfolio_yield_on_cost_pct: 0.0,
  total_estimated_yield_to_date_brl: 0.0,
  total_projected_12m_yield_brl: 0.0,
  total_projected_12m_value_brl: 0.0,
  total_consolidated_pnl_brl: 0.0,
  total_consolidated_return_pct: 0.0,
  allocations: [
    {
      arca_class: "ACOES",
      label: "Ações Brasil",
      invested_value: 0.0,
      current_value: 0.0,
      current_pct: 0.0,
      target_pct: 25.0,
      deviation_pct: -25.0,
      gap_value: 0.0,
      consolidated_pnl: 0.0,
    },
    {
      arca_class: "REAL_ESTATE",
      label: "Real Estate",
      invested_value: 0.0,
      current_value: 0.0,
      current_pct: 0.0,
      target_pct: 25.0,
      deviation_pct: -25.0,
      gap_value: 0.0,
      consolidated_pnl: 0.0,
    },
    {
      arca_class: "CAIXA",
      label: "Caixa & Renda Fixa",
      invested_value: 0.0,
      current_value: 0.0,
      current_pct: 0.0,
      target_pct: 25.0,
      deviation_pct: -25.0,
      gap_value: 0.0,
      consolidated_pnl: 0.0,
    },
    {
      arca_class: "ATIVOS_INTERNACIONAIS",
      label: "Ativos Internacionais",
      invested_value: 0.0,
      current_value: 0.0,
      current_pct: 0.0,
      target_pct: 25.0,
      deviation_pct: -25.0,
      gap_value: 0.0,
      consolidated_pnl: 0.0,
    },
  ],
  positions: [],
  earnings_by_month: {},
};

export const EMPTY_ANALYTICS: PortfolioAnalyticsDTO = {
  summary: {
    observations: 0,
    cumulative_return: 0.0,
    cagr: 0.0,
    real_return_vs_ipca: 0.0,
    annualized_volatility: 0.0,
    sharpe_ratio: 0.0,
    sortino_ratio: 0.0,
    max_drawdown: 0.0,
    calmar_ratio: 0.0,
    var_95_historical: 0.0,
    var_95_parametric: 0.0,
    cvar_95: 0.0,
    benchmarks: [
      { benchmark: "CDI", benchmark_return: 0.0, excess_return: 0.0 },
      { benchmark: "IPCA", benchmark_return: 0.0, excess_return: 0.0 },
      { benchmark: "IBOV", benchmark_return: 0.0, excess_return: 0.0 },
      { benchmark: "IFIX", benchmark_return: 0.0, excess_return: 0.0 },
      { benchmark: "SP500", benchmark_return: 0.0, excess_return: 0.0 },
    ],
    drawdown_curve: [],
  },
  correlation_matrix: {},
};

export function computeLocalContributionPlan(
  report: PortfolioReportDTO,
  amountBrl: number,
  strategy: IntraClassStrategy,
): ContributionPlanDTO {
  const safeAmount = Math.max(0, amountBrl);
  const currentTotal = report.total_current_value_brl;
  const newTotal = currentTotal + safeAmount;

  const deficits = report.allocations.map((a) => ({
    arca_class: a.arca_class,
    deficit: Math.max(0, (a.target_pct / 100) * newTotal - a.current_value),
  }));
  const totalDeficit = deficits.reduce((acc, d) => acc + d.deficit, 0);

  const byClassAllocated: Record<string, number> = {
    ACOES: 0,
    REAL_ESTATE: 0,
    CAIXA: 0,
    ATIVOS_INTERNACIONAIS: 0,
  };

  for (const d of deficits) {
    byClassAllocated[d.arca_class] =
      totalDeficit > 0
        ? Number(((safeAmount * d.deficit) / totalDeficit).toFixed(2))
        : Number((safeAmount / 4).toFixed(2));
  }

  const orders = report.positions.map((pos) => {
    const classPositions = report.positions.filter((p) => p.arca_class === pos.arca_class);
    const classBudget = byClassAllocated[pos.arca_class] || 0;
    let weight = 1 / Math.max(1, classPositions.length);

    if (strategy === "CERRADO") {
      const totalScore = classPositions.reduce(
        (acc, p) => acc + Math.max(1, p.cerrado_evaluation.score),
        0,
      );
      weight = Math.max(1, pos.cerrado_evaluation.score) / Math.max(1, totalScore);
    } else if (strategy === "MANUAL_WEIGHT") {
      weight = (pos.class_target_weight_pct || 100 / Math.max(1, classPositions.length)) / 100;
    }

    const allocated = Number((classBudget * weight).toFixed(2));
    const unitBrl = Math.max(0.01, pos.current_unit_price * pos.fx_rate);
    const isIntegerType = ["STOCK_BR", "ETF_BR", "FII", "BDR"].includes(pos.asset_type);
    const qty = isIntegerType
      ? Math.floor(allocated / unitBrl)
      : Number((allocated / unitBrl).toFixed(4));
    const executed = Number((qty * unitBrl).toFixed(2));

    return {
      asset_id: pos.asset_id,
      ticker: pos.ticker,
      name: pos.name,
      asset_type: pos.asset_type,
      arca_class: pos.arca_class,
      cerrado_score: pos.cerrado_evaluation.score,
      cerrado_recommendation:
        strategy === "EQUAL_WEIGHT"
          ? "PESO IGUAL (CERRADO OFF)"
          : pos.cerrado_evaluation.recommendation,
      intra_class_target_weight_pct: Number((weight * 100).toFixed(2)),
      allocated_amount_brl: allocated,
      unit_price_brl: Number(unitBrl.toFixed(2)),
      recommended_quantity: qty,
      executed_amount_brl: executed,
      projected_value_brl: Number((pos.current_value_brl + executed).toFixed(2)),
    };
  });

  const executedTotal = Number(
    orders.reduce((acc, o) => acc + o.executed_amount_brl, 0).toFixed(2),
  );

  return {
    contribution_amount_brl: safeAmount,
    executed_total_brl: executedTotal,
    unallocated_cash_brl: Number(Math.max(0, safeAmount - executedTotal).toFixed(2)),
    by_class_allocated_brl: byClassAllocated as ContributionPlanDTO["by_class_allocated_brl"],
    orders,
    projected_allocations: report.allocations,
  };
}

async function parseError(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (body.detail) {
      return JSON.stringify(body.detail);
    }
  } catch {
    // ignore JSON parse error
  }
  return `HTTP ${resp.status}`;
}

export async function fetchPortfolioReport(): Promise<PortfolioReportDTO> {
  try {
    const resp = await fetch("/api/v1/portfolio/consolidated");
    if (resp.ok) {
      return (await resp.json()) as PortfolioReportDTO;
    }
  } catch {
    // Return clean empty report when offline
  }
  return EMPTY_PORTFOLIO_REPORT;
}

export async function fetchAssets(): Promise<AssetDTO[]> {
  try {
    const resp = await fetch("/api/v1/assets?page=1&page_size=200&sort_by=ticker&sort_order=asc");
    if (resp.ok) {
      const data = (await resp.json()) as PaginatedResponse<AssetDTO>;
      return data.items;
    }
  } catch {
    // Return empty list when offline
  }
  return [];
}

export async function createAsset(payload: AssetCreatePayload): Promise<AssetDTO> {
  const resp = await fetch("/api/v1/assets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw new Error(await parseError(resp));
  }
  return (await resp.json()) as AssetDTO;
}

export async function deleteAsset(assetId: number): Promise<void> {
  const resp = await fetch(`/api/v1/assets/${assetId}?hard=true`, {
    method: "DELETE",
  });
  if (!resp.ok) {
    throw new Error(await parseError(resp));
  }
}

export async function updateAssetCerrado(
  assetId: number,
  payload: CerradoUpdatePayload,
): Promise<AssetDTO> {
  const resp = await fetch(`/api/v1/assets/${assetId}/cerrado`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw new Error(await parseError(resp));
  }
  return (await resp.json()) as AssetDTO;
}

export async function fetchTransactions(): Promise<TransactionDTO[]> {
  try {
    const resp = await fetch(
      "/api/v1/transactions?page=1&page_size=200&sort_by=trade_date&sort_order=desc",
    );
    if (resp.ok) {
      const data = (await resp.json()) as PaginatedResponse<TransactionDTO>;
      return data.items;
    }
  } catch {
    // Return empty list when offline
  }
  return [];
}

export async function createTransaction(
  payload: TransactionCreatePayload,
): Promise<TransactionDTO> {
  const resp = await fetch("/api/v1/transactions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw new Error(await parseError(resp));
  }
  return (await resp.json()) as TransactionDTO;
}

export async function deleteTransaction(txId: number): Promise<void> {
  const resp = await fetch(`/api/v1/transactions/${txId}`, {
    method: "DELETE",
  });
  if (!resp.ok) {
    throw new Error(await parseError(resp));
  }
}

export async function fetchEarnings(): Promise<EarningDTO[]> {
  try {
    const resp = await fetch(
      "/api/v1/earnings?page=1&page_size=200&sort_by=payment_date&sort_order=desc",
    );
    if (resp.ok) {
      const data = (await resp.json()) as PaginatedResponse<EarningDTO>;
      return data.items;
    }
  } catch {
    // Return empty list when offline
  }
  return [];
}

export async function createEarning(payload: EarningCreatePayload): Promise<EarningDTO> {
  const resp = await fetch("/api/v1/earnings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw new Error(await parseError(resp));
  }
  return (await resp.json()) as EarningDTO;
}

export async function deleteEarning(earningId: number): Promise<void> {
  const resp = await fetch(`/api/v1/earnings/${earningId}`, {
    method: "DELETE",
  });
  if (!resp.ok) {
    throw new Error(await parseError(resp));
  }
}

export async function simulateContribution(
  amountBrl: number,
  strategy: IntraClassStrategy,
): Promise<ContributionPlanDTO | null> {
  try {
    const resp = await fetch("/api/v1/portfolio/contribution", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        amount_brl: amountBrl,
        strategy_override: strategy,
      }),
    });
    if (resp.ok) {
      return (await resp.json()) as ContributionPlanDTO;
    }
  } catch {
    // Fallback to local calculation if API call fails
  }
  return null;
}

export async function fetchPortfolioAnalytics(): Promise<PortfolioAnalyticsDTO> {
  try {
    const resp = await fetch("/api/v1/portfolio/analytics");
    if (resp.ok) {
      return (await resp.json()) as PortfolioAnalyticsDTO;
    }
  } catch {
    // Return empty analytics when offline
  }
  return EMPTY_ANALYTICS;
}

export async function fetchArcaTargets(): Promise<ArcaTargetItemDTO[]> {
  try {
    const resp = await fetch("/api/v1/settings/arca-targets");
    if (resp.ok) {
      return (await resp.json()) as ArcaTargetItemDTO[];
    }
  } catch {
    // Return default 25% targets when offline
  }
  return [
    { arca_class: "ACOES", target_pct: 25, intra_class_strategy: "CERRADO" },
    { arca_class: "REAL_ESTATE", target_pct: 25, intra_class_strategy: "CERRADO" },
    { arca_class: "CAIXA", target_pct: 25, intra_class_strategy: "CERRADO" },
    { arca_class: "ATIVOS_INTERNACIONAIS", target_pct: 25, intra_class_strategy: "CERRADO" },
  ];
}

export async function updateArcaTargets(
  targets: ArcaTargetItemDTO[],
): Promise<ArcaTargetItemDTO[]> {
  const resp = await fetch("/api/v1/settings/arca-targets", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ targets }),
  });
  if (!resp.ok) {
    throw new Error(await parseError(resp));
  }
  return (await resp.json()) as ArcaTargetItemDTO[];
}
