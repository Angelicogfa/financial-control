import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { analysis, evaluation, trackedInstrument } from "./fixtures";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

describe("checklist and data reliability (Phase 25)", () => {
  it("flags expired and reopened manual answers on the checklist", async () => {
    const stale = evaluation({
      stale: 2,
      answers: [
        {
          question_id: "governance",
          text: "Tem boa governança?",
          category: "Governança",
          hint: "",
          value: "YES",
          answer: true,
          source: "MANUAL",
          automatable: false,
          answered_at: "2025-01-10T10:00:00Z",
          stale_reason: "EXPIRED",
        },
        {
          question_id: "age_30y",
          text: "Tem mais de 30 anos?",
          category: "Perenidade",
          hint: "",
          value: "YES",
          answer: true,
          source: "MANUAL",
          automatable: false,
          answered_at: "2026-02-10T10:00:00Z",
          stale_reason: "NEW_STATEMENT",
        },
      ],
    });
    mockApi([trackedInstrument(), { path: "/assets/1/analysis", reply: analysis({ checklist: stale }) }]);
    renderAt("/ativo/WEGE3?tab=checklist");

    expect(await screen.findByText("Resposta vencida")).toBeInTheDocument();
    expect(screen.getByText("Reaberta: demonstrativo novo")).toBeInTheDocument();
    const checklist = screen.getByRole("region", { name: "Vale a pena?" });
    expect(within(checklist).getByRole("note")).toHaveTextContent("2 resposta(s) manual(is) vencida(s)");
  });

  it("shows the suspicious data badge and the one-off dividends note on the valuation", async () => {
    const base = analysis();
    mockApi([
      trackedInstrument(),
      {
        path: "/assets/1/analysis",
        reply: analysis({
          fundamentals: {
            ...(base.fundamentals ?? {}),
            suspicious: { dividend_yield: "Dividend yield de 90,0% fora da faixa plausível (0,0% a 30,0%)." },
          },
          valuation: { ...base.valuation, suspicious_inputs: ["dividend_yield"], extraordinary_dividends: true },
        }),
      },
    ]);
    renderAt("/ativo/WEGE3?tab=valuation");

    expect(await screen.findByText("Dado suspeito")).toBeInTheDocument();
    const valuation = screen.getByRole("region", { name: "Está barato?" });
    expect(within(valuation).getByRole("note")).toHaveTextContent("Dividend yield de 90,0% fora da faixa plausível");
    expect(screen.getByText(/os últimos 12 meses estão bem acima da mediana/)).toBeInTheDocument();
  });

  it("keeps the valuation clean without flags", async () => {
    mockApi([trackedInstrument(), { path: "/assets/1/analysis", reply: analysis() }]);
    renderAt("/ativo/WEGE3?tab=valuation");
    await screen.findByText("Preço justo de Graham");
    expect(screen.queryByText("Dado suspeito")).not.toBeInTheDocument();
  });
});
