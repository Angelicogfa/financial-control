/** Phase 48.R3: new information architecture (old addresses removed in R9), global search
 *  and the instrument page for any ticker. */

import { fireEvent, render, screen, within } from "@testing-library/react";
import { matchPath, MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AppProviders, createQueryClient } from "../app/AppProviders";
import { AppRoutes } from "../app/AppRoutes";
import type { InstrumentViewDTO, SearchResultDTO } from "../api/types";
import { matchActions, QUICK_ACTIONS } from "../features/search/GlobalSearch";
import { AppShell } from "../layout/AppShell";
import { activeSection, DESTINATIONS, destinationOf } from "../layout/navigation";
import { analysis } from "./fixtures";
import { appRoutePaths, internalLinks } from "./links";
import { mockApi } from "./mockApi";

function Where() {
  const location = useLocation();
  return <output aria-label="Endereço">{`${location.pathname}${location.search}`}</output>;
}

function renderWithLocation(path: string, { shell = false } = {}) {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false, staleTime: 0 } });
  const routes = shell ? (
    <AppShell username="ana" onLogout={() => undefined}>
      <AppRoutes />
    </AppShell>
  ) : (
    <AppRoutes />
  );
  return render(
    <AppProviders client={client}>
      <MemoryRouter initialEntries={[path]}>
        {routes}
        <Where />
      </MemoryRouter>
    </AppProviders>,
  );
}

const address = () => screen.getByRole("status", { hidden: true, name: "Endereço" });

function view(overrides: Partial<InstrumentViewDTO> = {}): InstrumentViewDTO {
  return {
    key: "PETR4",
    kind: "LISTED",
    ticker: "PETR4",
    name: "Petrobras PN",
    asset_type: "STOCK_BR",
    sector: "Petróleo",
    logo_url: null,
    in_catalog: true,
    quote: { price: 38.5, currency: "BRL", source: "CATALOG_CLOSE", change_pct: 0.012, as_of: null, freshness: null },
    indicators: null,
    lenses: null,
    forecast: { status: "NOT_COMPUTED", seal_level: 0, seal_label: "Sem medida", bands: [] },
    tracking: null,
    treasury: null,
    data_gaps: ["Preço do fechamento do catálogo da B3; a cotação do dia ainda não foi buscada."],
    ...overrides,
  };
}

describe("old addresses (removed in Phase 48.R9)", () => {
  it("the root opens Início and an old address is not found", async () => {
    mockApi([]);
    renderWithLocation("/");
    expect(address()).toHaveTextContent("/inicio");
  });

  it.each(["/portfolio", "/tools/fixed-income", "/asset/3", "/settings/strategy"])("%s is gone", async (from) => {
    mockApi([]);
    renderWithLocation(from);
    expect(address()).toHaveTextContent(from);
    expect(await screen.findByText(/não encontrada/i)).toBeInTheDocument();
  });

  it("every internal link points to a route of the app", () => {
    const routes = appRoutePaths();
    expect(routes.length).toBeGreaterThan(30);
    expect(internalLinks().length).toBeGreaterThan(60);
    expect(routes.some((path) => matchPath(path, "/portfolio"))).toBe(false);
    const broken = internalLinks().filter((link) => !routes.some((path) => matchPath(path, link.path)));
    expect(broken).toEqual([]);
  });
});

describe("destinations and sections", () => {
  it("has seven destinations, each with its question", () => {
    expect(DESTINATIONS.map((d) => d.label)).toEqual([
      "Início",
      "Carteira",
      "Explorar",
      "Acompanhar",
      "Aportar",
      "Planejar",
      "Lançamentos",
    ]);
    expect(DESTINATIONS.every((d) => d.question.endsWith("?"))).toBe(true);
  });

  it("finds the destination and the section of a path", () => {
    expect(destinationOf("/carteira/raio-x")?.label).toBe("Carteira");
    expect(destinationOf("/ativo/PETR4")?.label).toBe("Explorar");
    expect(destinationOf("/configuracoes/contas")).toBeNull();
    const plan = DESTINATIONS.find((d) => d.to === "/planejar")!;
    expect(activeSection("/planejar/estudos/5", plan)?.label).toBe("Simulações");
    expect(activeSection("/planejar/modelo", plan)?.label).toBe("Modelo");
  });
});

