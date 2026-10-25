/** Single-user session (item 9.5). Cookies are httpOnly and same-origin. */

import { ApiError, request } from "./http";

export type AuthState =
  | { status: "checking" }
  | { status: "anonymous"; reason?: string }
  | { status: "authenticated"; username: string };

const NOT_CONFIGURED_MESSAGE =
  "O login ainda não foi configurado: defina AUTH_PASSWORD_HASH e AUTH_JWT_SECRET no .env " +
  "(veja as instruções em .env.example).";

/**
 * Resolve the current session. Only an explicit 401/503 means "log in"; when the API is
 * unreachable the app still loads and every screen shows the connection error.
 */
export async function fetchSession(): Promise<AuthState> {
  try {
    const response = await fetch("/api/v1/auth/me", { credentials: "same-origin" });
    if (response.ok) {
      const body = (await response.json()) as { username: string };
      return { status: "authenticated", username: body.username };
    }
    if (response.status === 401) return { status: "anonymous" };
    if (response.status === 503) return { status: "anonymous", reason: NOT_CONFIGURED_MESSAGE };
  } catch {
    // API unreachable: let the screens report it.
  }
  return { status: "authenticated", username: "" };
}

export async function login(username: string, password: string): Promise<string> {
  try {
    const body = await request<{ username: string }>("/auth/login", {
      method: "POST",
      body: { username, password },
    });
    return body.username;
  } catch (error) {
    if (error instanceof ApiError && error.code === "AUTH_NOT_CONFIGURED") {
      throw new Error(NOT_CONFIGURED_MESSAGE);
    }
    if (error instanceof ApiError && error.status === 401) {
      throw new Error("Usuário ou senha inválidos.");
    }
    throw error;
  }
}

export async function logout(): Promise<void> {
  await fetch("/api/v1/auth/logout", { method: "POST", credentials: "same-origin" });
}
