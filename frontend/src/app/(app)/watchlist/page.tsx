"use client";

import { useState } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { CategoryTabs } from "@/components/patterns/CategoryTabs";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { RunScanButton } from "@/components/dashboard/RunScanButton";
import { RecommendationBadge } from "@/components/badges/RecommendationBadge";
import type { RecommendationValue } from "@/components/badges/RecommendationBadge";
import { MyWatchlistPanel } from "@/components/watchlist/MyWatchlistPanel";
import { getWatchlists } from "@/lib/api/market";
import { useCategoryFetch } from "@/lib/hooks/useCategoryFetch";
import {
  WATCHLIST_CATEGORY_LABELS,
  WATCHLIST_CATEGORY_ORDER,
} from "@/lib/market-intelligence-labels";
import type { WatchlistEntry } from "@/lib/api/types";

const MY_LIST_TAB = "MY_LIST";

async function fetchWatchlistEntries(category: string): Promise<WatchlistEntry[]> {
  // MY_LIST_TAB is rendered entirely by <MyWatchlistPanel /> below and
  // never reaches this fetcher in practice, but useCategoryFetch still
  // calls it once on every category change (including into this tab) --
  // short-circuit rather than call GET /market/watchlists with a
  // category value the backend has never heard of.
  if (category === MY_LIST_TAB) {
    return [];
  }
  const result = await getWatchlists(category);
  return result.watchlists[0]?.entries ?? [];
}

const TABS = [MY_LIST_TAB, ...WATCHLIST_CATEGORY_ORDER];
const TAB_LABELS: Record<string, string> = { [MY_LIST_TAB]: "قائمتي", ...WATCHLIST_CATEGORY_LABELS };

export default function WatchlistPage() {
  const [category, setCategory] = useState<string>(MY_LIST_TAB);
  const state = useCategoryFetch(category, fetchWatchlistEntries);

  return (
    <div className="flex flex-col gap-bsr-4">
      <h1 className="text-lg font-semibold text-bsr-text-primary">المراقبة</h1>

      <CategoryTabs
        categories={TABS}
        labels={TAB_LABELS}
        active={category}
        onChange={setCategory}
      />

      {category === MY_LIST_TAB ? (
        <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-2 md:p-bsr-4">
          <MyWatchlistPanel />
        </section>
      ) : (
      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-2 md:p-bsr-4">
        {state.status === "loading" ? <LoadingScreen /> : null}

        {state.status === "unavailable" ? (
          <EmptyState
            title="لا توجد بيانات مسح للسوق بعد"
            description="شغّل أول مسح ذكي للسوق لعرض قوائم المراقبة."
            action={<RunScanButton />}
          />
        ) : null}

        {state.status === "error" ? (
          <EmptyState
            title="تعذّر تحميل قائمة المراقبة"
            description="تأكد من اتصال الخادم وحاول مرة أخرى."
          />
        ) : null}

        {state.status === "ready" && state.entries.length === 0 ? (
          <EmptyState title="لا توجد أسهم في هذه الفئة حالياً" />
        ) : null}

        {state.status === "ready" && state.entries.length > 0 ? (
          <ul className="flex flex-col divide-y divide-bsr-border-subtle">
            {state.entries.map((entry) => (
              <li
                key={entry.symbol}
                className="flex flex-col gap-bsr-2 px-bsr-4 py-bsr-3"
              >
                <div className="flex items-center justify-between">
                  <div className="flex flex-col">
                    <span className="bsr-numeric font-semibold text-bsr-text-primary">
                      {entry.symbol}
                    </span>
                    {entry.sector ? (
                      <span className="text-sm text-bsr-text-secondary">
                        {entry.sector}
                      </span>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-bsr-3">
                    {entry.confidence != null ? (
                      <span className="flex items-center gap-1 text-sm text-bsr-teal-500">
                        <AiStar size="sm" />
                        <span className="bsr-numeric">
                          {Math.round(entry.confidence)}%
                        </span>
                      </span>
                    ) : null}
                    {entry.recommendation ? (
                      <RecommendationBadge
                        value={entry.recommendation as RecommendationValue}
                      />
                    ) : null}
                  </div>
                </div>
                <p className="text-sm text-bsr-text-secondary">
                  {entry.reason}
                </p>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
      )}
    </div>
  );
}
