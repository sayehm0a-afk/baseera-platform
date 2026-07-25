/**
 * TEMPORARY DEV-ONLY AUTH SERVICE.
 *
 * The backend does not yet expose an authentication endpoint (no
 * `/api/v1/auth/*` route exists in src/api/routes/). Per the Phase 9
 * brief, this is a temporary service-layer interface only -- it does
 * NOT invent backend auth behavior, does not issue real tokens, and
 * must never be mistaken for production auth. It exists solely so the
 * Login screen has something real to call and every downstream screen
 * can already be wired to "is a user signed in" without inventing a
 * fake credential store.
 *
 * Replace `login`/`logout`/`getSession` with calls into a real
 * `/api/v1/auth/*` client the moment that backend endpoint exists --
 * no other file should need to change, since callers only depend on
 * this module's exported shape.
 */

const SESSION_STORAGE_KEY = "basirah.dev-session";

export interface DevSession {
  email: string;
  signedInAt: string;
}

export function login(email: string): DevSession {
  const session: DevSession = { email, signedInAt: new Date().toISOString() };
  if (typeof window !== "undefined") {
    window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  }
  return session;
}

export function logout(): void {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  }
}

export function getSession(): DevSession | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as DevSession;
  } catch {
    return null;
  }
}
