import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  BacktestSummaryDTO,
  PercentilesDTO,
  ProjectionDTO,
  ProjectionScenarioDTO,
  RobustnessDTO,
  SimulationResultDTO,
  SimulationRunDetailDTO,
  SimulationRunDTO,
} from "../api/types";
import {
  ProjectionView,
  RobustnessView,
  isActive,
  seriesOf,
  toBacktestRequest,
  toProjectionRequest,
} from "../pages/tools/SimulationPage";
import { mockApi, type Call } from "./mockApi";
import { renderAt } from "./render";

const last = (calls: Call[], method: string, path: string) =>
  [...calls].reverse().find((c) => c.method === method && c.path === path);

function summary(overrides: Partial<BacktestSummaryDTO> = {}): BacktestSummaryDTO {
  return {
    final_value: 15000,
    contributed: 12000,
    gain: 3000,
    money_weighted_return: 0.11,
    time_weighted_return: 0.25,
    annual_twr: 0.1,
    volatility: 0.15,
    max_drawdown: -0.2,
    trades: 30,
    fees: 12,
    taxes: 40,
    ...overrides,
  };
}

function result(key: string, label: string, overrides: Partial<SimulationResultDTO> = {}): SimulationResultDTO {
  return {
    key,
    label,
    summary: summary(),
    points: [
      { day: "2020-01-31", contribution: 1000, contributed: 1000, market_value: 1000, cash: 0, fees: 0, by_class: { ACOES: 1000 } },
      { day: "2020-02-28", contribution: 1000, contributed: 2000, market_value: 2100, cash: 100, fees: 1, by_class: { ACOES: 2000 } },
    ],
    unavailable: [],
    survivorship_bias: false,
    ...overrides,
  };
}

function run(overrides: Partial<SimulationRunDTO> = {}): SimulationRunDTO {
  return {
    id: 1,
    kind: "BACKTEST",
    status: "DONE",
    label: "Base",
    params: { start: "2020-01-01", end: "2020-03-01" },
    params_hash: "abcdef1234567890",
    data_hash: "0123456789abcdef",
    code_version: "33.4.0",
    seed: 7,
    created_at: "2026-10-28T12:00:00Z",
    ...overrides,
  };
}

function detail(overrides: Partial<SimulationRunDetailDTO> = {}): SimulationRunDetailDTO {
  return {
    ...run(),
    results: [result("strategy", "Estratégia"), result("benchmark:CDI", "CDI"), result("variant:band5:hold", "Banda 5")],
    ...overrides,
  };
}

const dist = { count: 2, minimum: 0.08, median: 0.09, maximum: 0.1 };
const window = { covered: true, months: 6, return_rate: -0.12, max_drawdown: -0.18 };

function robustness(overrides: Partial<RobustnessDTO> = {}): RobustnessDTO {
  return {
    run_id: 1,
    status: "DONE",
    series: [
      { key: "strategy", label: "Estratégia" },
      { key: "benchmark:CDI", label: "CDI" },
    ],
    crises: [
      {
        key: "COVID_2020",
        label: "Covid",
        start: "2020-02-01",
        end: "2020-03-31",
        outcomes: { strategy: window, "benchmark:CDI": { covered: false, months: 0 } },
      },
    ],
    shocks: [
      {
        key: "EQUITY_MINUS_30",
        label: "Ações −30% num mês",
        before: 10000,
        after: 8000,
        change: -2000,
        change_rate: -0.2,
        by_class: {},
        note: "",
      },
    ],
    variants: [
      {
        key: "variant:band5:hold",
        label: "Banda 5 p.p., só aportando",
        band_pct: 5,
        rebalance: false,
        summary: summary({ annual_twr: 0.08 }),
        selection: window,
        holdout: { covered: false, months: 0 },
      },
      {
        key: "variant:band5:rebalance",
        label: "Banda 5 p.p., rebalanceando",
        band_pct: 5,
        rebalance: true,
        summary: summary({ annual_twr: 0.1 }),
        selection: window,
        holdout: window,
      },
    ],
    annual_twr_distribution: dist,
    selection_distribution: dist,
    holdout_distribution: dist,
    holdout_start: "2023-03-01",
    trials_in_run: 2,
    trials_total: 10,
    warnings: ["Amostra curta: 2 meses (menos de 60)."],
    ...overrides,
  };
}

