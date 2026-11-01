import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ClassMatrixDTO, MatrixBoardDTO } from "../api/types";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

const LENSES = ["CERRADO", "QUALITY", "VALUATION", "IMPROVEMENT", "MOMENTUM", "INCOME", "RISK", "PROJECTION"] as const;

function row(ticker: string, rank: number, score: number, source: "PORTFOLIO" | "WATCHLIST" | "CATALOG", flags: string[] = []) {
  return {
    ticker,
    source,
    sector: "Setor",
    rank,
    score,
    expected: (score - 0.5) * 0.12,
    expected_low: -0.01,
    expected_high: 0.05,
    confidence: 0.8,
    cells: LENSES.map((lens) => ({ lens, value: score, weight: 0.125, contribution: score * 0.125 })),
    gaussian_score: score,
    gaussian_rank: rank,
    flags,
  };
}

function acoes(overrides: Partial<ClassMatrixDTO> = {}): ClassMatrixDTO {
  return {
    arca_class: "ACOES",
    objective: "MIXED",
    objective_label: "Misto",
    consistency_ratio: 0.011,
    scale_annual: 0.06,
    weights: LENSES.map((lens) => ({ lens, label: lens, weight: 0.125, gaussian_weight: 0.1 })),
    rows: [row("WEGE3", 1, 0.72, "PORTFOLIO"), row("ABCD3", 2, 0.61, "CATALOG", ["NOT_ANALYZED"])],
    excluded: [{ ticker: "RUIN3", source: "WATCHLIST", reasons: ["Comunicado de recuperação judicial em 10/06/2025."] }],
    construction: {
      k: 2,
      stop_reason: "Todos os 2 ativos possíveis entraram: cada um ainda melhorava a utilidade.",
      confidence: 0.8,
      selected: [
        { ticker: "WEGE3", sector: "Bens industriais", group: "WEGE3", weight: 0.55, score: 0.72, expected: 0.05, confidence: 0.8, reason: "Setor novo (Bens industriais)." },
        { ticker: "ABCD3", sector: "Saneamento", group: "WEGE3", weight: 0.45, score: 0.61, expected: 0.03, confidence: 0.7, reason: "Setor novo (Saneamento)." },
      ],
      skipped: [],
      curve: [
        { k: 1, added: "WEGE3", expected: 0.05, risk: 0.3, utility: -0.01 },
        { k: 2, added: "ABCD3", expected: 0.04, risk: 0.22, utility: -0.004 },
        { k: 3, added: "XYZW3", expected: 0.03, risk: 0.21, utility: -0.012 },
      ],
      notes: ["Poucos setores para o teto de 25%: teto usado de 50%."],
    },
    ...overrides,
  };
}

function board(overrides: Partial<MatrixBoardDTO> = {}): MatrixBoardDTO {
  return {
    status: "OK",
    as_of: "2026-10-31",
    classes: [
      acoes(),
      acoes({ arca_class: "REAL_ESTATE", objective: "DIVIDENDS", objective_label: "Dividendos", rows: [], construction: null, excluded: [] }),
    ],
    ...overrides,
  };
}

const RUNS = [
  { as_of: "2026-10-31", policy_version: 4, signal_month: "2026-09-30", assets: 40, eligible: 31, selected: { ACOES: ["WEGE3", "ABCD3"] } },
];

const BACKTEST = {
  status: "OK",
  as_of: "2026-10-31",
  passed: false,
  reason: "A hierarquia não superou os pesos iguais com confiança: diferença de +1,2% ao ano e 71% de chance de ser positiva (são precisos 90%).",
  first_month: "2012-04",
  last_month: "2026-09",
  months: 174,
  rebalances: 58,
  average_k: 6.4,
  strategy_annual: 0.031,
  equal_annual: 0.019,
  difference_annual: 0.012,
  hit_rate: 0.53,
  probability: 0.71,
  years: [{ year: 2025, months: 12, strategy: 0.08, equal: 0.05 }],
  weights: {},
  notes: ["Ficam de fora o Cerrado manual (sem respostas datadas) e a projeção."],
  scoreboard: [
    {
      horizon: 1,
      runs: 6,
      vs_equal: 0.004,
      beat_equal: 0.67,
      beat_equal_low: 0.3,
      beat_equal_high: 0.9,
      vs_cerrado: -0.002,
      beat_cerrado: 0.5,
      cerrado_runs: 4,
    },
  ],
};

