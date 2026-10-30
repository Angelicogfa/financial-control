import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AssetStatementsDTO } from "../api/types";
import { analysis } from "./fixtures";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

function statements(overrides: Partial<AssetStatementsDTO> = {}): AssetStatementsDTO {
  return {
    asset_id: 1,
    ticker: "WEGE3",
    status: "OK",
    cnpj: "84429695000111",
    template: "COMPANY",
    deliveries: [
      {
        reference_date: "2025-09-30",
        delivered_on: "2025-10-29",
        doc_type: "ITR",
        version: 2,
        revenue: 38_000_000_000,
        ebitda: 8_500_000_000,
        net_income: 6_000_000_000,
        dividends_paid: 2_900_000_000,
        equity: 22_000_000_000,
        net_debt: -4_400_000_000,
      },
    ],
    valuation: {
      price: 50,
      market_cap: 210_000_000_000,
      earnings_yield: 0.0288,
      dividend_yield: 0.014,
      price_to_book: 9.4,
      ev_to_ebitda: 24.2,
    },
    years_loaded: [2024, 2025],
    notes: ["Cada linha mostra o que se sabia logo depois da entrega."],
    ...overrides,
  };
}

describe("CVM statements in the Fundamentals tab (Phase 42.2)", () => {
  it("lists each delivery with its date and today's indicators", async () => {
    mockApi([
      { path: "/assets/1/analysis", reply: analysis() },
      { path: "/assets/1/statements", reply: statements() },
    ]);
    renderAt("/asset/1?tab=fundamentals");
    const table = await screen.findByRole("table", { name: "Balanços entregues à CVM" });
    expect(within(table).getByText("29/10/2025")).toBeInTheDocument();
    expect(within(table).getByText("· versão 2")).toBeInTheDocument();
    expect(within(table).getByText("Dívida líquida")).toBeInTheDocument();
    expect(within(screen.getByLabelText(/Indicadores ao preço/)).getByText("P/VP")).toBeInTheDocument();
    expect(screen.getByText("34,7")).toBeInTheDocument(); // P/L = 1 / 2.88%
    expect(screen.getByText(/Último: ITR de 30\/09\/2025, entregue em 29\/10\/2025/)).toBeInTheDocument();
  });

  it("hides company-only columns for a bank and explains a missing load", async () => {
    mockApi([
      { path: "/assets/1/analysis", reply: analysis() },
      { path: "/assets/1/statements", reply: statements({ template: "FINANCIAL" }) },
    ]);
    renderAt("/asset/1?tab=fundamentals");
    const table = await screen.findByRole("table", { name: "Balanços entregues à CVM" });
    expect(within(table).queryByText("Dívida líquida")).not.toBeInTheDocument();
    expect(within(table).queryByText("EBITDA 12m")).not.toBeInTheDocument();
  });

  it("says when the statements are not loaded yet", async () => {
    mockApi([
      { path: "/assets/1/analysis", reply: analysis() },
      {
        path: "/assets/1/statements",
        reply: statements({ status: "NOT_LOADED", deliveries: [], valuation: null, notes: ["Ainda não carregados."] }),
      },
    ]);
    renderAt("/asset/1?tab=fundamentals");
    expect(await screen.findByText("Balanços ainda não carregados")).toBeInTheDocument();
    expect(screen.getByText("Ainda não carregados.")).toBeInTheDocument();
  });
});
