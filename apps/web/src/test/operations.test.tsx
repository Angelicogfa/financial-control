import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { analysis, asset, report, savedPlan } from "./fixtures";
import { mockApi, type Call } from "./mockApi";
import { renderAt } from "./render";

const accounts = [{ id: 1, name: "XP", is_active: true }];
const page = <T,>(items: T[]) => ({
  items,
  meta: { page: 1, page_size: 50, total_items: items.length, total_pages: 1, sort_by: "id", sort_order: "desc" },
});
const last = (calls: Call[], method: string, path: string) =>
  [...calls].reverse().find((c) => c.method === method && c.path === path);

describe("asset detail", () => {
  it("shows summary, fundamentals and valuation by tab", async () => {
    mockApi([{ path: "/assets/1/analysis", reply: analysis() }]);
    renderAt("/asset/1");
    expect(await screen.findByText("Posição")).toBeInTheDocument();
    expect(screen.getByText("Descontado", { selector: ".app-badge" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Preço de WEGE3/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Fundamentos" }));
    expect(screen.getByText("ROE médio")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Lucro líquido anual/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Valuation" }));
    expect(screen.getByText("Preço justo de Graham")).toBeInTheDocument();
    expect(screen.getByText("Não passa")).toBeInTheDocument();
  });

  it("explains when valuation does not apply", async () => {
    mockApi([
      {
        path: "/assets/1/analysis",
        reply: analysis({
          valuation: { profile: "ETF", applicable: false, methods: [], verdict: "NOT_APPLICABLE", reason: "ETFs replicam índices." },
        }),
      },
    ]);
    renderAt("/asset/1?tab=valuation");
    expect(await screen.findByText("ETFs replicam índices.")).toBeInTheDocument();
  });

  it("saves checklist answers with evidence and the chosen profile", async () => {
    const { calls } = mockApi([
      { path: "/assets/1/analysis", reply: analysis() },
      { method: "PUT", path: "/assets/1/checklist", reply: asset() },
    ]);
    renderAt("/asset/1?tab=checklist");
    expect(await screen.findByText(/automática: ROE médio 18,0%/)).toBeInTheDocument();
    const governance = screen.getByRole("group", { name: "Tem boa governança?" });
    fireEvent.click(within(governance).getByRole("button", { name: "Sim" }));
    fireEvent.change(screen.getByLabelText("Evidência: Tem boa governança?"), { target: { value: "Novo Mercado" } });
    fireEvent.change(screen.getByLabelText("Perfil do checklist"), { target: { value: "BANK" } });
    expect(screen.getByText(/Salve para ver as perguntas do perfil Banco/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Salvar checklist" }));
    await screen.findByText("Checklist salvo.");
    expect(last(calls, "PUT", "/assets/1/checklist")?.body).toEqual({
      use_cerrado: true,
      checklist_profile: "BANK",
      cerrado_answers: { governance: "YES" },
      evidence: { governance: "Novo Mercado" },
    });
    expect(screen.getByText("Histórico da nota")).toBeInTheDocument();
  });

  it("lists the asset's trades and earnings", async () => {
    mockApi([
      { path: "/assets/1/analysis", reply: analysis() },
      {
        path: "/transactions",
        reply: page([{ id: 5, asset_id: 1, ticker: "WEGE3", kind: "BUY", trade_date: "2026-01-05", quantity: 10, unit_price: 40, fees: 0, fx_rate: 1, total_brl: 400 }]),
      },
      { path: "/corporate-events", reply: [] },
      {
        path: "/earnings",
        reply: page([{ id: 9, asset_id: 1, kind: "DIVIDEND", payment_date: "2025-03-01", gross_amount: 12, withholding_tax: 0, net_amount: 12, net_amount_brl: 12 }]),
      },
    ]);
    renderAt("/asset/1?tab=ledger");
    expect(await screen.findByRole("link", { name: "Editar" })).toHaveAttribute("href", "/ledger/trades/5/edit");
    fireEvent.click(screen.getByRole("tab", { name: "Proventos" }));
    expect(await screen.findByRole("img", { name: "Proventos líquidos recebidos por ano" })).toBeInTheDocument();
  });
});

describe("asset form", () => {
  it("creates a fixed income asset converting the typed rate", async () => {
    const { calls } = mockApi([{ method: "POST", path: "/assets", reply: asset({ id: 4 }) }]);
    renderAt("/asset/new");
    fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "FIXED_INCOME" } });
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "CDB Banco X" } });
    fireEvent.change(screen.getByLabelText("Taxa (%)"), { target: { value: "112,5" } });
    fireEvent.click(screen.getByRole("button", { name: "Cadastrar ativo" }));
    await waitFor(() => expect(last(calls, "POST", "/assets")).toBeDefined());
    const body = last(calls, "POST", "/assets")?.body as Record<string, unknown>;
    expect(body.asset_type).toBe("FIXED_INCOME");
    expect(body.ticker).toBeNull();
    expect(body.fixed_income_term).toMatchObject({ indexer: "CDI", contracted_rate: 1.125 });
  });
});

