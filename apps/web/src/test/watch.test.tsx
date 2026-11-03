/** Phase 48.R6: Acompanhar (alert rules, theses), the thesis chapter and the "why" of a
 *  contribution line. */

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AlertRuleDTO, AssetNoteDTO } from "../api/types";
import { thresholdFor } from "../features/watchlist/WatchlistPage";
import { thesisLead } from "../features/instrument/Thesis";
import { analysis, report, savedPlan, trackedInstrument } from "./fixtures";
import { mockApi } from "./mockApi";
import { renderAt } from "./render";

const rule: AlertRuleDTO = {
  id: 1,
  ticker: "PETR4",
  metric: "PRICE",
  operator: "BELOW",
  threshold: 40,
  is_active: true,
  description: "Preço de PETR4 abaixo de R$ 40,00",
  current_value: 38.5,
  triggered: true,
};

function note(overrides: Partial<AssetNoteDTO> = {}): AssetNoteDTO {
  return {
    id: 1,
    asset_id: 1,
    ticker: "WEGE3",
    written_on: "2026-05-01",
    text: "Compro pela margem; revisar no balanço",
    review_at: "2026-11-01",
    due: true,
    ...overrides,
  };
}

describe("alert rules", () => {
  it("sends the dividend yield as a fraction and rejects invalid limits", () => {
    expect(thresholdFor("DIVIDEND_YIELD", "8")).toBeCloseTo(0.08);
    expect(thresholdFor("PRICE", "30,50")).toBe(30.5);
    expect(thresholdFor("PRICE", "")).toBeNull();
    expect(thresholdFor("PRICE", "-1")).toBeNull();
  });

  it("creates, shows, pauses and deletes a rule", async () => {
    const { calls } = mockApi([
      { path: "/alert-rules", reply: [rule, { ...rule, id: 2, is_active: false, triggered: false, description: "P/VP de ITSA4 abaixo de 1,00", metric: "PRICE_TO_BOOK", current_value: 1.4 }] },
      { method: "POST", path: "/alert-rules", reply: { status: 201, json: rule } },
      { method: "PUT", path: "/alert-rules/1", reply: { ...rule, is_active: false, triggered: false } },
      { method: "DELETE", path: "/alert-rules/1", reply: { status: 204 } },
    ]);
    renderAt("/acompanhar?tab=alerts");

    const table = await screen.findByRole("table", { name: "Regras de alerta" });
    const [first, second] = within(table).getAllByRole("row").slice(1);
    expect(first).toHaveTextContent("Preço de PETR4 abaixo de R$ 40,00");
    expect(first).toHaveTextContent("R$ 38,50");
    expect(first).toHaveTextContent("Disparou");
    expect(second).toHaveTextContent("Pausada");
    expect(within(first).getByRole("link", { name: /PETR4/ })).toHaveAttribute("href", "/ativo/PETR4");

    const form = screen.getByRole("form", { name: "Nova regra de alerta" });
    fireEvent.change(within(form).getByLabelText("Código"), { target: { value: "vale3" } });
    fireEvent.change(within(form).getByLabelText("Indicador"), { target: { value: "DIVIDEND_YIELD" } });
    fireEvent.change(within(form).getByLabelText("Condição"), { target: { value: "ABOVE" } });
    fireEvent.change(within(form).getByLabelText("Limite"), { target: { value: "9" } });
    fireEvent.click(within(form).getByRole("button", { name: "Criar regra" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const body = calls.find((c) => c.method === "POST")?.body as { ticker: string; threshold: number; metric: string };
    expect(body.ticker).toBe("VALE3");
    expect(body.metric).toBe("DIVIDEND_YIELD");
    expect(body.threshold).toBeCloseTo(0.09);

    fireEvent.click(within(first).getByRole("button", { name: "Pausar" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ is_active: false }));
    fireEvent.click(within(first).getByRole("button", { name: /Apagar a regra/ }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("asks for the code and a valid limit", async () => {
    const { calls } = mockApi([{ path: "/alert-rules", reply: [] }]);
    renderAt("/acompanhar?tab=alerts");
    fireEvent.click(await screen.findByRole("button", { name: "Criar regra" }));
    expect(screen.getByText("Informe o código e um limite válido.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });
});

describe("theses", () => {
  it("summarizes the notes of an asset", () => {
    expect(thesisLead([])).toMatch(/Ainda sem tese/);
    expect(thesisLead([note()])).toBe("1 nota(s) pedem revisão.");
    expect(thesisLead([note({ due: false, review_at: "2027-01-10" })])).toBe("1 nota(s); a próxima revisão é em 10/01/2027.");
  });

  it("lists every thesis, the due ones flagged, in Acompanhar", async () => {
    mockApi([{ path: "/notes", reply: [note(), note({ id: 2, ticker: "ITSA4", due: false, review_at: "2027-01-10", text: "Holding barata" })] }]);
    renderAt("/acompanhar?tab=theses");
    const list = await screen.findByRole("list", { name: "Teses" });
    const items = within(list).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Revisar (desde 01/11/2026)");
    expect(within(items[0]).getByRole("link", { name: "WEGE3" })).toHaveAttribute("href", "/ativo/WEGE3?capitulo=tese");
    expect(items[1]).toHaveTextContent("Revisar em 10/01/2027");
  });

  it("writes a note in the thesis chapter of the asset", async () => {
    let saved = false;
    const { calls } = mockApi([
      trackedInstrument(),
      { path: "/assets/1/analysis", reply: analysis() },
      { path: "/assets/1/notes", reply: () => (saved ? [note({ due: false, review_at: "2027-01-10" })] : []) },
      {
        method: "POST",
        path: "/assets/1/notes",
        reply: () => {
          saved = true;
          return { status: 201, json: note() };
        },
      },
    ]);
    renderAt("/ativo/WEGE3?capitulo=tese");

    const chapter = await screen.findByRole("region", { name: "Minha tese" });
    await waitFor(() => expect(chapter).toHaveTextContent("Ainda sem tese"));
    fireEvent.change(within(chapter).getByLabelText("Nota da tese"), { target: { value: "Compro pela margem" } });
    fireEvent.change(within(chapter).getByLabelText("Revisar em"), { target: { value: "2027-01-10" } });
    fireEvent.click(within(chapter).getByRole("button", { name: "Guardar nota" }));

    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ text: "Compro pela margem", review_at: "2027-01-10" }));
    expect(await within(chapter).findByText("Revisar em 10/01/2027")).toBeInTheDocument();
  });
});

describe("Aportar with the why", () => {
  it("opens the lenses of a line only when asked", async () => {
    const { calls } = mockApi([
      { path: "/contributions/7", reply: savedPlan() },
      { path: "/portfolio/consolidated", reply: report() },
      { path: "/accounts", reply: [] },
      trackedInstrument(3, {
        lenses: {
          as_of: "2026-11-01",
          source: "PORTFOLIO",
          sector: "Imobiliário",
          items: [{ lens: "INCOME", normalized: 0.8, confidence: 0.9, note: "renda acima do setor" }],
        },
      }),
    ]);
    renderAt("/aportar/7");
    const button = await screen.findByRole("button", { name: "Ver as lentes de HGLG11" });
    expect(calls.some((c) => c.path.startsWith("/instruments/"))).toBe(false);
    fireEvent.click(button);
    expect(await screen.findByText("Ponto forte: Renda (80% da escala) — renda acima do setor.")).toBeInTheDocument();
  });

  it("points to the position check once the plan is confirmed", async () => {
    mockApi([
      { path: "/contributions/7", reply: savedPlan({ status: "CONFIRMED", confirmed_at: "2026-11-02T12:00:00Z", transaction_ids: [1] }) },
      { path: "/portfolio/consolidated", reply: report() },
      { path: "/accounts", reply: [] },
    ]);
    renderAt("/aportar/7");
    expect(await screen.findByRole("link", { name: "Carteira › Conferir" })).toHaveAttribute("href", "/carteira/conferir");
    const steps = screen.getByRole("list", { name: "Etapas do aporte" });
    expect(within(steps).getByText("Conferir").closest("li")).toHaveAttribute("aria-current", "step");
  });
});
