/** Unit and integration tests for Frontend formatting, pagination engine, clean empty state, Hamburger navigation, and API rendering. */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { EMPTY_PORTFOLIO_REPORT } from "../services/apiClient";
import type { PortfolioReportDTO } from "../types/api";
import {
  formatCurrencyBRL,
  formatPercent,
  paginateAndSortItems,
} from "../utils/formatters";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Frontend Utilities & Standardized Pagination Engine", () => {
  it("formats BRL currency and percentages accurately", () => {
    expect(formatCurrencyBRL(15400)).toContain("15.400,00");
    expect(formatPercent(16.03, 2, true)).toBe("+16,03%");
  });

  it("paginates, sorts, and filters records deterministically", () => {
    const sample = [
      { id: 1, ticker: "WEGE3", arca_class: "ACOES", val: 200 },
      { id: 2, ticker: "BBAS3", arca_class: "ACOES", val: 500 },
      { id: 3, ticker: "HGLG11", arca_class: "REAL_ESTATE", val: 300 },
    ];

    const page1 = paginateAndSortItems(
      sample,
      {
        page: 1,
        pageSize: 2,
        sortBy: "val",
        sortOrder: "desc",
        search: "",
        filters: {},
      },
      ["ticker"],
    );

    expect(page1.meta.total_items).toBe(3);
    expect(page1.meta.total_pages).toBe(2);
    expect(page1.items[0].ticker).toBe("BBAS3");
    expect(page1.items[1].ticker).toBe("HGLG11");

    const filtered = paginateAndSortItems(
      sample,
      {
        page: 1,
        pageSize: 10,
        sortBy: "ticker",
        sortOrder: "asc",
        search: "weg",
        filters: { arca_class: "ACOES" },
      },
      ["ticker"],
    );
    expect(filtered.meta.total_items).toBe(1);
    expect(filtered.items[0].ticker).toBe("WEGE3");
  });
});

describe("App UI/UX Integration (Clean Empty State, Hamburger Drawer & API Data)", () => {
  it("starts with a clean empty portfolio awaiting user input when database is empty", async () => {
    render(<App />);

    expect(screen.getByText("Patrimônio Atual Líquido")).toBeInTheDocument();
    expect(screen.getByText("Rendimento Estimado Até Hoje")).toBeInTheDocument();
    expect(screen.getByText("Ganho / Perda Consolidado")).toBeInTheDocument();
    expect(screen.getByText("Proventos Recebidos (MVP)")).toBeInTheDocument();

    expect(screen.getByTestId("table-dashboard-positions")).toBeInTheDocument();
    expect(
      screen.getByText(/Nenhuma posição aberta ainda/i),
    ).toBeInTheDocument();
  });

  it("renders backend positions and navigates across views via Hamburger Drawer with optional Cerrado", async () => {
    const mockedReport: PortfolioReportDTO = {
      ...EMPTY_PORTFOLIO_REPORT,
      total_invested_brl: 15400,
      total_current_value_brl: 20960,
      positions: [
        {
          asset_id: 1,
          ticker: "WEGE3",
          name: "WEG S.A.",
          asset_type: "STOCK_BR",
          arca_class: "ACOES",
          currency: "BRL",
          quantity: 400,
          average_price: 38.5,
          current_unit_price: 52.4,
          fx_rate: 1.0,
          price_freshness: "LIVE",
          invested_value_brl: 15400,
          gross_current_value_brl: 20960,
          estimated_tax_brl: 0,
          current_value_brl: 20960,
          unrealized_pnl_brl: 5560,
          unrealized_pnl_pct: 36.1,
          realized_pnl_brl: 0,
          received_earnings_brl: 620,
          earnings_12m_brl: 540,
          yield_on_cost_pct: 3.51,
          estimated_yield_to_date_brl: 6180,
          estimated_yield_to_date_pct: 40.13,
          estimated_yield_basis: "Valorização + Dividendos/JCP + YoC",
          projected_12m_yield_brl: 2216.8,
          consolidated_pnl_brl: 6180,
          consolidated_return_pct: 40.13,
          cerrado_evaluation: {
            asset_type: "STOCK_BR",
            use_cerrado: true,
            score: 10,
            max_score: 12,
            answered: 11,
            pending: 1,
            recommendation: "APTO",
          },
          class_target_weight_pct: 100,
          class_current_weight_pct: 100,
        },
      ],
    };

    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/api/v1/portfolio/consolidated")) {
        return new Response(JSON.stringify(mockedReport), { status: 200 });
      }
      return new Response(JSON.stringify({ items: [], meta: {} }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("WEGE3")).toBeInTheDocument();
    });

    const hamburgerBtn = screen.getByLabelText("Abrir menu de navegação");
    fireEvent.click(hamburgerBtn);

    const contributionLink = screen.getByText("Simulador de Aporte (2 Níveis)");
    fireEvent.click(contributionLink);

    expect(
      screen.getByText("Simulador de Aporte em 2 Níveis (ARCA + Estratégia Intra-Classe)"),
    ).toBeInTheDocument();

    const strategySelect = screen.getByLabelText("Estratégia Intra-Classe");
    fireEvent.change(strategySelect, { target: { value: "EQUAL_WEIGHT" } });

    await waitFor(() => {
      expect(screen.getAllByText("PESO IGUAL (CERRADO OFF)").length).toBeGreaterThan(0);
    });
  });
});
