import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AssetTaxStatusDTO, FixedIncomeComparisonDTO, OfferOutcomeDTO, OfferProjectionDTO } from "../api/types";
import { toOfferRequest } from "../pages/tools/FixedIncomeComparePage";
import { analysis, asset } from "./fixtures";
import { optionLabels } from "./combobox";
import { mockApi, type Call } from "./mockApi";
import { renderAt } from "./render";

const page = <T,>(items: T[]) => ({
  items,
  meta: { page: 1, page_size: 200, total_items: items.length, total_pages: 1, sort_by: "ticker", sort_order: "asc" },
});
const last = (calls: Call[], method: string, path: string) =>
  [...calls].reverse().find((c) => c.method === method && c.path === path);

const regressive = {
  regime: "FIXED_INCOME_REGRESSIVE" as const,
  tax_kind: "INCOME_TAX" as const,
  current_rate: 0.225,
  brackets: [
    { up_to_days: 180, rate: 0.225 },
    { up_to_days: 360, rate: 0.2 },
    { up_to_days: 720, rate: 0.175 },
    { up_to_days: null, rate: 0.15 },
  ],
  valid_from: "2005-01-01",
  valid_to: null,
  legal_basis: "Lei 11.033/2004, art. 1º",
  description: "Renda fixa tributada.",
};

function fixedIncomeStatus(overrides: Partial<AssetTaxStatusDTO> = {}): AssetTaxStatusDTO {
  return {
    asset_id: 1,
    ticker: "CDB-X",
    asset_type: "FIXED_INCOME",
    as_of_date: "2026-07-01",
    is_fixed_income: true,
    tax_exempt: false,
    regimes: [regressive],
    lots: [
      {
        start_date: "2026-01-02",
        principal: 10000,
        gross_value: 10700,
        gross_yield: 700,
        holding_days: 180,
        income_tax_rate: 0.225,
        iof_rate: 0,
        iof_due: 0,
        iof_free_date: null,
        income_tax_due: 157.5,
        net_value: 10542.5,
        next_bracket_date: "2026-07-02",
        days_to_next_bracket: 1,
        next_income_tax_rate: 0.2,
        projected_gross_at_next_bracket: 10704,
        tax_at_next_bracket: 140.8,
        tax_saving_by_waiting: 17.6,
        net_gain_by_waiting: 20.7,
      },
    ],
    invested_principal: 10000,
    gross_value: 10700,
    iof_due: 0,
    income_tax_due: 157.5,
    net_value: 10542.5,
    next_bracket_date: "2026-07-02",
    tax_saving_by_waiting: 17.6,
    ...overrides,
  };
}

const outcome = (days: number, net: number, redeemable = true): OfferOutcomeDTO => ({
  days,
  redemption_date: "2028-01-01",
  business_days: Math.round(days * 0.69),
  redeemable,
  gross_value: net + 300,
  gross_yield: net + 300 - 10000,
  iof: 0,
  income_tax_rate: 0.175,
  income_tax: 300,
  net_value: net,
  net_yield: net - 10000,
  gross_annual_rate: 0.15,
  net_annual_rate: 0.125,
});

const projection = (label: string, scenario: string, net: number, redeemable = true): OfferProjectionDTO => ({
  label,
  scenario,
  gross_annual_rate: 0.154,
  at_maturity: outcome(720, net),
  at_common_window: outcome(720, net, redeemable),
  equivalent_rates: [
    { up_to_days: 180, income_tax_rate: 0.225, exempt_equivalent_rate: 0.119, taxed_equivalent_rate: 0.199 },
    { up_to_days: null, income_tax_rate: 0.15, exempt_equivalent_rate: 0.131, taxed_equivalent_rate: 0.181 },
  ],
});

