import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Pagination } from "../components/Pagination";
import { clampPage, pageCount, paginate, usePagedRows, usePagination } from "../utils/pagination";
import { asset } from "./fixtures";
import { mockApi, type Call } from "./mockApi";
import { renderAt } from "./render";

const last = (calls: Call[], method: string, path: string) =>
  [...calls].reverse().find((c) => c.method === method && c.path === path);

describe("pagination helpers", () => {
  it("counts pages, with one page for an empty list", () => {
    expect(pageCount(0, 10)).toBe(1);
    expect(pageCount(10, 10)).toBe(1);
    expect(pageCount(11, 10)).toBe(2);
  });

  it("clamps the page to the list", () => {
    expect(clampPage(-1, 25, 10)).toBe(0);
    expect(clampPage(2, 25, 10)).toBe(2);
    expect(clampPage(3, 25, 10)).toBe(2);
    expect(clampPage(4, 0, 10)).toBe(0);
  });

  it("slices one page of the list", () => {
    const items = Array.from({ length: 12 }, (_, i) => i + 1);
    expect(paginate(items, 0, 5)).toEqual([1, 2, 3, 4, 5]);
    expect(paginate(items, 2, 5)).toEqual([11, 12]);
    expect(paginate(items, 9, 5)).toEqual([11, 12]);
    expect(paginate([], 0, 5)).toEqual([]);
  });
});

function renderBar(props: Partial<Parameters<typeof Pagination>[0]> = {}) {
  const handlers = { onChange: vi.fn(), onRefresh: vi.fn(), onPageSizeChange: vi.fn() };
  render(<Pagination page={0} pageSize={10} total={25} {...handlers} {...props} />);
  return handlers;
}

