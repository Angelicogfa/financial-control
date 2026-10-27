import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "../App";
import type { GrantOptionsDTO, PolicyDTO } from "../api/types";
import { daysLeft, expiryState } from "../pages/settings/agentic/expiry";
import { mcpClientConfig, mcpEndpoint } from "../pages/settings/agentic/mcpConnection";
import { scopeSize } from "../pages/settings/agentic/scope";
import { alerts, analytics, report } from "./fixtures";
import { mockApi, type Call } from "./mockApi";
import { renderAt } from "./render";

const policy: PolicyDTO = {
  version: 3,
  created_at: "2026-03-01T10:00:00Z",
  arca: [
    { arca_class: "ACOES", target_pct: 25, band_pct: 5, intra_class_strategy: "CERRADO" },
    { arca_class: "REAL_ESTATE", target_pct: 25, band_pct: 5, intra_class_strategy: "CERRADO" },
    { arca_class: "CAIXA", target_pct: 25, band_pct: 5, intra_class_strategy: "EQUAL_WEIGHT" },
    { arca_class: "ATIVOS_INTERNACIONAIS", target_pct: 25, band_pct: 5, intra_class_strategy: "CERRADO" },
  ],
  eligibility: { require_evaluation: false, min_score: 1, min_coverage_pct: 0 },
  valuation: {
    bazin_required_yield: 0.06,
    graham_multiplier: 22.5,
    reference_real_yield: 0.06,
    min_margin_of_safety: 0.15,
    projections: { cash_cdi_multiplier: 1 },
  },
};

const last = (calls: Call[], method: string, path: string) =>
  [...calls].reverse().find((c) => c.method === method && c.path === path);

