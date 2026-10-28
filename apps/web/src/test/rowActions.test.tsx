import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { IconButton, IconLink } from "../components/RowActions";
import { EditIcon, TrashIcon } from "../layout/icons";

describe("row actions", () => {
  it("renders an icon link named and titled by its label", () => {
    render(
      <MemoryRouter>
        <IconLink to="/ledger/trades/5/edit" label="Editar" icon={<EditIcon />} />
      </MemoryRouter>,
    );
    const link = screen.getByRole("link", { name: "Editar" });
    expect(link).toHaveAttribute("href", "/ledger/trades/5/edit");
    expect(link).toHaveAttribute("title", "Editar");
    expect(link).toHaveClass("app-icon-button");
  });

  it("runs the action on click and marks danger actions", () => {
    const onClick = vi.fn();
    render(<IconButton label="Excluir" icon={<TrashIcon />} danger onClick={onClick} />);
    const button = screen.getByRole("button", { name: "Excluir" });
    expect(button).toHaveClass("is-danger");
    expect(button).toHaveAttribute("title", "Excluir");
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("shows the busy label and blocks clicks while running", () => {
    const onClick = vi.fn();
    render(<IconButton label="Excluir" busyLabel="Excluindo…" icon={<TrashIcon />} busy onClick={onClick} />);
    const button = screen.getByRole("button", { name: "Excluindo…" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });
});
