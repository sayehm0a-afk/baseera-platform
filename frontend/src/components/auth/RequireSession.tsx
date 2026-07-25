"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import {
  getSessionServerSnapshot,
  getSessionSnapshot,
  subscribeToSession,
} from "@/lib/auth/temp-auth-service";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";

/** Guards every authenticated route: redirects to /login when no dev
 * session exists.
 *
 * Reads the session via useSyncExternalStore (not a useState lazy
 * initializer) so the first client render matches the SSR-rendered
 * HTML exactly -- localStorage doesn't exist on the server, so reading
 * it in a lazy initializer renders one thing server-side and a
 * different thing on hydration, a real mismatch bug, not just a lint
 * nag.
 *
 * The redirect effect deliberately does NOT depend on `session`: on
 * the hydration commit, useSyncExternalStore's rendered value is still
 * `getServerSnapshot()` (null, to match the SSR HTML) even though the
 * real client session already exists in localStorage -- an effect
 * keyed on that transient null fires a redirect to /login before the
 * very next commit corrects `session` to its real value, logging a
 * signed-in user out. Reading the session directly, once, in a
 * mount-only effect sidesteps that render-timing race entirely; the
 * render path still uses the synced `session` value so there's no
 * hydration mismatch. Reproduced and verified fixed with a live dev
 * server + Playwright (a valid session survived a full navigation to
 * a second route without bouncing to /login). */
export function RequireSession({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const session = useSyncExternalStore(
    subscribeToSession,
    getSessionSnapshot,
    getSessionServerSnapshot
  );

  useEffect(() => {
    if (!getSessionSnapshot()) {
      router.replace("/login");
    }
  }, [router]);

  if (!session) {
    return <LoadingScreen />;
  }
  return <>{children}</>;
}
