/** Phase 48.R4: the asset page as chapters, for registered assets and for any ticker. */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AppProviders, createQueryClient } from "../app/AppProviders";
import { AppRoutes } from "../app/AppRoutes";
import type { InstrumentLensesDTO, InstrumentViewDTO } from "../api/types";
import { chapterFromQuery, lensHighlights } from "../features/instrument/chapters";
import { analysis, asset, trackedInstrument } from "./fixtures";
import { mockApi } from "./mockApi";

function Where() {
  const location = useLocation();
  return <output aria-label="Endereço">{`${location.pathname}${location.search}`}</output>;
}

function renderAt(path: string) {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false, staleTime: 0 } });
  return render(
    <AppProviders client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
        <Where />
      </MemoryRouter>
    </AppProviders>,
  );
}

const lenses: InstrumentLensesDTO = {
  as_of: "2026-11-01",
  source: "PORTFOLIO",
  arca_class: "ACOES",
  sector: "Bens industriais",
  eligible: true,
  items: [
    { lens: "QUALITY", normalized: 0.9, confidence: 0.8, note: "ROE alto e estável" },
    { lens: "VALUATION", normalized: 0.2, confidence: 0.8, note: "caro contra o setor" },
    { lens: "MOMENTUM", normalized: null, confidence: 0, note: "" },
  ],
};

function untracked(overrides: Partial<InstrumentViewDTO> = {}): InstrumentViewDTO {
  return {
    key: "PETR4",
    kind: "LISTED",
    ticker: "PETR4",
    name: "Petrobras PN",
    asset_type: "STOCK_BR",
    sector: "Petróleo",
    in_catalog: true,
    quote: { price: 38.5, currency: "BRL", source: "CATALOG_CLOSE", change_pct: 0.012 },
    indicators: { price_to_earnings: 4.2, price_to_book: 1.1, return_on_equity: 0.25, dividend_yield: 0.12, suspicious: false },
    lenses,
    forecast: {
      status: "OK",
      seal_level: 2,
      seal_label: "Use com cautela",
      as_of: "2026-11-01",
      price_now: 38.5,
      bands: [{ months: 12, p5: 30, p50: 41, p95: 55, up_probability: 0.6 }],
    },
    tracking: null,
    data_gaps: [],
    ...overrides,
  };
}

describe("chapter helpers", () => {
  it("maps the old tabs and the chapter name of the address", () => {
    expect(chapterFromQuery(new URLSearchParams("tab=fundamentals"))).toBe("resultados");
    expect(chapterFromQuery(new URLSearchParams("tab=market"))).toBe("preco");
    expect(chapterFromQuery(new URLSearchParams("capitulo=valuation"))).toBe("valuation");
    expect(chapterFromQuery(new URLSearchParams("capitulo=nada"))).toBeNull();
    expect(chapterFromQuery(new URLSearchParams(""))).toBeNull();
  });

  it("names the strongest and the weakest lens with data", () => {
    const { strong, weak } = lensHighlights(lenses);
    expect(strong).toBe("Ponto forte: Qualidade (90% da escala) — ROE alto e estável.");
    expect(weak).toBe("Ponto fraco: Valuation (20% da escala) — caro contra o setor.");
    expect(lensHighlights(null)).toEqual({});
  });
});

