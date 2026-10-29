import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { LabDTO } from "../api/types";
import { LabView } from "../pages/simulation/views";
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
  it("tells the verdict in decision terms and charts the model that passed", () => {
    const data = lab({
      models: lab().models!.map((m) => ({
        ...m,
        cumulative_gain: [
          { month: "2026-08-31", value: m.passed ? 1.2 : -0.1 },
          { month: "2026-09-30", value: m.passed ? 1.4 : -0.3 },
        ],
      })),
    });
    render(<LabView data={data} />);
    expect(screen.getByRole("note", { name: "Veredito" })).toHaveTextContent(
      /Regimes: HMM com 2 estados previu o mês seguinte melhor que a regra simples/,
    );
    const table = screen.getByRole("table", { name: "Modelos do laboratório" });
    expect(within(table).getByRole("columnheader", { name: "Chance de ser melhor de verdade" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Acerto acumulado do Regimes: HMM com 2 estados/ })).toBeInTheDocument();
    // HMM is the model on the chart, so its stress regime shows too.
    expect(screen.getByRole("img", { name: /regime de estresse/ })).toBeInTheDocument();
  });

  it("charts the model picked in the table and says when it did not pass", () => {
    const data = lab({
      models: lab().models!.map((m) => ({ ...m, cumulative_gain: [{ month: "2026-08-31", value: 0 }, { month: "2026-09-30", value: -0.2 }] })),
    });
    render(<LabView data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "Risco: EWMA com λ = 0,94" }));
    expect(screen.getByRole("button", { name: "Risco: EWMA com λ = 0,94" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("img", { name: /Acerto acumulado do Risco: EWMA/ })).toBeInTheDocument();
    expect(screen.getByText(/Não passou: o gráfico aparece só para ilustrar/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /regime de estresse/ })).not.toBeInTheDocument();
  });

  it("states that no model passed", () => {
    render(<LabView data={lab({ approved: [], models: lab().models!.map((m) => ({ ...m, passed: false })) })} />);
    expect(screen.getByRole("note", { name: "Veredito" })).toHaveTextContent(/Nenhum modelo de regime ou de risco/);
    expect(screen.getByText("Nenhum modelo passou")).toBeInTheDocument();
  });
});

describe("QualityPage", () => {
  it("puts the confidence and the laboratory behind the seals", async () => {
    mockApi([
      { path: "/simulations/calibration", reply: { run_id: null } },
      { path: "/simulations/lab", reply: lab() },
    ]);
    renderAt("/tools/simulation/quality");
    expect(screen.getByRole("heading", { name: "Qualidade dos modelos" })).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: "Modelos do laboratório" })).toBeInTheDocument();
  });
});
