import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MANUAL_JOBS, MARKET_DATA_JOBS } from "../api/jobs";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

const NOT_RUN = { status: "NOT_RUN", reason: "Ainda não rodou." };

describe("job buttons on the screen of each subject", () => {
  it("keeps only the fetch jobs on the market data page", async () => {
    mockApi([
      { path: "/market/series-status", reply: [] },
      { path: "/market/job-runs", reply: [] },
      { path: "/market/worker-errors", reply: { unresolved_count: 0, errors: [] } },
    ]);
    renderAt("/settings/market-data");
    expect(await screen.findByRole("button", { name: "Carregar o histórico da simulação" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rodar o garimpo" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Calibrar a previsão de preço" })).not.toBeInTheDocument();
    expect(MARKET_DATA_JOBS.every((name) => MANUAL_JOBS.some((job) => job.name === name))).toBe(true);
  });

  it("runs the Garimpo from its own page", async () => {
    const { calls } = mockApi([
      { path: "/research/mining", reply: NOT_RUN },
      { path: "/market/job-runs", reply: [] },
      { method: "POST", path: "/market/job-runs/run_mining/request", reply: { status: 202, json: {} } },
    ]);
    renderAt("/research/mining");
    fireEvent.click(await screen.findByRole("button", { name: "Rodar o garimpo" }));
    await screen.findByRole("button", { name: "Rodar o garimpo" });
    expect(calls.some((c) => c.method === "POST" && c.path === "/market/job-runs/run_mining/request")).toBe(true);
  });

  it("runs the lenses and the past test from the recommendation page", async () => {
    mockApi([
      { path: "/recommendation/matrix", reply: { status: "NOT_COMPUTED", classes: [] } },
      { path: "/recommendation/runs", reply: [] },
      { path: "/recommendation/backtest", reply: { status: "NOT_COMPUTED" } },
      { path: "/market/job-runs", reply: [] },
    ]);
    renderAt("/recommendation?tab=runs");
    expect(await screen.findByRole("button", { name: "Rodar as lentes e os portões da recomendação" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rodar o teste no passado da recomendação" })).toBeInTheDocument();
  });

  it("shows the price forecast quality and its jobs on the models quality page", async () => {
    mockApi([
      { path: "/simulations/calibration", reply: { run_id: null } },
      { path: "/simulations/lab", reply: { run_id: null } },
      {
        path: "/market/forecast-quality",
        reply: {
          status: "OK",
          windows: 400,
          assets: 20,
          coverage_50: 0.48,
          coverage_90: 0.88,
          first_origin: "2015-01-31",
          last_origin: "2025-09-30",
          valuation: null,
          seal: { level: 3, label: "Confiável", text: "Quando o modelo disse 90%, aconteceu em 88%." },
        },
      },
      { path: "/market/job-runs", reply: [] },
    ]);
    renderAt("/tools/simulation/quality");
    expect(await screen.findByRole("heading", { name: "Previsão de preço dos ativos" })).toBeInTheDocument();
    expect(await screen.findByText("88%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Calibrar a previsão de preço" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recalcular a previsão de preço" })).toBeInTheDocument();
  });
});
