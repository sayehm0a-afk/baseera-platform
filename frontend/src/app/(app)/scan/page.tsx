"use client";

import { useState } from "react";
import { CategoryTabs } from "@/components/patterns/CategoryTabs";
import { EmptyState } from "@/components/patterns/EmptyState";
import { InstrumentRow } from "@/components/patterns/InstrumentRow";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { LiveScanPanel } from "@/components/dashboard/LiveScanPanel";
import { RunScanButton } from "@/components/dashboard/RunScanButton";
import { getRankings } from "@/lib/api/market";
import { useCategoryFetch } from "@/lib/hooks/useCategoryFetch";
import {
  RANKING_CATEGORY_LABELS,
  RANKING_CATEGORY_ORDER,
} from "@/lib/market-intelligence-labels";
import type { RankingEntry } from "@/lib/api/types";
import type { RecommendationValue } from "@/components/badges/RecommendationBadge";

async function fetchRankingEntries(category: string): Promise<RankingEntry[]> {
  const result = await getRankings(category);
  return result.rankings[0]?.entries ?? [];
}

export default function ScanPage() {
  const [category, setCategory] = useState<string>("TOP_BUY");
  const state = useCategoryFetch(category, fetchRankingEntries);

  return (
    <div className="flex flex-col gap-bsr-4">
      <h1 className="text-lg font-semibold text-bsr-text-primary">
        المسح الذكي للسوق
      </h1>

      <LiveScanPanel />

      <CategoryTabs
        categories={RANKING_CATEGORY_ORDER}
        labels={RANKING_CATEGORY_LABELS}
        active={category}
        onChange={setCategory}
      />

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-2 md:p-bsr-4">
        {state.status === "loading" ? <LoadingScreen /> : null}

        {state.status === "unavailable" ? (
          <EmptyState
            title="لا توجد بيانات مسح للسوق بعد"
            description="شغّل أول مسح ذكي للسوق لعرض النتائج حسب الفئة."
            action={<RunScanButton />}
          />
        ) : null}

        {state.status === "error" ? (
          <EmptyState
            title="تعذّر تحميل نتائج المسح"
            description="تأكد من اتصال الخادم وحاول مرة أخرى."
          />
        ) : null}

        {state.status === "ready" && state.entries.length === 0 ? (
          <EmptyState title="لا توجد نتائج في هذه الفئة حالياً" />
        ) : null}

        {state.status === "ready" && state.entries.length > 0 ? (
          <ul className="flex flex-col divide-y divide-bsr-border-subtle">
            {state.entries.map((entry) => (
              <li key={entry.symbol}>
                <InstrumentRow
                  symbol={entry.symbol}
                  sector={entry.sector}
                  price={entry.target_price}
                  priceKind="target"
                  changePct={entry.expected_return_pct}
                  recommendation={
                    (entry.recommendation as RecommendationValue) ?? undefined
                  }
                  confidence={entry.confidence}
                  href={`/stocks/${encodeURIComponent(entry.symbol)}`}
                />
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  );
}
