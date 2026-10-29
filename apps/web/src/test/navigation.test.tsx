import { fireEvent, render, screen, within } from "@testing-library/react";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Breadcrumbs } from "../layout/Breadcrumbs";
import { crumbsFor, nextTrail, type TrailEntry } from "../layout/trail";
import { useStoredState } from "../utils/storedState";
import { savedPlan, report } from "./fixtures";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

const e = (path: string, search = ""): TrailEntry => ({ path, search });

describe("breadcrumb trail", () => {
  it("puts section pages under Início", () => {
    expect(crumbsFor([e("/portfolio")])).toEqual([
      { label: "Início", to: "/home" },
      { label: "Carteira", to: null },
    ]);
  });

  it("hangs a detail page from the page it was opened from, filters included", () => {
    const trail = [e("/home"), e("/research", "?tab=screener"), e("/asset/5")];
    expect(crumbsFor(trail)).toEqual([
      { label: "Início", to: "/home" },
      { label: "Pesquisar", to: "/research?tab=screener" },
      { label: "Ativo", to: null },
    ]);
  });

  it("keeps the whole way from a contribution plan to the asset", () => {
    const trail = [e("/contribute"), e("/contribute/7"), e("/asset/3")];
    expect(crumbsFor(trail).map((c) => [c.label, c.to])).toEqual([
      ["Início", "/home"],
      ["Aportar", "/contribute"],
      ["Plano de aporte", "/contribute/7"],
      ["Ativo", null],
    ]);
  });

  it("goes back up when a page already in the trail is opened again", () => {
    let trail = [e("/home"), e("/portfolio"), e("/asset/3")];
    trail = nextTrail(trail, e("/asset/3/edit"), "PUSH");
    expect(crumbsFor(trail).map((c) => c.label)).toEqual(["Início", "Carteira", "Ativo", "Editar ativo"]);
    trail = nextTrail(trail, e("/asset/3"), "PUSH");
    expect(trail.map((t) => t.path)).toEqual(["/home", "/portfolio", "/asset/3"]);
    // A filter changed with `replace` updates the address of the same page.
    trail = nextTrail(trail, e("/asset/3", "?tab=market"), "REPLACE");
    expect(trail[trail.length - 1].search).toBe("?tab=market");
  });
});

function Harness() {
  return (
    <MemoryRouter initialEntries={["/research?sector=Bancos"]}>
      <Breadcrumbs />
      <Routes>
        <Route path="/research" element={<Link to="/asset/5">Abrir WEGE3</Link>} />
        <Route path="/asset/:id" element={<p>Página do ativo</p>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("Breadcrumbs", () => {
  it("shows the trail and goes back to the page with its filters", () => {
    render(<Harness />);
    const nav = screen.getByRole("navigation", { name: "Trilha de navegação" });
    expect(within(nav).getByText("Pesquisar")).toHaveAttribute("aria-current", "page");

    fireEvent.click(screen.getByRole("link", { name: "Abrir WEGE3" }));
    expect(screen.getByText("Página do ativo")).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Pesquisar" })).toHaveAttribute("href", "/research?sector=Bancos");
    expect(within(nav).getByText("Ativo")).toHaveAttribute("aria-current", "page");

    fireEvent.click(within(nav).getByRole("button", { name: /Voltar/ }));
    expect(screen.getByRole("link", { name: "Abrir WEGE3" })).toBeInTheDocument();
  });

  it("is in the topbar of every page", async () => {
    mockApi([]);
    renderAt("/settings/accounts", { shell: true });
    const nav = screen.getByRole("navigation", { name: "Trilha de navegação" });
    expect(within(nav).getByRole("link", { name: "Início" })).toHaveAttribute("href", "/home");
    expect(within(nav).getByText("Contas")).toHaveClass("app-topbar-title");
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
    const first = renderAt("/contribute/7");
    fireEvent.change(await screen.findByLabelText("Quantidade de HGLG11"), { target: { value: "5" } });
    expect(screen.getByRole("link", { name: "HGLG11" })).toHaveAttribute("href", "/asset/3");
    first.unmount();
    renderAt("/contribute/7");
    expect(await screen.findByLabelText("Quantidade de HGLG11")).toHaveValue("5");
  });
});
