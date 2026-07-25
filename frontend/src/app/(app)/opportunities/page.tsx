import { AiStar } from "@/components/ai/AiStar";
import { EmptyState } from "@/components/patterns/EmptyState";
import { AiSignalCard } from "@/components/patterns/AiSignalCard";
import { RunScanButton } from "@/components/dashboard/RunScanButton";
import { ApiError } from "@/lib/api/client";
import { getRankings } from "@/lib/api/market";
import { RANKING_CATEGORY_LABELS } from "@/lib/market-intelligence-labels";
import type { RankingEntry } from "@/lib/api/types";
import type { RecommendationValue } from "@/components/badges/RecommendationBadge";

const OPPORTUNITY_SECTIONS = [
  "TOP_STRONG_BUY",
  "TOP_BUY",
  "NEW_OPPORTUNITIES",
  "HIGHEST_EXPECTED_RETURN",
];

async function loadOpportunities(): Promise<
  | { available: true; sections: { category: string; entries: RankingEntry[] }[] }
  | { available: false }
> {
  try {
    const results = await Promise.all(
      OPPORTUNITY_SECTIONS.map((category) => getRankings(category))
    );
    return {
      available: true,
      sections: OPPORTUNITY_SECTIONS.map((category, index) => ({
        category,
        entries: results[index].rankings[0]?.entries ?? [],
      })),
    };
  } catch (error) {
    if (error instanceof ApiError && error.code === "no_market_scan_data") {
      return { available: false };
    }
    throw error;
  }
}

export default async function OpportunitiesPage() {
  const data = await loadOpportunities();

  if (!data.available) {
    return (
      <EmptyState
        title="لا توجد بيانات مسح للسوق بعد"
        description="شغّل أول مسح ذكي للسوق لعرض الفرص الاستثمارية."
        action={<RunScanButton />}
      />
    );
  }

  return (
    <div className="flex flex-col gap-bsr-8">
      <div className="flex items-center gap-bsr-2">
        <AiStar size="lg" />
        <h1 className="text-lg font-semibold text-bsr-text-primary">
          الفرص الاستثمارية
        </h1>
      </div>

      {data.sections.map((section) => (
        <section key={section.category}>
          <h2 className="mb-bsr-4 text-base font-semibold text-bsr-text-primary">
            {RANKING_CATEGORY_LABELS[section.category] ?? section.category}
          </h2>
          {section.entries.length === 0 ? (
            <EmptyState title="لا توجد فرص في هذه الفئة حالياً" />
          ) : (
            <div className="grid grid-cols-1 gap-bsr-4 sm:grid-cols-2 lg:grid-cols-4">
              {section.entries.slice(0, 8).map((entry) => (
                <AiSignalCard
                  key={`${section.category}-${entry.symbol}`}
                  symbol={entry.symbol}
                  sector={entry.sector}
                  recommendation={(entry.recommendation as RecommendationValue) ?? "HOLD"}
                  confidence={entry.confidence}
                  targetPrice={entry.target_price}
                  expectedReturnPct={entry.expected_return_pct}
                  href={`/ai?symbol=${encodeURIComponent(entry.symbol)}`}
                />
              ))}
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
