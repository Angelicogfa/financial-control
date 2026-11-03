import { fireEvent, render, screen, within } from "@testing-library/react";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Breadcrumbs } from "../layout/Breadcrumbs";
import { crumbsFor, nextTrail, type TrailEntry } from "../layout/trail";
import { FRESH_ENTRY, readStored, useFreshEntry, useStoredState, writeStored } from "../utils/storedState";
import { savedPlan, report } from "./fixtures";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

const e = (path: string, search = ""): TrailEntry => ({ path, search });

describe("breadcrumb trail", () => {
  it("puts section pages under Início", () => {
    expect(crumbsFor([e("/carteira")])).toEqual([
      { label: "Início", to: "/inicio" },
      { label: "Carteira", to: null },
    ]);
    expect(crumbsFor([e("/carteira/rentabilidade")]).map((c) => c.label)).toEqual([
      "Início",
      "Carteira",
      "Rentabilidade",
    ]);
  });

  it("hangs a detail page from the page it was opened from, filters included", () => {
    const trail = [e("/inicio"), e("/explorar", "?tab=treasury"), e("/ativo/WEGE3")];
    expect(crumbsFor(trail)).toEqual([
      { label: "Início", to: "/inicio" },
      { label: "Explorar", to: "/explorar?tab=treasury" },
      { label: "Ativo", to: null },
    ]);
  });

  it("keeps the whole way from a contribution plan to the asset", () => {
    const trail = [e("/aportar"), e("/aportar/7"), e("/ativo/HGLG11")];
    expect(crumbsFor(trail).map((c) => [c.label, c.to])).toEqual([
      ["Início", "/inicio"],
      ["Aportar", "/aportar"],
      ["Plano de aporte", "/aportar/7"],
      ["Ativo", null],
    ]);
  });

  it("goes back up when a page already in the trail is opened again", () => {
    let trail = [e("/inicio"), e("/carteira"), e("/ativo/ITSA4")];
    trail = nextTrail(trail, e("/ativo/ITSA4/editar"), "PUSH");
    expect(crumbsFor(trail).map((c) => c.label)).toEqual(["Início", "Explorar", "Ativo", "Editar ativo"]);
    trail = nextTrail(trail, e("/ativo/ITSA4"), "PUSH");
    expect(trail.map((t) => t.path)).toEqual(["/inicio", "/carteira", "/ativo/ITSA4"]);
    // A filter changed with `replace` updates the address of the same page.
    trail = nextTrail(trail, e("/ativo/ITSA4", "?tab=market"), "REPLACE");
    expect(trail[trail.length - 1].search).toBe("?tab=market");
  });
});

function Harness() {
  return (
    <MemoryRouter initialEntries={["/explorar?sector=Bancos"]}>
      <Breadcrumbs />
      <Routes>
        <Route path="/explorar" element={<Link to="/ativo/WEGE3">Abrir WEGE3</Link>} />
        <Route path="/ativo/:ticker" element={<p>Página do ativo</p>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("Breadcrumbs", () => {
  it("shows the trail and goes back to the page with its filters", () => {
    render(<Harness />);
    const nav = screen.getByRole("navigation", { name: "Trilha de navegação" });
    expect(within(nav).getByText("Explorar")).toHaveAttribute("aria-current", "page");

    fireEvent.click(screen.getByRole("link", { name: "Abrir WEGE3" }));
    expect(screen.getByText("Página do ativo")).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Explorar" })).toHaveAttribute("href", "/explorar?sector=Bancos");
    expect(within(nav).getByText("Ativo")).toHaveAttribute("aria-current", "page");

    fireEvent.click(within(nav).getByRole("button", { name: /Voltar/ }));
    expect(screen.getByRole("link", { name: "Abrir WEGE3" })).toBeInTheDocument();
  });

  it("is in the topbar of every page", async () => {
    mockApi([]);
    renderAt("/configuracoes/contas", { shell: true });
    const nav = screen.getByRole("navigation", { name: "Trilha de navegação" });
    expect(within(nav).getByRole("link", { name: "Início" })).toHaveAttribute("href", "/inicio");
    expect(within(nav).getByText("Contas")).toHaveClass("app-topbar-title");
  });

  it("lights the destination in the menu and the section in its tabs", async () => {
    mockApi([]);
    renderAt("/explorar/garimpo", { shell: true });
    const menu = screen.getByRole("complementary", { name: "Menu principal" });
    expect(within(menu).getByRole("link", { name: "Explorar" })).toHaveClass("active");
    expect(within(menu).getByRole("link", { name: "Carteira" })).not.toHaveClass("active");
    const sections = screen.getByRole("navigation", { name: "Seções de Explorar" });
    expect(within(sections).getByRole("link", { name: "Garimpo" })).toHaveAttribute("aria-current", "page");
    expect(within(sections).getByRole("link", { name: "Screener e Tesouro" })).not.toHaveAttribute("aria-current");
  });
});

function Counter() {
  const [value, setValue] = useStoredState("test:counter", 0);
  return (
    <button type="button" onClick={() => setValue((v) => v + 1)}>
      Valor {value}
    </button>
  );
}

describe("page state kept for the session", () => {
  it("comes back after leaving the page", () => {
    const first = render(<Counter />);
    fireEvent.click(screen.getByRole("button", { name: "Valor 0" }));
    first.unmount();
    render(<Counter />);
    expect(screen.getByRole("button", { name: "Valor 1" })).toBeInTheDocument();
  });

  it("keeps the unsaved edits of a contribution plan and links each asset", async () => {
    mockApi([
      { path: "/contributions/7", reply: savedPlan() },
      { path: "/portfolio/consolidated", reply: report() },
      { path: "/accounts", reply: [] },
    ]);
    const first = renderAt("/aportar/7");
    fireEvent.change(await screen.findByLabelText("Quantidade de HGLG11"), { target: { value: "5" } });
    expect(screen.getByRole("link", { name: "HGLG11" })).toHaveAttribute("href", "/ativo/HGLG11");
    first.unmount();
    renderAt("/aportar/7");
    expect(await screen.findByLabelText("Quantidade de HGLG11")).toHaveValue("5");
  });
});

function FreshCounter() {
  const entry = useFreshEntry("test:");
  return <Counter key={entry} />;
}

describe("a page opened from the menu starts clean", () => {
  it("drops the kept state on a menu entry and keeps it when coming back", () => {
    writeStored("test:counter", 3);
    const back = render(
      <MemoryRouter initialEntries={["/page"]}>
        <FreshCounter />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Valor 3" })).toBeInTheDocument();
    back.unmount();

    render(
      <MemoryRouter initialEntries={[{ pathname: "/page", state: FRESH_ENTRY }]}>
        <FreshCounter />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Valor 0" })).toBeInTheDocument();
    expect(readStored("test:counter", null)).toBeNull();
  });

  it("opens Explorar from the menu without the last search", async () => {
    writeStored("research:screener-search", { filters: { q: "banco" }, page: 0, pageSize: 25 });
    const { calls } = mockApi([]);
    renderAt("/explorar/garimpo", { shell: true });
    const menu = screen.getByRole("complementary", { name: "Menu principal" });
    fireEvent.click(within(menu).getByRole("link", { name: "Explorar" }));
    expect(await screen.findByRole("heading", { name: "Explorar" })).toBeInTheDocument();
    expect(readStored("research:screener-search", null)).toBeNull();
    expect(calls.some((c) => c.path === "/research/screener")).toBe(false);
  });
});

