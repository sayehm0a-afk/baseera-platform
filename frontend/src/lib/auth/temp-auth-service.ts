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

// Cached by raw string so `subscribeToSession`'s useSyncExternalStore
// consumer (RequireSession) gets a referentially stable snapshot when
// nothing has actually changed -- re-parsing a new object on every
// call would make useSyncExternalStore believe the store changes on
// every render and loop.
let cachedRaw: string | null = null;
let cachedSession: DevSession | null = null;

function readSession(): DevSession | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (raw === cachedRaw) {
    return cachedSession;
  }
  cachedRaw = raw;
  if (!raw) {
    cachedSession = null;
    return null;
  }
  try {
    cachedSession = JSON.parse(raw) as DevSession;
  } catch {
    cachedSession = null;
  }
  return cachedSession;
}

export function login(email: string): DevSession {
  const session: DevSession = { email, signedInAt: new Date().toISOString() };
  if (typeof window !== "undefined") {
    window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
    window.dispatchEvent(new StorageEvent("storage", { key: SESSION_STORAGE_KEY }));
  }
  return session;
}

export function logout(): void {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    window.dispatchEvent(new StorageEvent("storage", { key: SESSION_STORAGE_KEY }));
  }
}

export function getSession(): DevSession | null {
  return readSession();
}

/** `useSyncExternalStore` bindings for the dev session -- this is the
 * React-supplied mechanism for reading a browser-only value (like
 * localStorage) without a server/client hydration mismatch: it renders
 * `getServerSnapshot()`'s value for both the SSR pass and the first
 * client hydration pass, then transitions to `getSnapshot()`'s real
 * value immediately after, with no manual effect required. */
export function subscribeToSession(callback: () => void): () => void {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

export function getSessionSnapshot(): DevSession | null {
  return readSession();
}

export function getSessionServerSnapshot(): DevSession | null {
  return null;
}