describe("simulation helpers", () => {
  it("builds the backtest request and rejects a missing contribution", () => {
    const form = {
      start: "2010-01-01",
      end: "2020-01-01",
      monthly: "1.500,50",
      initial: "",
      correctByIpca: true,
      rebalance: false,
      universe: "REGISTERED" as const,
      policyMode: "CURRENT" as const,
      benchmarks: ["CDI" as const],
      variants: true,
      label: "  ",
    };
    expect(toBacktestRequest(form)).toMatchObject({
      monthly_contribution: 1500.5,
      initial_contribution: 0,
      variants: true,
      benchmarks: ["CDI"],
      label: null,
    });
    expect(toBacktestRequest({ ...form, monthly: "0" })).toBeNull();
    expect(toBacktestRequest({ ...form, monthly: "" })).toBeNull();
  });

  it("keeps variants out of the series and flags active runs", () => {
    expect(seriesOf(detail().results ?? []).map((r) => r.key)).toEqual(["strategy", "benchmark:CDI"]);
    expect(isActive("PENDING")).toBe(true);
    expect(isActive("RUNNING")).toBe(true);
    expect(isActive("DONE")).toBe(false);
    expect(isActive("TIMEOUT")).toBe(false);
  });
});

describe("RobustnessView", () => {
  it("shows crises, shocks, every variant, the trial count and the sample warnings", () => {
    render(<RobustnessView data={robustness()} />);
    expect(screen.getByText("Amostra curta: 2 meses (menos de 60).")).toBeInTheDocument();

    const crises = screen.getByRole("table", { name: "Crises históricas" });
    expect(within(crises).getByText("Covid")).toBeInTheDocument();
    expect(within(crises).getByText("-12,0%")).toBeInTheDocument();
    expect(within(crises).getByText("fora do período")).toBeInTheDocument();

    const shocks = screen.getByRole("table", { name: "Choques sintéticos" });
    expect(within(shocks).getByText("Ações −30% num mês")).toBeInTheDocument();

    expect(screen.getByText(/2 variantes nesta simulação · 10 testadas ao todo/)).toBeInTheDocument();
    const variants = screen.getByRole("table", { name: "Variantes" });
    expect(within(variants).getAllByRole("row")).toHaveLength(3);
    expect(within(variants).getByText("Até 01/03/2023")).toBeInTheDocument();
  });

  it("explains how to get variants and waits for an unfinished run", () => {
    const { unmount } = render(<RobustnessView data={robustness({ variants: [], trials_in_run: 0 })} />);
    expect(screen.getByText("Esta simulação não testou variantes")).toBeInTheDocument();
    unmount();
    render(<RobustnessView data={robustness({ status: "RUNNING" })} />);
    expect(screen.getByText("A robustez aparece quando a simulação terminar")).toBeInTheDocument();
  });
});

