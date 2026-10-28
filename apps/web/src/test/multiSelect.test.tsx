import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { MultiSelect, multiSelectSummary, type MultiSelectOption } from "../components/MultiSelect";

type Fruit = "A" | "B" | "C";
const OPTIONS: MultiSelectOption<Fruit>[] = [
  { value: "A", label: "Abacaxi" },
  { value: "B", label: "Banana" },
  { value: "C", label: "Caju" },
];

function Harness({ initial = [], onChange }: Readonly<{ initial?: Fruit[]; onChange?: (v: Fruit[]) => void }>) {
  const [value, setValue] = useState<Fruit[]>(initial);
  return (
    <div>
      <label htmlFor="fruits">Frutas</label>
      <MultiSelect
        id="fruits"
        options={OPTIONS}
        value={value}
        onChange={(next) => {
          setValue(next);
          onChange?.(next);
        }}
      />
      <p>fora</p>
    </div>
  );
}

describe("multiSelectSummary", () => {
  it("shows the placeholder, the labels while they fit, then a count", () => {
    expect(multiSelectSummary(OPTIONS, [], "Todos")).toBe("Todos");
    expect(multiSelectSummary(OPTIONS, ["B", "A"], "Todos")).toBe("Abacaxi, Banana");
    expect(multiSelectSummary(OPTIONS, ["A", "B", "C"], "Todos")).toBe("3 selecionados");
  });
});

describe("MultiSelect", () => {
  it("is labelled by its <label> and opens a list of checkboxes", () => {
    render(<Harness />);
    const trigger = screen.getByLabelText("Frutas");
    expect(trigger).toHaveTextContent("Todos");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
  });

  it("toggles several options and clears them", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.click(screen.getByLabelText("Frutas"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Abacaxi" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Caju" }));
    expect(onChange).toHaveBeenLastCalledWith(["A", "C"]);
    expect(screen.getByLabelText("Frutas")).toHaveTextContent("Abacaxi, Caju");
    fireEvent.click(screen.getByRole("checkbox", { name: "Abacaxi" }));
    expect(onChange).toHaveBeenLastCalledWith(["C"]);
    fireEvent.click(screen.getByRole("button", { name: "Limpar seleção" }));
    expect(onChange).toHaveBeenLastCalledWith([]);
    expect(screen.queryByRole("button", { name: "Limpar seleção" })).not.toBeInTheDocument();
  });

  it("closes on Escape (returning focus) and on a click outside", () => {
    render(<Harness initial={["B"]} />);
    const trigger = screen.getByLabelText("Frutas");
    fireEvent.click(trigger);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    fireEvent.click(trigger);
    fireEvent.mouseDown(screen.getByRole("checkbox", { name: "Banana" }));
    expect(screen.getByRole("checkbox", { name: "Banana" })).toBeChecked();
    fireEvent.mouseDown(screen.getByText("fora"));
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});
