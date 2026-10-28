import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { EarningsAgendaDTO, TreasuryMarketDTO } from "../api/types";
import { DeclaredEarnings } from "../pages/home/DeclaredEarnings";
import { TreasuryMarketPanel } from "../pages/portfolio/TreasuryMarketPanel";
import { analysis, asset } from "./fixtures";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

const market: TreasuryMarketDTO = {
  asset_id: 1,
  ticker: "PRE29",
  name: "Tesouro Prefixado 2029",
  as_of_date: "2026-10-28",
  status: "OPPORTUNITY",
  explanation: "O mercado está R$ 78,48 acima da curva.",
  maturity_date: "2029-01-01",
  price_date: "2026-10-28",
  market_price: 790,
  market_rate: 11.5,
  quantity: 2.45,
  curve_value: 1857.02,
  market_value: 1935.5,
  premium: 78.48,
  premium_pct: 0.0423,
  net_sale_value: 1891.51,
  reference_rate: 0.149,
  lots: [
    {
      start_date: "2026-03-17",
      quantity: 2.45,
      principal: 1715.54,
      purchase_rate: 0.1375,
      curve_value: 1857.02,
      market_value: 1935.5,
      premium: 78.48,
      holding_days: 225,
      curve_annual_rate: 0.1375,
      market_annual_rate: 0.2167,
      excess_rate: 0.0792,
      iof_on_sale: 0,
      income_tax_on_sale: 43.99,
      net_sale_value: 1891.51,
      net_hold_value: 2339.83,
      breakeven_rate: 0.1212,
      signals: ["EXCESS_RETURN", "REINVESTMENT"],
    },
  ],
  history: [
    { day: "2026-03-17", curve_value: 1715.54, market_value: 1715.0, premium: -0.54 },
    { day: "2026-10-28", curve_value: 1857.02, market_value: 1935.5, premium: 78.48 },
  ],
};

const agenda: EarningsAgendaDTO = {
  as_of_date: "2026-10-28",
  declared_net_brl: 12.0,
  declared_by_month: { "2026-11": 10, "2026-12": 2 },
  covered_tickers: ["BBAS3", "ITSA4"],
  items: [
    {
      ticker: "ITSA4",
      name: "Itaúsa",
      asset_id: 7,
      kind: "DIVIDEND",
      label: "DIVIDENDO",
      rate: 0.1,
      com_date: "2026-10-20",
      ex_date: "2026-10-21",
      payment_date: "2026-11-15",
      status: "AWAITING_PAYMENT",
      held: true,
      quantity: 100,
      gross_amount: 10,
      withholding_tax: 0,
      net_amount: 10,
    },
    {
      ticker: "BBAS3",
      name: "BB",
      asset_id: 9,
      kind: "JCP",
      label: "JRS CAP PROPRIO",
      rate: 0.25,
      com_date: "2026-11-03",
      ex_date: "2026-11-04",
      payment_date: "2026-12-10",
      status: "UPCOMING",
      held: false,
      quantity: 0,
    },
  ],
};

describe("treasury at market", () => {
  it("shows the market tab only for Treasury bonds, with lots and history", async () => {
    mockApi([
      {
        path: "/assets/1/analysis",
        reply: analysis({ asset: asset({ asset_type: "TREASURY", ticker: "PRE29", name: "Tesouro Prefixado 2029" }) }),
      },
      { path: "/portfolio/treasury-market/1", reply: market },
    ]);
    renderAt("/asset/1?tab=market");

    expect(await screen.findByText("Venda antecipada pode compensar")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Mercado" })).toBeInTheDocument();
    expect(screen.getByText("O mercado está R$ 78,48 acima da curva.")).toBeInTheDocument();
    const lots = screen.getByRole("table");
    expect(within(lots).getByText("Rende mais que a curva")).toBeInTheDocument();
    expect(within(lots).getByText("12,12%")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Valor na curva e a mercado desde a primeira compra" })).toBeInTheDocument();
  });

  it("hides the market tab for other assets", async () => {
    mockApi([{ path: "/assets/1/analysis", reply: analysis() }]);
    renderAt("/asset/1");
    await screen.findByRole("tab", { name: "Resumo" });
    expect(screen.queryByRole("tab", { name: "Mercado" })).not.toBeInTheDocument();
  });

  it("lists the bonds on the portfolio panel", async () => {
    mockApi([{ path: "/portfolio/treasury-market", reply: [{ ...market, status: "BELOW_CURVE", premium: -41.06 }] }]);
    render(
      <MemoryRouter>
        <TreasuryMarketPanel />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("link", { name: "Tesouro Prefixado 2029" })).toHaveAttribute("href", "/asset/1?tab=market");
    expect(screen.getByText("Abaixo da curva")).toBeInTheDocument();
  });
});

describe("declared earnings", () => {
  it("shows the agenda with held amounts and watchlist items", async () => {
    mockApi([{ path: "/portfolio/earnings-agenda", reply: agenda }]);
    render(
      <MemoryRouter>
        <DeclaredEarnings />
      </MemoryRouter>,
    );
    const card = await screen.findByRole("region", { name: "Proventos anunciados" });
    expect(within(card).getByText("Direito garantido")).toBeInTheDocument();
    expect(within(card).getByText("Watchlist")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "ITSA4" })).toHaveAttribute("href", "/asset/7");
    expect(within(card).getAllByText("R$ 10,00").length).toBeGreaterThan(0);
  });

  it("says when nothing is declared", async () => {
    mockApi([{ path: "/portfolio/earnings-agenda", reply: { ...agenda, items: [], declared_net_brl: 0, declared_by_month: {} } }]);
    render(
      <MemoryRouter>
        <DeclaredEarnings />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Nenhum provento anunciado")).toBeInTheDocument();
  });
});
