import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Hint } from "../components/Hint";

describe("Hint", () => {
  it("renders the trigger button with the accessible label", () => {
    render(<Hint about="Taxa">Texto de ajuda</Hint>);
    const button = screen.getByRole("button", { name: "Ajuda sobre Taxa" });
    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("renders generic label when about is omitted", () => {
    render(<Hint>Ajuda geral</Hint>);
    const button = screen.getByRole("button", { name: "Ajuda" });
    expect(button).toBeInTheDocument();
  });

  it("toggles the tooltip on click", () => {
    render(<Hint about="Taxa">Texto de ajuda</Hint>);
    const button = screen.getByRole("button", { name: "Ajuda sobre Taxa" });
    const tooltip = screen.getByRole("tooltip");

    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(tooltip).toHaveStyle({ position: "absolute" });

    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("opens on mouse enter and closes on mouse leave", () => {
    render(<Hint about="Taxa">Texto de ajuda</Hint>);
    const button = screen.getByRole("button", { name: "Ajuda sobre Taxa" });

    fireEvent.mouseEnter(button);
    expect(button).toHaveAttribute("aria-expanded", "true");

    fireEvent.mouseLeave(button);
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("opens on focus and closes on blur", () => {
    render(<Hint about="Taxa">Texto de ajuda</Hint>);
    const button = screen.getByRole("button", { name: "Ajuda sobre Taxa" });

    fireEvent.focus(button);
    expect(button).toHaveAttribute("aria-expanded", "true");

    fireEvent.blur(button);
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("closes on Escape key press", () => {
    render(<Hint about="Taxa">Texto de ajuda</Hint>);
    const button = screen.getByRole("button", { name: "Ajuda sobre Taxa" });

    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(button).toHaveAttribute("aria-expanded", "false");
  });
});
