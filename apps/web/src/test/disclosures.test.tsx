import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CvmDocumentDTO, DisclosureFeedDTO } from "../api/types";
import { DisclosureFeed } from "../pages/disclosures/DisclosureFeed";
import { optionLabels, pick } from "./combobox";
import { mockApi, type Call } from "./mockApi";

const doc = (id: number, category: string, overrides: Partial<CvmDocumentDTO> = {}): CvmDocumentDTO => ({
  id,
  protocol: `P${id}`,
  tickers: ["WEGE3"],
  company_name: "WEG S.A.",
  category,
  subject: `Assunto ${id}`,
  delivery_date: "2026-10-27",
  link: `https://www.rad.cvm.gov.br/doc/${id}`,
  read: false,
  ...overrides,
});

function feed(overrides: Partial<DisclosureFeedDTO> = {}): DisclosureFeedDTO {
  return {
    items: [doc(1, "Fato Relevante", { subject: "Aquisição de controle" }), doc(2, "Comunicado ao Mercado", { read: true })],
    unread_count: 1,
    category_counts: { "Fato Relevante": 1, "Comunicado ao Mercado": 1, Assembleia: 3 },
    companies: 2,
    unmapped: ["ITSA4"],
    note: "FIIs e ETFs não são companhias abertas.",
    ...overrides,
  };
}

describe("DisclosureFeed", () => {
  it("lists the documents, filters by category and marks them as read", async () => {
    let read = false;
    const { calls } = mockApi([
      { path: "/disclosures", reply: (call: Call) => (call.query.get("category") ? feed({ items: [feed().items![0]] }) : feed()) },
      {
        method: "POST",
        path: "/disclosures/read",
        reply: () => {
          read = true;
          return { updated: 1 };
        },
      },
    ]);
    render(<DisclosureFeed />);
    const list = await screen.findByRole("list", { name: "Documentos da CVM" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText("Aquisição de controle")).toBeInTheDocument();
    expect(within(items[0]).getByText("Novo")).toBeInTheDocument();
    expect(within(items[0]).getByRole("link", { name: "Abrir o documento na CVM" })).toHaveAttribute(
      "href",
      "https://www.rad.cvm.gov.br/doc/1",
    );
    expect(within(items[1]).queryByRole("button", { name: "Marcar como lido" })).toBeNull();
    expect(screen.getByText("1 não lido")).toBeInTheDocument();
    expect(screen.getByText(/Sem CNPJ no cadastro da CVM ainda: ITSA4/)).toBeInTheDocument();
    expect(screen.getByText("FIIs e ETFs não são companhias abertas.")).toBeInTheDocument();
    expect(optionLabels(screen.getByLabelText("Categoria"))).toContain("Assembleia (3)");

    pick(screen.getByLabelText("Categoria"), /^Fato Relevante/);
    await waitFor(() => expect(calls.some((c) => c.query.get("category") === "Fato Relevante")).toBe(true));

    fireEvent.click(await screen.findByRole("button", { name: "Marcar como lido" }));
    await waitFor(() => expect(read).toBe(true));
    const body = [...calls].reverse().find((c) => c.method === "POST")?.body;
    expect(body).toEqual({ ids: [1], asset_id: null });
  });

  it("marks everything of an asset as read and explains an empty feed", async () => {
    const { calls } = mockApi([
      { path: "/disclosures", reply: feed({ items: [], unread_count: 0, unmapped: [], note: null }) },
    ]);
    render(<DisclosureFeed assetId={7} />);
    expect(await screen.findByText("Nenhum documento")).toBeInTheDocument();
    expect(screen.getByText(/rode-a já em Dados de mercado/)).toBeInTheDocument();
    expect(calls[0].query.get("asset_id")).toBe("7");
  });

  it("sends mark-all with the asset scope", async () => {
    const { calls } = mockApi([
      { path: "/disclosures", reply: feed() },
      { method: "POST", path: "/disclosures/read", reply: { updated: 1 } },
    ]);
    render(<DisclosureFeed assetId={7} />);
    fireEvent.click(await screen.findByRole("button", { name: "Marcar todos como lidos" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ all: true, asset_id: 7 });
  });
});
