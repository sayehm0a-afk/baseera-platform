/**
 * Real auth service backed by /api/v1/auth/* (see src/api/routes/auth.py).
 * Replaces the old dev-only temp-auth-service.ts localStorage stub now
 * that the backend actually issues httpOnly access/refresh cookies.
 *
 * Session state can no longer be read synchronously (httpOnly cookies
 * are invisible to JS by design) -- it's an async GET /auth/me instead,
 * cached in a small module-level store so every consumer (RequireSession,
 * Settings, the splash screen) sees the same value without each firing
 * its own request. `undefined` means "not resolved yet" (used for the
 * loading state); `null` means "resolved: signed out."
 */

import { apiFetch } from "@/lib/api/client";

export interface AuthUser {
  id: number;
  email: string;
  full_name: string | null;
  is_email_verified: boolean;
  is_staff: boolean;
  staff_role: string | null;
  created_at: string;
  last_login_at: string | null;
}

type SessionState = AuthUser | null | undefined;

let currentSession: SessionState = undefined;
const listeners = new Set<() => void>();

function setSession(session: AuthUser | null): void {
  currentSession = session;
  listeners.forEach((listener) => listener());
}

/** Resolves the current session from the server -- the one place that
 * actually calls GET /auth/me. Never throws: an unauthenticated caller
 * (no session, or an expired one apiFetch couldn't silently refresh)
 * resolves to `null`, exactly like "signed out." */
export async function fetchSession(): Promise<AuthUser | null> {
  try {
    const user = await apiFetch<AuthUser>("/api/v1/auth/me");
    setSession(user);
    return user;
  } catch {
    setSession(null);
    return null;
  }
}

export async function register(
  email: string,
  password: string,
  fullName?: string
): Promise<AuthUser> {
  return apiFetch<AuthUser>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
      ...(fullName ? { full_name: fullName } : {}),
    }),
  });
}

export async function verifyEmail(token: string): Promise<void> {
  await apiFetch("/api/v1/auth/verify-email", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export async function resendVerification(email: string): Promise<void> {
  await apiFetch("/api/v1/auth/resend-verification", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function login(
  email: string,
  password: string
): Promise<AuthUser> {
  await apiFetch("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  // The login response body is a message, not the user -- /auth/me is
  // the single source of truth for the session shape everywhere else.
  const user = await fetchSession();
  if (!user) {
    throw new Error("Login succeeded but the session could not be loaded.");
  }
  return user;
}

export async function logout(): Promise<void> {
  try {
    await apiFetch("/api/v1/auth/logout", { method: "POST" });
  } finally {
    setSession(null);
  }
}

export async function logoutAll(): Promise<void> {
  try {
    await apiFetch("/api/v1/auth/logout-all", { method: "POST" });
  } finally {
    setSession(null);
  }
}

export async function forgotPassword(email: string): Promise<void> {
  await apiFetch("/api/v1/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function resetPassword(
  token: string,
  newPassword: string
): Promise<void> {
  await apiFetch("/api/v1/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  // A successful reset revokes every existing session server-side
  // (src/api/routes/auth.py) -- this client's own cached session (if
  // any) is now stale too.
  setSession(null);
}

/** `useSyncExternalStore` bindings, same shape the old temp-auth-service
 * exposed -- consumers don't need to change how they subscribe, only
 * what the resolved value means (`undefined` while loading, now that
 * this is genuinely async instead of a synchronous localStorage read). */
export function subscribeToSession(callback: () => void): () => void {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

export function getSessionSnapshot(): SessionState {
  return currentSession;
}

export function getSessionServerSnapshot(): SessionState {
  return undefined;
}