describe("strategy", () => {
  it("validates that targets sum 100% and saves fractions", async () => {
    let savedVersion = false;
    const { calls } = mockApi([
      // After saving, the current policy is the new version and the form remounts.
      { path: "/policy", reply: () => (savedVersion ? { ...policy, version: 4 } : policy) },
      { path: "/policy/versions", reply: [policy] },
      {
        method: "PUT",
        path: "/policy",
        reply: () => {
          savedVersion = true;
          return { ...policy, version: 4 };
        },
      },
    ]);
    renderAt("/settings/strategy");
    const target = await screen.findByLabelText("Meta de Ações");
    fireEvent.change(target, { target: { value: "30" } });
    expect(screen.getByText(/105%.*precisa somar 100%/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Salvar nova versão" }));
    expect(await screen.findByText("As metas das classes precisam somar 100%.")).toBeInTheDocument();
    expect(last(calls, "PUT", "/policy")).toBeUndefined();

    fireEvent.change(screen.getByLabelText("Meta de Caixa"), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText("Juro real de referência (NTN-B) (%)"), { target: { value: "6,5" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar nova versão" }));
    await screen.findByText("Nova versão da estratégia salva.");
    const body = last(calls, "PUT", "/policy")?.body as {
      arca: Array<{ arca_class: string; target_pct: number }>;
      valuation: Record<string, unknown>;
    };
    expect(body.arca.find((a) => a.arca_class === "ACOES")?.target_pct).toBe(30);
    expect(body.valuation.reference_real_yield).toBeCloseTo(0.065);
    expect(body.valuation.bazin_required_yield).toBeCloseTo(0.06);
    expect(body.valuation.projections).toEqual({ cash_cdi_multiplier: 1 });
  });
});

describe("accounts", () => {
  it("creates and edits accounts", async () => {
    const { calls } = mockApi([
      { path: "/accounts", reply: [{ id: 1, name: "XP", kind: "BROKER", is_active: true }] },
      { method: "POST", path: "/accounts", reply: { status: 201, json: { id: 2, name: "Inter" } } },
      { method: "PUT", path: "/accounts/1", reply: { id: 1, name: "XP Investimentos" } },
    ]);
    renderAt("/settings/accounts");
    expect(await screen.findByText("XP")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Inter" } });
    fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "BANK" } });
    fireEvent.click(screen.getByRole("button", { name: "Adicionar conta" }));
    await waitFor(() => expect(last(calls, "POST", "/accounts")?.body).toMatchObject({ name: "Inter", kind: "BANK" }));

    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    expect(screen.getByText("Editar XP")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "XP Investimentos" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(last(calls, "PUT", "/accounts/1")?.body).toMatchObject({ name: "XP Investimentos" }));
  });
});

describe("market data", () => {
  it("shows series freshness and worker runs", async () => {
    mockApi([
      {
        path: "/market/series-status",
        reply: [
          { symbol: "CDI", unit: "PERCENT_PER_DAY", points: 500, last_date: "2026-01-02", stale: true, missing_business_days: 3 },
          { symbol: "IBOV", unit: "INDEX_POINTS", points: 250, last_date: "2026-03-09", stale: false, missing_business_days: 0 },
        ],
      },
      {
        path: "/market/job-runs",
        reply: [{ job_name: "sync_instrument_catalog", status: "FAILED", attempts: 3, started_at: "2026-03-09T19:00:00Z", error: "timeout" }],
      },
    ]);
    renderAt("/settings/market-data");
    expect(await screen.findByText("Desatualizada")).toBeInTheDocument();
    expect(screen.getByText("Em dia")).toBeInTheDocument();
    expect(await screen.findByText("Catálogo de ativos B3")).toBeInTheDocument();
    expect(screen.getByText("timeout")).toBeInTheDocument();
  });
});

describe("session", () => {
  it("shows the login while there is no session and enters the shell after it", async () => {
    let logged = false;
    mockApi([
      { path: "/auth/me", reply: () => (logged ? { username: "ana" } : { status: 401, json: { detail: "Not authenticated" } }) },
      {
        method: "POST",
        path: "/auth/login",
        reply: (call: Call) => {
          const { password } = call.body as { password: string };
          if (password !== "certa") return { status: 401, json: { detail: "Invalid credentials" } };
          logged = true;
          return { username: "ana" };
        },
      },
      { path: "/portfolio/consolidated", reply: report() },
      { path: "/portfolio/snapshots", reply: [] },
      { path: "/portfolio/analytics", reply: analytics() },
      { path: "/alerts", reply: alerts() },
    ]);
    window.history.pushState({}, "", "/home");
    render(<App />);
    fireEvent.change(await screen.findByLabelText("Usuário"), { target: { value: "ana" } });
    fireEvent.change(screen.getByLabelText("Senha"), { target: { value: "errada" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByText("Usuário ou senha inválidos.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Senha"), { target: { value: "certa" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("complementary", { name: "Menu principal" })).toBeInTheDocument();
    expect(await screen.findByText("Como está a carteira")).toBeInTheDocument();
  });

  it("explains a missing login configuration", async () => {
    mockApi([{ path: "/auth/me", reply: { status: 503, json: { detail: "not configured", code: "AUTH_NOT_CONFIGURED" } } }]);
    render(<App />);
    expect(await screen.findByText(/O login ainda não foi configurado/)).toBeInTheDocument();
  });
});

const grantOptions: GrantOptionsDTO = {
  contexts: [
    {
      name: "portfolio",
      label: "Carteira & Desempenho",
      grantable: true,
      operations: [
        {
          name: "portfolio.consolidated",
          kind: "query",
          description: "Retorna o relatório consolidado da carteira.",
          grantable: true,
        },
      ],
    },
    {
      name: "assets",
      label: "Ativos & Checklist do Cerrado",
      grantable: true,
      operations: [
        {
          name: "assets.list",
          kind: "query",
          description: "Lista os ativos cadastrados.",
          grantable: true,
        },
        {
          name: "assets.create",
          kind: "command",
          description: "Cadastra um novo ativo.",
          grantable: true,
        },
      ],
    },
  ],
};

describe("agentic mcp settings", () => {
  it("computes expiry states, scope size, and MCP client config", () => {
    const now = new Date("2026-03-10T12:00:00Z").getTime();
    expect(daysLeft("2026-03-20T12:00:00Z", now)).toBe(10);
    expect(expiryState("2026-03-20T12:00:00Z", now)).toBe("soon");
    expect(expiryState("2026-06-20T12:00:00Z", now)).toBe("ok");
    expect(expiryState("2026-03-01T12:00:00Z", now)).toBe("expired");

    expect(
      scopeSize(grantOptions.contexts, {
        contexts: ["assets"],
        operations: ["portfolio.consolidated"],
      }),
    ).toBe(3);

    expect(mcpEndpoint()).toContain("/api/v1/mcp");
    const parsed = JSON.parse(mcpClientConfig("fck_secret123")) as {
      mcpServers: { "financial-control": { url: string; headers: { Authorization: string } } };
    };
    expect(parsed.mcpServers["financial-control"].headers.Authorization).toBe("Bearer fck_secret123");
  });

  it("creates a personal MCP key with scoped permissions and displays the secret once", async () => {
    const { calls } = mockApi([
      { path: "/agents/keys/options", reply: grantOptions },
      {
        path: "/agents/keys",
        reply: [
          {
            id: 1,
            name: "Claude Desktop",
            prefix: "fck_abcd1234",
            contexts: ["portfolio"],
            operations: ["assets.list"],
            created_at: "2026-03-10T10:00:00Z",
            expires_at: "2026-06-08T10:00:00Z",
            last_used_at: null,
            revision: 1,
          },
        ],
      },
      {
        method: "POST",
        path: "/agents/keys",
        reply: {
          status: 201,
          json: {
            id: 2,
            name: "Cursor Local",
            prefix: "fck_99887766",
            key: "fck_99887766_full_secret_token",
            contexts: ["portfolio"],
            operations: ["assets.list"],
            created_at: "2026-03-10T12:00:00Z",
            expires_at: "2026-06-08T12:00:00Z",
            last_used_at: null,
            revision: 1,
          },
        },
      },
    ]);

    renderAt("/settings/agentic/new");
    const nameInput = await screen.findByLabelText("Nome da chave");
    expect(await screen.findByText("Carteira & Desempenho")).toBeInTheDocument();

    fireEvent.change(nameInput, { target: { value: "Cursor Local" } });

    // Submitting without scope shows validation error
    fireEvent.click(screen.getByRole("button", { name: "Criar chave MCP" }));
    expect(await screen.findByText("Selecione ao menos um contexto ou operação para esta chave.")).toBeInTheDocument();
    expect(last(calls, "POST", "/agents/keys")).toBeUndefined();

    // Use "Somente leitura em tudo" shortcut (selects portfolio.consolidated + assets.list)
    fireEvent.click(screen.getByRole("button", { name: "Somente leitura em tudo" }));
    expect(screen.getByText("2 operações liberadas")).toBeInTheDocument();

    // Also check whole context for portfolio
    fireEvent.click(screen.getByLabelText("Conceder contexto inteiro portfolio"));

    fireEvent.click(screen.getByRole("button", { name: "Criar chave MCP" }));

    expect(
      await screen.findByText("Guarde esta chave agora — ela não será mostrada novamente"),
    ).toBeInTheDocument();
    expect(screen.getByText("fck_99887766_full_secret_token")).toBeInTheDocument();
    expect(last(calls, "POST", "/agents/keys")?.body).toEqual({
      name: "Cursor Local",
      contexts: ["portfolio"],
      operations: ["assets.list"],
      expires_in_days: 90,
    });
  });

  it("edits, renews, and revokes an existing MCP key", async () => {
    let revoked = false;
    const keyItem = {
      id: 1,
      name: "Claude Desktop",
      prefix: "fck_abcd1234",
      contexts: ["portfolio"],
      operations: ["assets.list"],
      created_at: "2026-03-10T10:00:00Z",
      expires_at: "2026-06-08T10:00:00Z",
      last_used_at: null,
      revision: 1,
    };

    const { calls } = mockApi([
      { path: "/agents/keys/options", reply: grantOptions },
      { path: "/agents/keys", reply: () => (revoked ? [] : [keyItem]) },
      { path: "/agents/keys/1", reply: keyItem },
      {
        method: "POST",
        path: "/agents/keys/1/renew",
        reply: { ...keyItem, expires_at: "2026-12-08T10:00:00Z", revision: 2 },
      },
      {
        method: "PUT",
        path: "/agents/keys/1",
        reply: {
          ...keyItem,
          name: "Claude Desktop Principal",
          contexts: ["portfolio", "assets"],
          operations: [],
          revision: 3,
        },
      },
      {
        method: "DELETE",
        path: "/agents/keys/1",
        reply: () => {
          revoked = true;
          return { status: 204 };
        },
      },
    ]);

    renderAt("/settings/agentic/1");
    expect(await screen.findByDisplayValue("Claude Desktop")).toBeInTheDocument();

    // Renew validity
    fireEvent.change(screen.getByLabelText("Renovar por"), { target: { value: "180" } });
    fireEvent.click(screen.getByRole("button", { name: "Renovar validade" }));
    expect(await screen.findByText(/Validade renovada até/)).toBeInTheDocument();
    expect(last(calls, "POST", "/agents/keys/1/renew")?.body).toEqual({ expires_in_days: 180 });

    // Open collapsible scope section and grant whole assets context
    fireEvent.click(screen.getByRole("button", { name: /Escopo de ferramentas MCP/ }));
    fireEvent.click(await screen.findByLabelText("Conceder contexto inteiro assets"));
    fireEvent.change(screen.getByLabelText("Nome da chave"), {
      target: { value: "Claude Desktop Principal" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));

    expect(await screen.findByText(/Alterações salvas/)).toBeInTheDocument();
    expect(last(calls, "PUT", "/agents/keys/1")?.body).toEqual({
      name: "Claude Desktop Principal",
      contexts: ["portfolio", "assets"],
      operations: [],
      expected_revision: 2,
    });

    // Return to list and revoke
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(await screen.findByText("fck_abcd1234…")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Revogar" }));
    expect(screen.getByRole("dialog", { name: "Confirmar revogação" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar revogação" }));
    expect(await screen.findByText(/Nenhuma chave MCP ativa/)).toBeInTheDocument();
    expect(last(calls, "DELETE", "/agents/keys/1")).toBeDefined();
  });
});

