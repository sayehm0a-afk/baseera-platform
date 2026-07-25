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
 * session exists. Reads the session via useSyncExternalStore (not a
 * useState lazy initializer) so the first client render matches the
 * SSR-rendered HTML exactly -- localStorage doesn't exist on the
 * server, so reading it in a lazy initializer would render one thing
 * server-side and a different thing on hydration, which is a real
 * hydration-mismatch bug, not just a lint nag. */
export function RequireSession({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const session = useSyncExternalStore(
    subscribeToSession,
    getSessionSnapshot,
    getSessionServerSnapshot
  );

  useEffect(() => {
    if (!session) {
      router.replace("/login");
    }
  }, [session, router]);

  if (!session) {
    return <LoadingScreen />;
  }
  return <>{children}</>;
}