function comparison(): FixedIncomeComparisonDTO {
  return {
    as_of_date: "2026-10-27",
    principal: 10000,
    common_window_days: 720,
    offers: [
      { label: "CDB", asset_id: null, indexer: "CDI_PERCENT", rate: 1.1, term_days: 720, tax_exempt: false, grace_days: 0 },
      { label: "LCA", asset_id: null, indexer: "CDI_PERCENT", rate: 0.9, term_days: 720, tax_exempt: true, grace_days: 0 },
    ],
    scenarios: [
      { name: "LOW", annual_cdi_rate: 0.12, annual_ipca_rate: 0.035 },
      { name: "BASE", annual_cdi_rate: 0.14, annual_ipca_rate: 0.045 },
    ],
    projections: [
      projection("CDB", "BASE", 12900),
      projection("LCA", "BASE", 12700),
      projection("CDB", "LOW", 12400),
      projection("LCA", "LOW", 12500),
    ],
    break_evens: [
      { scenario: "BASE", first: "CDB", second: "LCA", winner: "CDB", break_even_days: 361, always_ahead: false },
      { scenario: "LOW", first: "CDB", second: "LCA", winner: "LCA", break_even_days: 1, always_ahead: true },
    ],
    best_by_scenario: { BASE: "CDB", LOW: "LCA" },
  };
}

describe("asset tax tab", () => {
  it("shows the bracket, the next drop and the lot table for fixed income", async () => {
    mockApi([
      { path: "/assets/1/analysis", reply: analysis({ asset: asset({ asset_type: "FIXED_INCOME" }) }) },
      { path: "/tax/assets/1/status", reply: fixedIncomeStatus() },
    ]);
    renderAt("/asset/1?tab=tax");
    expect(await screen.findByText("Próxima queda de faixa")).toBeInTheDocument();
    expect(screen.getByText("IR estimado se resgatar hoje")).toBeInTheDocument();
    expect(screen.getByText("Tabela regressiva")).toBeInTheDocument();
    expect(screen.getByText("181 a 360 dias")).toBeInTheDocument();
    expect(screen.getByText("Acima de 720 dias")).toBeInTheDocument();
    expect(screen.getByText("IR economizado esperando")).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("em 1 dias")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Comparar com outro título" })).toHaveAttribute(
      "href",
      "/tools/fixed-income?asset=1",
    );
  });

  it("shows IOF still due and exempt positions", async () => {
    const base = fixedIncomeStatus();
    mockApi([
      { path: "/assets/1/analysis", reply: analysis() },
      {
        path: "/tax/assets/1/status",
        reply: fixedIncomeStatus({
          tax_exempt: true,
          regimes: [{ ...regressive, regime: "FIXED_INCOME_EXEMPT", brackets: [{ up_to_days: null, rate: 0 }], current_rate: 0 }],
          lots: [{ ...base.lots[0], iof_due: 12.3, iof_free_date: "2026-02-01", next_bracket_date: null }],
          tax_saving_by_waiting: 0,
        }),
      },
    ]);
    renderAt("/asset/1?tab=tax");
    expect(await screen.findByText("zera em 01/02/2026")).toBeInTheDocument();
    expect(screen.getByText("Isento")).toBeInTheDocument();
    expect(screen.getByText("Renda fixa isenta")).toBeInTheDocument();
    expect(screen.queryByText("IR economizado esperando")).not.toBeInTheDocument();
  });

  it("shows the informative regimes of market assets", async () => {
    mockApi([
      { path: "/assets/1/analysis", reply: analysis() },
      {
        path: "/tax/assets/1/status",
        reply: fixedIncomeStatus({
          is_fixed_income: false,
          asset_type: "STOCK_BR",
          lots: [],
          regimes: [
            { ...regressive, regime: "STOCK_SWING_TRADE", brackets: [{ up_to_days: null, rate: 0.15 }], current_rate: 0.15, description: "Ações: 15%." },
            { ...regressive, regime: "JCP_WITHHOLDING", brackets: [{ up_to_days: null, rate: 0.175 }], current_rate: 0.175, legal_basis: "LC 224/2025", description: "JCP 17,5%." },
          ],
        }),
      },
    ]);
    renderAt("/asset/1?tab=tax");
    expect(await screen.findByText("Ganho na venda de ações")).toBeInTheDocument();
    expect(screen.getByText("Juros sobre capital próprio")).toBeInTheDocument();
    expect(screen.getByText(/LC 224\/2025/)).toBeInTheDocument();
  });
});