describe("SimulationPage", () => {
  it("lists runs, shows the past of the latest one and switches to robustness", async () => {
    mockApi([
      { path: "/simulations", reply: [run()] },
      { path: "/simulations/1", reply: detail() },
      { path: "/simulations/1/robustness", reply: robustness() },
    ]);
    renderAt("/tools/simulation");
    expect(await screen.findByRole("heading", { name: "Simular carteira" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Base" })).toBeInTheDocument();

    const table = await screen.findByRole("table", { name: "Resumo" });
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Métrica", "Estratégia", "CDI"]);
    expect(screen.getByText(/Motor 33\.4\.0 · semente 7/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Robustez" }));
    expect(await screen.findByRole("table", { name: "Crises históricas" })).toBeInTheDocument();
  });

  it("submits a backtest with variants and selects the new run", async () => {
    const { calls } = mockApi([
      { path: "/simulations", reply: [] },
      { method: "POST", path: "/simulations/backtests", reply: run({ id: 2, status: "PENDING", label: null }) },
      { path: "/simulations/2", reply: detail({ id: 2, status: "PENDING", results: [] }) },
    ]);
    renderAt("/tools/simulation");
    expect(await screen.findByText("Nenhuma simulação ainda")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Aporte mensal (R$)"), { target: { value: "2000" } });
    fireEvent.click(screen.getByRole("button", { name: "Simular" }));

    expect(await screen.findByText(/Na fila do worker/)).toBeInTheDocument();
    const body = last(calls, "POST", "/simulations/backtests")?.body as Record<string, unknown>;
    expect(body).toMatchObject({ monthly_contribution: 2000, variants: true, benchmarks: ["CDI", "IBOV"] });
  });

  it("shows a failed run and rejects a zero contribution", async () => {
    mockApi([
      { path: "/simulations", reply: [run({ status: "TIMEOUT", error: "120 s" })] },
      { path: "/simulations/1", reply: detail({ status: "TIMEOUT", error: "120 s", results: [] }) },
    ]);
    renderAt("/tools/simulation");
    expect(await screen.findByText(/A simulação passou do tempo limite/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Aporte mensal (R$)"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Simular" }));
    expect(await screen.findByText("Informe um aporte mensal maior que zero.")).toBeInTheDocument();
  });
});

// --- future ------------------------------------------------------------------------------------

const band = (p50: number): PercentilesDTO => ({ p5: p50 * 0.6, p25: p50 * 0.8, p50, p75: p50 * 1.2, p95: p50 * 1.5 });

function scenario(name: string, label: string, overrides: Partial<ProjectionScenarioDTO> = {}): ProjectionScenarioDTO {
  return {
    key: `projection:${name}`,
    label,
    scenario: { name, annual_cdi_rate: 0.1, annual_ipca_rate: 0.04 },
    paths: 5000,
    horizon_months: 24,
    points: [
      { month: 0, contributed: 10000, wealth: band(10000), income: band(50) },
      { month: 12, contributed: 22000, wealth: band(24000), income: band(110) },
      { month: 24, contributed: 34000, wealth: band(40000), income: band(180) },
    ],
    final_wealth: band(40000),
    final_net_wealth: band(38000),
    final_income: band(180),
    max_drawdown: { p5: -0.3, p25: -0.2, p50: -0.15, p75: -0.1, p95: -0.05 },
    contributed: 34000,
    wealth_goal: { target: 35000, probability: 0.72, standard_error: 0.0063, months: { p5: 18, p25: 20, p50: 22, p75: 24, p95: 24 } },
    income_goal: { target: 10000, probability: 0, standard_error: 0, months: null },
    premises: [
      { arca_class: "ACOES", proxy: "IBOV", excess_annual: 0.031, volatility: 0.22, expected_annual: 0.134, income_yield: 0.05 },
      { arca_class: "CAIXA", proxy: "CDI", excess_annual: 0, volatility: 0, expected_annual: 0.085, income_yield: 0.04 },
    ],
    fees: 10,
    taxes: 0,
    ...overrides,
  };
}

function projection(overrides: Partial<ProjectionDTO> = {}): ProjectionDTO {
  return {
    run_id: 5,
    status: "DONE",
    scenarios: [
      scenario("LOW", "Juros em queda", { final_wealth: band(30000) }),
      scenario("BASE", "Juros na premissa"),
      scenario("HIGH", "Juros em alta", { final_wealth: band(50000) }),
    ],
    sample_start: "2010-01-29",
    sample_end: "2026-09-30",
    sample_months: 200,
    classes: ["ACOES", "CAIXA"],
    targets: { ACOES: 60, CAIXA: 40 },
    warnings: ["Simulação, não recomendação: teste."],
    ...overrides,
  };
}

const projectionRun = run({
  id: 5,
  kind: "PROJECTION",
  label: "Aposentadoria",
  params: { horizon_years: 2, monthly_contribution: 1000, mean_block_months: 12 },
});

describe("projection helpers", () => {
  const form = {
    horizonYears: "20",
    monthly: "1500",
    realGrowth: "1,5",
    wealthGoal: "1000000",
    incomeGoal: "",
    rebalance: true,
    fromPortfolio: true,
    initial: { ACOES: "0", REAL_ESTATE: "0", ATIVOS_INTERNACIONAIS: "0", CAIXA: "0" },
    cdi: "",
    ipca: "4,5",
    label: "",
  };

  it("converts percentages and leaves the starting point to the server", () => {
    expect(toProjectionRequest(form)).toEqual({
      horizon_years: 20,
      monthly_contribution: 1500,
      contribution_real_growth: 0.015,
      wealth_goal: 1_000_000,
      income_goal: null,
      rebalance: true,
      initial_by_class: null,
      cdi_rate: null,
      ipca_rate: 0.045,
      label: null,
    });
  });

  it("sends the typed values by class and rejects an invalid horizon", () => {
    const typed = toProjectionRequest({ ...form, fromPortfolio: false, initial: { ...form.initial, ACOES: "5000", CAIXA: "-1" } });
    expect(typed?.initial_by_class).toEqual({ ACOES: 5000, REAL_ESTATE: 0, ATIVOS_INTERNACIONAIS: 0, CAIXA: 0 });
    expect(toProjectionRequest({ ...form, horizonYears: "0" })).toBeNull();
    expect(toProjectionRequest({ ...form, horizonYears: "51" })).toBeNull();
    expect(toProjectionRequest({ ...form, monthly: "" })).toBeNull();
    expect(toProjectionRequest({ ...form, monthly: "0" })?.monthly_contribution).toBe(0);
  });
});

describe("ProjectionView", () => {
  it("shows the base scenario, the goals, the percentiles and the premises", () => {
    render(<ProjectionView data={projection()} run={projectionRun} />);
    expect(screen.getByText("Simulação, não recomendação: teste.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Juros na premissa" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("72%")).toBeInTheDocument();
    expect(screen.getByText(/Nenhuma trajetória chega à meta/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Faixas prováveis do patrimônio ano a ano" })).toBeInTheDocument();

    const table = screen.getByRole("table", { name: "Percentis ao fim do horizonte" });
    const wealth = within(table).getByText("Patrimônio").closest("tr") as HTMLElement;
    expect(within(wealth).getByText("R$ 40.000,00")).toBeInTheDocument();

    const premises = screen.getByRole("table", { name: "Premissas por classe" });
    expect(within(premises).getByText("CDI líquido de IR")).toBeInTheDocument();
    expect(within(premises).getByText("+3,1%")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Juros em alta" }));
    expect(within(wealth).getByText("R$ 50.000,00")).toBeInTheDocument();
  });

  it("waits for an unfinished projection", () => {
    render(<ProjectionView data={projection({ status: "RUNNING", scenarios: [] })} run={projectionRun} />);
    expect(screen.getByText("A projeção aparece quando a simulação terminar")).toBeInTheDocument();
  });
});

describe("SimulationPage future tab", () => {
  it("lists projections, shows the selected one and submits a new one", async () => {
    const { calls } = mockApi([
      { path: "/simulations", reply: (call: Call) => (call.query.get("kind") === "PROJECTION" ? [projectionRun] : [run()]) },
      { path: "/simulations/5", reply: { ...projectionRun, results: [] } },
      { path: "/simulations/5/projection", reply: projection() },
      { method: "POST", path: "/simulations/projections", reply: { ...projectionRun, id: 6, status: "PENDING" } },
      { path: "/simulations/6", reply: { ...projectionRun, id: 6, status: "PENDING", results: [] } },
    ]);
    renderAt("/tools/simulation?tab=future");
    expect(await screen.findByRole("button", { name: "Aposentadoria" })).toBeInTheDocument();
    expect(screen.getByText("2 anos · R$ 1.000,00/mês")).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: "Percentis ao fim do horizonte" })).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/simulations" && c.query.get("kind") === "PROJECTION")).toBe(true);

    fireEvent.change(screen.getByLabelText("Meta de renda passiva (R$/mês)"), { target: { value: "5000" } });
    fireEvent.click(screen.getByRole("button", { name: "Projetar" }));
    expect(await screen.findByText(/Na fila do worker/)).toBeInTheDocument();
    const body = last(calls, "POST", "/simulations/projections")?.body as Record<string, unknown>;
    expect(body).toMatchObject({ horizon_years: 20, monthly_contribution: 1000, income_goal: 5000, initial_by_class: null });
  });
});
