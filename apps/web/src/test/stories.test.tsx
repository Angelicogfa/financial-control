import { describe, expect, it } from "vitest";

import type {
  ClassAllocationDTO,
  PolicyDTO,
  PortfolioAnalyticsResponseDTO,
  PortfolioReportResponseDTO,
  SavedContributionPlanDTO,
} from "../api/types";
import { planStory } from "../pages/contribute/ContributePage";
import { marketSplit } from "../pages/home/story";
import { performanceStory } from "../pages/performance/PerformancePage";
import { portfolioStory } from "../pages/portfolio/PortfolioPage";
import { strategyStory } from "../pages/settings/StrategyPage";

function allocation(over: Partial<ClassAllocationDTO>): ClassAllocationDTO {
  return {
    arca_class: "ACOES",
    label: "Ações Brasil",
    invested_value: 1000,
    current_value: 1100,
    current_pct: 25,
    target_pct: 25,
    deviation_pct: 0,
    gap_value: 0,
    consolidated_pnl: 100,
    band_status: "WITHIN",
    ...over,
  };
}

describe("marketSplit", () => {
  it("puts Caixa, Ações and Real Estate in Bolsa and the rest in Internacional", () => {
    const [b3, abroad] = marketSplit([
      allocation({ arca_class: "ACOES", invested_value: 1000, current_value: 1200, consolidated_pnl: 200 }),
      allocation({ arca_class: "CAIXA", invested_value: 1000, current_value: 1000, consolidated_pnl: 0 }),
      allocation({ arca_class: "REAL_ESTATE", invested_value: 0, current_value: 0, consolidated_pnl: 0 }),
      allocation({ arca_class: "ATIVOS_INTERNACIONAIS", invested_value: 1000, current_value: 800, consolidated_pnl: -200 }),
    ]);
    expect(b3).toMatchObject({ label: "Bolsa", value: 2200, invested: 2000, pnl: 200, change: 0.1 });
    expect(b3.share).toBeCloseTo(2200 / 3000);
    expect(abroad).toMatchObject({ label: "Internacional", value: 800, change: -0.2 });
  });

  it("has no change when nothing was invested", () => {
    const [, abroad] = marketSplit([allocation({ arca_class: "ACOES" })]);
    expect(abroad.change).toBeNull();
    expect(abroad.share).toBe(0);
  });
});

function analytics(excess: number | null): PortfolioAnalyticsResponseDTO {
  return {
    status: "OK",
    curves: {},
    summary: {
      cumulative_return: 0.08,
      max_drawdown: -0.05,
      benchmarks:
        excess === null
          ? []
          : [
              { benchmark: "CDI", benchmark_return: 0.1, excess_return: excess },
              { benchmark: "IBOV", benchmark_return: 0.2, excess_return: -0.12 },
            ],
    },
  } as unknown as PortfolioAnalyticsResponseDTO;
}

describe("performanceStory", () => {
  it("tells the return, the gap to the CDI and the strongest reference", () => {
    const story = performanceStory(analytics(-0.02), "12 meses");
    expect(story.tone).toBe("negative");
    expect(story.text).toBe(
      "Em 12 meses, a carteira rendeu +8,0%, 2,0% abaixo do CDI, com queda máxima de -5,0%. A referência mais forte foi Ibovespa (+20,0%).",
    );
  });

  it("stays neutral without the CDI", () => {
    expect(performanceStory(analytics(null), "6 meses")).toEqual({
      tone: "neutral",
      text: "Em 6 meses, a carteira rendeu +8,0%, com queda máxima de -5,0%.",
    });
  });
});

function report(allocations: ClassAllocationDTO[]): PortfolioReportResponseDTO {
  return {
    total_current_value_brl: 5000,
    total_consolidated_pnl_brl: 400,
    total_consolidated_return_pct: 8,
    allocations,
    positions: [
      { asset_id: 1, arca_class: "ACOES", quantity: 10, invested_value_brl: 1000, ledger_status: "VALID" },
      { asset_id: 2, arca_class: "ACOES", quantity: 0, invested_value_brl: 0, ledger_status: "VALID" },
    ],
  } as unknown as PortfolioReportResponseDTO;
}

describe("portfolioStory", () => {
  it("names the class furthest from its band", () => {
    const story = portfolioStory(
      report([
        allocation({ label: "Ações Brasil", band_status: "BELOW", current_pct: 15, target_pct: 25, deviation_pct: -10 }),
        allocation({ arca_class: "CAIXA", label: "Caixa", band_status: "ABOVE", current_pct: 32, target_pct: 25, deviation_pct: 7 }),
      ]),
      "ALL",
    );
    expect(story.tone).toBe("caution");
    expect(story.text).toMatch(/^A carteira vale R\$\s5\.000,00 em 1 posição, com resultado consolidado de R\$\s400,00/);
    expect(story.text).toMatch(/Ações Brasil está abaixo da banda: 15,0% contra a meta de 25%\.$/);
  });

  it("describes one class on its tab", () => {
    const story = portfolioStory(report([allocation({ band_status: "WITHIN" })]), "ACOES");
    expect(story.text).toMatch(/^Ações Brasil soma R\$\s1\.100,00 em 1 ativo, 25,0% da carteira .* Está dentro da banda\.$/);
  });
});

describe("planStory", () => {
  it("says where the money goes and what is left over", () => {
    const saved = {
      plan: {
        contribution_amount_brl: 2000,
        by_class_allocated_brl: { ACOES: 1500, CAIXA: 400, REAL_ESTATE: 0 },
        unallocated_cash_brl: 100,
        orders: [{ recommended_quantity: 3 }, { recommended_quantity: 0 }],
      },
    } as unknown as SavedContributionPlanDTO;
    expect(planStory(saved)).toMatch(
      /^Dos R\$\s2\.000,00 do aporte, R\$\s1\.500,00 para Ações.*, R\$\s400,00 para Caixa.*, em 1 compra sugerida\. R\$\s100,00 ficam sem destino\.$/,
    );
  });
});

describe("strategyStory", () => {
  it("reads the targets and the eligibility rule", () => {
    const policy = {
      arca: [{ arca_class: "ACOES", target_pct: 25, band_pct: 5 }],
      eligibility: { require_evaluation: true, min_score: 2, answer_validity_months: 1 },
    } as unknown as PolicyDTO;
    const text = strategyStory(policy);
    expect(text).toMatch(/^Metas: .*Ações.* 25% \(±5 p\.p\.\)/);
    expect(text).toMatch(/Só ativos com checklist respondido e nota mínima 2 recebem aportes; as respostas valem 1 mês\.$/);
  });
});
