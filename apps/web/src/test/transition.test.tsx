/** Phase 34: how to reach a class's targets, and the optimizer's verdict per class. */

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OptimizedDTO, TransitionDTO } from "../api/types";
import { Optimized } from "../features/recommendation/Optimized";
import { contributionLead, salesLead, Transition } from "../features/recommendation/Transition";
import { mockApi } from "./mockApi";
import { render } from "./render";

afterEach(() => vi.unstubAllGlobals());

function plan(overrides: Partial<TransitionDTO> = {}): TransitionDTO {
  return {
    status: "OK",
    arca_class: "ACOES",
    as_of: "2026-11-02",
    total_brl: 100000,
    distance: 0.5,
    monthly_brl: 2000,
    months: 18,
    tolerance: 0.05,
    lines: [
      { ticker: "WEGE3", current_weight: 1, target_weight: 0.5, current_brl: 100000, target_brl: 50000, next_contribution_brl: 0, buy_brl: 0 },
      { ticker: "ITSA4", current_weight: 0, target_weight: 0.5, current_brl: 0, target_brl: 50000, next_contribution_brl: 2000, buy_brl: 46000 },
    ],
    sales: [{ ticker: "WEGE3", asset_type: "STOCK_BR", quantity: 500, value_brl: 50000, cost_brl: 25000, gain_brl: 24985 }],
    sold_brl: 50000,
    tax_brl: 3747.75,
    fees_brl: 29,
    cost_brl: 3776.75,
    split_months: 3,
    split_tax_brl: 0,
    expected_gain_year_brl: 4600,
    payback_months: 9.9,
    pays_off: true,
    payback_horizon_months: 36,
    ...overrides,
  };
}

const text = (value: string) => value.replace(/\u00a0/g, " ");

describe("the sentences of the transition", () => {
  it("tells the contributions path", () => {
    expect(text(contributionLead(plan()))).toBe(
      "Só com aportes de R$ 2.000,00 por mês, a classe chega perto dos pesos-alvo em 18 meses, sem vender nada nem pagar IR.",
    );
    expect(contributionLead(plan({ months: 0 }))).toBe("A classe já está perto dos pesos-alvo: não há o que mudar.");
    expect(contributionLead(plan({ months: null, monthly_brl: 0 }))).toContain("Informe quanto");
    expect(text(contributionLead(plan({ months: null })))).toContain("não chega perto dos pesos-alvo em 20 anos");
  });

  it("tells whether the sales pay off", () => {
    expect(text(salesLead(plan()))).toBe(
      "Vender R$ 50.000,00 custaria R$ 3.776,75 (R$ 3.747,75 de IR e R$ 29,00 de custos), pagos pela melhora esperada em 9,9 meses.",
    );
    expect(salesLead(plan({ pays_off: false, payback_months: 50 }))).toContain("mais que o horizonte de 36 meses");
    expect(salesLead(plan({ pays_off: false, payback_months: null }))).toContain("não paga esse custo");
    expect(salesLead(plan({ sales: [] }))).toContain("Nada a vender");
  });
});

describe("how to reach the targets", () => {
  it("only asks the API when requested and shows both paths", async () => {
    const { calls } = mockApi([{ path: "/recommendation/transition", reply: plan() }]);
    render(<Transition arcaClass="ACOES" />);
    expect(calls).toHaveLength(0);

    fireEvent.change(screen.getByLabelText("Aporte mensal nesta classe (R$)"), { target: { value: "2.000,00" } });
    fireEvent.click(screen.getByRole("button", { name: "Ver o caminho" }));

    expect(await screen.findByRole("table", { name: "Vendas do estudo" })).toHaveTextContent("WEGE3");
    expect(screen.getByRole("table", { name: "Pesos atuais e alvos" })).toHaveTextContent("ITSA4");
    expect(screen.getByText("IR em 3 meses")).toBeInTheDocument();
    expect(screen.getByText(/nenhuma ordem é dada/)).toBeInTheDocument();
    expect(calls[0].query.get("arca_class")).toBe("ACOES");
    expect(calls[0].query.get("monthly_brl")).toBe("2000");
  });

  it("refuses an invalid amount and explains a class without a run", async () => {
    const { calls } = mockApi([{ path: "/recommendation/transition", reply: plan({ status: "NOT_COMPUTED" }) }]);
    render(<Transition arcaClass="CAIXA" />);
    const field = screen.getByLabelText("Aporte mensal nesta classe (R$)");
    fireEvent.change(field, { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Ver o caminho" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Informe um valor");
    expect(calls).toHaveLength(0);

    fireEvent.change(field, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Ver o caminho" }));
    await waitFor(() => expect(screen.getByText(/ainda não tem rodada/)).toBeInTheDocument());
  });

  it("shows the API error", async () => {
    mockApi([{ path: "/recommendation/transition", reply: { status: 500, json: { detail: "falhou" } } }]);
    render(<Transition arcaClass="ACOES" />);
    fireEvent.click(screen.getByRole("button", { name: "Ver o caminho" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("the optimizer's verdict per class", () => {
  const optimized = { status: "OK", assets: [], utility: 0, construction_utility: 0, draws: 16 } as unknown as OptimizedDTO;

  it("says the test only covers Ações in the other classes", () => {
    render(<Optimized optimized={optimized} inUse={false} passedElsewhere />);
    expect(screen.getByText(/O teste no passado só cobre Ações/)).toBeInTheDocument();
  });

  it("keeps the usual text when it did not pass", () => {
    render(<Optimized optimized={optimized} inUse={false} />);
    expect(screen.getByText(/Ainda não venceu a construção/)).toBeInTheDocument();
  });
});
