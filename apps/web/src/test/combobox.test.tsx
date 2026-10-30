import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  Combobox,
  codeOptions,
  filterOptions,
  MAX_RENDERED_OPTIONS,
  normalizeSearch,
  resolveTyped,
  type ComboboxOption,
} from "../components/Combobox";

const ASSETS: ComboboxOption<number | "">[] = [
  { value: 1, label: "ITUB4 — Itaú Unibanco" },
  { value: 2, label: "ITSA4 — Itaúsa" },
  { value: 3, label: "03BK11 — Galapagos Teva Tesouro IPCA 3 anos" },
  { value: 4, label: "PETR4 — Petrobras" },
];

function Harness({
  initial = "",
  options = ASSETS,
  onChange,
  required = false,
}: Readonly<{
  initial?: number | "";
  options?: ComboboxOption<number | "">[];
  onChange?: (v: number | "") => void;
  required?: boolean;
}>) {
  const [value, setValue] = useState<number | "">(initial);
  return (
    <form onSubmit={(e) => e.preventDefault()}>
      <label htmlFor="asset">Ativo</label>
      <Combobox<number | "">
        id="asset"
        value={value}
        options={options}
        placeholder="Escolha o ativo"
        required={required}
        onChange={(next) => {
          setValue(next);
          onChange?.(next);
        }}
      />
      <button type="button">fora</button>
    </form>
  );
}

const field = () => screen.getByLabelText("Ativo") as HTMLInputElement;
const shown = () => screen.queryAllByRole("option").map((o) => o.textContent);

describe("search helpers", () => {
  it("ignores case and accents", () => {
    expect(normalizeSearch("  Itaúsa ")).toBe("itausa");
  });

  it("keeps options holding every typed word, in any order", () => {
    expect(filterOptions(ASSETS, "itau").map((o) => o.value)).toEqual([1, 2]);
    expect(filterOptions(ASSETS, "ipca teva").map((o) => o.value)).toEqual([3]);
    expect(filterOptions(ASSETS, "   ")).toEqual(ASSETS);
    expect(filterOptions(ASSETS, "xyz")).toEqual([]);
  });

  it("settles typed text on an exact label or a single match, else on nothing", () => {
    expect(resolveTyped(ASSETS, "petr")?.value).toBe(4);
    expect(resolveTyped(ASSETS, "itsa4 — itausa")?.value).toBe(2);
    expect(resolveTyped(ASSETS, "itau")).toBeNull();
    expect(resolveTyped(ASSETS, "nada")).toBeNull();
    expect(resolveTyped(ASSETS, "")).toBeNull();
    expect(resolveTyped([{ value: "", label: "Todos" }, ...ASSETS], "")?.value).toBe("");
  });

  it("builds options from codes and their labels", () => {
    expect(codeOptions(["A", "B"], { A: "Alfa" })).toEqual([
      { value: "A", label: "Alfa" },
      { value: "B", label: "B" },
    ]);
  });
});

