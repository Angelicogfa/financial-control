/** Tests for the single-user login gate (item 9.5). */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { UNAUTHORIZED_EVENT, apiFetch } from "../services/authClient";

afterEach(() => {
  vi.restoreAllMocks();
});

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

describe("Authentication gate", () => {
  it("shows the login form, signs in and loads the dashboard", async () => {
    let loggedIn = false;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/me")) {
        return loggedIn ? json({ username: "owner" }) : json({ detail: "x" }, 401);
      }
      if (url.endsWith("/api/v1/auth/login")) {
        const body = JSON.parse(String(init?.body)) as { password: string };
        loggedIn = body.password === "secret-pass";
        return loggedIn ? json({ username: "owner" }) : json({ detail: "bad" }, 401);
      }
      return json({ items: [], meta: {} }, 404);
    });

    render(<App />);

    fireEvent.change(await screen.findByLabelText("Usuário"), { target: { value: "owner" } });
    fireEvent.change(screen.getByLabelText("Senha"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Usuário ou senha inválidos.");

    fireEvent.change(screen.getByLabelText("Senha"), { target: { value: "secret-pass" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByText("Patrimônio Atual Líquido")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/login",
      expect.objectContaining({ credentials: "same-origin", method: "POST" }),
    );
  });

  it("explains when authentication is not configured", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json({ detail: "x", code: "AUTH_NOT_CONFIGURED" }, 503),
    );

    render(<App />);

    expect(await screen.findByRole("status")).toHaveTextContent("AUTH_PASSWORD_HASH");
  });

  it("returns to the login screen when a request answers 401", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).endsWith("/api/v1/auth/me")
        ? json({ username: "owner" })
        : json({ detail: "Session expired" }, 401),
    );
    const listener = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, listener);

    render(<App />);

    await waitFor(() => expect(listener).toHaveBeenCalled());
    expect(await screen.findByText("Sua sessão expirou. Entre novamente.")).toBeInTheDocument();
    window.removeEventListener(UNAUTHORIZED_EVENT, listener);
    expect((await apiFetch("/api/v1/assets")).status).toBe(401);
  });
});
