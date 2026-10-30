import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { mockApi } from "./mockApi";
import { renderAt } from "./render";

const feed = {
  items: [
    {
      id: 1,
      protocol: "P1",
      tickers: ["WEGE3"],
      company_name: "WEG",
      category: "Fato Relevante",
      subject: "Programa de Recompra de Ações",
      delivery_date: "2026-10-20",
      read: true,
      event_class: "BUYBACK",
      event_label: "Recompra de ações",
      reaction: { event_date: "2026-10-20", car_1: 0.021, car_5: 0.034, car_20: 0.05, confounded: false },
      typical_20: 0.012,
    },
  ],
  unread_count: 0,
  category_counts: { "Fato Relevante": 1 },
  companies: 1,
  unmapped: [],
};

const study = {
  status: "OK",
  as_of: "2026-10-25",
  events: 5400,
  confounded: 310,
  classes: [
    {
      event_class: "BUYBACK",
      label: "Recompra de ações",
      events: 420,
      horizons: [
        { horizon: 1, events: 420, mean: 0.01, effect: 0.009, effect_sd: 0.002, sign_probability: 0.99 },
        { horizon: 5, events: 418, mean: 0.012, effect: 0.011, effect_sd: 0.003, sign_probability: 0.98 },
        { horizon: 20, events: 410, mean: 0.014, effect: 0.012, effect_sd: 0.006, sign_probability: 0.95 },
      ],
      volatility_ratio: 1.08,
    },
  ],
};

describe("Event study on the relevant-facts page (Phase 42.4)", () => {
  it("shows each event's kind and reaction, and what usually follows each kind", async () => {
    mockApi([
      { path: "/disclosures/event-study", reply: study },
      { path: "/disclosures", reply: feed },
    ]);
    renderAt("/disclosures");
    expect(await screen.findByText(/Reação além do mercado: \+2,1% no dia, \+3,4% em 5/, undefined, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/costuma render \+1,2% em 20 pregões/)).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Estudo de eventos" }, { timeout: 5000 });
    expect(within(table).getByText("Recompra de ações")).toBeInTheDocument();
    expect(within(table).getByText("1,08×")).toBeInTheDocument();
    expect(within(table).getAllByText("claro")).toHaveLength(3);
  });

  it("leaves the study out until it is computed", async () => {
    mockApi([
      { path: "/disclosures/event-study", reply: { status: "NOT_COMPUTED", events: 0, confounded: 0, classes: [] } },
      { path: "/disclosures", reply: { ...feed, items: [] } },
    ]);
    renderAt("/disclosures");
    expect(await screen.findByText("Comunicados à CVM", undefined, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Estudo de eventos" })).not.toBeInTheDocument();
  });
});