describe("global search", () => {
  const found: SearchResultDTO = {
    query: "petr",
    total: 2,
    hits: [
      { key: "PETR4", kind: "LISTED", ticker: "PETR4", name: "Petrobras PN", match: "TICKER_PREFIX", close: 38.5, holds_position: true, tracked_asset_id: 3 },
      { key: "PETR3", kind: "LISTED", ticker: "PETR3", name: "Petrobras ON", match: "TICKER_PREFIX", close: 41, holds_position: false },
    ],
  };

  it("offers each address once", () => {
    const addresses = QUICK_ACTIONS.map((a) => a.to);
    expect(new Set(addresses).size).toBe(addresses.length);
  });

  it("matches quick actions by word, without accents", () => {
    expect(matchActions("import").map((a) => a.to)).toContain("/lancamentos/importar");
    expect(matchActions("lancamentos").map((a) => a.to)).toContain("/lancamentos");
    expect(matchActions("")).toEqual([]);
  });

  it("opens with Ctrl+K, searches after a pause and opens the chosen ticker with Enter", async () => {
    const { calls } = mockApi([
      { path: "/search", reply: found },
      { path: "/instruments/PETR3", reply: view({ key: "PETR3", ticker: "PETR3", name: "Petrobras ON" }) },
    ]);
    renderWithLocation("/carteira", { shell: true });

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const dialog = await screen.findByRole("dialog", { name: "Busca global" });
    fireEvent.change(within(dialog).getByRole("combobox", { name: "Buscar ativo ou ação" }), {
      target: { value: "petr" },
    });

    const options = await within(dialog).findAllByRole("option");
    expect(options[0]).toHaveTextContent("PETR4");
    expect(options[0]).toHaveTextContent("Na carteira");
    expect(calls.filter((c) => c.path === "/search")).toHaveLength(1); // one call after the pause
    expect(calls.find((c) => c.path === "/search")?.query.get("q")).toBe("petr");

    fireEvent.keyDown(dialog, { key: "ArrowDown" });
    fireEvent.keyDown(dialog, { key: "Enter" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(address()).toHaveTextContent("/ativo/PETR3");
    expect(await screen.findByRole("heading", { name: "PETR3 · Petrobras ON" })).toBeInTheDocument();
  });

  it("opens with '/' outside a field and closes with Escape", async () => {
    mockApi([]);
    renderWithLocation("/carteira", { shell: true });
    fireEvent.keyDown(window, { key: "/" });
    const dialog = await screen.findByRole("dialog", { name: "Busca global" });
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("goes to a quick action", async () => {
    mockApi([{ path: "/search", reply: { query: "aport", hits: [], total: 0 } }]);
    renderWithLocation("/carteira", { shell: true });
    fireEvent.click(screen.getByRole("button", { name: /Buscar ativo ou ação/ }));
    const dialog = await screen.findByRole("dialog", { name: "Busca global" });
    fireEvent.change(within(dialog).getByRole("combobox"), { target: { value: "aport" } });
    fireEvent.click(within(dialog).getByRole("option", { name: /^Aportar/ }));
    expect(address()).toHaveTextContent("/aportar");
  });
});

describe("instrument page /ativo/:ticker", () => {
  it("shows what the database has for a ticker that is not registered, and follows it", async () => {
    let tracked = false;
    const { calls } = mockApi([
      {
        path: "/instruments/PETR4",
        reply: () => (tracked ? view({ tracking: { asset_id: 1, is_active: true, holds_position: false, purpose: "ARCA" } }) : view()),
      },
      {
        method: "POST",
        path: "/research/watchlist",
        reply: () => {
          tracked = true;
          return { status: 201, json: {} };
        },
      },
      { path: "/assets/1/analysis", reply: analysis({ position: null }) },
    ]);
    renderWithLocation("/ativo/PETR4");

    expect(await screen.findByRole("heading", { name: "PETR4 · Petrobras PN" })).toBeInTheDocument();
    expect(screen.getByText(/fechamento do catálogo da B3/, { selector: "p" })).toHaveTextContent("+1,20% no dia");
    expect(screen.getByText(/a cotação do dia ainda não foi buscada/, { selector: "li" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Acompanhar" }));

    expect(await screen.findByText("Sem posição: o ativo está em observação.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ ticker: "PETR4", name: "Petrobras PN", asset_type: "STOCK_BR" });
  });

  it("opens the current asset page for a registered ticker", async () => {
    mockApi([
      { path: "/instruments/WEGE3", reply: view({ key: "WEGE3", ticker: "WEGE3", tracking: { asset_id: 1, is_active: true, holds_position: true, purpose: "ARCA" } }) },
      { path: "/assets/1/analysis", reply: analysis() },
    ]);
    renderWithLocation("/ativo/WEGE3");
    expect(await screen.findByText("Posição")).toBeInTheDocument();
  });

  it("says when the ticker does not exist", async () => {
    mockApi([{ path: "/instruments/ZZZZ3", reply: { status: 404, json: { detail: "not found", code: "INSTRUMENT_NOT_FOUND" } } }]);
    renderWithLocation("/ativo/ZZZZ3");
    expect(await screen.findByText("Não encontramos ZZZZ3")).toBeInTheDocument();
  });
});
