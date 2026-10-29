import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AssetComparisonDTO } from "../api/types";
import { compareLink, formatIndicator, parseTickers, searchFilters } from "../pages/tools/AssetComparePage";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

const comparison: AssetComparisonDTO = {
  assets: [
    {
      ticker: "WEGE3",
      name: "WEG",
      asset_type: "STOCK_BR",
      profile: "STOCK",
      asset_id: 7,
      currency: "BRL",
      price: 40,
      valuation_verdict: "FAIR",
      checklist_score: 5,
      checklist_max_score: 8,
      checklist_recommendation: "APTO",
      statement_years: 2,
    },
    {
      ticker: "HGLG11",
      name: "CSHG Logística",
      asset_type: "FII",
      profile: "FII_BRICK",
      asset_id: null,
      currency: "BRL",
      price: 160,
      valuation_verdict: "DISCOUNTED",
      checklist_score: 2,
      checklist_max_score: 6,
      checklist_recommendation: "REVISAR",
      statement_years: 0,
    },
  ],
  rows: [
    {
      key: "price_to_earnings",
      label: "P/L",
      group: "VALUATION",
      unit: "MULTIPLE",
      better: "LOWER",
      values: { WEGE3: 30.5, HGLG11: 9.2 },
      best: ["HGLG11"],
    },
    {
      key: "return_on_equity",
      label: "ROE",
      group: "PROFITABILITY",
      unit: "FRACTION",
      better: "HIGHER",
      values: { WEGE3: 0.3, HGLG11: null },
      best: [],
    },
  ],
  history: [
    {
      ticker: "WEGE3",
      points: [
        { year: 2023, revenue: 100, net_income: 10, roe: 0.2, dividend_yield: 0.02 },
        { year: 2024, revenue: 120, net_income: 15, roe: 0.25, dividend_yield: 0.03 },
      ],
    },
    { ticker: "HGLG11", points: [] },
  ],
  warnings: ["Perfis diferentes (FII × ação): os indicadores não significam a mesma coisa entre eles."],
  groups: [
    { group: "VALUATION", label: "Valuation" },
    { group: "DEBT", label: "Endividamento" },
    { group: "EFFICIENCY", label: "Eficiência" },
    { group: "PROFITABILITY", label: "Rentabilidade" },
    { group: "GROWTH", label: "Crescimento" },
  ],
  indicators: [
    { key: "price_to_earnings", label: "P/L", group: "VALUATION", unit: "MULTIPLE", better: "LOWER" },
    { key: "return_on_equity", label: "ROE", group: "PROFITABILITY", unit: "FRACTION", better: "HIGHER" },
  ],
};

