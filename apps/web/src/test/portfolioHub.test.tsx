/** Phase 48.R5: Carteira › Proventos and Carteira › Conferir. */

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { IncomeSummaryDTO, ReconciliationDTO, ReconciliationLineDTO } from "../api/types";
import { fixLink } from "../features/portfolio/ReconciliationPage";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

const agenda = { as_of: "2026-11-02", items: [], total_net_brl: 0, warnings: [] };

const income: IncomeSummaryDTO = {
  as_of: "2026-11-02",
  last_12m_brl: 1200,
  previous_12m_brl: 1000,
  total_brl: 2500,
  yield_on_cost: 0.08,
  months: [
    { month: "2026-10", net_brl: 150 },
    { month: "2026-11", net_brl: 0 },
  ],
  by_year: { 2025: 1300, 2026: 1200 },
  assets: [{ asset_id: 3, ticker: "HGLG11", last_12m_brl: 900, yield_on_cost: 0.1 }],
};

function line(overrides: Partial<ReconciliationLineDTO>): ReconciliationLineDTO {
  return {
    product: "Acoes",
    ticker: "ITSA4",
    asset_id: 2,
    account_id: 1,
    institution: "XP INVESTIMENTOS",
    b3_quantity: 40,
    ledger_quantity: 50,
    difference: -10,
    status: "DIVERGENT",
    note: "",
    resolution: "OPEN",
    ...overrides,
  };
}

function result(overrides: Partial<ReconciliationDTO> = {}): ReconciliationDTO {
  return {
    id: null,
    reference_date: "2026-10-31",
    file_name: "posicao-2026-10-31.xlsx",
    counts: { match: 1, divergent: 1, only_b3: 1, only_ledger: 0, not_compared: 1, open_issues: 2 },
    lines: [
      line({ ticker: "PETR4", asset_id: 1, b3_quantity: 100, ledger_quantity: 100, difference: 0, status: "MATCH" }),
      line({}),
      line({ ticker: "VALE3", asset_id: null, account_id: null, b3_quantity: 20, ledger_quantity: 0, difference: 20, status: "ONLY_B3", note: "Ativo não cadastrado: cadastre-o e lance a compra." }),
      line({ ticker: null, asset_id: null, product: "Tesouro Direto", b3_quantity: 1.5, ledger_quantity: 0, difference: 1.5, status: "NOT_COMPARED", note: "Tesouro Selic 2029: sem código de negociação, conferido só pelo valor." }),
    ],
    ...overrides,
  };
}

describe("Carteira › Proventos", () => {
  it("shows the last 12 months against the previous ones, the yield on cost and who paid", async () => {
    mockApi([
      { path: "/portfolio/income", reply: income },
      { path: "/portfolio/earnings-agenda", reply: agenda },
    ]);
    renderAt("/carteira/proventos");

    const kpis = await screen.findByLabelText("Proventos recebidos");
    expect(kpis).toHaveTextContent("R$ 1.200,00");
    expect(kpis).toHaveTextContent("+20,0% sobre os 12 anteriores");
    expect(kpis).toHaveTextContent("8,0%");
    expect(screen.getByRole("link", { name: "HGLG11" })).toHaveAttribute("href", "/ativo/HGLG11");
    expect(screen.getByRole("heading", { name: "Anunciados" })).toBeInTheDocument();
  });

  it("explains an empty history", async () => {
    mockApi([
      { path: "/portfolio/income", reply: { ...income, total_brl: 0, last_12m_brl: 0, assets: [], months: [] } },
      { path: "/portfolio/earnings-agenda", reply: agenda },
    ]);
    renderAt("/carteira/proventos");
    expect(await screen.findByText("Nenhum provento recebido ainda")).toBeInTheDocument();
  });
});