describe("registered asset in chapters", () => {
  it("tells the story in chapters with the index, the lenses and the quote age", async () => {
    mockApi([
      trackedInstrument(1, {
        lenses,
        quote: { price: 50, currency: "BRL", source: "STORED_QUOTE", as_of: "2026-11-01T15:00:00Z" },
      }),
      { path: "/assets/1/analysis", reply: analysis() },
    ]);
    renderAt("/ativo/WEGE3");

    const index = await screen.findByRole("navigation", { name: "Capítulos" });
    expect(within(index).getAllByRole("link").map((a) => a.textContent)).toEqual([
      "Em resumo",
      "Na minha carteira",
      "Preço",
      "Vale a pena?",
      "Está barato?",
      "Resultados",
      "Proventos",
      "O que pode acontecer",
      "Notícias e eventos",
      "Imposto e lançamentos",
    ]);
    const summary = screen.getByRole("region", { name: "Em resumo" });
    expect(within(summary).getByText(/Ponto forte: Qualidade/)).toBeInTheDocument();
    expect(within(summary).getByRole("list", { name: /Lentes da recomendação/ })).toBeInTheDocument();
    expect(screen.getByText(/cotação guardada ·/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Editar ativo" })).toHaveAttribute("href", "/ativo/WEGE3/editar");
  });

  it("loads a chapter only when it is opened", async () => {
    const { calls } = mockApi([
      trackedInstrument(),
      { path: "/assets/1/analysis", reply: analysis() },
      { path: "/assets/1/forecast", reply: { asset_id: 1, ticker: "WEGE3", status: "NOT_COMPUTED", seal: { level: 0, label: "Sem medida", text: "" } } },
    ]);
    renderAt("/ativo/WEGE3");
    const forecast = await screen.findByRole("region", { name: "O que pode acontecer" });
    expect(calls.some((c) => c.path === "/assets/1/forecast")).toBe(false);

    fireEvent.click(within(forecast).getByRole("button", { name: "Ver detalhes: O que pode acontecer" }));
    await within(forecast).findByRole("button", { name: "Ocultar detalhes: O que pode acontecer" });
    expect(calls.some((c) => c.path === "/assets/1/forecast")).toBe(true);
  });

  it("says when valuation does not apply, in the chapter lead", async () => {
    const base = analysis();
    mockApi([
      trackedInstrument(),
      { path: "/assets/1/analysis", reply: analysis({ valuation: { ...base.valuation, applicable: false, verdict: "NOT_APPLICABLE" } }) },
    ]);
    renderAt("/ativo/WEGE3");
    const chapter = await screen.findByRole("region", { name: "Está barato?" });
    expect(chapter).toHaveTextContent("O valuation não se aplica a este tipo de ativo");
  });
});

describe("old asset addresses", () => {
  it("send /asset/:id to /ativo/:ticker with the old tab kept", async () => {
    mockApi([
      { path: "/assets/1", reply: asset({ id: 1, ticker: "WEGE3" }) },
      trackedInstrument(),
      { path: "/assets/1/analysis", reply: analysis() },
    ]);
    renderAt("/asset/1?tab=valuation");
    expect(await screen.findByRole("region", { name: "Está barato?" })).toBeInTheDocument();
    expect(screen.getByRole("status", { hidden: true, name: "Endereço" })).toHaveTextContent("/ativo/WEGE3?tab=valuation");
    expect(screen.getByRole("button", { name: "Ocultar detalhes: Está barato?" })).toBeInTheDocument();
  });

  it("send /asset/:id/edit to the edit form by ticker", async () => {
    mockApi([
      { path: "/assets/1", reply: asset({ id: 1, ticker: "WEGE3" }) },
      trackedInstrument(),
    ]);
    renderAt("/asset/1/edit");
    await waitFor(() =>
      expect(screen.getByRole("status", { hidden: true, name: "Endereço" })).toHaveTextContent("/ativo/WEGE3/editar"),
    );
  });
});

describe("any ticker in chapters", () => {
  it("shows how it would enter, its results, its forecast and its price by ticker", async () => {
    const { calls } = mockApi([
      { path: "/instruments/PETR4", reply: untracked() },
      { path: "/instruments/PETR4/prices", reply: { range: "1y", points: [{ date: "2026-10-01", close: 37 }, { date: "2026-11-01", close: 38.5 }], change: 0.04 } },
    ]);
    renderAt("/ativo/PETR4");

    expect(await screen.findByRole("region", { name: "Como entraria" })).toHaveTextContent("Entraria em Ações.");
    expect(screen.getByRole("region", { name: "Resultados" })).toHaveTextContent("P/L 4,2 · P/VP 1,1 · ROE 25,0% · DY 12,0%");
    expect(screen.getByRole("region", { name: "O que pode acontecer" })).toHaveTextContent("de R$ 30,00 a R$ 55,00");
    expect(await screen.findByRole("img", { name: /Preço de PETR4/ })).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/instruments/PETR4/prices")?.query.get("range")).toBe("1y");
  });

  it("tells a Tesouro bond enters by registering it", async () => {
    mockApi([
      {
        path: "/instruments/tesouro-ipca-15052035",
        reply: untracked({
          key: "tesouro-ipca-15052035",
          kind: "TREASURY",
          ticker: "tesouro-ipca-15052035",
          name: "Tesouro IPCA+ 2035",
          asset_type: "TREASURY",
          lenses: null,
          indicators: null,
          forecast: null,
          quote: { price: 2100.5, currency: "BRL", source: "TREASURY_PRICE" },
          treasury: { bond_type: "Tesouro IPCA+", maturity_date: "2035-05-15", indexer: "IPCA", liquidity: "DAILY", buy_rate: 7.1, buy_price: 2100.5 },
        }),
      },
    ]);
    renderAt("/ativo/tesouro-ipca-15052035");
    expect(await screen.findByRole("link", { name: "Cadastrar título" })).toHaveAttribute("href", "/carteira/novo-ativo");
    expect(screen.queryByRole("button", { name: "Acompanhar" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Preço" })).toHaveTextContent("Taxa de compra7,1% a.a.");
  });
});