describe("Combobox", () => {
  it("is labelled by its <label>, shows the placeholder and opens on click", () => {
    render(<Harness />);
    expect(field()).toHaveAttribute("role", "combobox");
    expect(field()).toHaveAttribute("placeholder", "Escolha o ativo");
    expect(field()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    fireEvent.click(field());
    expect(field()).toHaveAttribute("aria-expanded", "true");
    expect(shown()).toHaveLength(4);
  });

  it("filters while typing and picks with a click", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.change(field(), { target: { value: "itaú" } });
    expect(shown()).toEqual(["ITUB4 — Itaú Unibanco", "ITSA4 — Itaúsa"]);
    fireEvent.click(screen.getByRole("option", { name: "ITSA4 — Itaúsa" }));
    expect(onChange).toHaveBeenCalledWith(2);
    expect(field()).toHaveValue("ITSA4 — Itaúsa");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("moves with the arrows and picks with Enter without submitting the form", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.keyDown(field(), { key: "ArrowDown" });
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    fireEvent.keyDown(field(), { key: "ArrowDown" });
    fireEvent.keyDown(field(), { key: "ArrowDown" });
    fireEvent.keyDown(field(), { key: "ArrowUp" });
    const active = field().getAttribute("aria-activedescendant");
    expect(document.getElementById(active ?? "")).toHaveTextContent("ITSA4 — Itaúsa");
    fireEvent.keyDown(field(), { key: "End" });
    fireEvent.keyDown(field(), { key: "Home" });
    fireEvent.keyDown(field(), { key: "ArrowDown" });
    const enter = fireEvent.keyDown(field(), { key: "Enter" });
    expect(enter).toBe(false);
    expect(onChange).toHaveBeenCalledWith(2);
  });

  it("never keeps a value outside the list: unmatched typing goes back to the choice", () => {
    const onChange = vi.fn();
    render(<Harness initial={4} onChange={onChange} />);
    expect(field()).toHaveValue("PETR4 — Petrobras");
    fireEvent.change(field(), { target: { value: "VALE3" } });
    expect(screen.getByText("Nenhuma opção encontrada")).toBeInTheDocument();
    expect(fireEvent.keyDown(field(), { key: "Enter" })).toBe(false);
    fireEvent.blur(field());
    expect(field()).toHaveValue("PETR4 — Petrobras");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("takes the only match when the field loses focus", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.change(field(), { target: { value: "03bk" } });
    fireEvent.blur(field());
    expect(onChange).toHaveBeenCalledWith(3);
    expect(field()).toHaveValue("03BK11 — Galapagos Teva Tesouro IPCA 3 anos");
  });

  it("gives up the typing on Escape", () => {
    render(<Harness initial={1} />);
    fireEvent.change(field(), { target: { value: "pet" } });
    fireEvent.keyDown(field(), { key: "Escape" });
    expect(field()).toHaveValue("ITUB4 — Itaú Unibanco");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("clearing the text picks the empty option when there is one", () => {
    const onChange = vi.fn();
    render(<Harness initial={1} options={[{ value: "", label: "Todos" }, ...ASSETS]} onChange={onChange} />);
    fireEvent.change(field(), { target: { value: "" } });
    fireEvent.blur(field());
    expect(onChange).toHaveBeenCalledWith("");
    expect(field()).toHaveValue("");
  });

  it("is required while nothing is chosen", () => {
    render(<Harness required />);
    expect(field()).toBeRequired();
    expect(field()).toBeInvalid();
  });

  it("draws a bounded list and asks to refine past it", () => {
    const many = Array.from({ length: MAX_RENDERED_OPTIONS + 50 }, (_, i) => ({ value: i + 1, label: `ATIVO${i + 1}` }));
    render(<Harness options={many} />);
    fireEvent.click(field());
    expect(shown()).toHaveLength(MAX_RENDERED_OPTIONS);
    expect(screen.getByText(`Mostrando ${MAX_RENDERED_OPTIONS} de ${many.length}. Digite para refinar.`)).toBeInTheDocument();
    fireEvent.change(field(), { target: { value: "ativo149" } });
    expect(shown()).toEqual(["ATIVO149"]);
  });

  it("toggles from the chevron and does not reopen inside a wrapping label", () => {
    const onChange = vi.fn();
    render(
      <label>
        Itens
        <Combobox value={10} options={codeOptions([10, 20])} onChange={onChange} />
      </label>,
    );
    const input = screen.getByLabelText("Itens");
    const chevron = input.parentElement?.querySelector(".app-combobox-chevron") as HTMLElement;
    fireEvent.mouseDown(chevron);
    expect(input).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(within(screen.getByRole("listbox")).getByRole("option", { name: "20" }));
    expect(onChange).toHaveBeenCalledWith(20);
    expect(input).toHaveAttribute("aria-expanded", "false");
    fireEvent.mouseDown(chevron);
    fireEvent.mouseDown(chevron);
    expect(input).toHaveAttribute("aria-expanded", "false");
  });

  it("stays shut while disabled and says when options are loading", () => {
    const { rerender } = render(<Combobox label="Conta" value="" options={[]} onChange={vi.fn()} loading />);
    const input = screen.getByRole("combobox", { name: "Conta" });
    expect(input).toHaveAttribute("placeholder", "Carregando…");
    fireEvent.click(input);
    expect(screen.getByText("Carregando…")).toBeInTheDocument();
    rerender(<Combobox label="Conta" value="" options={[]} onChange={vi.fn()} disabled />);
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input).toBeDisabled();
  });
});