const WEIGHTS = {
  status: "OK",
  as_of: "2026-11-01",
  objective: "MIXED",
  passed: false,
  reason: "Os dados não justificaram mudar os seus pesos: os pesos ajustados renderam +0.8% ao ano a mais nas 10 melhores notas, com 64% de confiança (são precisos 90%).",
  origins: 9,
  oos_months: 108,
  improvement_annual: 0.008,
  probability: 0.64,
  lines: [
    {
      lens: "QUALITY",
      label: "Qualidade",
      declared: 0.236,
      estimate_annual_per_z: 0.012,
      sign_probability: 0.97,
      data: 0.4,
      candidate: 0.318,
      used: 0.236,
    },
  ],
};

describe("Recomendação (Phase 45.5)", () => {
  it("explains the choice of the class: lead, chosen assets, curve, matrix, gates and runs", async () => {
    mockApi([
      { path: "/recommendation/matrix", reply: board() },
      { path: "/recommendation/runs", reply: RUNS },
      { path: "/recommendation/backtest", reply: BACKTEST },
    ]);
    renderAt("/recommendation");
    expect(await screen.findByText(/a recomendação escolheu 2: WEGE3, ABCD3/)).toBeInTheDocument();
    expect(screen.getByText("Decide o aporte")).toBeInTheDocument();

    const chosen = screen.getByRole("table", { name: "Escolhidos e pesos-alvo" });
    expect(within(chosen).getByText("55,0%")).toBeInTheDocument();
    expect(within(chosen).getByText("anda junto com WEGE3")).toBeInTheDocument();
    expect(screen.getByText(/teto usado de 50%/)).toBeInTheDocument();

    const curve = screen.getByRole("table", { name: "Curva do K" });
    expect(within(curve).getByText("recusado")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Matriz de decisão" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Matriz de decisão" }));
    const matrix = await screen.findByRole("table", { name: "Matriz de decisão" });
    expect(within(matrix).getByText("catálogo")).toBeInTheDocument();
    expect(within(matrix).getByText(/Faça a análise do Cerrado/)).toBeInTheDocument();

    const gates = screen.getByRole("table", { name: "Fora pelos portões" });
    expect(within(gates).getByText(/recuperação judicial/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Real Estate" }));
    expect(await screen.findByText("Nenhum ativo passou nos portões")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Rodadas" }));
    const runs = await screen.findByRole("table", { name: "Rodadas" });
    expect(within(runs).getByText("v4")).toBeInTheDocument();
    expect(within(runs).getByText("Ações: WEGE3, ABCD3")).toBeInTheDocument();
    expect(screen.queryByText("Decide o aporte")).not.toBeInTheDocument();
  });

  it("compares A and not B lens by lens", async () => {
    const api = mockApi([
      { path: "/recommendation/matrix", reply: board() },
      { path: "/recommendation/runs", reply: RUNS },
      { path: "/recommendation/backtest", reply: BACKTEST },
      {
        path: "/recommendation/compare",
        reply: {
          status: "OK",
          a: row("WEGE3", 1, 0.72, "PORTFOLIO"),
          b: row("ABCD3", 2, 0.61, "CATALOG"),
          differences: [{ lens: "QUALITY", label: "Qualidade", a: 0.9, b: 0.5, weight: 0.236, difference: 0.094 }],
        },
      },
    ]);
    renderAt("/recommendation?tab=compare");
    fireEvent.click(await screen.findByRole("button", { name: "Comparar" }));
    const table = await screen.findByRole("table", { name: "A e não B" });
    expect(within(table).getByText("Qualidade")).toBeInTheDocument();
    expect(within(table).getByText("0,094")).toBeInTheDocument();
    const call = api.calls.find((c) => c.path === "/recommendation/compare");
    expect(call?.query.get("a")).toBe("WEGE3");
    expect(call?.query.get("b")).toBe("ABCD3");
  });

  it("shows the contribution next to the current rule", async () => {
    const api = mockApi([
      { path: "/recommendation/matrix", reply: board() },
      { path: "/recommendation/runs", reply: RUNS },
      { path: "/recommendation/backtest", reply: BACKTEST },
      {
        path: "/recommendation/contribution",
        reply: {
          status: "OK",
          as_of: "2026-10-31",
          amount: 5000,
          classes: [
            {
              arca_class: "ACOES",
              budget: 2500,
              covered: true,
              confidence: 0.8,
              current_orders: [{ ticker: "WEGE3", amount: 2500, quantity: 50, new: false, reason: "" }],
              recommended_orders: [
                { ticker: "WEGE3", amount: 1400, quantity: 28, new: false, reason: "Setor novo." },
                { ticker: "ABCD3", amount: 1080, quantity: 90, new: true, reason: "Setor novo." },
              ],
              recommended_leftover: 20,
            },
          ],
        },
      },
    ]);
    renderAt("/recommendation?tab=compare");
    fireEvent.change(await screen.findByLabelText("Valor do aporte (R$)"), { target: { value: "5000" } });
    fireEvent.click(screen.getByRole("button", { name: "Comparar com a regra antiga" }));
    const recommended = await screen.findByRole("table", { name: "Aporte (recomendação)" });
    expect(within(recommended).getByText("novo")).toBeInTheDocument();
    expect(within(screen.getByRole("table", { name: "Regra antiga" })).getByText("WEGE3")).toBeInTheDocument();
    expect(screen.getByText(/Sobra sem compra/)).toBeInTheDocument();
    expect(api.calls.find((c) => c.path === "/recommendation/contribution")?.query.get("amount_brl")).toBe("5000");
  });

  it("says when the recommendation has not run", async () => {
    mockApi([
      { path: "/recommendation/matrix", reply: { status: "NOT_COMPUTED", classes: [] } },
      { path: "/recommendation/runs", reply: [] },
      { path: "/recommendation/backtest", reply: { status: "NOT_COMPUTED" } },
    ]);
    renderAt("/recommendation");
    expect(await screen.findByText("A recomendação ainda não rodou")).toBeInTheDocument();
    expect(screen.getByText(/dá para pedir agora na aba Rodadas/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Rodadas" }));
    expect(await screen.findByText("Nenhuma rodada ainda.")).toBeInTheDocument();
  });
  it("shows the past test and the scoreboard (Phase 45.6)", async () => {
    mockApi([
      { path: "/recommendation/matrix", reply: board() },
      { path: "/recommendation/runs", reply: RUNS },
      { path: "/recommendation/backtest", reply: BACKTEST },
    ]);
    renderAt("/recommendation?tab=past");
    expect(await screen.findByText("Não passou")).toBeInTheDocument();
    expect(screen.getAllByText(/71% de chance de ser positiva/).length).toBeGreaterThan(0);
    const years = screen.getByRole("table", { name: "Teste no passado por ano" });
    expect(within(years).getByText("2025")).toBeInTheDocument();
    const score = screen.getByRole("table", { name: "Placar das rodadas" });
    expect(within(score).getByText("-0,2% (4)")).toBeInTheDocument();
  });

  it("shows the lens weights validated by the data (Phase 45.7)", async () => {
    mockApi([
      { path: "/recommendation/matrix", reply: board() },
      { path: "/recommendation/runs", reply: RUNS },
      { path: "/recommendation/backtest", reply: BACKTEST },
      { path: "/recommendation/weights", reply: WEIGHTS },
    ]);
    renderAt("/recommendation?tab=past");
    expect(await screen.findByText("Ficam os seus pesos")).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Pesos validados pelos dados" });
    expect(within(table).getByText("Qualidade")).toBeInTheDocument();
    expect(within(table).getByText("31,8%")).toBeInTheDocument();
    expect(within(table).getByText("97% de confiança no sentido")).toBeInTheDocument();
  });

  it("pages the decision matrix and the assets left out by the gates", async () => {
    const rows = Array.from({ length: 12 }, (_, i) => row(`T${String(i).padStart(2, "0")}3`, i + 1, 0.9 - i * 0.01, "CATALOG"));
    const excluded = Array.from({ length: 11 }, (_, i) => ({
      ticker: `X${String(i).padStart(2, "0")}3`,
      source: "CATALOG" as const,
      reasons: ["Volume abaixo do piso."],
    }));
    const { calls } = mockApi([
      { path: "/recommendation/matrix", reply: board({ classes: [acoes({ rows, excluded })] }) },
      { path: "/recommendation/runs", reply: RUNS },
      { path: "/recommendation/backtest", reply: BACKTEST },
      { path: "/recommendation/weights", reply: WEIGHTS },
    ]);
    renderAt("/recommendation?tab=matrix");
    const matrix = await screen.findByRole("table", { name: "Matriz de decisão" });
    expect(within(matrix).getByText("T003")).toBeInTheDocument();
    expect(within(matrix).queryByText("T113")).not.toBeInTheDocument();
    const [matrixPager, gatesPager] = screen.getAllByRole("navigation", { name: "Paginação" });
    expect(matrixPager).toHaveTextContent("1–10 de 12");
    expect(gatesPager).toHaveTextContent("1–10 de 11");

    fireEvent.click(within(matrixPager).getByRole("button", { name: "Próxima página" }));
    expect(within(screen.getByRole("table", { name: "Matriz de decisão" })).getByText("T113")).toBeInTheDocument();
    expect(matrixPager).toHaveTextContent("11–12 de 12");

    fireEvent.click(within(gatesPager).getByRole("button", { name: "Próxima página" }));
    expect(within(screen.getByRole("table", { name: "Fora pelos portões" })).getByText("X103")).toBeInTheDocument();

    const before = calls.filter((c) => c.path === "/recommendation/matrix").length;
    fireEvent.click(within(matrixPager).getByRole("button", { name: "Recarregar" }));
    await screen.findByRole("table", { name: "Matriz de decisão" });
    expect(calls.filter((c) => c.path === "/recommendation/matrix").length).toBeGreaterThan(before);
  });

  it("shows the live scoreboard with your place among the random portfolios (Phase 45.8a)", async () => {
    const summary = (final: number, irr: number) => ({
      start: "2024-01-10",
      end: "2026-10-30",
      final_value: final,
      contributed: 1800,
      gain: final - 1800,
      irr,
      twr: 0.2,
      annual_twr: 0.07,
      volatility: 0.12,
      max_drawdown: -0.08,
      fees: 1.5,
      taxes: 0,
    });
    mockApi([
      { path: "/recommendation/matrix", reply: board() },
      {
        path: "/recommendation/live",
        reply: {
          status: "OK",
          as_of: "2026-11-01",
          prospective_since: "2026-11-01",
          prospective_months: 0,
          verdict_ready: false,
          yours: summary(2100, 0.09),
          lines: [
            {
              key: "EQUAL",
              label: "Pesos iguais",
              started: "2024-01-10",
              retroactive: true,
              whole: summary(2250, 0.11),
              yours: summary(2100, 0.09),
              difference: 150,
            },
          ],
          randoms: {
            portfolios: 200,
            rank: { portfolios: 200, beaten: 124, share: 0.62, low: 0.55, high: 0.68 },
            irr_low: 0.03,
            irr_mid: 0.08,
            irr_high: 0.13,
          },
          curve: [
            { day: "2024-01-31", yours: 1000, values: { EQUAL: 1010 }, random_low: 980, random_high: 1030 },
            { day: "2024-02-29", yours: 1020, values: { EQUAL: 1040 }, random_low: 990, random_high: 1050 },
          ],
        },
      },
    ]);
    renderAt("/recommendation?tab=live");
    expect(await screen.findByText(/0 de 12 meses/)).toBeInTheDocument();
    expect(screen.getByText(/bateu 62% das 200 carteiras aleatórias/)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Placar ao vivo" });
    expect(within(table).getByText("Pesos iguais")).toBeInTheDocument();
    expect(within(table).getByText("retroativo")).toBeInTheDocument();
    expect(within(table).getByText(/150,00/)).toBeInTheDocument();
    expect(screen.queryByText("Decide o aporte")).not.toBeInTheDocument();
  });

  it("says when the live scoreboard has not run", async () => {
    mockApi([
      { path: "/recommendation/matrix", reply: board() },
      { path: "/recommendation/live", reply: { status: "NOT_COMPUTED" } },
    ]);
    renderAt("/recommendation?tab=live");
    expect(await screen.findByText("O placar ao vivo ainda não rodou")).toBeInTheDocument();
  });

  it("shows the optimizer next to the construction and its verdict in the past (Phase 45.8b)", async () => {
    const base = acoes();
    const optimized = {
      status: "OK" as const,
      assets: [
        { ticker: "WEGE3", weight: 0.6, low: 0.45, high: 0.7, frequency: 1, construction_weight: 0.55 },
        { ticker: "ABCD3", weight: 0.4, low: 0.2, high: 0.5, frequency: 0.4, construction_weight: 0.45 },
      ],
      expected: 0.03,
      risk: 0.2,
      utility: -0.01,
      construction_utility: -0.012,
      cvar: 0.21,
      current_cvar: 0.25,
      construction_cvar: 0.22,
      cvar_bound: true,
      draws: 16,
      notes: ["Instáveis (entram em menos da metade dos sorteios): ABCD3."],
    };
    mockApi([
      {
        path: "/recommendation/matrix",
        reply: board({ classes: [acoes({ construction: { ...base.construction!, optimized } })] }),
      },
      {
        path: "/recommendation/backtest",
        reply: {
          ...BACKTEST,
          optimizer_status: "OK",
          optimizer_passed: false,
          optimizer_reason: "O otimizador não superou a construção com confiança.",
          optimizer_months: 72,
          optimizer_annual: 0.02,
          optimizer_difference_annual: 0.004,
          optimizer_hit_rate: 0.52,
          optimizer_probability: 0.61,
        },
      },
      { path: "/recommendation/weights", reply: WEIGHTS },
    ]);
    renderAt("/recommendation");
    const table = await screen.findByRole("table", { name: "Otimizador" });
    expect(within(table).getByText("60,0%")).toBeInTheDocument();
    expect(within(table).getByText("45% a 70%")).toBeInTheDocument();
    expect(screen.getByText("Referência")).toBeInTheDocument();
    expect(screen.getByText(/Instáveis/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Teste no passado" }));
    expect(await screen.findByText("Otimizador contra a construção")).toBeInTheDocument();
    expect(screen.getByText(/não superou a construção/)).toBeInTheDocument();
  });

  it("says the optimizer decides the contribution once it passed", async () => {
    const base = acoes();
    mockApi([
      {
        path: "/recommendation/matrix",
        reply: board({
          optimizer_in_use: true,
          classes: [
            acoes({
              construction: {
                ...base.construction!,
                optimized: { status: "OK", assets: [], utility: 0, construction_utility: 0, draws: 16 },
              },
            }),
          ],
        }),
      },
    ]);
    renderAt("/recommendation");
    expect(await screen.findByText("Em uso: decide o aporte")).toBeInTheDocument();
  });

  it("says when the Cerrado lens is off in the policy", async () => {
    mockApi([{ path: "/recommendation/matrix", reply: board({ classes: [acoes({ cerrado_in_use: false })] }) }]);
    renderAt("/recommendation");
    expect(await screen.findByText("Sem o Cerrado")).toBeInTheDocument();
  });
});
