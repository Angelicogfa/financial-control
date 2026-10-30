import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AssetForecastDTO, ForecastHorizonDTO } from "../api/types";
import { chanceAbove } from "../pages/asset/ForecastTab";
import { analysis } from "./fixtures";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

/** Price = level x 100: P(price > 50) is 50%. */
const GRID = Array.from({ length: 99 }, (_, i) => i + 1);

function horizon(months: number, overrides: Partial<ForecastHorizonDTO> = {}): ForecastHorizonDTO {
  return {
    months,
    target_date: "2027-10-30",
    p5: 5,
    p25: 25,
    p50: 50,
    p75: 75,
    p95: 95,
    total_return_p50: 0.12,
    up: { value: 0.62, low: 0.6, high: 0.64 },
    fall_20: { value: 0.11, low: 0.1, high: 0.12 },
    thresholds: [
      { key: "NOW", label: "Acima do preço de hoje", price: 40, direction: "above", probability: 0.62 },
      { key: "FAIR", label: "Acima do preço justo (valuation)", price: 60, direction: "above", probability: 0.4 },
      { key: "FALL_20", label: "Queda de 20% ou mais", price: 32, direction: "below", probability: 0.11 },
    ],
    price_quantiles: GRID,
    ...overrides,
  };
}

function forecast(overrides: Partial<AssetForecastDTO> = {}): AssetForecastDTO {
  return {
    asset_id: 1,
    ticker: "WEGE3",
    status: "OK",
    as_of: "2026-10-30",
    price_now: 40,
    lead: "Em 12 meses, há 62% de chance de WEGE3 estar acima do preço de hoje (R$ 40,00).",
    months_used: 108,
    beta: 1.1,
    dividend_yield_annual: 0.025,
    horizons: [horizon(3), horizon(6), horizon(12), horizon(24, { up: { value: 0.7, low: 0.68, high: 0.72 } })],
    drivers: [
      { key: "MARKET", label: "Mercado (classe)", annual: 0.08, note: "" },
      { key: "VALUATION", label: "Valuation", annual: null, note: "Entra na Fase 42.3" },
    ],
    seal: { level: 3, label: "Confiável", text: "Quando o modelo disse 90%, aconteceu em 88% das vezes." },
    warnings: [],
    model_version: "42.1.0",
    ...overrides,
  };
}

describe("Probabilidades tab (Phase 42.1)", () => {
  it("reads chances from the quantile grid like the API", () => {
    expect(chanceAbove(GRID, 50)).toBeCloseTo(0.5);
    expect(chanceAbove(GRID, 25.5)).toBeCloseTo(0.745);
    expect(chanceAbove(GRID, 0.5)).toBe(0.995);
    expect(chanceAbove(GRID, 150)).toBe(0.005);
    expect(chanceAbove([1, 2], 1.5)).toBeNull();
  });

  it("shows the lead, the chances, the drivers and the seal", async () => {
    mockApi([
      { path: "/assets/1/analysis", reply: analysis() },
      { path: "/assets/1/forecast", reply: forecast() },
    ]);
    renderAt("/asset/1?tab=forecast");
    expect(await screen.findByText(/há 62% de chance de WEGE3/)).toBeInTheDocument();
    expect(screen.getByText("Chance de subir")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Chances em 12 meses" });
    expect(within(table).getByText("Acima do preço justo (valuation)")).toBeInTheDocument();
    expect(screen.getByText("Entra na Fase 42.3")).toBeInTheDocument();
    expect(screen.getByText("Confiável")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "24 meses" }));
    expect(screen.getByText("70%")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Preço (R$)"), { target: { value: "50" } });
    expect(screen.getByText(/Chance de estar acima de R\$\s?50,00 em 24 meses: 50%/)).toBeInTheDocument();
  });

  it("hides a forecast the calibration does not back", async () => {
    mockApi([
      { path: "/assets/1/analysis", reply: analysis() },
      {
        path: "/assets/1/forecast",
        reply: forecast({
          status: "LOW_CONFIDENCE",
          horizons: [],
          warnings: ["As faixas ainda não se confirmaram bem no passado."],
          seal: { level: 1, label: "Indicativo", text: "Poucas janelas." },
        }),
      },
    ]);
    renderAt("/asset/1?tab=forecast");
    expect(await screen.findByText("Previsão oculta por baixa confiança")).toBeInTheDocument();
    expect(screen.getByText("Poucas janelas.")).toBeInTheDocument();
    expect(screen.queryByText("Chance de subir")).not.toBeInTheDocument();
  });
});
