"use client";

import { useEffect, useState } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { EmptyState } from "@/components/patterns/EmptyState";
import { AiSignalCard } from "@/components/patterns/AiSignalCard";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { RunScanButton } from "@/components/dashboard/RunScanButton";
import { ApiError } from "@/lib/api/client";
import { getAlerts, getMarketSummary, getRankings, getScanRun, getSectors } from "@/lib/api/market";
import { ALERT_SEVERITY_LABELS, RUN_STATUS_LABELS } from "@/lib/market-intelligence-labels";
import type {
  Alert,
  MarketScanRun,
  MarketSummary,
  RankingEntry,
  SectorSummary,
} from "@/lib/api/types";
import type { RecommendationValue } from "@/components/badges/RecommendationBadge";

type DashboardData =
  | { status: "loading" }
  | { status: "unavailable" }
  | { status: "error" }
  | {
      status: "ready";
      summary: MarketSummary;
      sectors: SectorSummary[];
      alerts: Alert[];
      topBuy: RankingEntry[];
      run: MarketScanRun | null;
    };

// A Client Component, not a Server Component: apiFetch relies on the
// browser's own httpOnly session cookie (credentials: "include") --
// Next.js Server Component fetches run in a separate Node process
// with no browser cookie jar, so a server-rendered version of this
// page always 401s ("No access token was presented") against a real
// running backend, confirmed directly while verifying this screen
// end-to-end with a real login. Matches the same client-side pattern
// already used (and already working) by /scan, /watchlist, and the
// stock-detail page.
function useDashboardData(): DashboardData {
  const [data, setData] = useState<DashboardData>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [summary, sectors, alerts, rankings] = await Promise.all([
          getMarketSummary(),
          getSectors(),
          getAlerts({ limit: 8 }),
          getRankings("TOP_BUY"),
        ]);
        const run = summary.scan_run_id != null ? await getScanRun(summary.scan_run_id) : null;
        if (cancelled) return;
        setData({
          status: "ready",
          summary,
          sectors: sectors.sectors,
          alerts: alerts.alerts,
          topBuy: rankings.rankings[0]?.entries.slice(0, 4) ?? [],
          run,
        });
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

export default function DashboardPage() {
  const data = useDashboardData();

  if (data.status === "loading") {
    return <LoadingScreen />;
  }

  if (data.status === "error") {
    return (
      <EmptyState
        title="تعذّر تحميل نظرة السوق"
        description="تأكد من اتصال الخادم وحاول مرة أخرى."
      />
    );
  }

  if (data.status === "unavailable") {
    return (
      <EmptyState
        title="لا توجد بيانات مسح للسوق بعد"
        description="شغّل أول مسح ذكي للسوق للحصول على نظرة عامة، توزيع القطاعات، والتنبيهات."
        action={<RunScanButton />}
      />
    );
  }

  const { summary, sectors, alerts, topBuy, run } = data;

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

        {run ? (
          <div className="mt-bsr-3 grid grid-cols-2 gap-bsr-3 md:grid-cols-4">
            <StatTile label="حالة آخر مسح" value={RUN_STATUS_LABELS[run.status] ?? run.status} />
            <StatTile
              label="فشل / تخطّي"
              value={`${run.symbols_failed} / ${run.symbols_skipped}`}
            />
            <StatTile
              label="مدة المسح"
              value={
                run.duration_seconds != null
                  ? `${Math.round(run.duration_seconds)} ث`
                  : "—"
              }
            />
            <StatTile
              label="آخر تحديث"
              value={
                run.finished_at
                  ? new Date(run.finished_at).toLocaleString("ar-SA")
                  : "—"
              }
            />
          </div>
        ) : null}
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
                sector={entry.sector_ar ?? entry.sector}
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
                      {sector.sector_ar ?? sector.sector}
                    </span>
                    <span className="bsr-numeric text-xs text-bsr-text-secondary">
                      {Math.round(sector.breadth * 100)}%
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-bsr-4 text-sm">
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
                      {ALERT_SEVERITY_LABELS[alert.severity] ?? alert.severity}
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
