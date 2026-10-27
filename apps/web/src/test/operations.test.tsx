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
    expect(screen.getByLabelText("Data de emissão (opcional)")).toHaveValue("");
    expect(screen.getByLabelText("Data de emissão (opcional)")).not.toBeRequired();
    expect(screen.queryByLabelText("Paga juros semestrais")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cadastrar ativo" }));
    await waitFor(() => expect(last(calls, "POST", "/assets")).toBeDefined());
    const body = last(calls, "POST", "/assets")?.body as Record<string, unknown>;
    expect(body.asset_type).toBe("FIXED_INCOME");
    expect(body.ticker).toBeNull();
    expect(body.fixed_income_term).toMatchObject({
      indexer: "CDI",
      contracted_rate: 1.125,
      issue_date: null,
      semiannual_coupons: false,
    });
  });

  it("flags a semiannual Tesouro Prefixado and explains the purchase rate", async () => {
    const treasuryReply = {
      results: [
        {
          symbol: "tesouro-prefixado-com-juros-semestrais-01012035",
          name: "Tesouro Prefixado com Juros Semestrais 2035",
          bond_type: "Tesouro Prefixado com Juros Semestrais",
          instrument_kind: "TESOURO_PRE",
          indexer: "PRE",
          raw_indexer: "prefixado",
          coupon_type: "semestral",
          maturity_date: "2035-01-01",
          contracted_rate_percent: 13.5,
          liquidity: "AT_MATURITY",
          asset_id: null,
        },
      ],
      total: 1,
      unavailable_reason: null,
    };
    const { calls } = mockApi([
      { path: "/research/treasury", reply: treasuryReply },
      { method: "POST", path: "/assets", reply: asset({ id: 13, asset_type: "TREASURY" }) },
    ]);
    renderAt("/asset/new");
    fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "TREASURY" } });
    fireEvent.change(screen.getByLabelText("Título ou vencimento"), { target: { value: "2035" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar títulos" }));
    fireEvent.click(await screen.findByRole("button", { name: "Usar título" }));

    expect(screen.getByLabelText("Paga juros semestrais")).toBeChecked();
    expect(screen.getByText(/taxa implícita no preço/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Instrumento"), { target: { value: "TESOURO_SELIC" } });
    expect(screen.queryByText(/taxa implícita no preço/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Instrumento"), { target: { value: "TESOURO_PRE" } });

    fireEvent.click(screen.getByRole("button", { name: "Cadastrar ativo" }));
    await waitFor(() => expect(last(calls, "POST", "/assets")).toBeDefined());
    const body = last(calls, "POST", "/assets")?.body as Record<string, unknown>;
    expect(body.fixed_income_term).toMatchObject({
      instrument_kind: "TESOURO_PRE",
      issue_date: null,
      semiannual_coupons: true,
    });
  });

  it("searches Tesouro Direto via Brapi and fills the contract fields", async () => {
    const treasuryReply = {
      results: [
        {
          symbol: "tesouro-ipca-15052035",
          name: "Tesouro IPCA+ 2035",
          bond_type: "Tesouro IPCA+",
          instrument_kind: "TESOURO_IPCA",
          indexer: "IPCA",
          raw_indexer: "ipca",
          coupon_type: "zero",
          maturity_date: "2035-05-15",
          buy_rate: 6.42,
          sell_rate: 6.54,
          buy_price: 2345.67,
          sell_price: 2310.12,
          base_price: 2310.12,
          rate_type: "realAnnualRateOverIpca",
          rate_unit: "% a.a.",
          contracted_rate_percent: 6.42,
          liquidity: "AT_MATURITY",
          asset_id: null,
        },
      ],
      total: 1,
      unavailable_reason: null,
    };
    const { calls } = mockApi([
      { path: "/research/treasury", reply: treasuryReply },
      { method: "POST", path: "/assets", reply: asset({ id: 12, asset_type: "TREASURY" }) },
    ]);
    renderAt("/asset/new");
    fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "TREASURY" } });
    fireEvent.change(screen.getByLabelText("Título ou vencimento"), { target: { value: "2035" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar títulos" }));
    expect(await screen.findByText("Tesouro IPCA+ 2035")).toBeInTheDocument();
    expect(last(calls, "GET", "/research/treasury")?.query.get("q")).toBe("2035");

    fireEvent.click(screen.getByRole("button", { name: "Usar título" }));
    expect(screen.getByLabelText("Nome")).toHaveValue("Tesouro IPCA+ 2035");
    expect(screen.getByLabelText("Taxa (%)")).toHaveValue("6,42");
    expect(screen.getByLabelText("Vencimento")).toHaveValue("2035-05-15");
    expect(screen.getByLabelText("Emissor")).toHaveValue("Tesouro Nacional");

    fireEvent.click(screen.getByRole("button", { name: "Cadastrar ativo" }));
    await waitFor(() => expect(last(calls, "POST", "/assets")).toBeDefined());
    const body = last(calls, "POST", "/assets")?.body as Record<string, unknown>;
    expect(body.asset_type).toBe("TREASURY");
    expect(body.name).toBe("Tesouro IPCA+ 2035");
    expect(body.fixed_income_term).toMatchObject({
      instrument_kind: "TESOURO_IPCA",
      indexer: "IPCA",
      contracted_rate: 0.0642,
      maturity_date: "2035-05-15",
      issuer: "Tesouro Nacional",
    });
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
        reply: { status: 201, json: { asset_id: 9, ticker: "ITUB4", arca_class: "ATIVOS_INTERNACIONAIS" } },
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

    // "Observar" asks for the ARCA quadrant first, with the suggestion preselected.
    fireEvent.click(screen.getByRole("button", { name: "Observar" }));
    const quadrant = screen.getByRole("combobox", { name: "Classe ARCA de ITUB4" });
    expect(quadrant).toHaveValue("ACOES");
    expect(within(quadrant).getByRole("option", { name: "Ações (sugerida)" })).toBeInTheDocument();
    fireEvent.change(quadrant, { target: { value: "ATIVOS_INTERNACIONAIS" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    expect(await screen.findByText("ITUB4 está em observação em Ativos internacionais.")).toBeInTheDocument();
    expect(last(calls, "POST", "/research/watchlist")?.body).toMatchObject({
      ticker: "ITUB4",
      asset_type: "STOCK_BR",
      arca_class: "ATIVOS_INTERNACIONAIS",
    });
  });

  it("cancels the quadrant choice without following", async () => {
    const result = {
      results: [{ ticker: "BBAS3", name: "BB", asset_type: "STOCK_BR", arca_class: "ACOES" }],
      candidates: 1,
      scanned: 1,
      truncated: false,
      arca_classes: [],
      catalog_size: 7,
    };
    const { calls } = mockApi([{ path: "/research/screener", reply: result }]);
    renderAt("/research");
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    fireEvent.click(await screen.findByRole("button", { name: "Observar" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.getByRole("button", { name: "Observar" })).toBeInTheDocument();
    expect(last(calls, "POST", "/research/watchlist")).toBeUndefined();
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
      { method: "PUT", path: "/research/watchlist/9/classification", reply: { ...item, arca_class: "CAIXA" } },
      { method: "POST", path: "/research/watchlist", reply: { status: 201, json: { ...item, asset_id: 10, ticker: "TAEE11" } } },
      { method: "DELETE", path: "/research/watchlist/9", reply: { status: 204 } },
    ]);
    renderAt("/research?tab=watchlist");
    expect(await screen.findByRole("link", { name: "BBAS3" })).toHaveAttribute("href", "/asset/9");
    expect(screen.getByText("Elegível")).toBeInTheDocument();

    // Reclassify in place.
    const quadrant = screen.getByRole("combobox", { name: "Classe ARCA de BBAS3" });
    expect(quadrant).toHaveValue("ACOES");
    fireEvent.change(quadrant, { target: { value: "CAIXA" } });
    await waitFor(() =>
      expect(last(calls, "PUT", "/research/watchlist/9/classification")?.body).toEqual({ arca_class: "CAIXA" }),
    );

    // Follow by code with a chosen quadrant (empty = the suggestion).
    fireEvent.change(screen.getByLabelText("Observar código"), { target: { value: "taee11" } });
    expect(screen.getByLabelText("Classe ARCA")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("Classe ARCA"), { target: { value: "REAL_ESTATE" } });
    fireEvent.click(screen.getByRole("button", { name: "Adicionar" }));
    await waitFor(() =>
      expect(last(calls, "POST", "/research/watchlist")?.body).toMatchObject({ ticker: "TAEE11", arca_class: "REAL_ESTATE" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Remover" }));
    await waitFor(() => expect(last(calls, "DELETE", "/research/watchlist/9")).toBeDefined());
  });

  it("searches Tesouro Direto in the research tab and registers a bond", async () => {
    const treasuryReply = {
      results: [
        {
          symbol: "tesouro-selic-01032031",
          name: "Tesouro Selic 2031",
          bond_type: "Tesouro Selic",
          instrument_kind: "TESOURO_SELIC",
          indexer: "SELIC",
          raw_indexer: "selic",
          coupon_type: "zero",
          maturity_date: "2031-03-01",
          buy_rate: 0.1,
          sell_rate: 0.11,
          buy_price: 20074.43,
          sell_price: 20055.44,
          base_price: 20055.44,
          rate_type: "spreadOverSelic",
          rate_unit: "% a.a.",
          contracted_rate_percent: 100,
          liquidity: "DAILY",
          asset_id: null,
        },
      ],
      total: 1,
      unavailable_reason: null,
    };
    const { calls } = mockApi([
      { path: "/research/treasury", reply: treasuryReply },
      {
        method: "POST",
        path: "/assets",
        reply: { status: 201, json: asset({ id: 25, ticker: "TESOURO_SELIC-TESOURONAC-20310301", name: "Tesouro Selic 2031", asset_type: "TREASURY" }) },
      },
    ]);
    renderAt("/research?tab=treasury");
    fireEvent.change(screen.getByLabelText("Indexador"), { target: { value: "SELIC" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    expect(await screen.findByText("Tesouro Selic 2031")).toBeInTheDocument();
    expect(screen.getByText("SELIC + 0,10% a.a.")).toBeInTheDocument();
    expect(last(calls, "GET", "/research/treasury")?.query.get("indexer")).toBe("SELIC");

    fireEvent.click(screen.getByRole("button", { name: "Cadastrar" }));
    expect(await screen.findByText(/Tesouro Selic 2031 .* cadastrado com sucesso/)).toBeInTheDocument();
    expect(last(calls, "POST", "/assets")?.body).toMatchObject({
      name: "Tesouro Selic 2031",
      asset_type: "TREASURY",
      arca_class: "CAIXA",
      fixed_income_term: {
        instrument_kind: "TESOURO_SELIC",
        indexer: "SELIC",
        contracted_rate: 1,
        maturity_date: "2031-03-01",
        liquidity: "DAILY",
        semiannual_coupons: false,
      },
    });
    const followed = last(calls, "POST", "/assets")?.body as { fixed_income_term: Record<string, unknown> };
    expect(followed.fixed_income_term).not.toHaveProperty("issue_date");
  });

  it("displays unavailable_reason when Brapi requires Pro plan for Tesouro Direto", async () => {
    mockApi([
      {
        path: "/research/treasury",
        reply: {
          results: [],
          total: 0,
          unavailable_reason: "Tesouro Direto e renda fixa requer o plano Pro.",
        },
      },
    ]);
    renderAt("/research?tab=treasury");
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    expect(await screen.findByText("Tesouro Direto e renda fixa requer o plano Pro.")).toBeInTheDocument();
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

  const usfr = asset({ id: 7, ticker: "USFR", name: "WisdomTree Floating Rate Treasury", asset_type: "ETF_INTL", currency: "USD" });

  it("shows the FX field and the BRL total for a preset USD asset", async () => {
    mockApi([
      { path: "/assets", reply: page([asset(), usfr]) },
      { path: "/accounts", reply: accounts },
    ]);
    renderAt("/ledger/trades/new?asset=7");
    const fx = await screen.findByLabelText("Câmbio USD/BRL do dia");
    expect(screen.getByLabelText(/Preço unitário \(USD\)/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Quantidade"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText(/Preço unitário/), { target: { value: "50,25" } });
    fireEvent.change(screen.getByLabelText("Taxas"), { target: { value: "1" } });
    fireEvent.change(fx, { target: { value: "5,2" } });
    expect(screen.getByText(/Total em reais/)).toHaveTextContent("R$ 2.618,20");
  });

  it("keeps the FX field and the saved rate when editing a USD trade", async () => {
    const usdTrade = { ...trade, id: 6, asset_id: 7, ticker: "USFR", quantity: 2, unit_price: 50, fees: 0, fx_rate: 5.5, total_brl: 550 };
    const { calls } = mockApi([
      { path: "/transactions/6", reply: usdTrade },
      { path: "/assets", reply: page([asset(), usfr]) },
      { path: "/accounts", reply: accounts },
      { method: "PUT", path: "/transactions/6", reply: usdTrade },
      { path: "/transactions", reply: page([usdTrade]) },
    ]);
    renderAt("/ledger/trades/6/edit");
    expect(await screen.findByLabelText("Câmbio USD/BRL do dia")).toHaveValue("5,5");
    expect(screen.getByText(/Total em reais/)).toHaveTextContent("R$ 550,00");
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(last(calls, "PUT", "/transactions/6")?.body).toMatchObject({ fx_rate: 5.5, quantity: 2, unit_price: 50 }));
  });

  it("hides the FX field for a BRL asset", async () => {
    mockApi([
      { path: "/assets", reply: page([asset(), usfr]) },
      { path: "/accounts", reply: accounts },
    ]);
    renderAt("/ledger/trades/new?asset=1");
    await screen.findByRole("option", { name: /WEGE3/ });
    expect(screen.queryByLabelText(/Câmbio/)).not.toBeInTheDocument();
  });

  it("keeps the FX field and the saved rate when editing a USD earning", async () => {
    const earning = { id: 9, asset_id: 7, kind: "DIVIDEND", payment_date: "2026-02-01", gross_amount: 10, withholding_tax: 3, net_amount: 7, fx_rate: 5, net_amount_brl: 35 };
    const { calls } = mockApi([
      { path: "/earnings/9", reply: earning },
      { path: "/assets", reply: page([asset(), usfr]) },
      { path: "/accounts", reply: accounts },
      { method: "PUT", path: "/earnings/9", reply: earning },
      { path: "/earnings", reply: page([earning]) },
    ]);
    renderAt("/ledger/earnings/9/edit");
    expect(await screen.findByLabelText("Câmbio do pagamento")).toHaveValue("5");
    expect(screen.getByText(/Líquido em reais/)).toHaveTextContent("R$ 35,00");
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(last(calls, "PUT", "/earnings/9")?.body).toMatchObject({ fx_rate: 5, gross_amount: 10 }));
  });

  it("previews and commits a B3 statement", async () => {
    const preview = {
      kind: "NEGOTIATION",
      counts: { NEW: 1, UNKNOWN_ASSET: 1 },
      unknown_tickers: [
        { ticker: "ITSA4", asset_type: "STOCK_BR", arca_class: "ACOES" },
        { ticker: "XPTO1", asset_type: null, arca_class: null },
      ],
      lines: [
        { line_no: 2, action: "TRADE", status: "NEW", entry_date: "2024-01-02", ticker: "WEGE3", description: "compra", quantity: 10, unit_price: 36.5, amount: 365, trade_kind: "BUY", note: "" },
        { line_no: 3, action: "TRADE", status: "UNKNOWN_ASSET", entry_date: "2024-01-02", ticker: "ITSA4", description: "compra", quantity: 100, unit_price: 9.8, amount: 980, trade_kind: "BUY", note: "Ativo não cadastrado" },
      ],
    };
    const { calls } = mockApi([
      { path: "/accounts", reply: accounts },
      { method: "POST", path: "/imports/b3/preview", reply: preview },
      {
        path: "/assets/classification",
        reply: (call: Call) => ({
          ticker: call.query.get("ticker"),
          asset_type: call.query.get("asset_type"),
          arca_class: call.query.get("asset_type") === "BDR" ? "ATIVOS_INTERNACIONAIS" : "ACOES",
          source: "TYPE",
          reason: "",
        }),
      },
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
    expect(screen.getByRole("combobox", { name: "Classe ARCA de ITSA4" })).toHaveValue("ACOES");

    // A ticker of unknown type stays off until its type is chosen; the quadrant follows the type.
    const xpto = screen.getByRole("checkbox", { name: /XPTO1/ });
    expect(xpto).toBeDisabled();
    fireEvent.change(screen.getByRole("combobox", { name: "Tipo de XPTO1" }), { target: { value: "BDR" } });
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Classe ARCA de XPTO1" })).toHaveValue("ATIVOS_INTERNACIONAIS"),
    );
    expect(xpto).toBeChecked();
    fireEvent.click(xpto);

    fireEvent.change(screen.getByRole("combobox", { name: "Classe ARCA de ITSA4" }), { target: { value: "CAIXA" } });
    fireEvent.click(screen.getByRole("button", { name: "Importar 2 linha(s)" }));
    expect(await screen.findByText(/Importado: 2 operação/)).toBeInTheDocument();
    const body = last(calls, "POST", "/imports/b3/commit")?.body as Record<string, string>;
    expect(JSON.parse(body.new_assets)).toEqual([{ ticker: "ITSA4", asset_type: "STOCK_BR", arca_class: "CAIXA" }]);
  });

  it("leaves unchecked lines out of the preview and the commit", async () => {
    const buy = { line_no: 2, action: "TRADE", entry_date: "2021-05-10", ticker: "AESB3", description: "compra", quantity: 2, unit_price: 14, amount: 28, trade_kind: "BUY" };
    const sell = { line_no: 3, action: "TRADE", entry_date: "2021-05-14", ticker: "AESB3", description: "venda", quantity: 2, unit_price: 15, amount: 30, trade_kind: "SELL" };
    const preview = (call: Call) => {
      const skipped = (call.body as Record<string, string>).skip_lines === "2";
      return {
        kind: "NEGOTIATION",
        counts: skipped ? { IGNORED: 1, INVALID: 1 } : { NEW: 2 },
        unknown_tickers: [],
        lines: skipped
          ? [
              { ...buy, status: "IGNORED", note: "Ignorada por você" },
              { ...sell, status: "INVALID", note: "Venda maior que o saldo" },
            ]
          : [
              { ...buy, status: "NEW", note: "" },
              { ...sell, status: "NEW", note: "" },
            ],
      };
    };
    const { calls } = mockApi([
      { path: "/accounts", reply: accounts },
      { method: "POST", path: "/imports/b3/preview", reply: preview },
      {
        method: "POST",
        path: "/imports/b3/commit",
        reply: { kind: "NEGOTIATION", created: { TRADE: 0, EARNING: 0, EVENT: 0 }, skipped: { IGNORED: 1, INVALID: 1 }, created_assets: [] },
      },
    ]);
    renderAt("/ledger/import");
    fireEvent.change(screen.getByLabelText("Arquivo (.xlsx ou .csv)"), { target: { files: [new File(["x"], "negociacao.xlsx")] } });
    expect(await screen.findByRole("button", { name: "Importar 2 linha(s)" })).toBeEnabled();

    fireEvent.click(screen.getByRole("checkbox", { name: "Importar linha 2" }));
    expect(await screen.findByText("Venda maior que o saldo")).toBeInTheDocument();
    expect(last(calls, "POST", "/imports/b3/preview")?.body).toMatchObject({ skip_lines: "2" });
    // The skipped line can be checked again; the invalid sell has nothing to toggle.
    expect(screen.getByRole("checkbox", { name: "Importar linha 2" })).not.toBeChecked();
    expect(screen.queryByRole("checkbox", { name: "Importar linha 3" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Importar 0 linha(s)" })).toBeDisabled();
  });

  it("registers a bank security from the movement statement once its rate is typed", async () => {
    const term = {
      instrument_kind: "CDB",
      indexer: "CDI",
      contracted_rate: null,
      issue_date: null,
      maturity_date: null,
      tax_exempt: false,
      liquidity: "AT_MATURITY",
      issuer: "ITAU UNIBANCO S.A.",
    };
    const preview = {
      kind: "MOVEMENT",
      counts: { UNKNOWN_ASSET: 1 },
      unknown_tickers: [
        { ticker: "CDB-ITAUUNIBANCO", name: "CDB ITAU UNIBANCO S.A.", asset_type: "FIXED_INCOME", arca_class: "CAIXA", fixed_income_term: term },
      ],
      lines: [
        { line_no: 2, action: "TRADE", status: "UNKNOWN_ASSET", entry_date: "2026-03-17", ticker: "CDB-ITAUUNIBANCO", description: "aplicacao", quantity: 857575, unit_price: 0.01, amount: 8575.75, trade_kind: "BUY", note: "Ativo não cadastrado" },
      ],
    };
    const { calls } = mockApi([
      { path: "/accounts", reply: accounts },
      { method: "POST", path: "/imports/b3/preview", reply: preview },
      {
        method: "POST",
        path: "/imports/b3/commit",
        reply: { kind: "MOVEMENT", created: { TRADE: 1, EARNING: 0, EVENT: 0 }, skipped: {}, created_assets: ["CDB-ITAUUNIBAN-LIQ"] },
      },
    ]);
    renderAt("/ledger/import");
    fireEvent.change(screen.getByLabelText("Arquivo (.xlsx ou .csv)"), { target: { files: [new File(["x"], "movimentacao.xlsx")] } });

    const security = await screen.findByRole("checkbox", { name: /CDB-ITAUUNIBANCO/ });
    expect(security).not.toBeChecked();
    expect(security).toBeDisabled(); // the rate is never in a B3 statement
    expect(screen.getByRole("combobox", { name: "Tipo de CDB-ITAUUNIBANCO" })).toBeDisabled();
    expect(screen.getByLabelText("Data de emissão (opcional)")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Importar 0 linha(s)" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "CDB Itaú liquidez diária" } });
    fireEvent.change(screen.getByLabelText("Taxa contratada"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Liquidez"), { target: { value: "DAILY" } });
    expect(security).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "Importar 1 linha(s)" }));
    expect(await screen.findByText(/ativos cadastrados: CDB-ITAUUNIBAN-LIQ/)).toBeInTheDocument();
    const body = last(calls, "POST", "/imports/b3/commit")?.body as Record<string, string>;
    expect(JSON.parse(body.new_assets)).toEqual([
      {
        ticker: "CDB-ITAUUNIBANCO",
        asset_type: "FIXED_INCOME",
        arca_class: "CAIXA",
        name: "CDB Itaú liquidez diária",
        fixed_income_term: {
          instrument_kind: "CDB",
          indexer: "CDI",
          contracted_rate: 1,
          issue_date: null,
          maturity_date: null,
          tax_exempt: false,
          liquidity: "DAILY",
          issuer: "ITAU UNIBANCO S.A.",
          semiannual_coupons: false,
        },
      },
    ]);
  });
});
