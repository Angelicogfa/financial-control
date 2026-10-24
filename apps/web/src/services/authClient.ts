/** Session API for the single-user login (item 9.5). Cookies are httpOnly and same-origin. */

export const UNAUTHORIZED_EVENT = "fincontrol:unauthorized";

export type AuthState =
  | { status: "checking" }
  | { status: "anonymous"; reason?: string }
  | { status: "authenticated"; username: string };

/** fetch wrapper that sends the session cookie and announces expired sessions. */
export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const resp = await fetch(input, { credentials: "same-origin", ...init });
  if (resp.status === 401) {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  return resp;
}

async function readDetail(resp: Response): Promise<{ detail: string; code?: string }> {
  try {
    const body = (await resp.json()) as { detail?: unknown; code?: string };
    return { detail: typeof body.detail === "string" ? body.detail : `HTTP ${resp.status}`, code: body.code };
  } catch {
    return { detail: `HTTP ${resp.status}` };
  }
}

const NOT_CONFIGURED_MESSAGE =
  "O login ainda não foi configurado: defina AUTH_PASSWORD_HASH e AUTH_JWT_SECRET no .env " +
  "(veja as instruções em .env.example).";

/**
 * Resolve the current session. Only an explicit 401/503 from the API means "log in";
 * other failures (API offline) let the app load and show its own empty/error states.
 */
export async function fetchSession(): Promise<AuthState> {
  try {
    const resp = await fetch("/api/v1/auth/me", { credentials: "same-origin" });
    if (resp.ok) {
      const body = (await resp.json()) as { username: string };
      return { status: "authenticated", username: body.username };
    }
    if (resp.status === 401) {
      return { status: "anonymous" };
    }
    if (resp.status === 503) {
      return { status: "anonymous", reason: NOT_CONFIGURED_MESSAGE };
    }
  } catch {
    // API unreachable: fall through
  }
  return { status: "authenticated", username: "" };
}

export async function login(username: string, password: string): Promise<string> {
  const resp = await fetch("/api/v1/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (resp.ok) {
    const body = (await resp.json()) as { username: string };
    return body.username;
  }
  const { detail, code } = await readDetail(resp);
  if (code === "AUTH_NOT_CONFIGURED") {
    throw new Error(NOT_CONFIGURED_MESSAGE);
  }
  throw new Error(resp.status === 401 ? "Usuário ou senha inválidos." : detail);
}

export async function logout(): Promise<void> {
  await fetch("/api/v1/auth/logout", { method: "POST", credentials: "same-origin" });
}
