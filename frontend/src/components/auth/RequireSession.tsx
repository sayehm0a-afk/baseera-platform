"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getSession, type DevSession } from "@/lib/auth/temp-auth-service";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";

/** Guards every authenticated route: redirects to /login when no dev
 * session exists. Client-side only because temp-auth-service is a
 * localStorage-backed dev stub, not a real server session -- this is
 * itself part of the disclosed, temporary nature of that service. */
export function RequireSession({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [session] = useState<DevSession | null>(() => getSession());

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
