import { fireEvent, screen, within } from "@testing-library/react";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { CandidateResultDTO, CandidatesDTO, SimulationRunDTO } from "../api/types";
import { CandidatesView, toCandidatesRequest } from "../pages/tools/SimulationPage";
import { mockApi, type Call } from "./mockApi";
import { renderAt } from "./render";

const run: SimulationRunDTO = {
  id: 8,
  kind: "CANDIDATES",
  status: "DONE",
  label: "Candidatos",
  params: { candidates: [{ ticker: "WEGE3" }, { ticker: "ITUB4" }] },
  params_hash: "abcdef1234567890",
  data_hash: "0123456789abcdef",
  code_version: "33.7.0",
  seed: 7,
  created_at: "2026-10-29T12:00:00Z",
};

function candidate(ticker: string, rank: number, overrides: Partial<CandidateResultDTO["effect"]> = {}): CandidateResultDTO {
  return {
    ticker,
    name: ticker,
    arca_class: "ACOES",
    asset_type: "STOCK_BR",
    source: rank === 1 ? "WATCHLIST" : "SCREENER",
    eligible: rank === 1 ? true : null,
    dividend_yield: 0.05,
    suspicious: false,
    zone: "NO_DATA",
    fit: {
      months: 120,
      alpha_annual: 0.08,
      alpha_post_annual: 0.01,
      alpha_post_sd_annual: 0.02,
      beta: 1.2,
      beta_post: 1.1,
      beta_post_sd: 0.1,
      shrinkage: 0.85,
      residual_vol_annual: 0.2,
    },
    effect: {
      ticker,
      share_in_class: 0.25,
      weight: 0.15,
      delta_final_wealth: rank === 1 ? 1240 : -310,
      p_improve: rank === 1 ? 0.64 : 0.41,
      p_improve_low: rank === 1 ? 0.62 : 0.39,
      p_improve_high: rank === 1 ? 0.66 : 0.43,
      delta_goal_probability: 0.012,
      delta_cvar_12m: 0.004,
      delta_drawdown: 0.01,
      delta_diversification: 0.03,
      delta_income_yield: 0.0015,
      top_k_share: rank === 1 ? 0.9 : 0.4,
      rank,
      ...overrides,
    },
  };
}

function data(overrides: Partial<CandidatesDTO> = {}): CandidatesDTO {
  return {
    run_id: 8,
    status: "DONE",
    horizon_months: 60,
    paths: 2000,
    base: { final_net_wealth_p50: 80000, cvar_12m: -0.12, drawdown_median: -0.1, diversification: 1.2, goal_probability: 0.55 },
    candidates: [candidate("WEGE3", 1), candidate("ITUB4", 2)],
    excluded: [{ ticker: "NEWB3", reason: "Menos de 36 meses de histórico guardado" }],
    tested: 3,
    evaluated: 2,
    warnings: ["Candidatos para investigar, não recomendação de compra."],
    ...overrides,
  };
}

describe("candidates helpers", () => {
  it("builds the request with the weight mode", () => {
    const form = {
      horizonYears: "5",
      monthly: "1000",
      wealthGoal: "",
      includeScreener: true,
      minVolume: "1000000",
      includeIneligible: false,
      fixedWeight: true,
      weightPct: "7,5",
      ruptureStress: true,
      label: "",
    };
    expect(toCandidatesRequest(form)).toEqual({
      horizon_years: 5,
      monthly_contribution: 1000,
      wealth_goal: null,
      include_screener: true,
      screener_min_volume: 1000000,
      include_ineligible: false,
      weight_mode: "FIXED",
      fixed_weight: 0.075,
      rupture_stress: true,
      label: null,
    });
    expect(toCandidatesRequest({ ...form, horizonYears: "31" })).toBeNull();
    expect(toCandidatesRequest({ ...form, fixedWeight: false })?.weight_mode).toBe("NEXT_CONTRIBUTION");
  });
});

describe("CandidatesView", () => {
  it("ranks the candidates with the chance of a real improvement and lists the excluded", () => {
    render(
      <MemoryRouter>
        <CandidatesView data={data()} run={run} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Candidatos para investigar, não recomendação de compra.")).toBeInTheDocument();
    const rows = within(screen.getByRole("table", { name: "Candidatos" })).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    const first = within(rows[0]);
    expect(first.getByRole("link", { name: "WEGE3" })).toHaveAttribute("href", expect.stringContaining("WEGE3"));
    expect(first.getByText("64%")).toBeInTheDocument();
    expect(first.getByText("62% a 66%")).toBeInTheDocument();
    expect(first.getByText(/\+8,0% → \+1,0%/)).toBeInTheDocument();
    expect(first.getByText("90%")).toBeInTheDocument();
    expect(within(rows[1]).getByText(/screener/)).toBeInTheDocument();
    const excluded = screen.getByLabelText("Candidatos excluídos");
    expect(within(excluded).getByText(/Menos de 36 meses/)).toBeInTheDocument();
    // The lead tells the conclusion before the table.
    expect(screen.getByRole("note", { name: "Em resumo" })).toHaveTextContent(/WEGE3 é o mais promissor: 64%/);
    expect(screen.getByText(/chance de meta de 55%/)).toBeInTheDocument();
  });

  it("waits for an unfinished evaluation", () => {
    render(
      <MemoryRouter>
        <CandidatesView data={data({ status: "RUNNING", candidates: [] })} run={run} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Os candidatos aparecem quando a avaliação terminar")).toBeInTheDocument();
  });
});

describe("SimulationPage candidates tab", () => {
  it("submits an evaluation and shows the selected one", async () => {
    const { calls } = mockApi([
      { path: "/simulations", reply: (call: Call) => (call.query.get("kind") === "CANDIDATES" ? [run] : []) },
      { path: "/simulations/8", reply: { ...run, results: [] } },
      { path: "/simulations/8/candidates", reply: data() },
      { method: "POST", path: "/simulations/candidates", reply: { ...run, id: 9, status: "PENDING" } },
      { path: "/simulations/9", reply: { ...run, id: 9, status: "PENDING", results: [] } },
    ]);
    renderAt("/tools/simulation?tab=candidates");
    // Three chained requests (runs, run detail, candidates): give it room when the suite is busy.
    expect(await screen.findByRole("table", { name: "Candidatos" }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText("2 candidatos")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Avaliar candidatos" }));
    expect(await screen.findByText(/Na fila do worker/)).toBeInTheDocument();
    const body = [...calls].reverse().find((c) => c.method === "POST")?.body as Record<string, unknown>;
    expect(body).toMatchObject({ horizon_years: 5, include_screener: true, weight_mode: "NEXT_CONTRIBUTION" });
  });
});
