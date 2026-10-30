import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AssetContributionOrderDTO, ClassContributionRationaleDTO } from "../api/types";
import { classReasonText, orderReasonText, orderWeightText } from "../pages/contribute/Rationale";
import { report, savedPlan } from "./fixtures";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

const order = (overrides: Partial<AssetContributionOrderDTO> = {}): AssetContributionOrderDTO => ({
  ...savedPlan().plan.orders[0],
  ...overrides,
});
const rule = (overrides: Partial<ClassContributionRationaleDTO> = {}): ClassContributionRationaleDTO => ({
  ...savedPlan().plan.class_rationale![1],
  ...overrides,
});

describe("contribution rationale texts", () => {
  it("names the class rule with its numbers", () => {
    expect(classReasonText(rule())).toMatch(/^Abaixo da banda \(0,0% contra a meta de 50%, tolerância de 5%\): recompõe primeiro; faltavam R\$\s3\.000,00/);
    expect(classReasonText(rule({ reason: "BELOW_BAND_PRIORITY" }))).toMatch(/precisavam de mais que o aporte inteiro/);
    expect(classReasonText(rule({ reason: "BELOW_TARGET", deficit_brl: 200 }))).toMatch(/na proporção do que falta, R\$\s200,00/);
    expect(classReasonText(rule({ reason: "ABOVE_TARGET" }))).toMatch(/não recebe\.$/);
    expect(classReasonText(rule({ reason: "NO_ELIGIBLE_ASSETS", first_level_brl: 300 }))).toMatch(/Receberia R\$\s300,00, mas não tem ativo elegível/);
  });

  it("explains each asset, rounding and leftovers included", () => {
    expect(orderReasonText(order())).toMatch(/reservados R\$\s1\.000,00\. R\$\s40,00 não compram mais uma unidade\.$/);
    expect(orderReasonText(order({ executed_amount_brl: 1120, leftover_amount_brl: 160 }))).toMatch(/Mais R\$\s160,00 vindos das sobras/);
    expect(orderReasonText(order({ reason: "LEFTOVER_FILL", leftover_amount_brl: 160 }))).toMatch(/só com as sobras de outros ativos \(R\$\s160,00\)/);
    expect(orderReasonText(order({ reason: "PRICE_ABOVE_BUDGET", allocated_amount_brl: 100 }))).toMatch(/uma unidade custa 160/);
    expect(orderReasonText(order({ reason: "ZERO_WEIGHT" }), "CERRADO")).toBe("Nota zero no checklist: sem peso na classe.");
    expect(orderReasonText(order({ reason: "ZERO_WEIGHT" }), "MANUAL_WEIGHT")).toBe("Sem peso manual: não recebe.");
    expect(orderReasonText(order({ reason: null }))).toBe("");
  });

  it("tells where the target weight comes from", () => {
    expect(orderWeightText(order(), "CERRADO")).toBe("Nota 1 no checklist → peso alvo 100,0% · hoje 0,0%");
    expect(orderWeightText(order(), "EQUAL_WEIGHT")).toMatch(/^Peso igual/);
    // Old plans keep only the target weight.
    expect(orderWeightText(order({ reason: null }))).toBe("Peso alvo 100,0%");
  });
});

describe("contribution rationale on the page", () => {
  const routes = (plan = savedPlan()) => [
    { path: "/contributions/7", reply: plan },
    { path: "/portfolio/consolidated", reply: report() },
    { path: "/accounts", reply: [] },
  ];

  it("shows the rule of each class and why each asset is bought", async () => {
    mockApi(routes());
    renderAt("/contribute/7");
    const table = await screen.findByRole("table", { name: "Regra aplicada a cada classe" });
    const realEstate = within(table).getByRole("row", { name: /Real Estate/ });
    expect(realEstate).toHaveTextContent(/recompõe primeiro/);
    expect(realEstate).toHaveTextContent("Pela nota do checklist");
    expect(realEstate).toHaveTextContent("Da Estratégia · 1 ativo elegível");
    expect(screen.getByRole("columnheader", { name: "Por quê" })).toBeInTheDocument();
    expect(screen.getByText(/Abaixo do peso alvo: reservados/)).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Limites do cálculo" })).toHaveTextContent(/não uma otimização/);
  });

  it("says so when the plan was saved before the rationale", async () => {
    const legacy = savedPlan();
    legacy.plan.class_rationale = undefined;
    legacy.plan.orders = legacy.plan.orders.map((o) => ({ ...o, reason: undefined }));
    mockApi(routes(legacy));
    renderAt("/contribute/7");
    expect(await screen.findByText(/Plano salvo antes da justificativa/)).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Regra aplicada a cada classe" })).not.toBeInTheDocument();
  });
});
