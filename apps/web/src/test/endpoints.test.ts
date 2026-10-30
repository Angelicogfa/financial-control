import { describe, expect, it } from "vitest";

import { api } from "../api/endpoints";
import { asset } from "./fixtures";
import { mockApi, type Call } from "./mockApi";

const meta = (page: number, totalPages: number, totalItems: number) => ({
  page,
  page_size: 200,
  total_items: totalItems,
  total_pages: totalPages,
  has_next: page < totalPages,
  has_prev: page > 1,
  sort_by: "ticker",
  sort_order: "asc",
});

describe("api.assets.list", () => {
  it("reads every page so pickers see assets past the 200th", async () => {
    const { calls } = mockApi([
      {
        path: "/assets",
        reply: (call: Call) => {
          const page = Number(call.query.get("page"));
          return { items: [asset({ id: page, ticker: `T${page}` })], meta: meta(page, 3, 3) };
        },
      },
    ]);
    const all = await api.assets.list(false);
    expect(all.items.map((a) => a.ticker)).toEqual(["T1", "T2", "T3"]);
    expect(calls.map((c) => c.query.get("page"))).toEqual(["1", "2", "3"]);
    expect(calls.every((c) => c.query.get("page_size") === "200" && c.query.get("active_only") === "false")).toBe(true);
  });

  it("stops at the first page when it holds everything", async () => {
    const { calls } = mockApi([{ path: "/assets", reply: { items: [asset()], meta: meta(1, 1, 1) } }]);
    const all = await api.assets.list();
    expect(all.items).toHaveLength(1);
    expect(calls).toHaveLength(1);
  });
});
