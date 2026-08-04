"use client";

import { useEffect, useState } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { EmptyState } from "@/components/patterns/EmptyState";
import { AiSignalCard } from "@/components/patterns/AiSignalCard";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { RunScanButton } from "@/components/dashboard/RunScanButton";
import { ApiError } from "@/lib/api/client";
import { getOpportunities } from "@/lib/api/market";
import type { OpportunityCategory } from "@/lib/api/types";
import type { RecommendationValue } from "@/components/badges/RecommendationBadge";

type OpportunitiesData =
  | { status: "loading" }
  | { status: "unavailable" }
  | { status: "error" }
  | { status: "ready"; sections: OpportunityCategory[] };

// Client Component: same reason as /dashboard -- apiFetch depends on
// the browser's httpOnly session cookie, which a Next.js Server
// Component fetch never receives (confirmed via a real 401
// "No access token was presented" when this page was still a Server
// Component and was tested end-to-end with a real login).
//
// Phase 2D: a single /api/v1/market/opportunities call now returns
// exactly the same 8 curated categories this page always rendered
// (src.market_intelligence.opportunity_ranking), each already carrying
// its Arabic label and a transparent scoring-factor description --
// replacing the previous 8 parallel getRankings(category) calls with
// one round trip and one server-side source of truth for the labels.
function useOpportunitiesData(): OpportunitiesData {
  const [data, setData] = useState<OpportunitiesData>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const result = await getOpportunities();
        if (cancelled) return;
        setData({ status: "ready", sections: result.categories });
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiError && error.code === "no_market_scan_data") {
          setData({ status: "unavailable" });
        } else {
          setData({ status: "error" });
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return data;
}

export default function OpportunitiesPage() {
  const data = useOpportunitiesData();

  if (data.status === "loading") {
    return <LoadingScreen />;
  }

  if (data.status === "error") {
    return (
      <EmptyState
        title="تعذّر تحميل الفرص الاستثمارية"
        description="تأكد من اتصال الخادم وحاول مرة أخرى."
      />
    );
  }

  if (data.status === "unavailable") {
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
          <h2 className="mb-1 text-base font-semibold text-bsr-text-primary">
            {section.label_ar}
          </h2>
          <p className="mb-bsr-4 text-xs text-bsr-text-secondary">{section.scoring_factor_ar}</p>
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
                  currentPrice={entry.current_price}
                  targetPrice={entry.target_price}
                  stopLoss={entry.stop_loss}
                  riskRewardRatio={entry.risk_reward_ratio}
                  timeHorizon={entry.time_horizon}
                  riskLevel={entry.risk_level}
                  expectedReturnPct={entry.expected_return_pct}
                  href={`/stocks/${encodeURIComponent(entry.symbol)}`}
                />
              ))}
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
