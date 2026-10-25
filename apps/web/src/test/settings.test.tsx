import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "../App";
import type { PolicyDTO } from "../api/types";
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
    const { calls } = mockApi([
      { path: "/policy", reply: policy },
      { path: "/policy/versions", reply: [policy] },
      { method: "PUT", path: "/policy", reply: { ...policy, version: 4 } },
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
