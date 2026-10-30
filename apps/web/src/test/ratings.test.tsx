import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { analysis } from "./fixtures";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

describe("Indicator ratings in the Fundamentals tab", () => {
  it("says beside each indicator whether it is good, and against what", async () => {
    mockApi([
      {
        path: "/assets/1/analysis",
        reply: analysis({
          fundamentals: { price_to_earnings: 25, dividend_yield: 0.015, return_on_equity: 0.3, profit_margin: 2.143 },
          indicator_ratings: {
            price_to_earnings: { status: "BAD", reference: "Bem acima de 15, o máximo da estratégia." },
            dividend_yield: { status: "CAUTION", reference: "Abaixo de 6,0% (Bazin)." },
            return_on_equity: { status: "GOOD", reference: "A partir de 10,0%, como pede o checklist." },
            profit_margin: { status: "SUSPICIOUS", reference: "Fora do possível (acima de 100% da receita): confira o dado." },
          },
        }),
      },
      { path: "/assets/1/statements", reply: { asset_id: 1, ticker: "WEGE3", status: "NOT_A_COMPANY" } },
    ]);
    renderAt("/asset/1?tab=fundamentals");
    const card = (await screen.findByText("Indicadores atuais", undefined, { timeout: 5000 })).closest("section")!;
    expect(within(card).getByText("Ruim")).toBeInTheDocument();
    expect(within(card).getByText("Atenção")).toBeInTheDocument();
    expect(within(card).getByText("Bom")).toBeInTheDocument();
    expect(within(card).getByText("Confira o dado")).toBeInTheDocument();
    expect(within(card).getByText("Bem acima de 15, o máximo da estratégia.")).toBeInTheDocument();
  });
});
