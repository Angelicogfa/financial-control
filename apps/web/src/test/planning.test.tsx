/** Phase 48.R8: Planejar › Metas, Planejar › Renda futura and the amount suggested in Aportar. */

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { GoalDTO, IncomeForecastDTO } from "../api/types";
import { goalLead } from "../features/planning/GoalsPage";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

function goal(overrides: Partial<GoalDTO> = {}): GoalDTO {
  return {
    id: 1,
    kind: "WEALTH",
    name: "Independência",
    target_brl: 1000000,
    target_date: "2036-11-02",
    monthly_contribution_brl: 3000,
    annual_return: 0.06,
    income_yield: 0.06,
    is_active: true,
    months_left: 120,
    current_brl: 400000,
    target_wealth_brl: 1000000,
    current_wealth_brl: 400000,
    progress: 0.4,
    projected_wealth_brl: 1206000,
    required_monthly_brl: 1650,
    status: "ON_TRACK",
    ...overrides,
  };
}

const forecast: IncomeForecastDTO = {
  as_of: "2026-11-02",
  months: [
    { month: "2026-11", declared_brl: 172.5, estimated_brl: 0, total_brl: 172.5 },
    { month: "2026-12", declared_brl: 0, estimated_brl: 90, total_brl: 90 },
  ],
  next_12m_brl: 262.5,
  declared_brl: 172.5,
  assets: [{ asset_id: 3, ticker: "HGLG11", next_12m_brl: 262.5 }],
};

describe("goals", () => {
  it("says what it takes from now on", () => {
    const lead = (g: GoalDTO) => goalLead(g).replace(/\u00a0/g, " ");
    expect(lead(goal())).toBe("Em 10 ano(s), com R$ 3.000,00 por mês chega a R$ 1.206.000,00.");
    expect(lead(goal({ status: "OFF_TRACK", months_left: 14, monthly_contribution_brl: 500 }))).toBe(
      "Em 1 ano(s) e 2 mês(es), faltam R$ 1.650,00 por mês (hoje: R$ 500,00).",
    );
    expect(lead(goal({ status: "REACHED" }))).toBe("Meta atingida.");
  });

  it("lists the goals with their progress, creates and deletes one", async () => {
    const { calls } = mockApi([
      {
        path: "/goals",
        reply: [goal(), goal({ id: 2, kind: "PASSIVE_INCOME", name: "Renda", target_brl: 5000, current_brl: 1500, progress: 0.3, status: "OFF_TRACK" })],
      },
      { method: "POST", path: "/goals", reply: { status: 201, json: goal() } },
      { method: "DELETE", path: "/goals/1", reply: { status: 204 } },
    ]);
    renderAt("/planejar/metas");

    const list = await screen.findByRole("list", { name: "Metas" });
    const [first, second] = within(list).getAllByRole("listitem");
    expect(first).toHaveTextContent("No caminho");
    expect(within(first).getByRole("progressbar", { name: "Progresso de Independência" })).toHaveAttribute("aria-valuenow", "40");
    expect(second).toHaveTextContent("Fora do caminho");
    expect(second).toHaveTextContent("por mês de R$ 5.000,00");

    const form = screen.getByRole("form", { name: "Nova meta" });
    fireEvent.change(within(form).getByLabelText("Tipo"), { target: { value: "PASSIVE_INCOME" } });
    fireEvent.change(within(form).getByLabelText("Nome"), { target: { value: "Renda de 5 mil" } });
    fireEvent.change(within(form).getByLabelText("Renda por mês (R$)"), { target: { value: "5000" } });
    fireEvent.change(within(form).getByLabelText("Até"), { target: { value: "2036-01-01" } });
    fireEvent.change(within(form).getByLabelText("Aporte mensal (R$)"), { target: { value: "2.000,00" } });
    fireEvent.change(within(form).getByLabelText("Yield da renda (% a.a.)"), { target: { value: "8" } });
    fireEvent.click(within(form).getByRole("button", { name: "Criar meta" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      kind: "PASSIVE_INCOME",
      name: "Renda de 5 mil",
      target_brl: 5000,
      target_date: "2036-01-01",
      monthly_contribution_brl: 2000,
      annual_return: 0.06,
      income_yield: 0.08,
    });

    fireEvent.click(within(first).getByRole("button", { name: "Apagar a meta Independência" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("asks for the missing fields", async () => {
    const { calls } = mockApi([{ path: "/goals", reply: [] }]);
    renderAt("/planejar/metas");
    fireEvent.click(await screen.findByRole("button", { name: "Criar meta" }));
    expect(screen.getByText("Preencha o nome, o valor, a data e as premissas.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });
});

describe("future income", () => {
  it("shows declared and estimated income and switches the horizon", async () => {
    const { calls } = mockApi([{ path: "/portfolio/income-forecast", reply: forecast }]);
    renderAt("/planejar/renda-futura");

    expect(await screen.findByLabelText("Renda futura")).toHaveTextContent("R$ 262,50");
    const table = screen.getByRole("table", { name: "Renda prevista por mês" });
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("R$ 172,50");
    expect(screen.getByRole("link", { name: "HGLG11" })).toHaveAttribute("href", "/ativo/HGLG11");

    fireEvent.click(screen.getByRole("button", { name: "36 meses" }));
    await waitFor(() => expect(calls.some((c) => c.query.get("months") === "36")).toBe(true));
  });
});

describe("Aportar suggested by the goals", () => {
  it("offers the largest monthly contribution an open goal asks for", async () => {
    mockApi([
      { path: "/contributions", reply: [] },
      { path: "/goals", reply: [goal({ required_monthly_brl: 1650.2 }), goal({ id: 2, name: "Reserva", required_monthly_brl: 900, status: "OFF_TRACK" }), goal({ id: 3, status: "REACHED", required_monthly_brl: 0 })] },
    ]);
    renderAt("/aportar");
    const hint = await screen.findByRole("note", { name: "Pelas suas metas" });
    expect(hint).toHaveTextContent("A meta “Independência” pede R$ 1.651,00 por mês até 02/11/2036.");
    fireEvent.click(within(hint).getByRole("button", { name: "Usar este valor" }));
    expect(screen.getByLabelText("Quanto vai aportar (R$)")).toHaveValue("1651");
  });
});