describe("fixed income comparator", () => {
  it("converts typed rows and portfolio rows to API offers (ADR 0006)", () => {
    const row = {
      key: 1,
      assetId: "" as const,
      label: " LCA ",
      indexer: "CDI_PERCENT" as const,
      rate: "92,5",
      termDays: "720",
      graceDays: "",
      taxExempt: true,
    };
    expect(toOfferRequest(row)).toEqual({
      label: "LCA",
      indexer: "CDI_PERCENT",
      rate: 0.925,
      term_days: 720,
      grace_days: null,
      tax_exempt: true,
    });
    expect(toOfferRequest({ ...row, indexer: "IPCA_SPREAD", rate: "6,5", graceDays: "90" })).toMatchObject({
      rate: 0.065,
      grace_days: 90,
    });
    expect(toOfferRequest({ ...row, assetId: 7, label: "" })).toEqual({ asset_id: 7, label: null });
  });

  it("compares typed offers and switches scenarios", async () => {
    const { calls } = mockApi([
      { path: "/assets", reply: page([]) },
      { method: "POST", path: "/tax/fixed-income/compare", reply: comparison() },
    ]);
    renderAt("/tools/fixed-income");
    expect(await screen.findByRole("heading", { name: "Comparar renda fixa" })).toBeInTheDocument();
    fireEvent.change(screen.getAllByLabelText("Nome")[0], { target: { value: "CDB" } });
    fireEvent.change(screen.getAllByLabelText("Nome")[1], { target: { value: "LCA" } });
    fireEvent.click(screen.getByRole("button", { name: "Comparar" }));

    expect(await screen.findByText(/CDB passa a render mais que LCA a partir de 361 dias/)).toBeInTheDocument();
    const body = last(calls, "POST", "/tax/fixed-income/compare")?.body as { offers: unknown[]; principal: number };
    expect(body.principal).toBe(10000);
    expect(body.offers).toEqual([
      { label: "CDB", indexer: "CDI_PERCENT", rate: 1.1, term_days: 720, grace_days: null, tax_exempt: false },
      { label: "LCA", indexer: "CDI_PERCENT", rate: 0.9, term_days: 720, grace_days: null, tax_exempt: true },
    ]);
    expect(screen.getByText("Na janela comum de 720 dias")).toBeInTheDocument();
    expect(screen.getByText("Melhor")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Juros em queda" }));
    expect(screen.getByText(/LCA rende mais que CDB em qualquer prazo da janela/)).toBeInTheDocument();
  });

  it("preselects a portfolio asset, adds and removes offers and shows API errors", async () => {
    const cdb = asset({
      id: 7,
      ticker: "CDB-ITAU",
      name: "CDB Itaú",
      asset_type: "FIXED_INCOME",
      fixed_income_term: {
        instrument_kind: "CDB",
        indexer: "CDI",
        contracted_rate: "1.10",
        issue_date: "2026-01-02",
        maturity_date: "2028-01-02",
        tax_exempt: false,
        liquidity: "AT_MATURITY",
      },
    });
    const { calls } = mockApi([
      { path: "/assets", reply: page([cdb, asset()]) },
      {
        method: "POST",
        path: "/tax/fixed-income/compare",
        reply: { status: 400, json: { code: "INCOMPLETE_OFFER", detail: "Offer 3 needs indexer" } },
      },
    ]);
    renderAt("/tools/fixed-income?asset=7");
    const origin = (await screen.findAllByLabelText("Origem"))[0];
    await waitFor(() => expect(origin).toHaveValue("CDB-ITAU — CDB Itaú"));
    expect(optionLabels(origin)).not.toContainEqual(expect.stringMatching(/WEGE3/));
    expect(screen.getByText(/vêm do cadastro do ativo/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Adicionar título" }));
    expect(screen.getAllByLabelText("Origem")).toHaveLength(3);
    fireEvent.click(screen.getAllByRole("button", { name: "Remover título" })[2]);
    expect(screen.getAllByLabelText("Origem")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Comparar" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    const body = last(calls, "POST", "/tax/fixed-income/compare")?.body as { offers: Array<{ asset_id?: number }> };
    expect(body.offers[0]).toEqual({ asset_id: 7, label: null });
  });
});
