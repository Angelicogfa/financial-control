/** HTTP client for /api/v1: same-origin session cookie, typed errors that reach the screen. */

export const UNAUTHORIZED_EVENT = "fincontrol:unauthorized";
export const API_PREFIX = "/api/v1";

/** An error the screen can show: the API's own message and code, or a connection failure. */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export const OFFLINE_MESSAGE =
  "Não foi possível falar com o servidor. Verifique se a API está no ar e tente de novo.";

type QueryValue = string | number | boolean | null | undefined | Array<string | number>;
export type Query = Record<string, QueryValue>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  form?: FormData;
  query?: Query;
}

export function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((item) => params.append(key, String(item)));
    else params.append(key, String(value));
  }
  const search = params.toString();
  return `${API_PREFIX}${path}${search ? `?${search}` : ""}`;
}

function detailOf(body: unknown, status: number): { message: string; code?: string } {
  if (body && typeof body === "object") {
    const { detail, code } = body as { detail?: unknown; code?: unknown };
    if (typeof detail === "string") return { message: detail, code: typeof code === "string" ? code : undefined };
    if (Array.isArray(detail) && detail.length > 0) {
      // FastAPI validation errors: [{loc, msg}]
      const first = detail[0] as { loc?: unknown[]; msg?: string };
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : undefined;
      return { message: `${field ? `${String(field)}: ` : ""}${first.msg ?? "dado inválido"}`, code: "VALIDATION" };
    }
  }
  return { message: `Erro ${status} ao falar com o servidor.` };
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, form, query } = options;
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (form) payload = form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: payload,
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, OFFLINE_MESSAGE, "OFFLINE");
  }

  if (response.status === 401) {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    throw new ApiError(401, "Sua sessão expirou. Entre de novo.", "UNAUTHORIZED");
  }
  if (response.status === 204) return undefined as T;

  let parsed: unknown = null;
  try {
    parsed = await response.json();
  } catch {
    parsed = null;
  }
  if (!response.ok) {
    const { message, code } = detailOf(parsed, response.status);
    throw new ApiError(response.status, message, code);
  }
  return parsed as T;
}

/** Message for any thrown value. */
export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Algo deu errado.";
}
