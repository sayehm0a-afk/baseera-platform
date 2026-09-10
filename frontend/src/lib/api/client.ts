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

// Single-flight refresh, within this tab: concurrent 401s (e.g. a
// screen firing several requests at once right as the access token
// expires) must trigger exactly one /auth/refresh call from THIS page,
// not one per failed request.
let refreshInFlight: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/** Cross-tab serialization for the actual /auth/refresh network call.
 * `refreshInFlight` above only dedupes within one page/module instance
 * -- a second browser tab of the SAME login has its own separate copy
 * of that variable, so two tabs whose access tokens expire close
 * together would otherwise each fire their own /auth/refresh at
 * nearly the same moment, both presenting the SAME (not yet rotated)
 * refresh cookie. The backend correctly treats that as reuse of an
 * already-consumed token and revokes the whole session family --
 * logging every tab out, even though nothing was actually stolen (see
 * tests/integration/test_refresh_rotation_concurrency.py for the
 * server-side proof of that exact race).
 *
 * The Web Locks API (`navigator.locks`, supported since Safari 15.4)
 * serializes the underlying fetch across every tab of this origin, not
 * just this page. Access/refresh tokens are httpOnly cookies the
 * browser already shares across all tabs -- so once one tab's response
 * lands and rotates them, a second tab's call (which only runs after
 * the lock is released) naturally presents the NEW, still-valid
 * cookie instead of racing on the one that was just consumed. This
 * closes the false-positive at its source, on the frontend, without
 * touching the backend's reuse-detection (a genuine stolen-token
 * replay is still caught and still revokes the family exactly as
 * before). Falls back to the plain per-tab request on the rare browser
 * without Web Locks support -- a known, accepted limitation there. */
async function performRefresh(): Promise<boolean> {
  if (typeof navigator !== "undefined" && "locks" in navigator) {
    return await navigator.locks.request("basirah-auth-refresh", async () => doRefreshRequest());
  }
  return doRefreshRequest();
}

function doRefreshRequest(): Promise<boolean> {
  return apiFetch("/api/v1/auth/refresh", { method: "POST" })
    .then(() => true)
    .catch(() => false);
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
  const { _isRetry, ...rest } = init ?? {};

  const response = await fetch(path, {
    ...rest,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...csrfHeaders(),
      ...rest.headers,
    },
    cache: "no-store",
  });

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
