import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  BacktestSummaryDTO,
  RobustnessDTO,
  SimulationResultDTO,
  SimulationRunDetailDTO,
  SimulationRunDTO,
} from "../api/types";
import { RobustnessView, isActive, seriesOf, toBacktestRequest } from "../pages/tools/SimulationPage";
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
