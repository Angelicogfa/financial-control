import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PortfolioHealthDTO } from "../api/types";
import { formatHealthValue } from "../pages/health/HealthPage";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

const health: PortfolioHealthDTO = {
  as_of_date: "2026-10-27",
  status: "CRITICAL",
  total_value_brl: 380000,
  pillars: [
    {
      pillar: "CONCENTRATION",
      title: "Concentração",
      status: "CRITICAL",
      checks: [
        {
          key: "fgc_exposure",
          title: "Exposição por instituição (FGC)",
          status: "CRITICAL",
          value: 1.2,
          unit: "FRACTION",
          warning_threshold: 0.9,
          critical_threshold: 1,
          explanation: "Maior exposição: BANCO A com R$ 300.000,00.",
          action: "Distribua entre outras instituições.",
        },
      ],
    },
    {
      pillar: "RISK",
      title: "Risco",
      status: "INSUFFICIENT_DATA",
      checks: [
        {
          key: "volatility",
          title: "Volatilidade anualizada",
          status: "INSUFFICIENT_DATA",
          explanation: "São necessários 60 retornos diários da carteira (há 12).",
          observations: 12,
          min_observations: 60,
        },
      ],
    },
    {
      pillar: "LIQUIDITY",
      title: "Liquidez, renda e tributos",
      status: "OK",
      checks: [
        {
          key: "emergency_reserve",
          title: "Reserva de emergência",
          status: "OK",
          value: 7.5,
          unit: "MONTHS",
          warning_threshold: 6,
          critical_threshold: 3,
          explanation: "A reserva cobre 7,5 meses.",
        },
      ],
    },
  ],
  concentration: [{ dimension: "CLASS", hhi: 0.5, effective_count: 2, weights: { CAIXA: 0.5, ACOES: 0.5 } }],
  institutions: [{ issuer: "BANCO A", value_brl: 300000, limit_brl: 250000, usage: 1.2 }],
};

describe("portfolio health", () => {
  it("shows pillars worst first with value, limits, action and the minimum window", async () => {
    mockApi([{ path: "/portfolio/health", reply: health }]);
    renderAt("/health");

    const pillars = await screen.findAllByRole("region");
    const titles = pillars.map((p) => p.getAttribute("aria-label"));
    expect(titles).toEqual(["Resumo", "Concentração", "Risco", "Liquidez, renda e tributos"]);

    const concentration = within(pillars[1]);
    expect(concentration.getAllByText("Crítico").length).toBeGreaterThan(0);
    expect(concentration.getByText("120,0%")).toBeInTheDocument();
    expect(concentration.getByText("Distribua entre outras instituições.")).toBeInTheDocument();
    expect(concentration.getByText(/Limites: atenção 90,0% · crítico 100,0%/)).toBeInTheDocument();

    expect(within(pillars[2]).getByText(/Janela mínima: 60 \(há 12\)/)).toBeInTheDocument();
    expect(within(pillars[3]).getByText("7,5 meses")).toBeInTheDocument();
    expect(screen.getByText(/1 crítico\(s\), 0 em atenção, 1 ok e 1 sem dados suficientes/)).toBeInTheDocument();
    expect(screen.getByText("Caixa")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "BANCO A" })).toBeInTheDocument();
  });

  it("lists enumerations one per line and marks checks built from cleaned data", async () => {
    const report: PortfolioHealthDTO = {
      ...health,
      pillars: [
        {
          pillar: "DIVERSIFICATION",
          title: "Diversificação de risco",
          status: "WARNING",
          checks: [
            {
              key: "risk_contribution",
              title: "Contribuição ao risco",
              status: "WARNING",
              value: 0.4,
              unit: "FRACTION",
              explanation: "WEGE3 responde por 40,0% do risco com 20,0% do peso. Por quadrante:",
              items: ["Ações Brasil: 60% do peso e 90% do risco", "Caixa & Renda Fixa: 40% do peso e 10% do risco"],
              suspicious: "Dados descartados antes do cálculo: XPML11: preço do provedor fora de escala descartado em 14/01/2026.",
            },
          ],
        },
      ],
    };
    mockApi([{ path: "/portfolio/health", reply: report }]);
    renderAt("/health");
    const pillar = (await screen.findAllByRole("region"))[1];
    const items = within(pillar).getAllByRole("listitem").filter((li) => li.closest(".health-check-items"));
    expect(items.map((li) => li.textContent)).toEqual([
      "Ações Brasil: 60% do peso e 90% do risco",
      "Caixa & Renda Fixa: 40% do peso e 10% do risco",
    ]);
    const note = within(pillar).getByRole("note");
    expect(note).toHaveTextContent("Dado suspeito");
    expect(note).toHaveTextContent(/XPML11: preço do provedor fora de escala/);
  });

  it("shows the error state when the API fails", async () => {
    mockApi([{ path: "/portfolio/health", reply: { status: 503, json: { detail: "fora do ar" } } }]);
    renderAt("/health");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("formats each unit", () => {
    expect(formatHealthValue(0.153, "FRACTION")).toBe("15,3%");
    expect(formatHealthValue(1.234, "RATIO")).toBe("1,23");
    expect(formatHealthValue(3, "MONTHS")).toBe("3 meses");
    expect(formatHealthValue(null, "BRL")).toBe("—");
    expect(formatHealthValue(1500, "BRL")).toMatch(/R\$\s1\.500,00/);
  });
});
