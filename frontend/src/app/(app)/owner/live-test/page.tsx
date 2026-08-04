"use client";

import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { AiSignalCard } from "@/components/patterns/AiSignalCard";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LiveScanPanel } from "@/components/dashboard/LiveScanPanel";
import { RunScanButton } from "@/components/dashboard/RunScanButton";
import { getMarketStatus, getRankings } from "@/lib/api/market";
import type { MarketStatus, RankingEntry } from "@/lib/api/types";
import type { RecommendationValue } from "@/components/badges/RecommendationBadge";

const STATUS_LABEL_CLASS: Record<string, string> = {
  OPEN: "text-bsr-market-up",
  PRE_OPEN_AUCTION: "text-bsr-action-watch",
  CLOSING_AUCTION: "text-bsr-action-watch",
  CLOSED: "text-bsr-text-secondary",
  PROVIDER_UNREACHABLE: "text-bsr-market-down",
};

function MarketStatusPill({ marketStatus }: { marketStatus: MarketStatus | null }) {
  if (!marketStatus) {
    return <p className="text-sm text-bsr-text-muted">تعذّر تحميل حالة السوق.</p>;
  }
  const colorClass = STATUS_LABEL_CLASS[marketStatus.status] ?? "text-bsr-text-secondary";
  return (
    <div className="flex flex-col gap-bsr-1 text-sm">
      <span className={`font-semibold ${colorClass}`}>{marketStatus.label_ar}</span>
      <span className="text-bsr-text-secondary">
        وقت الخادم (الرياض):{" "}
        <span className="bsr-numeric">{new Date(marketStatus.server_time_riyadh).toLocaleString("ar-SA")}</span>
      </span>
      {marketStatus.last_completed_session_date ? (
        <span className="text-bsr-text-secondary">
          آخر جلسة مكتملة:{" "}
          <span className="bsr-numeric">{marketStatus.last_completed_session_date}</span>
        </span>
      ) : null}
      <span className={marketStatus.provider_connected ? "text-bsr-market-up" : "text-bsr-market-down"}>
        {marketStatus.provider_connected ? "الاتصال بمزود البيانات سليم" : "تعذر الاتصال بمزود البيانات"}
      </span>
      <span className="text-xs text-bsr-text-muted">{marketStatus.holiday_calendar_disclosed_gap}</span>
    </div>
  );
}

function LiveTestPageInner() {
  const [marketStatus, setMarketStatus] = useState<MarketStatus | null>(null);
  const [topOpportunities, setTopOpportunities] = useState<RankingEntry[] | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadMarketStatus() {
      try {
        const ms = await getMarketStatus();
        if (!cancelled) setMarketStatus(ms);
      } catch {
        if (!cancelled) setMarketStatus(null);
      }
    }

    async function loadOpportunities() {
      try {
        const rankings = await getRankings("TOP_BUY");
        if (!cancelled) setTopOpportunities(rankings.rankings[0]?.entries ?? []);
      } catch {
        if (!cancelled) setTopOpportunities([]);
      }
    }

    loadMarketStatus();
    loadOpportunities();
    const interval = setInterval(() => {
      loadMarketStatus();
      loadOpportunities();
    }, 15000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="flex flex-col gap-bsr-4">
      <h1 className="text-lg font-semibold text-bsr-text-primary">اختبار السوق المباشر</h1>
      <p className="text-sm text-bsr-text-secondary">
        هذه الصفحة تستخدم بيانات الإنتاج الحقيقية فقط -- وليست وضع تجربة (demo). كل زر أو رقم هنا يعكس
        الحالة الفعلية للمنصة الآن.
      </p>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
        <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">حالة السوق الآن</h2>
        <MarketStatusPill marketStatus={marketStatus} />
      </section>

      <section className="flex flex-col items-start gap-bsr-2 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
        <h2 className="text-base font-semibold text-bsr-text-primary">تشغيل المسح</h2>
        <p className="text-sm text-bsr-text-secondary">
          يستخدم هذا الزر نفس مسار المسح الحقيقي الذي يستخدمه الجدول التلقائي، ولا يمكن تشغيل مسحين في
          نفس الوقت.
        </p>
        <RunScanButton label="بدء مسح حقيقي الآن" />
      </section>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
        <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">تقدّم المسح الحالي</h2>
        <LiveScanPanel />
      </section>

      <section>
        <h2 className="mb-bsr-4 text-base font-semibold text-bsr-text-primary">أفضل الفرص المؤهلة حالياً</h2>
        {topOpportunities == null ? (
          <p className="text-sm text-bsr-text-muted">جارٍ التحميل...</p>
        ) : topOpportunities.length === 0 ? (
          <EmptyState title="لا توجد فرص شراء مؤهلة حالياً" />
        ) : (
          <div className="grid grid-cols-1 gap-bsr-4 sm:grid-cols-2 lg:grid-cols-4">
            {topOpportunities.slice(0, 8).map((entry) => (
              <AiSignalCard
                key={entry.symbol}
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
    </div>
  );
}

export default function LiveTestPage() {
  return (
    <RequireStaff>
      <LiveTestPageInner />
    </RequireStaff>
  );
}
