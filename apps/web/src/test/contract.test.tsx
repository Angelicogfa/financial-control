/** Tests for the phase 8 API contract on the frontend: rate scale and data-quality notices. */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { EMPTY_PORTFOLIO_REPORT } from "../services/apiClient";
import type { PortfolioReportDTO, ValuedPositionDTO } from "../types/api";
import {
  DEFAULT_RATE_PERCENT,
  contractedRateToPercent,
  percentToContractedRate,
} from "../utils/rates";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Contracted rate conversion (ADR 0006)", () => {
  it("converts typed percentages to the API scale and back", () => {
    expect(percentToContractedRate(110)).toBe(1.1);
    expect(percentToContractedRate(6.5)).toBe(0.065);
    expect(percentToContractedRate(12.5)).toBe(0.125);
    expect(contractedRateToPercent("1.12")).toBe(112);
    expect(contractedRateToPercent(0.062)).toBe(6.2);
  });

  it("offers a sensible default per indexer", () => {
    expect(DEFAULT_RATE_PERCENT.CDI).toBe("110");
    expect(DEFAULT_RATE_PERCENT.IPCA).toBe("6");
  });
});

describe("Data quality notices", () => {
  it("lists assets whose ledger is invalid", async () => {
    // Shape returned by the API for an asset whose ledger cannot be valued.
    const broken: ValuedPositionDTO = {
      asset_id: 7,
      ticker: "PETR4",
      name: "Petrobras",
      asset_type: "STOCK_BR",
      arca_class: "ACOES",
      currency: "BRL",
      quantity: 0,
      average_price: 0,
      current_unit_price: 0,
      fx_rate: 1,
      price_freshness: "FALLBACK",
      invested_value_brl: 0,
      gross_current_value_brl: 0,
      estimated_tax_brl: 0,
      current_value_brl: 0,
      unrealized_pnl_brl: 0,
      unrealized_pnl_pct: 0,
      realized_pnl_brl: 0,
      received_earnings_brl: 0,
      earnings_12m_brl: 0,
      yield_on_cost_pct: 0,
      estimated_yield_to_date_brl: 0,
      estimated_yield_to_date_pct: 0,
      estimated_yield_basis: "Invalid ledger",
      projected_12m_yield_brl: 0,
      consolidated_pnl_brl: 0,
      consolidated_return_pct: 0,
      cerrado_evaluation: {
        asset_type: "STOCK_BR",
        use_cerrado: true,
        score: 0,
        max_score: 12,
        answered: 0,
        pending: 12,
        recommendation: "INCOMPLETO",
      },
      class_target_weight_pct: 0,
      class_current_weight_pct: 0,
      ledger_status: "INVALID",
      ledger_message: "Cannot sell 10 on 2025-01-02; held quantity is 0",
    };
    const report: PortfolioReportDTO = { ...EMPTY_PORTFOLIO_REPORT, positions: [broken] };

    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (String(input).includes("/api/v1/portfolio/consolidated")) {
        return new Response(JSON.stringify(report), { status: 200 });
      }
      return new Response(JSON.stringify({ items: [], meta: {} }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Lançamentos inconsistentes em PETR4");
    });
  });
});
