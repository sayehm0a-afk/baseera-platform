"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import {
  fetchSession,
  getSessionServerSnapshot,
  getSessionSnapshot,
  subscribeToSession,
} from "@/lib/auth/auth-service";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";

/** Guards every authenticated route: redirects to /login when no
 * session exists.
 *
 * The session is now a real, async GET /auth/me (httpOnly cookies are
 * invisible to JS, so there's no synchronous read to do anymore) --
 * `getSessionSnapshot()` returns `undefined` until that first request
 * resolves, `null` once it's resolved to "signed out," or the user
 * object once signed in. `useSyncExternalStore` still matches the SSR
 * render (`getServerSnapshot()` also returns `undefined`) to the first
 * client render, so there's no hydration mismatch; a mount-only effect
 * kicks off the actual `fetchSession()` call, and the loading screen
 * covers the entire `undefined` window until it resolves either way. */
export function RequireSession({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const session = useSyncExternalStore(
    subscribeToSession,
    getSessionSnapshot,
    getSessionServerSnapshot
  );

  useEffect(() => {
    fetchSession().then((user) => {
      if (!user) {
        router.replace("/login");
      }
    });
    // Intentionally runs once on mount -- re-fetching on every render
    // would spam GET /auth/me for no benefit; navigations between
    // already-authenticated routes reuse the cached session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (session === undefined || session === null) {
    return <LoadingScreen />;
  }
  return <>{children}</>;
}
