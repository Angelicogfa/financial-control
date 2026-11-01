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

describe("Recomendação (Phase 45.5)", () => {
  it("explains the choice of the class: lead, chosen assets, curve, matrix, gates and runs", async () => {
    mockApi([
      { path: "/recommendation/matrix", reply: board() },
      { path: "/recommendation/runs", reply: RUNS },
      { path: "/recommendation/backtest", reply: BACKTEST },
    ]);
    renderAt("/recommendation");
    expect(await screen.findByText(/a recomendação escolheu 2: WEGE3, ABCD3/)).toBeInTheDocument();
    expect(screen.getByText("Ainda não decide o aporte")).toBeInTheDocument();

    const chosen = screen.getByRole("table", { name: "Escolhidos e pesos-alvo" });
    expect(within(chosen).getByText("55,0%")).toBeInTheDocument();
    expect(within(chosen).getByText("anda junto com WEGE3")).toBeInTheDocument();
    expect(screen.getByText(/teto usado de 50%/)).toBeInTheDocument();

    const curve = screen.getByRole("table", { name: "Curva do K" });
    expect(within(curve).getByText("recusado")).toBeInTheDocument();

    const matrix = screen.getByRole("table", { name: "Matriz de decisão" });
    expect(within(matrix).getByText("catálogo")).toBeInTheDocument();
    expect(within(matrix).getByText(/Faça a análise do Cerrado/)).toBeInTheDocument();

    const gates = screen.getByRole("table", { name: "Fora pelos portões" });
    expect(within(gates).getByText(/recuperação judicial/)).toBeInTheDocument();

    const runs = await screen.findByRole("table", { name: "Rodadas" });
    expect(within(runs).getByText("v4")).toBeInTheDocument();
    expect(within(runs).getByText("Ações: WEGE3, ABCD3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Real Estate" }));
    expect(await screen.findByText("Nenhum ativo passou nos portões")).toBeInTheDocument();
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
    renderAt("/recommendation");
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
    renderAt("/recommendation");
    fireEvent.change(await screen.findByLabelText("Valor do aporte (R$)"), { target: { value: "5000" } });
    fireEvent.click(screen.getByRole("button", { name: "Comparar com o aporte atual" }));
    const recommended = await screen.findByRole("table", { name: "Recomendação" });
    expect(within(recommended).getByText("novo")).toBeInTheDocument();
    expect(within(screen.getByRole("table", { name: "Regra atual" })).getByText("WEGE3")).toBeInTheDocument();
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
    expect(await screen.findByText("Nenhuma rodada ainda.")).toBeInTheDocument();
  });
  it("shows the past test and the scoreboard (Phase 45.6)", async () => {
    mockApi([
      { path: "/recommendation/matrix", reply: board() },
      { path: "/recommendation/runs", reply: RUNS },
      { path: "/recommendation/backtest", reply: BACKTEST },
    ]);
    renderAt("/recommendation");
    expect(await screen.findByText("Não passou")).toBeInTheDocument();
    expect(screen.getAllByText(/71% de chance de ser positiva/).length).toBeGreaterThan(0);
    const years = screen.getByRole("table", { name: "Teste no passado por ano" });
    expect(within(years).getByText("2025")).toBeInTheDocument();
    const score = screen.getByRole("table", { name: "Placar das rodadas" });
    expect(within(score).getByText("-0,2% (4)")).toBeInTheDocument();
  });
});