describe("research", () => {
  it("screens the catalog and follows a candidate", async () => {
    const result = {
      results: [
        { ticker: "ITUB4", name: "Itaú", asset_type: "STOCK_BR", arca_class: "ACOES", close: 32, volume_brl: 8e8, dividend_yield: 0.07, valuation_verdict: "FAIR" },
      ],
      candidates: 3,
      scanned: 3,
      truncated: false,
      arca_classes: [],
      catalog_size: 7,
      catalog_updated_at: "2026-03-10T19:00:00Z",
    };
    const { calls } = mockApi([
      { path: "/research/screener", reply: result },
      {
        method: "POST",
        path: "/research/watchlist",
        reply: { status: 201, json: { asset_id: 9, ticker: "ITUB4" } },
      },
    ]);
    renderAt("/research");
    fireEvent.change(screen.getByLabelText("DY mínimo (%)"), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Fundo imobiliário" }));
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    expect(await screen.findByText("ITUB4")).toBeInTheDocument();
    const query = last(calls, "GET", "/research/screener")?.query;
    expect(query?.get("min_dy")).toBe("0.05");
    expect(query?.getAll("asset_type")).toEqual(["FII"]);
    expect(screen.getByText(/1 resultado\(s\) de 3 candidato\(s\)/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Observar" }));
    expect(await screen.findByText("ITUB4 está em observação.")).toBeInTheDocument();
    expect(last(calls, "POST", "/research/watchlist")?.body).toMatchObject({ ticker: "ITUB4", asset_type: "STOCK_BR" });
  });

  it("lists and removes watched assets", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const item = {
      asset_id: 9,
      ticker: "BBAS3",
      name: "Banco do Brasil",
      asset_type: "STOCK_BR",
      arca_class: "ACOES",
      lifecycle_status: "ELIGIBLE",
      eligible: true,
      price: 27,
      checklist_profile: "BANK",
      checklist_score: 3,
      checklist_coverage_pct: 40,
      checklist_recommendation: "APTO",
      valuation_verdict: "DISCOUNTED",
      margin: 0.2,
    };
    const { calls } = mockApi([
      { path: "/research/watchlist", reply: [item] },
      { method: "DELETE", path: "/research/watchlist/9", reply: { status: 204 } },
    ]);
    renderAt("/research?tab=watchlist");
    expect(await screen.findByRole("link", { name: "BBAS3" })).toHaveAttribute("href", "/asset/9");
    expect(screen.getByText("Elegível")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remover" }));
    await waitFor(() => expect(last(calls, "DELETE", "/research/watchlist/9")).toBeDefined());
  });
});

describe("contribute", () => {
  it("creates a draft from the amount", async () => {
    const { calls } = mockApi([
      { path: "/contributions", reply: [savedPlan({ id: 3, status: "CONFIRMED" })] },
      { method: "POST", path: "/contributions", reply: { status: 201, json: savedPlan() } },
      { path: "/contributions/7", reply: savedPlan() },
      { path: "/portfolio/consolidated", reply: report() },
      { path: "/accounts", reply: accounts },
    ]);
    renderAt("/contribute");
    expect(await screen.findByRole("link", { name: "#3" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Quanto vai aportar (R$)"), { target: { value: "1.000,00" } });
    fireEvent.click(screen.getByRole("button", { name: "Sugerir distribuição" }));
    await waitFor(() => expect(last(calls, "POST", "/contributions")?.body).toEqual({ amount_brl: 1000, strategy_override: null }));
  });

  it("shows before/after by class and confirms the edited executions", async () => {
    let confirmed = false;
    const { calls } = mockApi([
      { path: "/contributions/7", reply: () => savedPlan(confirmed ? { status: "CONFIRMED", transaction_ids: [11], confirmed_at: "2026-03-10T13:00:00Z" } : {}) },
      { path: "/portfolio/consolidated", reply: report() },
      { path: "/accounts", reply: accounts },
      {
        method: "POST",
        path: "/contributions/7/confirm",
        reply: () => {
          confirmed = true;
          return savedPlan({ status: "CONFIRMED" });
        },
      },
    ]);
    renderAt("/contribute/7");
    expect(await screen.findByRole("list", { name: "Peso de cada classe antes e depois do aporte" })).toBeInTheDocument();
    expect(screen.getByText(/ficam sem destino/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Quantidade de HGLG11"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Preço de HGLG11"), { target: { value: "158,5" } });
    await screen.findByRole("option", { name: "XP" });
    fireEvent.change(screen.getByLabelText("Conta"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar 1 compra(s)" }));
    expect(await screen.findByText(/Plano confirmado/)).toBeInTheDocument();
    expect(last(calls, "POST", "/contributions/7/confirm")?.body).toMatchObject({
      account_id: 1,
      executions: [{ asset_id: 3, quantity: 5, unit_price: 158.5, fees: 0 }],
    });
  });

  it("refuses to confirm without any asset", async () => {
    mockApi([
      { path: "/contributions/7", reply: savedPlan() },
      { path: "/portfolio/consolidated", reply: report() },
      { path: "/accounts", reply: accounts },
    ]);
    renderAt("/contribute/7");
    fireEvent.click(await screen.findByLabelText("Comprar HGLG11"));
    fireEvent.click(screen.getByRole("button", { name: "Confirmar 0 compra(s)" }));
    expect(await screen.findByText("Escolha ao menos um ativo com quantidade maior que zero.")).toBeInTheDocument();
  });
});

describe("ledger", () => {
  const trade = { id: 5, asset_id: 1, ticker: "WEGE3", kind: "BUY", trade_date: "2026-01-05", quantity: 10, unit_price: 40, fees: 0, fx_rate: 1, total_brl: 400 };

  it("lists trades, filters and shows the API refusal on delete", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { calls } = mockApi([
      { path: "/transactions", reply: page([trade]) },
      { path: "/assets", reply: page([asset()]) },
      { path: "/accounts", reply: accounts },
      {
        method: "DELETE",
        path: "/transactions/5",
        reply: { status: 409, json: { detail: "This change would leave WEGE3 with an invalid ledger", code: "LEDGER_CONFLICT" } },
      },
    ]);
    renderAt("/ledger");
    expect(await screen.findByRole("link", { name: "WEGE3" })).toBeInTheDocument();
    await screen.findByRole("option", { name: "WEGE3" });
    fireEvent.change(screen.getByLabelText("Ativo"), { target: { value: "1" } });
    await waitFor(() => expect(last(calls, "GET", "/transactions")?.query.get("asset_id")).toBe("1"));
    fireEvent.click(await screen.findByRole("button", { name: "Excluir" }));
    expect(await screen.findByText(/invalid ledger/)).toBeInTheDocument();
  });

  it("creates a trade", async () => {
    const { calls } = mockApi([
      { path: "/assets", reply: page([asset()]) },
      { path: "/accounts", reply: accounts },
      { method: "POST", path: "/transactions", reply: { status: 201, json: trade } },
      { path: "/transactions", reply: page([trade]) },
    ]);
    renderAt("/ledger/trades/new?asset=1");
    await screen.findByRole("option", { name: /WEGE3/ });
    fireEvent.change(screen.getByLabelText("Quantidade"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText(/Preço unitário/), { target: { value: "40,5" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(last(calls, "POST", "/transactions")?.body).toMatchObject({ asset_id: 1, quantity: 10, unit_price: 40.5, kind: "BUY" }));
  });

  it("previews and commits a B3 statement", async () => {
    const preview = {
      kind: "NEGOTIATION",
      counts: { NEW: 1, UNKNOWN_ASSET: 1 },
      unknown_tickers: [{ ticker: "ITSA4", asset_type: "STOCK_BR" }],
      lines: [
        { line_no: 2, action: "TRADE", status: "NEW", entry_date: "2024-01-02", ticker: "WEGE3", description: "compra", quantity: 10, unit_price: 36.5, amount: 365, trade_kind: "BUY", note: "" },
        { line_no: 3, action: "TRADE", status: "UNKNOWN_ASSET", entry_date: "2024-01-02", ticker: "ITSA4", description: "compra", quantity: 100, unit_price: 9.8, amount: 980, trade_kind: "BUY", note: "Ativo não cadastrado" },
      ],
    };
    const { calls } = mockApi([
      { path: "/accounts", reply: accounts },
      { method: "POST", path: "/imports/b3/preview", reply: preview },
      {
        method: "POST",
        path: "/imports/b3/commit",
        reply: { kind: "NEGOTIATION", created: { TRADE: 2, EARNING: 0, EVENT: 0 }, skipped: {}, created_assets: ["ITSA4"] },
      },
    ]);
    renderAt("/ledger/import");
    const file = new File(["x"], "negociacao.xlsx");
    fireEvent.change(screen.getByLabelText("Arquivo (.xlsx ou .csv)"), { target: { files: [file] } });
    expect(await screen.findByText("Ativos que ainda não estão cadastrados")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /ITSA4/ })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Importar 2 linha(s)" }));
    expect(await screen.findByText(/Importado: 2 operação/)).toBeInTheDocument();
    expect(last(calls, "POST", "/imports/b3/commit")?.body).toMatchObject({ create_tickers: "ITSA4" });
  });
});
