import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

  it("slides the bubble left when it would leave the viewport", () => {
    render(<Hint about="Payout">Texto de ajuda</Hint>);
    const tooltip = screen.getByRole("tooltip");
    Object.defineProperty(document.documentElement, "clientWidth", { configurable: true, value: 1000 });
    const rect = vi
      .spyOn(tooltip, "getBoundingClientRect")
      .mockReturnValue({ left: 800, right: 1080, top: 0, bottom: 40, width: 280, height: 40, x: 800, y: 0, toJSON: () => ({}) });

    fireEvent.click(screen.getByRole("button", { name: "Ajuda sobre Payout" }));
    // 1080 - (1000 - 8) = 88 px past the edge.
    expect(tooltip).toHaveStyle({ left: "-88px" });

    rect.mockRestore();
    Reflect.deleteProperty(document.documentElement, "clientWidth");
  });
});
