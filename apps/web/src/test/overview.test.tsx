import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { alerts, analytics, position, report } from "./fixtures";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

const snapshots = [
  { snapshot_date: "2026-02-01", invested_value: 4000, market_value: 4500, consolidated_pnl: 500, earnings_cum: 0, net_flow: 0 },
  { snapshot_date: "2026-03-01", invested_value: 4000, market_value: 4900, consolidated_pnl: 900, earnings_cum: 0, net_flow: 0 },
];

function overviewApi(overrides: Record<string, unknown> = {}) {
  return mockApi([
    { path: "/portfolio/consolidated", reply: overrides.report ?? report() },
    { path: "/portfolio/snapshots", reply: snapshots },
    { path: "/portfolio/analytics", reply: overrides.analytics ?? analytics() },
    { path: "/alerts", reply: overrides.alerts ?? alerts() },
    {
      path: "/market/worker-errors",
      reply: overrides.workerErrors ?? { unresolved_count: 2, errors: [] },
    },
    { method: "POST", path: "/alerts/dismissals", reply: { status: 204 } },
    { path: "/accounts", reply: [{ id: 1, name: "XP", is_active: true }] },
  ]);
}

describe("shell", () => {
  it("shows the menu sections, the page title and the alert count", async () => {
    overviewApi();
    renderAt("/portfolio", { shell: true });
    const nav = screen.getByRole("complementary", { name: "Menu principal" });
    for (const label of ["Visão geral", "Operação", "Configuração"]) {
      expect(within(nav).getByText(label)).toBeInTheDocument();
    }
    expect(within(nav).getByRole("link", { name: /Carteira/ })).toHaveClass("active");
    expect(screen.getByText("Carteira", { selector: ".app-topbar-title" })).toBeInTheDocument();
    expect(await within(nav).findByLabelText("1 alertas")).toBeInTheDocument();
    expect(await within(nav).findByLabelText("2 erros do worker")).toBeInTheDocument();
  });

  it("answers unknown addresses with a 404 page and redirects / to the home", async () => {
    overviewApi();
    renderAt("/nada-aqui");
    expect(screen.getByText("Página não encontrada")).toBeInTheDocument();
    renderAt("/");
    expect(await screen.findByText("Como está a carteira")).toBeInTheDocument();
  });

  it("toggles the theme", () => {
    overviewApi();
    renderAt("/settings/accounts", { shell: true });
    const before = document.documentElement.getAttribute("data-theme");
    fireEvent.click(screen.getByRole("button", { name: /Usar tema/ }));
    expect(document.documentElement.getAttribute("data-theme")).not.toBe(before);
  });
});

describe("home (analytics)", () => {
  it("tells the story: headline, indicators, allocation, alerts and evolution", async () => {
    const { calls } = overviewApi();
    renderAt("/home");
    expect(await screen.findByText(/Real Estate está abaixo da banda/)).toBeInTheDocument();
    expect(screen.getByText("Patrimônio")).toBeInTheDocument();
    expect(await screen.findByText("+5,0%")).toBeInTheDocument(); // TWR from the base-100 curve
    expect(screen.getByText("CDI no período: 0,1%")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Peso atual de cada classe contra a meta" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Real Estate abaixo da banda" })).toHaveAttribute("href", "/contribute");
    expect(await screen.findByRole("img", { name: /Evolução da carteira/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Dispensar" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/alerts/dismissals")).toBe(true));
    expect(calls.find((c) => c.path === "/alerts/dismissals")?.body).toEqual({ key: "band:REAL_ESTATE:BELOW", days: 7 });
  });

  it("shows the API error instead of zeros", async () => {
    mockApi([
      { path: "/portfolio/consolidated", reply: { status: 500, json: { detail: "Banco indisponível" } } },
      { path: "/alerts", reply: alerts() },
      { path: "/portfolio/snapshots", reply: [] },
      { path: "/portfolio/analytics", reply: analytics() },
    ]);
    renderAt("/home");
    expect(await screen.findByRole("alert")).toHaveTextContent("Banco indisponível");
    expect(screen.queryByText("R$ 0,00")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeInTheDocument();
  });

  it("explains insufficient history", async () => {
    overviewApi({ analytics: analytics({ status: "INSUFFICIENT_HISTORY", available_points: 1 }) });
    renderAt("/home");
    expect(await screen.findByText(/Histórico insuficiente: o gráfico aparece/)).toBeInTheDocument();
  });
});

describe("performance", () => {
  it("shows the base-100 chart, risk and the class comparison", async () => {
    overviewApi();
    renderAt("/performance");
    expect(await screen.findByRole("img", { name: /Carteira e referências/ })).toBeInTheDocument();
    expect(screen.getByText("Índice de Sharpe")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Drawdown da carteira/ })).toBeInTheDocument();
    expect(await screen.findByText("Por classe")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "24 meses" }));
    expect(screen.getByRole("button", { name: "24 meses" })).toHaveAttribute("aria-pressed", "true");
  });

  it("says when the history is insufficient", async () => {
    overviewApi({ analytics: analytics({ status: "INSUFFICIENT_HISTORY", available_points: 1 }) });
    renderAt("/performance");
    expect(await screen.findByText(/Histórico insuficiente para medir a carteira/)).toBeInTheDocument();
    expect(screen.queryByText("Índice de Sharpe")).not.toBeInTheDocument();
  });
});

describe("portfolio", () => {
  it("groups positions by ARCA class, links assets and filters by account", async () => {
    const { calls } = overviewApi({
      report: report({
        positions: [
          position(),
          position({ asset_id: 2, ticker: "OLD3", lifecycle_status: "REVIEW", price_freshness: "FALLBACK" }),
          position({ asset_id: 3, ticker: "WATCH3", quantity: 0, invested_value_brl: 0 }),
        ],
      }),
    });
    renderAt("/portfolio");
    expect(await screen.findByRole("link", { name: "WEGE3" })).toHaveAttribute("href", "/asset/1");
    expect(screen.getByText(/Ações · R\$/)).toBeInTheDocument();
    expect(screen.getByText("Em revisão")).toBeInTheDocument();
    expect(screen.getByText("Sem cotação")).toBeInTheDocument();
    expect(screen.queryByText("WATCH3")).not.toBeInTheDocument();
    expect(screen.getByText("Nenhuma posição nesta classe.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Ações" }));
    expect(await screen.findByRole("list", { name: "Peso dos ativos em Ações" })).toBeInTheDocument();

    await screen.findByRole("option", { name: "XP" });
    fireEvent.change(screen.getByLabelText("Conta"), { target: { value: "1" } });
    await waitFor(() =>
      expect(calls.some((c) => c.path === "/portfolio/consolidated" && c.query.get("account_id") === "1")).toBe(true),
    );
  });

  it("guides an empty portfolio", async () => {
    overviewApi({ report: report({ positions: [] }) });
    renderAt("/portfolio");
    expect(await screen.findByText("Nenhuma posição ainda")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Importar extrato" })).toHaveAttribute("href", "/ledger/import");
  });
});
