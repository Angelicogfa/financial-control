import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AssetPriceHistoryDTO, SimulationResultDTO } from "../api/types";
import { KpiGrid, Lead, Notes, Section, Segmented } from "../components/Section";
import { PriceHistory } from "../pages/asset/PriceHistory";
import { pastStory } from "../pages/tools/SimulationPage";
import { plural } from "../utils/format";
import { mockApi, type Call } from "./mockApi";

afterEach(() => vi.unstubAllGlobals());

describe("plural", () => {
  it("never writes (s)", () => {
    expect(plural(1, "modelo passou", "modelos passaram")).toBe("1 modelo passou");
    expect(plural(3, "modelo passou", "modelos passaram")).toBe("3 modelos passaram");
    expect(plural(5636, "não lido", "não lidos")).toBe("5.636 não lidos");
  });
});

describe("report building blocks", () => {
  it("a section has a heading, a subtitle and actions", () => {
    render(
      <Section title="Preço" subtitle="Em 12 meses" actions={<button type="button">Ação</button>}>
        <p>corpo</p>
      </Section>,
    );
    expect(screen.getByRole("heading", { name: "Preço" })).toBeInTheDocument();
    expect(screen.getByText("Em 12 meses")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ação" })).toBeInTheDocument();
    expect(screen.getByText("corpo")).toBeInTheDocument();
  });

  it("the lead and the indicators carry their tone", () => {
    const { container } = render(
      <>
        <Lead tone="negative">
          <p>Abaixo do CDI.</p>
        </Lead>
        <KpiGrid items={[{ label: "Ganho", value: "R$ 10", tone: "positive", note: "sobre o aportado" }]} />
      </>,
    );
    expect(screen.getByRole("note", { name: "Em resumo" })).toHaveClass("is-negative");
    expect(container.querySelector(".app-kpi.is-positive")).toHaveTextContent("GanhoR$ 10sobre o aportado");
  });

  it("notes stack one per line and fold after three", () => {
    render(<Notes items={["a", "b", "c", "d", "e"]} label="Avisos" />);
    const notes = screen.getByRole("complementary", { name: "Avisos" });
    expect(within(notes).getAllByRole("listitem")).toHaveLength(3);
    fireEvent.click(within(notes).getByRole("button", { name: "Mostrar mais 2" }));
    expect(within(notes).getAllByRole("listitem")).toHaveLength(5);
    fireEvent.click(within(notes).getByRole("button", { name: "Mostrar menos" }));
    expect(within(notes).getAllByRole("listitem")).toHaveLength(3);
  });

  it("renders no notes without items", () => {
    const { container } = render(<Notes items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("the segmented control marks the chosen option", () => {
    const onChange = vi.fn();
    render(<Segmented options={[["a", "A"], ["b", "B"]]} value="a" onChange={onChange} label="Escolha" />);
    expect(screen.getByRole("button", { name: "A" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "B" }));
    expect(onChange).toHaveBeenCalledWith("b");
  });
});

function series(key: string, label: string, final: number, byClass: Record<string, number>, cash = 0): SimulationResultDTO {
  return {
    key,
    label,
    summary: {
      final_value: final,
      contributed: 2000,
      gain: final - 2000,
      money_weighted_return: 0.1,
      time_weighted_return: 0.1,
      annual_twr: 0.1,
      volatility: 0.1,
      max_drawdown: -0.2,
      trades: 2,
      fees: 1,
    },
    points: [
      { day: "2020-01-31", contribution: 1000, contributed: 1000, market_value: 1000, cash: 0, fees: 0 },
      { day: "2020-02-28", contribution: 1000, contributed: 2000, market_value: final, cash, fees: 1, by_class: byClass },
    ],
  };
}

describe("pastStory", () => {
  it("compares the strategy with the same flow in the CDI and names the best reference", () => {
    const story = pastStory([
      series("strategy", "Estratégia", 2100, { ACOES: 2100 }),
      series("benchmark:CDI", "CDI", 2200, {}),
      series("benchmark:IBOV", "Ibovespa", 2500, {}),
    ]);
    expect(story.tone).toBe("negative");
    expect(story.lines[0]).toMatch(/chegou a R\$\s2\.100,00, R\$\s100,00 abaixo do mesmo fluxo aplicado no CDI/);
    expect(story.lines[1]).toMatch(/^TIR de 10,00% a\.a\., queda máxima de -20,0%, a melhor referência foi Ibovespa/);
  });

  it("says why when almost everything ended in cash", () => {
    const story = pastStory([series("strategy", "Estratégia", 2100, { CAIXA: 2050 }, 50), series("benchmark:CDI", "CDI", 2000, {})]);
    expect(story.tone).toBe("caution");
    expect(story.cashShare).toBeCloseTo(1);
    expect(story.lines[2]).toMatch(/terminou em Caixa.*elegibilidade/);
  });
});

function prices(range: AssetPriceHistoryDTO["range"], closes: number[]): AssetPriceHistoryDTO {
  return {
    range,
    points: closes.map((close, i) => ({ date: `2021-01-${String(i + 1).padStart(2, "0")}`, close })),
    change: closes[closes.length - 1] / closes[0] - 1,
    high: { date: "2021-01-02", price: Math.max(...closes) },
    low: { date: "2021-01-01", price: Math.min(...closes) },
    dropped_spikes: range === "max" ? 1 : 0,
  };
}

describe("PriceHistory", () => {
  it("loads the chosen period and tells the change, the high and the low", async () => {
    const { calls } = mockApi([
      { path: "/assets/7/prices", reply: (call: Call) => prices(call.query.get("range") as AssetPriceHistoryDTO["range"], call.query.get("range") === "5y" ? [10, 20, 15] : [10, 12, 11]) },
    ]);
    render(<PriceHistory assetId={7} ticker="WEGE3" currency="BRL" fallback={[]} />);
    expect(await screen.findByText(/Em 12 meses, WEGE3/)).toHaveTextContent("Em 12 meses, WEGE3 subiu 10,0%.");
    expect(screen.getByRole("button", { name: "1 ano" })).toHaveAttribute("aria-pressed", "true");
    expect(calls[0].query.get("range")).toBe("1y");

    fireEvent.click(screen.getByRole("button", { name: "5 anos" }));
    expect(await screen.findByText(/Em 5 anos, WEGE3/)).toHaveTextContent("subiu 50,0%");
    expect(screen.getByLabelText("Resumo do período")).toHaveTextContent(/Máxima R\$\s20,00 em 02\/01\/2021/);
    expect(calls.map((c) => c.query.get("range"))).toEqual(["1y", "5y"]);

    fireEvent.click(screen.getByRole("button", { name: "Tudo" }));
    expect(await screen.findByText(/Cotações isoladas erradas/)).toBeInTheDocument();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["6 meses", "1 ano", "2 anos", "5 anos", "Tudo"]);
  });

  it("shows the one-year series of the analysis when the API fails", async () => {
    mockApi([{ path: "/assets/7/prices", reply: { status: 500, json: { detail: "fora" } } }]);
    render(
      <PriceHistory
        assetId={7}
        ticker="WEGE3"
        currency="BRL"
        fallback={[
          { date: "2021-01-01", close: 10 },
          { date: "2021-01-02", close: 11 },
        ]}
      />,
    );
    expect(await screen.findByRole("img", { name: /Preço de WEGE3: 1 ano/ })).toBeInTheDocument();
  });
});