describe("pagination bar", () => {
  it("shows the range, the page and disables the way back on the first page", () => {
    const { onChange } = renderBar();
    expect(screen.getByText("1–10 de 25")).toBeInTheDocument();
    expect(screen.getByText("Página 1 de 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Primeira página" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Página anterior" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Próxima página" }));
    expect(onChange).toHaveBeenLastCalledWith(1);
    fireEvent.click(screen.getByRole("button", { name: "Última página" }));
    expect(onChange).toHaveBeenLastCalledWith(2);
  });

  it("disables the way forward on the last page", () => {
    const { onChange } = renderBar({ page: 2 });
    expect(screen.getByText("21–25 de 25")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Próxima página" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Última página" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Página anterior" }));
    expect(onChange).toHaveBeenLastCalledWith(1);
    fireEvent.click(screen.getByRole("button", { name: "Primeira página" }));
    expect(onChange).toHaveBeenLastCalledWith(0);
  });

  it("stays visible with no rows", () => {
    renderBar({ total: 0 });
    expect(screen.getByText("Nenhum registro")).toBeInTheDocument();
    expect(screen.getByText("Página 1 de 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Próxima página" })).toBeDisabled();
  });

  it("changes the page size and keeps a size outside the catalog selected", () => {
    const { onPageSizeChange } = renderBar({ pageSize: 20 });
    const select = screen.getByLabelText("Itens por página");
    expect(select).toHaveValue("20");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["5", "10", "20", "50", "100"]);
    fireEvent.change(select, { target: { value: "50" } });
    expect(onPageSizeChange).toHaveBeenCalledWith(50);
  });

  it("hides the size selector without a handler", () => {
    render(<Pagination page={0} pageSize={10} total={3} onChange={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.queryByLabelText("Itens por página")).not.toBeInTheDocument();
  });

  it("reloads, and is disabled while reloading", () => {
    const { onRefresh } = renderBar();
    fireEvent.click(screen.getByRole("button", { name: "Recarregar" }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("spins while reloading", () => {
    renderBar({ refreshing: true });
    const reload = screen.getByRole("button", { name: "Recarregar" });
    expect(reload).toBeDisabled();
    expect(reload).toHaveClass("app-pagination-refreshing");
  });
});

function PagerProbe() {
  const [search, setSearch] = useState("a");
  const pager = usePagination(search);
  return (
    <>
      <span data-testid="state">
        {pager.page}/{pager.pageSize}
      </span>
      <button type="button" onClick={() => pager.setPage(3)}>
        go
      </button>
      <button type="button" onClick={() => pager.setPageSize(50)}>
        size
      </button>
      <button type="button" onClick={() => setSearch("b")}>
        search
      </button>
    </>
  );
}

function RowsProbe() {
  const [items, setItems] = useState(Array.from({ length: 12 }, (_, i) => i + 1));
  const { rows, pagination } = usePagedRows(items);
  return (
    <>
      <span data-testid="rows">{rows.join(",")}</span>
      <button type="button" onClick={() => setItems((list) => list.slice(0, 10))}>
        shrink
      </button>
      <Pagination {...pagination} onRefresh={() => undefined} />
    </>
  );
}

describe("pagination hooks", () => {
  it("goes back to the first page on a new search or a new page size", () => {
    render(<PagerProbe />);
    expect(screen.getByTestId("state")).toHaveTextContent("0/10");
    fireEvent.click(screen.getByRole("button", { name: "go" }));
    expect(screen.getByTestId("state")).toHaveTextContent("3/10");
    fireEvent.click(screen.getByRole("button", { name: "search" }));
    expect(screen.getByTestId("state")).toHaveTextContent("0/10");
    fireEvent.click(screen.getByRole("button", { name: "go" }));
    fireEvent.click(screen.getByRole("button", { name: "size" }));
    expect(screen.getByTestId("state")).toHaveTextContent("0/50");
  });

  it("pages a list in memory and clamps when it shrinks", () => {
    render(<RowsProbe />);
    expect(screen.getByTestId("rows")).toHaveTextContent("1,2,3,4,5,6,7,8,9,10");
    fireEvent.click(screen.getByRole("button", { name: "Próxima página" }));
    expect(screen.getByTestId("rows")).toHaveTextContent("11,12");
    fireEvent.click(screen.getByRole("button", { name: "shrink" }));
    expect(screen.getByTestId("rows")).toHaveTextContent("1,2,3,4,5,6,7,8,9,10");
    expect(screen.getByText("Página 1 de 1")).toBeInTheDocument();
  });
});

const accounts = [{ id: 1, name: "XP", is_active: true }];
const meta = (page: number, pageSize: number, total: number) => ({
  page,
  page_size: pageSize,
  total_items: total,
  total_pages: Math.ceil(total / pageSize),
  sort_by: "id",
  sort_order: "desc",
});
const trade = (id: number) => ({
  id,
  asset_id: 1,
  ticker: `T${id}`,
  kind: "BUY",
  trade_date: "2026-01-05",
  quantity: 1,
  unit_price: 10,
  fees: 0,
  fx_rate: 1,
  total_brl: 10,
});

describe("paged ledger", () => {
  it("asks the API for one page of trades at a time and starts over on a new filter", async () => {
    const { calls } = mockApi([
      {
        path: "/transactions",
        reply: (call: Call) => {
          const page = Number(call.query.get("page"));
          const size = Number(call.query.get("page_size"));
          const start = (page - 1) * size;
          const items = Array.from({ length: Math.max(0, Math.min(size, 23 - start)) }, (_, i) => trade(start + i + 1));
          return { items, meta: meta(page, size, 23) };
        },
      },
      { path: "/assets", reply: { items: [asset()], meta: meta(1, 200, 1) } },
      { path: "/accounts", reply: accounts },
    ]);
    renderAt("/ledger");
    expect(await screen.findByRole("link", { name: "T1" })).toBeInTheDocument();
    expect(last(calls, "GET", "/transactions")?.query.get("page")).toBe("1");
    expect(last(calls, "GET", "/transactions")?.query.get("page_size")).toBe("10");
    expect(screen.getByText("1–10 de 23")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Última página" }));
    expect(await screen.findByRole("link", { name: "T21" })).toBeInTheDocument();
    expect(last(calls, "GET", "/transactions")?.query.get("page")).toBe("3");
    expect(screen.getByText("21–23 de 23")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Itens por página"), { target: { value: "50" } });
    await waitFor(() => expect(last(calls, "GET", "/transactions")?.query.get("page_size")).toBe("50"));
    expect(last(calls, "GET", "/transactions")?.query.get("page")).toBe("1");
    expect(await screen.findByText("1–23 de 23")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Recarregar" }));
    await waitFor(() => expect(calls.filter((c) => c.path === "/transactions").length).toBe(4));

    await screen.findByRole("option", { name: "WEGE3" });
    fireEvent.change(screen.getByLabelText("Ativo"), { target: { value: "1" } });
    await waitFor(() => expect(last(calls, "GET", "/transactions")?.query.get("asset_id")).toBe("1"));
    expect(last(calls, "GET", "/transactions")?.query.get("page")).toBe("1");
  });

  it("pages corporate events in memory", async () => {
    const events = Array.from({ length: 11 }, (_, i) => ({
      id: i + 1,
      asset_id: 1,
      ticker: `E${i + 1}`,
      kind: "SPLIT",
      ex_date: "2026-01-05",
      factor: 2,
      unit_cost: null,
      imported: false,
    }));
    mockApi([
      { path: "/corporate-events", reply: events },
      { path: "/assets", reply: { items: [asset()], meta: meta(1, 200, 1) } },
      { path: "/accounts", reply: accounts },
    ]);
    renderAt("/ledger?tab=events");
    expect(await screen.findByText("E10")).toBeInTheDocument();
    expect(screen.queryByText("E11")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Próxima página" }));
    expect(screen.getByText("E11")).toBeInTheDocument();
    expect(screen.getByText("11–11 de 11")).toBeInTheDocument();
  });
});

describe("paged research", () => {
  it("asks the API for each page of the screener, reaching every match", async () => {
    const all = Array.from({ length: 2415 }, (_, i) => ({
      ticker: `AAAA${i + 1}`,
      name: `Ativo ${i + 1}`,
      asset_type: "STOCK_BR",
      arca_class: "ACOES",
      close: 10,
    }));
    const { calls } = mockApi([
      {
        path: "/research/screener",
        reply: (call: Call) => {
          const page = Number(call.query.get("page"));
          const size = Number(call.query.get("limit"));
          const results = all.slice((page - 1) * size, page * size);
          return {
            results,
            total: all.length,
            page,
            page_size: size,
            candidates: all.length,
            scanned: results.length,
            truncated: false,
            arca_classes: [],
            catalog_size: all.length,
          };
        },
      },
      { path: "/research/sectors", reply: [] },
    ]);
    const screenerCalls = () => calls.filter((c) => c.path === "/research/screener");
    renderAt("/research");
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    expect(await screen.findByText("AAAA10")).toBeInTheDocument();
    expect(last(calls, "GET", "/research/screener")?.query.get("page")).toBe("1");
    expect(last(calls, "GET", "/research/screener")?.query.get("limit")).toBe("10");
    expect(screen.getByText(/2415 resultado\(s\) de 2415 candidato\(s\)/)).toBeInTheDocument();
    expect(screen.getByText("1–10 de 2415")).toBeInTheDocument();
    expect(screen.getByText("Página 1 de 242")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Última página" }));
    expect(await screen.findByText("AAAA2415")).toBeInTheDocument();
    expect(last(calls, "GET", "/research/screener")?.query.get("page")).toBe("242");
    expect(screen.getByText("2411–2415 de 2415")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Itens por página"), { target: { value: "100" } });
    expect(await screen.findByText("AAAA100")).toBeInTheDocument();
    expect(last(calls, "GET", "/research/screener")?.query.get("page")).toBe("1");
    expect(last(calls, "GET", "/research/screener")?.query.get("limit")).toBe("100");

    fireEvent.click(screen.getByRole("button", { name: "Próxima página" }));
    expect(await screen.findByText("AAAA200")).toBeInTheDocument();
    const before = screenerCalls().length;
    fireEvent.click(screen.getByRole("button", { name: "Recarregar" }));
    await waitFor(() => expect(screenerCalls().length).toBe(before + 1));
    // Reloading asks for the same page again.
    expect(last(calls, "GET", "/research/screener")?.query.get("page")).toBe("2");
  });

  it("pages the watchlist", async () => {
    const watched = Array.from({ length: 6 }, (_, i) => ({
      asset_id: i + 1,
      ticker: `WWWW${i + 1}`,
      name: `Observado ${i + 1}`,
      asset_type: "STOCK_BR",
      arca_class: "ACOES",
      lifecycle_status: "WATCHING",
      checklist_profile: "GENERAL",
      checklist_score: 0,
      checklist_recommendation: "NEUTRAL",
      checklist_coverage_pct: 0,
      valuation_verdict: "FAIR",
      price: 10,
      margin: null,
    }));
    mockApi([{ path: "/research/watchlist", reply: watched }]);
    renderAt("/research?tab=watchlist");
    expect(await screen.findByRole("link", { name: "WWWW6" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Itens por página"), { target: { value: "5" } });
    expect(screen.queryByRole("link", { name: "WWWW6" })).not.toBeInTheDocument();
    expect(screen.getByText("Página 1 de 2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Última página" }));
    expect(screen.getByRole("link", { name: "WWWW6" })).toBeInTheDocument();
  });
});
