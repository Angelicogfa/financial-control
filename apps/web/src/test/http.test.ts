import { describe, expect, it, vi } from "vitest";

import { ApiError, buildUrl, request, UNAUTHORIZED_EVENT } from "../api/http";
import { mockApi } from "./mockApi";

describe("http client", () => {
  it("builds URLs with repeated array params and skips empty values", () => {
    expect(buildUrl("/research/screener", { asset_type: ["FII", "STOCK_BR"], q: "", limit: 5, x: undefined })).toBe(
      "/api/v1/research/screener?asset_type=FII&asset_type=STOCK_BR&limit=5",
    );
  });

  it("returns JSON and sends bodies", async () => {
    const { calls } = mockApi([{ method: "POST", path: "/accounts", reply: { id: 1, name: "XP" } }]);
    const result = await request<{ id: number }>("/accounts", { method: "POST", body: { name: "XP" } });
    expect(result.id).toBe(1);
    expect(calls[0].body).toEqual({ name: "XP" });
  });

  it("propagates the API message and code", async () => {
    mockApi([{ path: "/assets/9", reply: { status: 404, json: { detail: "Asset id=9 not found", code: "NOT_FOUND" } } }]);
    await expect(request("/assets/9")).rejects.toMatchObject({ status: 404, code: "NOT_FOUND", message: "Asset id=9 not found" });
  });

  it("summarizes validation errors", async () => {
    mockApi([
      { method: "POST", path: "/x", reply: { status: 422, json: { detail: [{ loc: ["body", "amount"], msg: "too small" }] } } },
    ]);
    await expect(request("/x", { method: "POST", body: {} })).rejects.toThrow("amount: too small");
  });

  it("announces expired sessions", async () => {
    mockApi([{ path: "/alerts", reply: { status: 401, json: { detail: "Session expired" } } }]);
    const listener = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, listener);
    await expect(request("/alerts")).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalled();
    window.removeEventListener(UNAUTHORIZED_EVENT, listener);
  });

  it("reports the API being offline instead of empty data", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(request("/portfolio/consolidated")).rejects.toMatchObject({ status: 0, code: "OFFLINE" });
  });

  it("handles 204 responses", async () => {
    mockApi([{ method: "DELETE", path: "/transactions/1", reply: { status: 204 } }]);
    await expect(request("/transactions/1", { method: "DELETE" })).resolves.toBeUndefined();
  });
});
