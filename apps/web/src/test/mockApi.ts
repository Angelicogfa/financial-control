/** A fake API for page tests: routes answer by method and path; every call is recorded. */

import { vi } from "vitest";

export interface Call {
  method: string;
  path: string;
  query: URLSearchParams;
  body: unknown;
}

type Reply = { status?: number; json?: unknown } | unknown;
type Handler = (call: Call) => Reply;

export interface Route {
  method?: string;
  path: string | RegExp;
  reply: Handler | Reply;
}

/** A reply envelope has only `status` (a number) and/or `json`; anything else is a payload. */
function isReply(value: unknown): value is { status?: number; json?: unknown } {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const keys = Object.keys(value);
  const status = (value as { status?: unknown }).status;
  return (
    keys.length > 0 &&
    keys.every((k) => k === "status" || k === "json") &&
    (status === undefined || typeof status === "number")
  );
}

export function mockApi(routes: Route[]) {
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.pathname.replace(/^\/api\/v1/, "");
    let body: unknown = undefined;
    if (typeof init?.body === "string") body = JSON.parse(init.body);
    else if (init?.body instanceof FormData) body = Object.fromEntries(init.body.entries());
    const call: Call = { method, path, query: url.searchParams, body };
    calls.push(call);
    const route = routes.find(
      (r) =>
        (r.method ?? "GET") === method && (typeof r.path === "string" ? r.path === path : r.path.test(path)),
    );
    if (!route) {
      return new Response(JSON.stringify({ detail: `No mock for ${method} ${path}` }), { status: 404 });
    }
    const raw = typeof route.reply === "function" ? (route.reply as Handler)(call) : route.reply;
    const reply = isReply(raw) ? raw : { json: raw };
    const status = reply.status ?? 200;
    if (status === 204) return new Response(null, { status });
    return new Response(JSON.stringify(reply.json ?? null), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}
