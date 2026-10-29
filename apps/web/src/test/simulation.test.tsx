import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  BacktestSummaryDTO,
  CalibrationDTO,
  PercentilesDTO,
  ProjectionDTO,
  ProjectionScenarioDTO,
  RobustnessDTO,
  SimulationResultDTO,
  SimulationRunDTO,
} from "../api/types";
import { CalibrationView, ProjectionView, RobustnessView, isActive, seriesOf } from "../pages/simulation/views";

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

describe("RobustnessView validation", () => {
  it("shows the verdict on the best variant with the three tests", () => {
    render(
      <RobustnessView
        data={robustness({
          validation: {
            best: "variant:band5:rebalance",
            best_label: "Banda 5 p.p., rebalanceando",
            best_sharpe_annual: 0.42,
            expected_max_sharpe_annual: 0.61,
            deflated_probability: 0.31,
            trials: 40,
            observations: 120,
            pbo: 0.58,
            pbo_combinations: 252,
            gate_probability: 0.63,
            passed: false,
            verdict: "Sem evidência de que a melhor configuração seja melhor de verdade.",
          },
        })}
      />,
    );
    const section = screen.getByRole("region", { name: "Validação estatística" });
    expect(within(section).getByText("Sem evidência")).toBeInTheDocument();
    expect(within(section).getByText("Banda 5 p.p., rebalanceando")).toBeInTheDocument();
    expect(within(section).getByText(/40 tentativas/)).toBeInTheDocument();
    expect(within(section).getByText("58%", { exact: false })).toBeInTheDocument();
    expect(within(section).getByText(/contra 0,61 esperado do acaso/)).toBeInTheDocument();
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
    wealth_goal: {
      target: 35000,
      probability: 0.72,
      standard_error: 0.0063,
      months: { p5: 18, p25: 20, p50: 22, p75: 24, p95: 24 },
      low: 0.64,
      high: 0.8,
      by_generator: { BOOTSTRAP: 0.8, BAYESIAN_NORMAL: 0.64 },
    },
    income_goal: { target: 10000, probability: 0, standard_error: 0, months: null },
    premises: [
      {
        arca_class: "ACOES",
        proxy: "IBOV",
        excess_annual: 0.031,
        volatility: 0.22,
        expected_annual: 0.134,
        income_yield: 0.05,
        prior_excess_annual: 0.03,
        posterior_excess_annual: 0.025,
      },
      { arca_class: "CAIXA", proxy: "CDI", excess_annual: 0, volatility: 0, expected_annual: 0.085, income_yield: 0.04 },
    ],
    fees: 10,
    taxes: 0,
    events: [
      { key: "LOSS_10_12M", label: "Perder mais de 10% nos primeiros 12 meses", probability: 0.08, standard_error: 0.004, low: 0.06, high: 0.11 },
      { key: "BEAT_CDI", label: "Render mais que o CDI no horizonte", probability: 0.55, standard_error: 0.007, low: 0.5, high: 0.6 },
    ],
    generators: [
      { key: "BOOTSTRAP", label: "Bootstrap em blocos", weight: 0.3, paths: 1500 },
      { key: "BAYESIAN_NORMAL", label: "Normal bayesiana", weight: 0.7, paths: 3500 },
    ],
    prior_months: 84,
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
    calibration_run: 9,
    ...overrides,
  };
}

const projectionRun = run({
  id: 5,
  kind: "PROJECTION",
  label: "Aposentadoria",
  params: { horizon_years: 2, monthly_contribution: 1000, mean_block_months: 12 },
});

describe("ProjectionView", () => {
  it("shows the base scenario, the goals, the percentiles and the premises", () => {
    render(<ProjectionView data={projection()} run={projectionRun} />);
    expect(screen.getByText("Simulação, não recomendação: teste.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Juros na premissa" })).toHaveAttribute("aria-pressed", "true");
    const goal = screen.getByRole("heading", { name: /Meta de patrimônio/ }).closest("div") as HTMLElement;
    expect(within(goal).getByText("72%")).toBeInTheDocument();
    expect(within(goal).getByText("(64% a 80%)")).toBeInTheDocument();
    // The lead and the indicators come first.
    expect(screen.getByRole("note", { name: "Em resumo" })).toHaveTextContent(/chance de chegar à meta .* é de 72%/);
    expect(within(screen.getByLabelText("Indicadores da projeção")).getByText("72%")).toBeInTheDocument();
    expect(screen.getByText(/Por gerador: Bootstrap em blocos 80% · Normal bayesiana 64%/)).toBeInTheDocument();
    const others = screen.getByRole("list", { name: "Outras chances" });
    expect(within(others).getByText(/Perder mais de 10% nos primeiros 12 meses/)).toHaveTextContent("8% (6% a 11%)");
    expect(screen.getByText(/Bootstrap em blocos 30% · Normal bayesiana 70% \(pesos da calibração #9\)/)).toBeInTheDocument();
    expect(screen.getByText(/pesa o equivalente a 84 meses/)).toBeInTheDocument();
    expect(screen.getByText(/Nenhuma trajetória chega à meta/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Faixas prováveis do patrimônio ano a ano" })).toBeInTheDocument();

    const table = screen.getByRole("table", { name: "Percentis ao fim do horizonte" });
    const wealth = within(table).getByText("Patrimônio").closest("tr") as HTMLElement;
    expect(within(wealth).getByText("R$ 40.000,00")).toBeInTheDocument();

    const premises = screen.getByRole("table", { name: "Premissas por classe" });
    expect(within(premises).getByText("CDI líquido de IR")).toBeInTheDocument();
    expect(within(premises).getByText("+3,1%")).toBeInTheDocument();
    expect(within(premises).getByText("+3,0%")).toBeInTheDocument();
    expect(within(premises).getByText("+2,5%")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Juros em alta" }));
    expect(within(wealth).getByText("R$ 50.000,00")).toBeInTheDocument();
  });

  it("waits for an unfinished projection", () => {
    render(<ProjectionView data={projection({ status: "RUNNING", scenarios: [] })} run={projectionRun} />);
    expect(screen.getByText("A projeção aparece quando a simulação terminar")).toBeInTheDocument();
  });
});

// --- confidence and tab guide -----------------------------------------------------------------

function calibration(overrides: Partial<CalibrationDTO> = {}): CalibrationDTO {
  const generator = (key: string, label: string, status: "CALIBRATED" | "MISCALIBRATED" | "INCONCLUSIVE", weight: number) => ({
    key,
    label,
    weight,
    windows: 120,
    effective_windows: 10,
    coverage: status === "MISCALIBRATED" ? 0.62 : 0.88,
    coverage_low: status === "MISCALIBRATED" ? 0.45 : 0.72,
    coverage_high: status === "MISCALIBRATED" ? 0.78 : 0.96,
    status,
    pit_histogram: [12, 12, 12, 12, 12, 12, 12, 12, 12, 12],
    mean_pit: 0.51,
    brier_loss: 0.041,
    brier_beat_cdi: 0.2,
    log_score: 1.02,
  });
  return {
    run_id: 9,
    status: "DONE",
    finished_at: "2026-10-28T20:00:00Z",
    horizon_months: 12,
    windows: 120,
    effective_windows: 10,
    first_origin: "2012-01-31",
    last_origin: "2025-10-31",
    classes: ["ACOES", "CAIXA"],
    targets: { ACOES: 0.6, CAIXA: 0.4 },
    weights: { BOOTSTRAP: 0.1, BAYESIAN_BOOTSTRAP: 0.2, BAYESIAN_NORMAL: 0.7 },
    generators: [
      generator("BOOTSTRAP", "Bootstrap em blocos", "MISCALIBRATED", 0.1),
      generator("BAYESIAN_BOOTSTRAP", "Bootstrap bayesiano", "INCONCLUSIVE", 0.2),
      generator("BAYESIAN_NORMAL", "Normal bayesiana", "CALIBRATED", 0.7),
      generator("STACKED", "Combinação (stacking)", "CALIBRATED", 1),
    ],
    origins: [
      { origin: "2012-01-31", realized: 0.08, forecasts: { STACKED: { p5: -0.1, p50: 0.09, p95: 0.3, pit: 0.45 } } },
      { origin: "2012-02-29", realized: -0.05, forecasts: { STACKED: { p5: -0.12, p50: 0.08, p95: 0.29, pit: 0.2 } } },
    ],
    warnings: ["Há gerador mal calibrado: teste."],
    pending_run_id: null,
    ...overrides,
  };
}

describe("CalibrationView", () => {
  it("shows every generator with its coverage interval, status and weight", () => {
    render(<CalibrationView data={calibration()} />);
    expect(screen.getByText("Há gerador mal calibrado: teste.")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Calibração dos geradores" });
    const bootstrap = within(table).getByText("Bootstrap em blocos").closest("tr") as HTMLElement;
    expect(within(bootstrap).getByText("Mal calibrado")).toBeInTheDocument();
    expect(within(bootstrap).getByText("62%")).toBeInTheDocument();
    expect(within(bootstrap).getByText("45% a 78%")).toBeInTheDocument();
    expect(within(table).getByText("Inconclusivo")).toBeInTheDocument();
    const normal = within(table).getByText("Normal bayesiana").closest("tr") as HTMLElement;
    expect(within(normal).getByText("70%")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Histograma do PIT da combinação" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /previsto pela combinação e realizado/ })).toBeInTheDocument();
  });
});

describe("simulation helpers", () => {
  it("keeps variants out of the series and flags active runs", () => {
    const series = [{ key: "strategy" }, { key: "variant:b5" }, { key: "benchmark:CDI" }] as SimulationResultDTO[];
    expect(seriesOf(series).map((r) => r.key)).toEqual(["strategy", "benchmark:CDI"]);
    expect(isActive("PENDING")).toBe(true);
    expect(isActive("DONE")).toBe(false);
  });
});