describe("Carteira › Conferir", () => {
  it("prefills the trade that fixes each difference", () => {
    expect(fixLink(line({}), "2026-10-31")).toBe(
      "/lancamentos/negociacoes/nova?asset=2&kind=SELL&quantity=10&date=2026-10-31&account=1",
    );
    expect(fixLink(line({ difference: 5, b3_quantity: 55 }), "2026-10-31")).toContain("kind=BUY&quantity=5");
    expect(fixLink(line({ asset_id: null, ticker: "VALE3", status: "ONLY_B3" }), "2026-10-31")).toBe("/ativo/VALE3");
    expect(fixLink(line({ status: "MATCH" }), "2026-10-31")).toBeNull();
  });

  it("says the position was never checked, previews a statement and saves it", async () => {
    let saved = false;
    const { calls } = mockApi([
      { path: "/reconciliation", reply: () => (saved ? [{ id: 7, reference_date: "2026-10-31", file_name: "posicao-2026-10-31.xlsx", counts: result().counts }] : []) },
      { method: "POST", path: "/reconciliation/b3/preview", reply: result() },
      {
        method: "POST",
        path: "/reconciliation/b3/commit",
        reply: () => {
          saved = true;
          return result({ id: 7, lines: result().lines.map((l, i) => ({ ...l, id: i + 1 })) });
        },
      },
      { path: "/reconciliation/7", reply: result({ id: 7, lines: result().lines.map((l, i) => ({ ...l, id: i + 1 })) }) },
    ]);
    renderAt("/carteira/conferir");

    expect(await screen.findByText(/ainda não foi conferida/)).toBeInTheDocument();
    const file = new File(["x"], "posicao-2026-10-31.xlsx");
    fireEvent.change(screen.getByLabelText("Extrato de Posição (.xlsx ou .csv)"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Conferir" }));

    const table = await screen.findByRole("table", { name: "Linhas da conferência" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("ITSA4");
    expect(rows[0]).toHaveTextContent("Quantidade diferente");
    expect(within(rows[0]).getByRole("link", { name: "Lançar diferença" })).toHaveAttribute(
      "href",
      "/lancamentos/negociacoes/nova?asset=2&kind=SELL&quantity=10&date=2026-10-31&account=1",
    );
    expect(within(table).getByRole("link", { name: "Abrir ativo" })).toHaveAttribute("href", "/ativo/VALE3");
    expect(within(table).getByText(/sem código de negociação/)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/reconciliation/b3/preview")?.method).toBe("POST");

    fireEvent.click(screen.getByRole("button", { name: "Gravar conferência" }));
    expect(await screen.findByRole("heading", { name: "Conferência de 31/10/2026" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/2 diferença\(s\) em aberto/)).toBeInTheDocument());
  });

  it("marks a difference of a saved check as explained", async () => {
    const saved = result({ id: 7, lines: result().lines.map((l, i) => ({ ...l, id: i + 1 })) });
    const { calls } = mockApi([
      { path: "/reconciliation", reply: [{ id: 7, reference_date: "2026-10-31", file_name: "posicao-2026-10-31.xlsx", counts: saved.counts }] },
      { path: "/reconciliation/7", reply: saved },
      { method: "PUT", path: "/reconciliation/7/lines/2", reply: { ...saved.lines[1], resolution: "RESOLVED" } },
    ]);
    renderAt("/carteira/conferir");
    fireEvent.click(await screen.findByRole("button", { name: "Ver linhas" }));
    const table = await screen.findByRole("table", { name: "Linhas da conferência" });
    fireEvent.click(within(table).getAllByRole("button", { name: "Marcar como explicado" })[0]);
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ resolution: "RESOLVED" });
  });
});

describe("prefilled trade from the check", () => {
  it("opens the trade form with kind, quantity and date from the address", async () => {
    mockApi([
      { path: "/assets", reply: { items: [], meta: { page: 1, page_size: 200, total_items: 0, total_pages: 0 } } },
      { path: "/accounts", reply: [] },
    ]);
    renderAt("/lancamentos/negociacoes/nova?asset=2&kind=SELL&quantity=10&date=2026-10-31");
    expect(await screen.findByDisplayValue("2026-10-31")).toBeInTheDocument();
    expect(screen.getByDisplayValue("10")).toBeInTheDocument();
  });
});
