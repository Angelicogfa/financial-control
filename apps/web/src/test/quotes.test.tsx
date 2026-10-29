import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { QuoteStatusDTO } from "../api/types";
import { QuoteClock } from "../pages/home/QuoteClock";
import { mockApi } from "./mockApi";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function status(over: Partial<QuoteStatusDTO> = {}): QuoteStatusDTO {
  return {
    holdings: 3,
    stored: 3,
    oldest_at: "2026-10-29T14:35:00Z",
    newest_at: "2026-10-29T14:36:00Z",
    stale: 0,
    stale_minutes: 30,
    ...over,
  };
}

describe("QuoteClock", () => {
  it("tells when the quotes were fetched and how many are out of date", async () => {
    mockApi([{ path: "/market/quotes/status", reply: status({ stale: 2, stored: 1 }) }]);
    render(<QuoteClock onRefreshed={() => undefined} />);
    expect(await screen.findByRole("status")).toHaveTextContent(
      /Cotações de .*2 posições sem atualização há mais de 30 min/,
    );
  });

  it("hides itself without holdings", async () => {
    const { calls } = mockApi([{ path: "/market/quotes/status", reply: status({ holdings: 0, stored: 0 }) }]);
    const { container } = render(<QuoteClock onRefreshed={() => undefined} />);
    await vi.waitFor(() => expect(calls.length).toBe(1));
    expect(container).toBeEmptyDOMElement();
  });

  it("asks the worker for fresh quotes and reloads when they arrive", async () => {
    let replies = 0;
    const { calls } = mockApi([
      {
        path: "/market/quotes/status",
        reply: () => {
          replies += 1;
          return status(replies > 1 ? { newest_at: "2026-10-29T14:50:00Z" } : {});
        },
      },
      { method: "POST", path: "/market/job-runs/warm_portfolio_quotes/request", reply: { status: 202, json: {} } },
    ]);
    const onRefreshed = vi.fn();
    render(<QuoteClock onRefreshed={onRefreshed} />);
    const button = await screen.findByRole("button", { name: "Atualizar" });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fireEvent.click(button);
    expect((await screen.findByText("Atualizando…")).closest("button")).toBeDisabled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4500);
    });
    await vi.waitFor(() => expect(onRefreshed).toHaveBeenCalledTimes(1));
    expect(calls.some((c) => c.method === "POST" && c.path === "/market/job-runs/warm_portfolio_quotes/request")).toBe(
      true,
    );
  });
});
