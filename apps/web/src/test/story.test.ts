import { describe, expect, it } from "vitest";

import { alignCurves, curveReturn, headline, lastMonths, patrimonyChange } from "../pages/home/story";
import { alerts, allocation, position, report } from "./fixtures";

/** Intl uses non-breaking spaces. */
const plain = (text: string) => text.replace(/\s/g, " ");

describe("home story", () => {
  it("measures the patrimony change net of contributions", () => {
    const snapshots = [
      { snapshot_date: "2026-02-01", invested_value: 1000, market_value: 1000, consolidated_pnl: 0, earnings_cum: 0, net_flow: 0 },
      { snapshot_date: "2026-02-20", invested_value: 1500, market_value: 1550, consolidated_pnl: 50, earnings_cum: 0, net_flow: 500 },
    ];
    const change = patrimonyChange(snapshots, 1600, 30, new Date("2026-03-03T12:00:00"));
    expect(change?.days).toBe(30);
    expect(change?.value).toBeCloseTo(0.1);
    expect(patrimonyChange([], 100)).toBeNull();
  });

  it("writes the headline from the numbers", () => {
    const sentences = headline(report(), { value: 0.021, days: 30 }, alerts().alerts).map(plain);
    expect(sentences[0]).toBe("Patrimônio de R$ 5 mil, +2,1% em 30 dias (sem contar aportes).");
    expect(sentences[1]).toBe("Real Estate está abaixo da banda: 0,0% contra meta de 25%.");
    expect(sentences[2]).toBe("Há 1 alerta pedindo atenção.");
  });

  it("guides an empty portfolio and balanced classes", () => {
    expect(headline(report({ positions: [position({ quantity: 0, current_value_brl: 0 })] }), null, [])[0]).toMatch(
      /ainda está vazia/,
    );
    const balanced = report({ allocations: [allocation({ band_status: "WITHIN" })] });
    expect(headline(balanced, null, []).map(plain)).toEqual([
      "Patrimônio de R$ 5 mil.",
      "Todas as classes estão dentro das bandas.",
    ]);
  });

  it("aligns curves on a shared axis with gaps", () => {
    const aligned = alignCurves(
      {
        PORTFOLIO: [
          { date: "2026-03-02", value: 100 },
          { date: "2026-03-03", value: 101 },
        ],
        IBOV: [
          { date: "2026-03-01", value: 100 },
          { date: "2026-03-03", value: 99 },
        ],
        CDI: [{ date: "2026-03-01", value: 100 }],
      },
      ["PORTFOLIO", "CDI", "IBOV"],
    );
    expect(aligned.labels).toEqual(["2026-03-01", "2026-03-02", "2026-03-03"]);
    expect(aligned.series).toEqual({ PORTFOLIO: [null, 100, 101], IBOV: [100, null, 99] });
    expect(curveReturn([{ value: 100 }, { value: 105 }])).toBeCloseTo(0.05);
    expect(curveReturn(undefined)).toBeNull();
  });

  it("fills the last twelve months", () => {
    const months = lastMonths({ "2026-02": 12 }, 3, new Date(2026, 2, 15));
    expect(months).toEqual([
      ["2026-01", 0],
      ["2026-02", 12],
      ["2026-03", 0],
    ]);
  });
});
