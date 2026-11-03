/** Phase 48.R9: saved views of the screens and the monthly report. */

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MonthlyReportDTO, SavedViewDTO } from "../api/types";
import { lastClosedMonth, monthTitle, reportLead } from "../features/portfolio/MonthlyReportPage";
import { mockApi, type Call } from "./mockApi";
import { renderAt } from "./render";

afterEach(() => vi.unstubAllGlobals());

const last = (calls: Call[], method: string, path: string) =>
  [...calls].reverse().find((c) => c.method === method && c.path === path);

const meta = { page: 1, page_size: 10, total: 0, pages: 0 };

function view(overrides: Partial<SavedViewDTO> = {}): SavedViewDTO {
  return {
    id: 4,
    scope: "LEDGER",
    name: "Conta XP em 2026",
    filters: { account_id: 2, date_from: "2026-01-01" },
    created_at: "2026-11-02T10:00:00Z",
    updated_at: "2026-11-02T10:00:00Z",
    ...overrides,
  };
}

describe("saved views", () => {
  it("applies a saved view to the ledger filters, saves the current ones and deletes a view", async () => {
    const { calls } = mockApi([
      { path: "/saved-views", reply: [view()] },
      { method: "PUT", path: "/saved-views", reply: (c: Call) => view({ id: 5, name: (c.body as { name: string }).name }) },
      { method: "DELETE", path: "/saved-views/5", reply: { status: 204 } },
      { path: "/transactions", reply: { items: [], meta } },
      { path: "/assets", reply: { items: [], meta } },
      { path: "/accounts", reply: [{ id: 2, name: "XP" }] },
    ]);
    renderAt("/lancamentos");

    const group = await screen.findByRole("group", { name: "Visões salvas" });
    const select = within(group).getByLabelText("Visão salva");
    await within(group).findByRole("option", { name: "Conta XP em 2026" });
    expect(last(calls, "GET", "/saved-views")?.query.get("scope")).toBe("LEDGER");

    fireEvent.change(select, { target: { value: "4" } });
    await waitFor(() => expect(last(calls, "GET", "/transactions")?.query.get("account_id")).toBe("2"));
    expect(last(calls, "GET", "/transactions")?.query.get("date_from")).toBe("2026-01-01");
    expect(within(group).getByLabelText("Nome da visão")).toHaveValue("Conta XP em 2026");

    fireEvent.change(within(group).getByLabelText("Nome da visão"), { target: { value: "Só a XP" } });
    fireEvent.click(within(group).getByRole("button", { name: "Salvar visão" }));
    await waitFor(() => expect(last(calls, "PUT", "/saved-views")).toBeDefined());
    expect(last(calls, "PUT", "/saved-views")?.body).toEqual({
      scope: "LEDGER",
      name: "Só a XP",
      filters: { account_id: 2, date_from: "2026-01-01" },
    });
    expect(await within(group).findByRole("status")).toHaveTextContent("Visão “Só a XP” salva.");

    fireEvent.click(within(group).getByRole("button", { name: "Apagar visão" }));
    await waitFor(() => expect(last(calls, "DELETE", "/saved-views/5")).toBeDefined());
    expect(await within(group).findByRole("status")).toHaveTextContent("Visão apagada.");
  });

  it("needs a name before saving", async () => {
    mockApi([
      { path: "/saved-views", reply: [] },
      { path: "/transactions", reply: { items: [], meta } },
      { path: "/assets", reply: { items: [], meta } },
      { path: "/accounts", reply: [] },
    ]);
    renderAt("/lancamentos");
    const group = await screen.findByRole("group", { name: "Visões salvas" });
    expect(within(group).getByRole("button", { name: "Salvar visão" })).toBeDisabled();
    expect(await within(group).findByRole("option", { name: "Nenhuma visão salva" })).toBeInTheDocument();
  });
});

