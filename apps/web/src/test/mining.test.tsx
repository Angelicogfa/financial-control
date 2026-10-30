import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MiningOverviewDTO } from "../api/types";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

function overview(overrides: Partial<MiningOverviewDTO> = {}): MiningOverviewDTO {
  return {
    status: "OK",
    found_on: "2026-11-01",
    month: "2026-10-31",
    trusted: true,
    reason: "Fora da amostra, os achados renderam +3,1% ao ano sobre o universo depois dos custos.",
    oos_months: 132,
    oos_excess_annual: 0.031,
    oos_probability: 0.95,
    oos_hit_rate: 0.6,
    pbo: 0.48,
    loss_probability: 0.1,
    variants: 45,
    cost_annual: 0.006,
    weights: [
      { signal: "VALUE", estimate_annual_per_z: 0.04, weight_annual_per_z: 0.04, sign_probability: 0.97, used: true },
      { signal: "MOMENTUM", estimate_annual_per_z: 0.005, weight_annual_per_z: 0, sign_probability: 0.6, used: false },
    ],
    findings: [
      {
        rank: 1,
        ticker: "ABCD3",
        company: "Cia ABCD",
        sector: "Bens Industriais",
        score_annual: 0.052,
        signals: { VALUE: 1.8, QUALITY: 0.4 },
        reason: "Barata frente ao próprio histórico e ao setor (z +1,8)",
        asset_id: null,
      },
      {
        rank: 2,
        ticker: "WEGE3",
        company: "WEG",
        sector: "Bens Industriais",
        score_annual: 0.03,
        signals: { VALUE: 0.9 },
        reason: "Barata frente ao próprio histórico e ao setor (z +0,9)",
        asset_id: 7,
      },
    ],
    record: [
      {
        horizon: 12,
        trusted: true,
        runs: 20,
        findings: 200,
        beat: 116,
        beat_share: 0.58,
        beat_low: 0.51,
        beat_high: 0.65,
        mean_excess_annual: 0.024,
      },
    ],
    ...overrides,
  };
}

describe("Garimpo (Phase 43)", () => {
  it("shows the findings, why they appeared, the weights and the record", async () => {
    mockApi([{ path: "/research/mining", reply: overview() }]);
    renderAt("/research/mining");
    const table = await screen.findByRole("table", { name: "Achados da semana" }, { timeout: 5000 });
    expect(within(table).getByText("ABCD3")).toBeInTheDocument();
    expect(within(table).getByText("Barata frente ao próprio histórico e ao setor (z +1,8)")).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "WEGE3" })).toHaveAttribute("href", "/asset/7");
    expect(within(table).queryByRole("link", { name: "ABCD3" })).not.toBeInTheDocument();
    expect(within(table).queryByRole("link", { name: "Ver ativo" })).not.toBeInTheDocument();
    expect(screen.getByText("Chance de perder do universo")).toBeInTheDocument();
    expect(screen.getByText(/não usado \(60% de confiança no sentido\)/)).toBeInTheDocument();
    const record = screen.getByRole("table", { name: "Placar dos achados" });
    expect(within(record).getByText("58%")).toBeInTheDocument();
  });

  it("labels an untrusted list as a ranking under observation", async () => {
    mockApi([
      {
        path: "/research/mining",
        reply: overview({ trusted: false, reason: "Só 3 anos fora da amostra; são precisos 5." }),
      },
    ]);
    renderAt("/research/mining");
    expect(await screen.findByRole("table", { name: "Ranking em observação" }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/ainda não são achados confiáveis/)).toBeInTheDocument();
  });

  it("follows a finding and explains a missing ticker", async () => {
    let followed = false;
    const { calls } = mockApi([
      {
        method: "GET",
        path: "/research/mining",
        reply: () =>
          followed
            ? overview({ findings: overview().findings!.map((f) => ({ ...f, asset_id: f.asset_id ?? 9 })) })
            : overview(),
      },
      {
        method: "POST",
        path: "/research/watchlist",
        reply: () => {
          followed = true;
          return { asset_id: 9, ticker: "ABCD3" };
        },
      },
      {
        path: /\/research\/mining\/why\//,
        reply: {
          ticker: "PETR4",
          status: "RANKED",
          rank: 31,
          ranked: 120,
          score_annual: 0.004,
          cutoff_annual: 0.02,
          signals: { VALUE: -0.5 },
          reasons: ["O sinal de valor pesou contra (z -0,5)."],
        },
      },
    ]);
    renderAt("/research/mining");
    fireEvent.click(await screen.findByRole("button", { name: "Seguir" }, { timeout: 5000 }));
    await waitFor(() => expect(screen.getByRole("link", { name: "ABCD3" })).toHaveAttribute("href", "/asset/9"));
    expect(screen.queryByRole("button", { name: "Seguir" })).not.toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toMatchObject({ ticker: "ABCD3", asset_type: "STOCK_BR" });

    fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: "petr4" } });
    fireEvent.click(screen.getByRole("button", { name: "Ver" }));
    expect(await screen.findByText(/posição 31 de 120/)).toBeInTheDocument();
    expect(screen.getByText("O sinal de valor pesou contra (z -0,5).")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/research/mining/why/PETR4")).toBe(true);
  });

  it("says when it has not run yet", async () => {
    mockApi([{ path: "/research/mining", reply: overview({ status: "NOT_RUN", reason: "Ainda não rodou." }) }]);
    renderAt("/research/mining");
    expect(await screen.findByText("O garimpo ainda não rodou", undefined, { timeout: 5000 })).toBeInTheDocument();
  });
});
