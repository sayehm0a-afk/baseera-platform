import type { ApiErrorBody } from "./types";

// Auth bootstrap endpoints never have a prior session to refresh, and
// /auth/refresh itself must never trigger its own retry (that would
// recurse forever the moment a refresh legitimately fails) -- a 401
// from any of these is a real, final answer, not "the access token
// expired mid-session."
const AUTH_BOOTSTRAP_PATHS = new Set([
  "/api/v1/auth/register",
  "/api/v1/auth/login",
  "/api/v1/auth/refresh",
  "/api/v1/auth/verify-email",
  "/api/v1/auth/forgot-password",
  "/api/v1/auth/reset-password",
]);

// next.config.ts's own rewrite proxy already bounds every request to
// 120s (see its own `proxyTimeout` comment for why that ceiling exists
// and isn't unbounded). Without a client-side cutoff of our own, a
// hung backend/proxy left `fetch` waiting indefinitely -- no spinner
// ever resolves, no error is ever shown, and it looks identical to a
// process that's simply broken. Deliberately set a few seconds above
// the proxy's own 120s ceiling so this never fires first and steals
// the (more specific) proxy timeout's own error -- this is a last-
// resort backstop, not the primary timeout.
const DEFAULT_TIMEOUT_MS = 130_000;

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

function readCookie(name: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const match = document.cookie.match(
    new RegExp(`(?:^|; )${name}=([^;]*)`)
  );
  return match ? decodeURIComponent(match[1]) : null;
}

/** The same-origin rewrite in next.config.ts makes the non-httpOnly
 * CSRF cookie readable here, including after a reload with an expired
 * access token. Read the current cookie for EVERY request: another tab
 * may have rotated it since this tab's last response. Never cache the
 * response-header value, which can be stale or lost on navigation.
 * Access/refresh cookies remain httpOnly and are never read by JS. */
function csrfHeaders(): Record<string, string> {
  const token = readCookie("csrf_token");
  return token ? { "X-CSRF-Token": token } : {};
}

// Single-flight refresh: concurrent 401s (e.g. a screen firing several
// requests at once right as the access token expires) must trigger
// exactly one /auth/refresh call, not one per failed request.
let refreshInFlight: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = apiFetch("/api/v1/auth/refresh", { method: "POST" })
      .then(() => true)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

/** Thin, typed fetch wrapper over the existing FastAPI backend -- never
 * re-implements backend logic, only calls it. Every route under
 * /api/v1/* returns `{"error": {"code": ..., "message": ...}}` on
 * failure (see tests/integration/api/*), which this maps to `ApiError`
 * so callers can branch on `.code` instead of parsing prose.
 *
 * Browser requests use relative URLs through Next's same-origin API
 * rewrite, so Safari need not accept third-party cookies. Credentials
 * sends the httpOnly access/refresh cookies (and the CSRF cookie). A 401
 * from anything other than an auth-bootstrap endpoint is treated as "the
 * access token probably just expired": one silent refresh-and-retry is
 * attempted before giving up and surfacing the original error. */
export async function apiFetch<T>(
  path: string,
  init?: RequestInit & { _isRetry?: boolean }
): Promise<T> {
  const { _isRetry, signal: callerSignal, ...rest } = init ?? {};

  // Respect a caller-supplied signal (none currently exist, but never
  // silently override one a future caller adds) -- otherwise apply the
  // default backstop timeout above.
  const controller = callerSignal ? null : new AbortController();
  const timeoutId = controller
    ? setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)
    : null;

  let response: Response;
  try {
    response = await fetch(path, {
      ...rest,
      signal: callerSignal ?? controller?.signal,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...csrfHeaders(),
        ...rest.headers,
      },
      cache: "no-store",
    });
  } catch (err) {
    if (controller?.signal.aborted) {
      throw new ApiError(0, "request_timeout", "انتهت مهلة الاتصال بالخادم.");
    }
    throw err;
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }

  if (
    response.status === 401 &&
    !_isRetry &&
    !AUTH_BOOTSTRAP_PATHS.has(path)
  ) {
    const refreshed = await refreshSession();
    if (refreshed) {
      return apiFetch<T>(path, { ...init, _isRetry: true });
    }
  }

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