function report(overrides: Partial<MonthlyReportDTO> = {}): MonthlyReportDTO {
  return {
    month: "2026-10-01",
    start_date: "2026-09-30",
    end_date: "2026-10-30",
    start_value_brl: 100000,
    end_value_brl: 104000,
    bought_brl: 3000,
    sold_brl: 0,
    net_flow_brl: 3000,
    income_brl: 450,
    result_brl: 1450,
    month_return: 0.0142,
    trades: [{ trade_date: "2026-10-10", ticker: "HGLG11", kind: "BUY", quantity: 20, value_brl: 3000 }],
    earnings: [{ payment_date: "2026-10-14", ticker: "HGLG11", kind: "DIVIDEND", net_brl: 450 }],
    allocation: [{ arca_class: "REAL_ESTATE", value_brl: 30000, current_pct: 0.2885, target_pct: 0.25 }],
    tax: { tax_brl: 120, darf_brl: 120, due_date: "2026-11-30", paid_on: null, exempt: false, stock_sales_brl: 0 },
    goals: [{ name: "Independência", status: "OFF_TRACK", progress: 0.104, required_monthly_brl: 4200 }],
    data_gaps: [],
    ...overrides,
  };
}

describe("monthly report", () => {
  it("names the months and tells the month in one sentence", () => {
    expect(monthTitle("2026-10")).toBe("outubro de 2026");
    expect(lastClosedMonth("2026-11-02")).toBe("2026-10");
    expect(lastClosedMonth("2027-01-15")).toBe("2026-12");
    const lead = (r: MonthlyReportDTO) => reportLead(r).replace(/\u00a0/g, " ");
    expect(lead(report())).toBe(
      "A carteira foi de R$ 100.000,00 para R$ 104.000,00, com R$ 3.000,00 de aportes líquidos; descontados os aportes, ganhou R$ 1.450,00 (+1,42% no mês).",
    );
    expect(lead(report({ net_flow_brl: -500, result_brl: -200, month_return: null }))).toBe(
      "A carteira foi de R$ 100.000,00 para R$ 104.000,00, com R$ 500,00 de resgates líquidos; descontados os aportes, perdeu R$ 200,00.",
    );
    expect(lead(report({ end_date: null }))).toBe("Não há retrato da carteira neste mês para medir o resultado.");
  });

  it("shows the month, switches it and prints it as PDF", async () => {
    const { calls } = mockApi([{ path: "/portfolio/monthly-report", reply: report() }]);
    const print = vi.fn();
    vi.stubGlobal("print", print);
    renderAt("/carteira/relatorio?mes=2026-10");

    expect(screen.getByRole("heading", { name: "Relatório de outubro de 2026" })).toBeInTheDocument();
    expect(await screen.findByRole("note", { name: "Em resumo" })).toHaveClass("is-positive");
    expect(screen.getByRole("table", { name: "Negociações do mês" })).toHaveTextContent("Compra");
    expect(screen.getByRole("table", { name: "Proventos do mês" })).toHaveTextContent("R$ 450,00");
    expect(screen.getByRole("table", { name: "Alocação no fim do mês" })).toHaveTextContent("Real Estate");
    expect(screen.getByText(/ainda não marcado como pago/)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Metas no fim do mês" })).toHaveTextContent("fora do caminho");
    expect(last(calls, "GET", "/portfolio/monthly-report")?.query.get("month")).toBe("2026-10");

    fireEvent.click(screen.getByRole("button", { name: "Salvar em PDF" }));
    expect(print).toHaveBeenCalledOnce();

    fireEvent.change(screen.getByLabelText("Mês"), { target: { value: "2026-09" } });
    await waitFor(() => expect(last(calls, "GET", "/portfolio/monthly-report")?.query.get("month")).toBe("2026-09"));
  });

  it("says what is missing in an empty month", async () => {
    mockApi([
      {
        path: "/portfolio/monthly-report",
        reply: report({ trades: [], earnings: [], tax: null, goals: [], allocation: [], data_gaps: ["Não há retrato da carteira dentro do mês."] }),
      },
    ]);
    renderAt("/carteira/relatorio?mes=2026-10");
    expect(await screen.findByText("Nenhuma compra ou venda no mês.")).toBeInTheDocument();
    expect(screen.getByText("Sem vendas tributáveis no mês.")).toBeInTheDocument();
    expect(screen.getByText("Não há retrato da carteira dentro do mês.")).toBeInTheDocument();
  });
});