describe("asset comparator", () => {
  it("parses and builds ticker lists", () => {
    expect(parseTickers(" wege3,HGLG11,wege3,,a1,b1,c1,d1")).toEqual(["WEGE3", "HGLG11", "A1", "B1", "C1"]);
    expect(parseTickers(null)).toEqual([]);
    expect(compareLink("WEGE3", "ITUB4")).toBe("/tools/compare?tickers=WEGE3%2CITUB4");
    expect(formatIndicator(0.123, "FRACTION")).toBe("12,3%");
    expect(formatIndicator(9.2, "MULTIPLE")).toBe("9,2");
    expect(formatIndicator(null, "MULTIPLE")).toBe("—");
  });

  it("builds screener filters from the search form", () => {
    expect(searchFilters({ q: "  ", sector: "", arcaClasses: [] })).toEqual({
      q: undefined,
      sector: undefined,
      arca_class: undefined,
      limit: 20,
    });
    expect(searchFilters({ q: " banco ", sector: "Finance", arcaClasses: ["ACOES"] })).toEqual({
      q: "banco",
      sector: ["Finance"],
      arca_class: ["ACOES"],
      limit: 20,
    });
  });

  it("asks for two tickers before calling the API", async () => {
    const { calls } = mockApi([]);
    renderAt("/tools/compare?tickers=WEGE3");
    expect(await screen.findByText("Escolha ao menos dois ativos")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/research/compare")).toBe(false);
  });

  it("shows assets side by side, the best of each row, warnings and lets indicators be hidden", async () => {
    const { calls } = mockApi([{ path: "/research/compare", reply: comparison }]);
    renderAt("/tools/compare?tickers=WEGE3,HGLG11");

    const table = await screen.findByRole("table");
    expect(calls.find((c) => c.path === "/research/compare")?.query.get("tickers")).toBe("WEGE3,HGLG11");
    expect(screen.getByRole("note")).toHaveTextContent("Perfis diferentes");
    expect(within(table).getByRole("link", { name: "WEGE3" })).toHaveAttribute("href", "/asset/7");

    const pl = within(table).getByText("P/L").closest("tr") as HTMLElement;
    const cells = within(pl).getAllByRole("cell");
    expect(cells[2]).toHaveClass("compare-best");
    expect(cells[2]).toHaveTextContent("9,2 ▲ melhor");
    expect(cells[1]).not.toHaveClass("compare-best");
    expect(within(table).getByText("30,0%")).toBeInTheDocument();
    expect(within(table).getByText("Descontado")).toBeInTheDocument();
    expect(within(table).getByText("5/8")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Escolher indicadores"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Rentabilidade" }));
    await waitFor(() => expect(within(table).queryByText("ROE")).not.toBeInTheDocument());
    expect(within(table).getByText("P/L")).toBeInTheDocument();

    expect(screen.getByRole("img", { name: "Receita por ano" })).toBeInTheDocument();
  });

  it("adds and removes tickers through the URL", async () => {
    const { calls } = mockApi([{ path: "/research/compare", reply: comparison }]);
    renderAt("/tools/compare?tickers=WEGE3");
    fireEvent.change(screen.getByLabelText("Ticker para comparar"), { target: { value: "hglg11" } });
    fireEvent.click(screen.getByRole("button", { name: "Adicionar" }));
    await screen.findByRole("table");
    expect(calls.find((c) => c.path === "/research/compare")?.query.get("tickers")).toBe("WEGE3,HGLG11");

    fireEvent.click(screen.getByRole("button", { name: "Remover HGLG11" }));
    expect(await screen.findByText("Escolha ao menos dois ativos")).toBeInTheDocument();
  });

  it("searches by sector and ARCA class and adds a result to the comparison", async () => {
    const screener = {
      results: [
        { ticker: "ITUB4", name: "Itaú", asset_type: "STOCK_BR", arca_class: "ACOES", sector: "Finance", close: 32 },
        { ticker: "WEGE3", name: "WEG", asset_type: "STOCK_BR", arca_class: "ACOES", sector: "Industrials", close: 40 },
      ],
      candidates: 2,
      scanned: 2,
      truncated: false,
      catalog_size: 7,
    };
    const { calls } = mockApi([
      { path: "/research/screener", reply: screener },
      { path: "/research/sectors", reply: ["Finance", "Industrials"] },
      { path: "/research/compare", reply: comparison },
    ]);
    renderAt("/tools/compare?tickers=WEGE3");

    expect(await screen.findByRole("option", { name: "Finance" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Setor"), { target: { value: "Finance" } });
    fireEvent.click(screen.getByLabelText("Classe ARCA"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Ações" }));
    fireEvent.change(screen.getByLabelText("Nome ou código"), { target: { value: "ita" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));

    const results = await screen.findByRole("table", { name: "Resultados da busca" });
    const query = calls.find((c) => c.path === "/research/screener")?.query;
    expect(query?.getAll("sector")).toEqual(["Finance"]);
    expect(query?.getAll("arca_class")).toEqual(["ACOES"]);
    expect(query?.get("q")).toBe("ita");
    expect(within(results).getByText(/Itaú · Finance/)).toBeInTheDocument();
    expect(within(results).getByRole("button", { name: "Adicionar WEGE3" })).toBeDisabled();

    fireEvent.click(within(results).getByRole("button", { name: "Adicionar ITUB4" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/research/compare")?.query.get("tickers")).toBe("WEGE3,ITUB4"),
    );
    expect(screen.getByRole("button", { name: "Remover ITUB4" })).toBeInTheDocument();
  });
});
