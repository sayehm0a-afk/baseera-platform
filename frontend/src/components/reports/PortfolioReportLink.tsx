"use client";

import { useSyncExternalStore } from "react";
import { getStoredPortfolioId } from "@/lib/portfolio/local-portfolio";
import { EmptyState } from "@/components/patterns/EmptyState";

function subscribe(): () => void {
  return () => {};
}

export function PortfolioReportLink() {
  // Local storage never changes from another tab's perspective within
  // this simple read-once use case, so an empty subscribe is enough --
  // getServerSnapshot returns null to keep the first client render
  // identical to the SSR pass.
  const portfolioId = useSyncExternalStore(
    subscribe,
    getStoredPortfolioId,
    () => null
  );

  if (portfolioId == null) {
    return (
      <EmptyState
        title="لا توجد محفظة محلَّلة بعد"
        description="حلّل محفظتك من صفحة المحفظة للحصول على تقرير صحة شامل."
      />
    );
  }

  return (
    <a
      href="/portfolio"
      className="block rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-overlay px-bsr-4 py-bsr-3 text-sm text-bsr-text-primary hover:border-bsr-gold-500/40"
    >
      عرض تقرير صحة المحفظة الكامل ←
    </a>
  );
}
