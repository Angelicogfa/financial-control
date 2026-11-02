/** Phase 48.R7: Carteira › Imposto. */

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TaxMonthDTO, TaxYearDTO } from "../api/types";
import { darfStatus } from "../features/portfolio/TaxPage";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

function month(overrides: Partial<TaxMonthDTO> = {}): TaxMonthDTO {
  return {
    month: "2025-03",
    categories: [
      {
        category: "COMMON",
        sales_brl: 25000,
        result_brl: 3000,
        exempt_gain_brl: 0,
        loss_in_brl: 0,
        loss_used_brl: 0,
        loss_out_brl: 0,
        taxable_brl: 3000,
        rate: 0.15,
        tax_brl: 450,
      },
    ],
    stock_sales_brl: 25000,
    exempt: false,
    tax_brl: 450,
    withheld_brl: 1.25,
    withheld_credit_in_brl: 0,
    withheld_credit_out_brl: 0,
    carried_darf_in_brl: 0,
    darf_brl: 448.75,
    carried_darf_out_brl: 0,
    due_date: "2025-04-30",
    darf_code: "6015",
    paid_on: null,
    sales: [],
    ...overrides,
  };
}

const year: TaxYearDTO = {
  year: 2025,
  months: [
    month({ month: "2025-02", exempt: true, stock_sales_brl: 13000, tax_brl: 0, darf_brl: 0, withheld_brl: 0.65, categories: [{ ...month().categories[0], sales_brl: 13000, result_brl: -2000, taxable_brl: 0, tax_brl: 0, loss_out_brl: 2000 }] }),
    month(),
  ],
  foreign: { year: 2025, sales_brl: 4125, result_brl: 1625, loss_in_brl: 250, loss_out_brl: 0, taxable_brl: 1375, rate: 0.15, tax_brl: 206.25 },
  tax_brl: 450,
  darf_brl: 448.75,
  open_darf_brl: 448.75,
  issues: [],
};

describe("DARF status", () => {
  it("tells paid, due, overdue, carried and nothing to pay", () => {
    expect(darfStatus(month({ paid_on: "2025-04-25" }), "2025-05-10").label).toBe("Pago em 25/04/2025");
    expect(darfStatus(month(), "2025-04-10").label).toBe("A pagar");
    expect(darfStatus(month(), "2025-05-02")).toEqual({ label: "Vencido", tone: "danger" });
    expect(darfStatus(month({ darf_brl: 0, carried_darf_out_brl: 7.47 }), "2025-05-02").label).toBe("Abaixo de R$ 10: acumula");
    expect(darfStatus(month({ darf_brl: 0 }), "2025-05-02").label).toBe("Nada a pagar");
  });
});

describe("Carteira › Imposto", () => {
  it("shows the year month by month, the losses to offset and the foreign assessment", async () => {
    const { calls } = mockApi([{ path: "/tax/monthly", reply: year }]);
    renderAt("/carteira/imposto?ano=2025");

    const table = await screen.findByRole("table", { name: "Apuração mensal" });
    const [feb, mar] = within(table).getAllByRole("row").slice(1);
    expect(feb).toHaveTextContent("isento");
    expect(feb).toHaveTextContent("Nada a pagar");
    expect(mar).toHaveTextContent("R$ 448,75");
    expect(mar).toHaveTextContent("30/04/2025");
    expect(calls[0].query.get("year")).toBe("2025");
    expect(screen.getByLabelText("Imposto do ano")).toHaveTextContent("Prejuízo a compensar · Operações comuns");
    expect(screen.getByRole("heading", { name: "Exterior (anual)" })).toBeInTheDocument();
    expect(screen.getByLabelText("Exterior no ano")).toHaveTextContent("R$ 206,25");
  });

  it("opens the sales of a month and marks its DARF as paid", async () => {
    const { calls } = mockApi([
      { path: "/tax/monthly", reply: year },
      {
        path: "/tax/monthly/2025-03",
        reply: month({
          sales: [
            { asset_id: 1, ticker: "PETR4", on: "2025-03-05", quantity: 1000, sale_value_brl: 25000, cost_brl: 22000, fees_brl: 0, gain_brl: 3000, day_trade: false, category: "COMMON" },
          ],
        }),
      },
      { method: "PUT", path: "/tax/monthly/2025-03/darf", reply: month({ paid_on: "2026-11-02" }) },
    ]);
    renderAt("/carteira/imposto?ano=2025");
    const table = await screen.findByRole("table", { name: "Apuração mensal" });
    const mar = within(table).getAllByRole("row")[2];

    fireEvent.click(within(mar).getByRole("button", { name: "Ver vendas" }));
    const sales = await screen.findByRole("table", { name: "Vendas do mês" });
    expect(sales).toHaveTextContent("PETR4");
    expect(sales).toHaveTextContent("R$ 3.000,00");

    fireEvent.click(within(mar).getByRole("button", { name: "Marcar como pago" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect((calls.find((c) => c.method === "PUT")?.body as { paid_on: string }).paid_on).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("says when the year has no sale", async () => {
    mockApi([{ path: "/tax/monthly", reply: { ...year, months: [], foreign: null, tax_brl: 0, darf_brl: 0, open_darf_brl: 0 } }]);
    renderAt("/carteira/imposto?ano=2025");
    expect(await screen.findByText("Nenhuma venda de renda variável em 2025")).toBeInTheDocument();
  });
});
