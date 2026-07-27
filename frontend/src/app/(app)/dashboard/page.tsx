import { AiStar } from "@/components/ai/AiStar";
import { EmptyState } from "@/components/patterns/EmptyState";
import { AiSignalCard } from "@/components/patterns/AiSignalCard";
import { RunScanButton } from "@/components/dashboard/RunScanButton";
import { ApiError } from "@/lib/api/client";
import { getAlerts, getMarketSummary, getRankings, getSectors } from "@/lib/api/market";
import type {
  Alert,
  MarketSummary,
  RankingEntry,
  SectorSummary,
} from "@/lib/api/types";
import type { RecommendationValue } from "@/components/badges/RecommendationBadge";

async function loadDashboardData(): Promise<
  | {
      available: true;
      summary: MarketSummary;
      sectors: SectorSummary[];
      alerts: Alert[];
      topBuy: RankingEntry[];
    }
  | { available: false }
> {
  try {
    const [summary, sectors, alerts, rankings] = await Promise.all([
      getMarketSummary(),
      getSectors(),
      getAlerts({ limit: 8 }),
      getRankings("TOP_BUY"),
    ]);
    return {
      available: true,
      summary,
      sectors: sectors.sectors,
      alerts: alerts.alerts,
      topBuy: rankings.rankings[0]?.entries.slice(0, 4) ?? [],
    };
  } catch (error) {
    if (error instanceof ApiError && error.code === "no_market_scan_data") {
      return { available: false };
    }
    throw error;
  }
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-bsr-1 rounded-bsr-md bg-bsr-surface-overlay px-bsr-4 py-bsr-3">
      <span className="text-xs text-bsr-text-secondary">{label}</span>
      <span className="bsr-numeric text-xl font-semibold text-bsr-text-primary">
        {value}
      </span>
    </div>
  );
}

export default async function DashboardPage() {
  const data = await loadDashboardData();

  if (!data.available) {
    return (
      <EmptyState
        title="لا توجد بيانات مسح للسوق بعد"
        description="شغّل أول مسح ذكي للسوق للحصول على نظرة عامة، توزيع القطاعات، والتنبيهات."
        action={<RunScanButton />}
      />
    );
  }

  const { summary, sectors, alerts, topBuy } = data;

  return (
    <div className="flex flex-col gap-bsr-6">
      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6">
        <div className="mb-bsr-4 flex items-center gap-bsr-2">
          <AiStar />
          <h1 className="text-lg font-semibold text-bsr-text-primary">
            نظرة عامة على السوق
          </h1>
        </div>
        <div className="grid grid-cols-2 gap-bsr-3 md:grid-cols-4">
          <StatTile label="عدد الأسهم الممسوحة" value={String(summary.symbols_scanned)} />
          <StatTile
            label="نسبة الصعود/الهبوط"
            value={
              summary.bull_bear_ratio != null
                ? summary.bull_bear_ratio.toFixed(2)
                : "—"
            }
          />
          <StatTile
            label="متوسط الثقة"
            value={
              summary.average_confidence != null
                ? `${Math.round(summary.average_confidence)}%`
                : "—"
            }
          />
          <StatTile
            label="إشارات شراء / بيع"
            value={`${summary.buy_signal_count} / ${summary.sell_signal_count}`}
          />
        </div>
      </section>

      <section>
        <div className="mb-bsr-4 flex items-center justify-between">
          <div className="flex items-center gap-bsr-2">
            <AiStar />
            <h2 className="text-base font-semibold text-bsr-text-primary">
              إشارات بصيرة AI اليوم
            </h2>
          </div>
          <a href="/opportunities" className="text-sm text-bsr-gold-500 hover:underline">
            عرض جميع الفرص
          </a>
        </div>
        {topBuy.length === 0 ? (
          <EmptyState title="لا توجد إشارات شراء بارزة في هذا المسح" />
        ) : (
          <div className="grid grid-cols-1 gap-bsr-4 sm:grid-cols-2 lg:grid-cols-4">
            {topBuy.map((entry) => (
              <AiSignalCard
                key={entry.symbol}
                symbol={entry.symbol}
                sector={entry.sector}
                recommendation={(entry.recommendation as RecommendationValue) ?? "HOLD"}
                confidence={entry.confidence}
                targetPrice={entry.target_price}
                expectedReturnPct={entry.expected_return_pct}
                href={`/stocks/${encodeURIComponent(entry.symbol)}`}
              />
            ))}
          </div>
        )}
      </section>

      <div className="grid grid-cols-1 gap-bsr-6 lg:grid-cols-2">
        <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6">
          <h2 className="mb-bsr-4 text-base font-semibold text-bsr-text-primary">
            توزيع القطاعات
          </h2>
          {sectors.length === 0 ? (
            <EmptyState title="لا توجد بيانات قطاعات لهذا المسح" />
          ) : (
            <div className="grid grid-cols-1 gap-bsr-2 sm:grid-cols-2">
              {sectors.map((sector) => (
                <div
                  key={sector.sector}
                  className="flex flex-col gap-bsr-2 rounded-bsr-md bg-bsr-surface-overlay px-bsr-3 py-bsr-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-bsr-text-primary">
                      {sector.sector}
                    </span>
                    <span className="bsr-numeric text-xs text-bsr-text-secondary">
                      {Math.round(sector.breadth * 100)}%
                    </span>
                  </div>
                  <div className="flex items-center gap-bsr-4 text-sm">
                    <span className="text-bsr-action-buy">
                      شراء {sector.buy_count}
                    </span>
                    <span className="text-bsr-action-sell">
                      بيع {sector.sell_count}
                    </span>
                    <span className="text-bsr-action-hold">
                      احتفاظ {sector.hold_count}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6">
          <h2 className="mb-bsr-4 text-base font-semibold text-bsr-text-primary">
            تنبيهات ذكية
          </h2>
          {alerts.length === 0 ? (
            <EmptyState title="لا توجد تنبيهات حالياً" />
          ) : (
            <ul className="flex flex-col gap-bsr-2">
              {alerts.map((alert, index) => (
                <li
                  key={`${alert.alert_type}-${alert.symbol ?? "market"}-${index}`}
                  className="rounded-bsr-md px-bsr-3 py-bsr-2 hover:bg-bsr-surface-overlay"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-bsr-text-primary">
                      {alert.symbol ?? alert.sector ?? "السوق العام"}
                    </span>
                    <span className="text-xs text-bsr-text-muted">
                      {alert.severity}
                    </span>
                  </div>
                  <p className="text-sm text-bsr-text-secondary">
                    {alert.message}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
