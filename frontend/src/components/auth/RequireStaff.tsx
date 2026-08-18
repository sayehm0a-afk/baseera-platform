"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import {
  getSessionServerSnapshot,
  getSessionSnapshot,
  subscribeToSession,
} from "@/lib/auth/auth-service";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";

/** Gates the owner-only pages (لوحة المالك / اختبار السوق المباشر) on
 * `is_staff`. This is UX only -- the real security boundary is server
 * side: every admin route these pages call requires
 * require_staff_role(StaffRole.ADMIN) (src/auth/rbac.py) and returns a
 * real 403 to a non-staff caller regardless of what this component
 * does. Assumes it renders inside RequireSession, so the session is
 * already resolved (not undefined) by the time this mounts. */
export function RequireStaff({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const session = useSyncExternalStore(
    subscribeToSession,
    getSessionSnapshot,
    getSessionServerSnapshot
  );

  useEffect(() => {
    if (session !== undefined && (session === null || !session.is_staff)) {
      router.replace("/radar");
    }
  }, [session, router]);

  if (session === undefined || session === null || !session.is_staff) {
    return <LoadingScreen />;
  }
  return <>{children}</>;
}
