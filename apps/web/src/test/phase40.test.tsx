import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WealthByAccountDTO } from "../api/types";
import { NAV_SECTIONS } from "../layout/navigation";
import { AccountsWealth } from "../pages/home/AccountsWealth";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

afterEach(() => vi.unstubAllGlobals());

function group(key: "B3" | "INTERNATIONAL", value: number, change: number | null) {
  return {
    key,
    label: key === "B3" ? "Bolsa" : "Internacional",
    value_brl: value,
    invested_brl: value,
    pnl_brl: 0,
    change,
  };
}

const wealth: WealthByAccountDTO = {
  as_of_date: "2026-10-29",
  total_value_brl: 1740,
  accounts: [
    {
      account_id: 1,
      name: "XP",
      institution: "XP Investimentos",
      value_brl: 1290,
      invested_brl: 1100,
      pnl_brl: 190,
      change: 0.1727,
      share: 0.7414,
      groups: [group("B3", 1200, 0.2), group("INTERNATIONAL", 90, -0.1)],
    },
    {
      account_id: 2,
      name: "Avenue",
      value_brl: 450,
      invested_brl: 500,
      pnl_brl: -50,
      change: -0.1,
      share: 0.2586,
      groups: [group("B3", 0, null), group("INTERNATIONAL", 450, -0.1)],
    },
  ],
  groups: [group("B3", 1200, 0.2), group("INTERNATIONAL", 540, -0.1)],
};

describe("wealth by account on the Home", () => {
  it("lists each account split into Bolsa and Internacional with its rise or fall", async () => {
    mockApi([{ path: "/portfolio/by-account", reply: wealth }]);
    render(<AccountsWealth />);
    const table = await screen.findByRole("table", { name: "Patrimônio por conta" });
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent(/XP.*R\$\s1\.200,00.*alta de 20,0%.*R\$\s90,00.*queda de 10,0%.*R\$\s1\.290,00.*74,1%/);
    // An account without Bolsa shows a dash, not a zero.
    expect(within(rows[2]).getAllByRole("cell")[1]).toHaveTextContent("—");
    expect(rows[3]).toHaveTextContent(/Todas as contas.*R\$\s1\.200,00.*R\$\s540,00.*R\$\s1\.740,00.*100%/);
    expect(screen.getByText(/2 contas com posição · a maior é XP, com 74% do total/)).toBeInTheDocument();
  });

  it("shows nothing without accounts with positions", async () => {
    const { calls } = mockApi([{ path: "/portfolio/by-account", reply: { ...wealth, accounts: [] } }]);
    const { container } = render(<AccountsWealth />);
    await vi.waitFor(() => expect(calls.length).toBe(1));
    await vi.waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});

describe("relevant facts page", () => {
  it("sits right below the portfolio health in the menu", () => {
    const overview = NAV_SECTIONS[0].items.map((i) => i.to);
    expect(overview.indexOf("/disclosures")).toBe(overview.indexOf("/health") + 1);
  });

  it("shows the CVM feed with its reading notes", async () => {
    mockApi([
      {
        path: "/disclosures",
        reply: { items: [], unread_count: 0, categories: {}, unmapped: [], note: null, last_delivery: null },
      },
    ]);
    renderAt("/disclosures");
    expect(screen.getByRole("heading", { name: "Fatos relevantes" })).toBeInTheDocument();
    expect(await screen.findByRole("complementary", { name: "Como ler este resultado" })).toHaveTextContent(
      /mais de 30 dias/,
    );
  });
});
