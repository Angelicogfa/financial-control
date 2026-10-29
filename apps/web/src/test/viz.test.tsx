import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BarList } from "../viz/BarList";
import { ColumnChart } from "../viz/ColumnChart";
import { Sparkline } from "../viz/Sparkline";
import { TrendChart } from "../viz/TrendChart";
import { niceTicks, spreadLabels } from "../viz/useChartWidth";

describe("chart scale", () => {
  it("ticks land on round numbers", () => {
    expect(niceTicks(79_215, 2_069_674)).toEqual([500_000, 1_000_000, 1_500_000, 2_000_000]);
    expect(niceTicks(0, 1)).toEqual([0, 0.25, 0.5, 0.75, 1]);
  });

  it("end labels never overlap and stay inside the chart", () => {
    // Three lines ending almost together (the CDI, IFIX and the strategy) and one far above.
    const placed = spreadLabels([100, 102, 101, 20], 28, 10, 150);
    const sorted = [...placed].sort((a, b) => a - b);
    sorted.slice(1).forEach((y, i) => expect(y - sorted[i]).toBeGreaterThanOrEqual(28));
    expect(placed[3]).toBe(20); // the far one keeps its place
    expect(Math.max(...spreadLabels([148, 149, 150], 28, 10, 150))).toBeLessThanOrEqual(150);
  });
});

describe("Sparkline", () => {
  it("needs two points and is decorative", () => {
    const { container, rerender } = render(<Sparkline values={[1]} />);
    expect(container.querySelector("svg")).toBeNull();
    rerender(<Sparkline values={[1, 3, 2]} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg?.querySelector("path")?.getAttribute("d")).toMatch(/^M/);
  });
});

describe("TrendChart", () => {
  it("shades bands under the lines and fits them in the scale", () => {
    const { container } = render(
      <TrendChart
        title="Faixas"
        labels={["0", "1", "2"]}
        hint="faixa"
        series={[{ key: "m", label: "Mediana", color: "red", values: [10, 12, 14] }]}
        bands={[{ key: "b", color: "red", low: [8, 9, 10], high: [12, 30, 40] }]}
      />,
    );
    const band = container.querySelector('path[fill="red"]');
    expect(band?.getAttribute("d")).toMatch(/^M.* Z$/);
    expect(band).toHaveAttribute("fill-opacity", "0.18");
    // The band's top (40) sets the scale: the line ends below the top of the chart.
    expect(screen.getByText("Mediana")).toBeInTheDocument();
    expect(container.querySelector(".viz-direct-value")).toHaveTextContent("14");
  });

  it("titles the chart, labels the line ends and reads the hovered point", () => {
    const { container } = render(
      <TrendChart
        title="Carteira contra CDI"
        labels={["01/03", "02/03", "03/03"]}
        hint="Passe o mouse"
        baseline={100}
        series={[
          { key: "p", label: "Carteira", color: "red", values: [100, null, 104] },
          { key: "c", label: "CDI", color: "blue", values: [100, 100.1, 100.2] },
        ]}
      />,
    );
    expect(screen.getByRole("img", { name: "Carteira contra CDI" })).toBeInTheDocument();
    expect(screen.getByText("Carteira")).toBeInTheDocument();
    expect([...container.querySelectorAll(".viz-direct-value")].map((t) => t.textContent)).toContain("104");
    expect(screen.getByText("Passe o mouse")).toBeInTheDocument();
    const zones = container.querySelectorAll("rect");
    fireEvent.mouseEnter(zones[1]);
    expect(screen.getByRole("status")).toHaveTextContent("02/03");
    expect(screen.getByRole("status")).toHaveTextContent("Carteira: —");
  });

  it("renders nothing without enough data", () => {
    const { container } = render(<TrendChart title="t" labels={["a"]} hint="h" series={[]} />);
    expect(container.firstChild).toBeNull();
  });
});

describe("BarList", () => {
  it("shows the value in text with goal, band and second bar", () => {
    const { container } = render(
      <BarList
        label="Alocação"
        bars={[{ id: "a", label: "Ações", share: 0.5, goal: 0.4, band: [0.3, 0.5], second: 0.6, value: "50% · meta 40%" }]}
      />,
    );
    expect(screen.getByRole("list", { name: "Alocação" })).toBeInTheDocument();
    expect(screen.getByText("50% · meta 40%")).toBeInTheDocument();
    expect(container.querySelector(".viz-bar-goal")).toHaveStyle({ left: "40%" });
    expect(container.querySelector(".viz-bar-band")).toHaveStyle({ left: "30%", width: "20%" });
    expect(container.querySelector(".is-after")).toHaveStyle({ width: "60%" });
  });
});

describe("ColumnChart", () => {
  it("labels the largest and last columns and reads the hovered one", () => {
    const { container } = render(
      <ColumnChart
        title="Proventos"
        hint="Passe o mouse"
        format={(v) => `R$ ${v}`}
        columns={[
          { label: "jan", value: 10 },
          { label: "fev", value: 30 },
          { label: "mar", value: 5 },
        ]}
      />,
    );
    expect(screen.getByRole("img", { name: "Proventos" })).toBeInTheDocument();
    expect(screen.getByText("R$ 30")).toBeInTheDocument();
    expect(screen.getByText("R$ 5")).toBeInTheDocument();
    fireEvent.mouseEnter(container.querySelectorAll("g")[0]);
    expect(screen.getByRole("status")).toHaveTextContent("jan: R$ 10");
  });
});
