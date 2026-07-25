import type { ApiErrorBody } from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** Thin, typed fetch wrapper over the existing FastAPI backend -- never
 * re-implements backend logic, only calls it. Every route under
 * /api/v1/* returns `{"error": {"code": ..., "message": ...}}` on
 * failure (see tests/integration/api/*), which this maps to `ApiError`
 * so callers can branch on `.code` instead of parsing prose. */
export async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // response body wasn't JSON -- fall through to the generic error below
    }
    throw new ApiError(
      response.status,
      body?.error?.code ?? "unknown_error",
      body?.error?.message ?? response.statusText
    );
  }

  return response.json() as Promise<T>;
}
