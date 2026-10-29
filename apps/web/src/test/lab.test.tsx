import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { LabDTO } from "../api/types";
import { LabView } from "../pages/tools/SimulationPage";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

function lab(overrides: Partial<LabDTO> = {}): LabDTO {
  return {
    run_id: 11,
    status: "DONE",
    finished_at: "2026-10-29T12:00:00Z",
    months: 200,
    first_forecast: "2012-01-31",
    last_forecast: "2026-09-30",
    trials: 12,
    pbo: 0.41,
    loss_probability: 0.03,
    models: [
      {
        key: "HMM2",
        label: "Regimes: HMM com 2 estados",
        family: "REGIME",
        months: 140,
        mean_gain: 0.0213,
        gate_probability: 0.97,
        deflated_probability: 0.96,
        stable: true,
        passed: true,
        reasons: [],
      },
      {
        key: "EWMA94",
        label: "Risco: EWMA com λ = 0,94",
        family: "RISK",
        months: 140,
        mean_gain: -0.004,
        gate_probability: 0.31,
        deflated_probability: 0.12,
        stable: false,
        passed: false,
        reasons: ["chance de superar a referência de 31% (precisa de 95%)"],
      },
    ],
    approved: ["HMM2"],
    regime: [
      { month: "2026-08-31", stress_probability: 0.12 },
      { month: "2026-09-30", stress_probability: 0.64 },
    ],
    verdict: "Passaram nos portões: Regimes: HMM com 2 estados.",
    warnings: ["12 tentativas de modelo registradas no laboratório até agora."],
    pending_run_id: null,
    ...overrides,
  };
}

describe("LabView", () => {
  it("shows the verdict, each model's gates and the regime probability", () => {
    render(<LabView data={lab()} />);
    const verdict = screen.getByRole("region", { name: "Veredito do laboratório" });
    expect(within(verdict).getByText("1 modelo passou")).toBeInTheDocument();
    expect(within(verdict).getByText(/12 tentativas registradas · PBO do conjunto 41%/)).toBeInTheDocument();
    const rows = within(screen.getByRole("table", { name: "Modelos do laboratório" })).getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("Passou")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Não passou")).toBeInTheDocument();
    expect(within(rows[1]).getByText(/precisa de 95%/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Probabilidade do regime de estresse mês a mês" })).toBeInTheDocument();
  });

  it("states that no model passed", () => {
    render(<LabView data={lab({ approved: [], verdict: "Nenhum modelo passou nos portões." })} />);
    expect(screen.getAllByText(/Nenhum modelo passou/).length).toBeGreaterThan(0);
  });
});

describe("SimulationPage laboratory tab", () => {
  it("runs the laboratory and waits for the worker", async () => {
    let queued = false;
    const { calls } = mockApi([
      {
        path: "/simulations/lab",
        reply: () => (queued ? { run_id: null, pending_run_id: 12 } : { run_id: null, pending_run_id: null }),
      },
      {
        method: "POST",
        path: "/simulations/lab",
        reply: () => {
          queued = true;
          return { status: 202, json: { id: 12, kind: "LAB", status: "PENDING", params_hash: "x", code_version: "33.9.0", seed: 1 } };
        },
      },
    ]);
    renderAt("/tools/simulation?tab=lab");
    expect(await screen.findByText("O laboratório ainda não rodou")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Rodar o laboratório" }));
    expect(await screen.findByText(/Na fila do worker/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/simulations/lab")).toBe(true);
  });
});
