import type { ReactNode } from "react";
import { TopBar } from "./TopBar";
import { SideNav } from "./SideNav";
import { MobileTabBar } from "./MobileTabBar";

interface AppShellProps {
  children: ReactNode;
}

/** The one shared authenticated-app layout (top bar + side nav +
 * content + mobile tab bar) every screen renders inside -- UI Spec
 * Global Invariants §0: a screen implementing its own top bar or nav
 * is defective by definition. */
export function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex h-dvh flex-col">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <SideNav />
        <main className="min-w-0 flex-1 overflow-y-auto p-bsr-4 md:p-bsr-6">
          {children}
        </main>
      </div>
      <MobileTabBar />
    </div>
  );
}
