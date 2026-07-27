import type { ReactNode } from "react";
import { RequireSession } from "@/components/auth/RequireSession";
import { AppShell } from "@/components/shell/AppShell";

export default function AuthenticatedLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <RequireSession>
      <AppShell>{children}</AppShell>
    </RequireSession>
  );
}
