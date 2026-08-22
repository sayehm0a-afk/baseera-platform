"use client";

import { useEffect, useState } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { AiSignalCard } from "@/components/patterns/AiSignalCard";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import {
  RecommendationBadge,
  type RecommendationValue,
} from "@/components/badges/RecommendationBadge";
import { getPortfolioNewsAlerts, refreshPortfolioNewsAlerts } from "@/lib/api/portfolio";
import type { PortfolioAnalysis, PortfolioNewsAlert } from "@/lib/api/portfolio-types";
import {
  HEALTH_BAND_LABELS,
  POSITION_ACTION_LABELS,
  RISK_LEVEL_LABELS,
  healthBandColorClass,
} from "@/lib/portfolio-labels";
import { PORTFOLIO_ALERT_TYPE_LABELS, alertSeverityColorClass } from "@/lib/news-labels";

function Stat({ label, value, valueClassName }: { label: string; value: string; valueClassName?: string }) {
  return (
    <div className="flex flex-col gap-bsr-1 rounded-bsr-md bg-bsr-surface-overlay px-bsr-4 py-bsr-3">
      <span className="text-xs text-bsr-text-secondary">{label}</span>
      <span className={`bsr-numeric text-xl font-semibold ${valueClassName ?? "text-bsr-text-primary"}`}>
        {value}
      </span>
    </div>
  );
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6">
      <h2 className="mb-bsr-4 text-base font-semibold text-bsr-text-primary">{title}</h2>
      {children}
    </section>
  );
}

function NewsAlertsSection({ portfolioId }: { portfolioId: number }) {
  const [alerts, setAlerts] = useState<PortfolioNewsAlert[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPortfolioNewsAlerts(portfolioId)
      .then((result) => {
        if (!cancelled) setAlerts(result.alerts);
      })
      .catch(() => {
        if (!cancelled) setError("تعذّر تحميل تنبيهات الأخبار.");
      });
    return () => {
      cancelled = true;
    };
  }, [portfolioId]);

  async function handleRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      await refreshPortfolioNewsAlerts(portfolioId);
      const result = await getPortfolioNewsAlerts(portfolioId);
      setAlerts(result.alerts);
    } catch {
      setError("تعذّر تحديث تنبيهات الأخبار.");
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <SectionCard title="تنبيهات الأخبار">
      <div className="mb-bsr-4 flex items-center justify-between">
        <p className="text-sm text-bsr-text-secondary">
          تنبيهات مبنية على أخبار محللة تخص المراكز الحالية في المحفظة.
        </p>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={refreshing}
          className="whitespace-nowrap rounded-bsr-md border border-bsr-border-subtle px-bsr-4 py-bsr-2 text-sm text-bsr-text-primary hover:bg-bsr-surface-overlay disabled:opacity-50"
        >
          {refreshing ? "جارٍ التحديث..." : "تحديث التنبيهات"}
        </button>
      </div>

      {alerts === null && !error ? <LoadingScreen /> : null}

      {error ? <p className="text-sm text-bsr-market-down">{error}</p> : null}

      {alerts !== null && alerts.length === 0 ? (
        <EmptyState title="لا توجد تنبيهات أخبار حالياً لمراكز هذه المحفظة" />
      ) : null}

      {alerts !== null && alerts.length > 0 ? (
        <ul className="flex flex-col divide-y divide-bsr-border-subtle">
          {alerts.map((alert) => (
            <li key={alert.id} className="flex flex-col gap-bsr-1 py-bsr-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-bsr-2">
                  <span className="bsr-numeric font-semibold text-bsr-text-primary">
                    {alert.symbol}
                  </span>
                  <span
                    className={`rounded-bsr-full px-bsr-3 py-1 text-xs font-medium ${alertSeverityColorClass(alert.severity)}`}
                  >
                    {PORTFOLIO_ALERT_TYPE_LABELS[alert.alert_type] ?? alert.alert_type}
                  </span>
                </div>
                <span className="text-xs text-bsr-text-muted">
                  {new Date(alert.generated_at).toLocaleString("ar-SA", { calendar: "gregory" })}
                </span>
              </div>
              <p className="text-sm text-bsr-text-secondary">{alert.message_ar ?? alert.message}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </SectionCard>
  );
}

interface PortfolioDetailProps {
  analysis: PortfolioAnalysis;
  onEdit: () => void;
  onReset: () => void;
}

export function PortfolioDetail({ analysis, onEdit, onReset }: PortfolioDetailProps) {
  const { health_score, risk_profile, diversification, concentration, allocation, sector_exposure, recommendations } = analysis;

  return (
    <div className="flex flex-col gap-bsr-6">
      <div className="flex flex-wrap items-center justify-between gap-bsr-3">
        <div>
          <h1 className="text-lg font-semibold text-bsr-text-primary">{analysis.name}</h1>
          <p className="text-sm text-bsr-text-secondary">
            آخر تحليل: {new Date(analysis.generated_at).toLocaleString("ar-SA", { calendar: "gregory" })}
          </p>
        </div>
        <div className="flex gap-bsr-2">
          <button
            type="button"
            onClick={onEdit}
            className="rounded-bsr-md border border-bsr-border-subtle px-bsr-4 py-bsr-2 text-sm text-bsr-text-primary hover:bg-bsr-surface-overlay"
          >
            تعديل المراكز
          </button>
          <button
            type="button"
            onClick={onReset}
            className="rounded-bsr-md px-bsr-4 py-bsr-2 text-sm text-bsr-text-secondary hover:bg-bsr-surface-overlay"
          >
            محفظة جديدة
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-bsr-3 md:grid-cols-4">
        <Stat label="القيمة الإجمالية" value={analysis.total_value.toFixed(2)} />
        <Stat label="الرصيد النقدي" value={analysis.cash.toFixed(2)} />
        <Stat
          label="صحة المحفظة"
          value={`${Math.round(health_score.score)} / 100`}
          valueClassName={healthBandColorClass(health_score.band)}
        />
        <Stat
          label="مستوى المخاطرة"
          value={RISK_LEVEL_LABELS[risk_profile.risk_level] ?? risk_profile.risk_level}
        />
      </div>

      <SectionCard title="المراكز">
        {analysis.holdings.length === 0 ? (
          <EmptyState title="لا توجد مراكز في هذه المحفظة" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-bsr-border-subtle text-start text-bsr-text-secondary">
                  <th className="px-bsr-2 py-bsr-2 text-start">الرمز</th>
                  <th className="px-bsr-2 py-bsr-2 text-start">الكمية</th>
                  <th className="px-bsr-2 py-bsr-2 text-start">السعر الحالي</th>
                  <th className="px-bsr-2 py-bsr-2 text-start">القيمة السوقية</th>
                  <th className="px-bsr-2 py-bsr-2 text-start">الوزن</th>
                  <th className="px-bsr-2 py-bsr-2 text-start">ربح/خسارة غير محققة</th>
                  <th className="px-bsr-2 py-bsr-2 text-start">التوصية</th>
                </tr>
              </thead>
              <tbody>
                {analysis.holdings.map((holding) => (
                  <tr key={holding.symbol} className="border-b border-bsr-border-subtle last:border-0">
                    <td className="bsr-numeric px-bsr-2 py-bsr-2 font-semibold text-bsr-text-primary">
                      {holding.symbol}
                      {!holding.available ? (
                        <span className="ms-bsr-2 text-xs text-bsr-text-muted">(لا تتوفر بيانات)</span>
                      ) : null}
                    </td>
                    <td className="bsr-numeric px-bsr-2 py-bsr-2">{holding.quantity}</td>
                    <td className="bsr-numeric px-bsr-2 py-bsr-2">
                      {holding.latest_price != null ? holding.latest_price.toFixed(2) : "—"}
                    </td>
                    <td className="bsr-numeric px-bsr-2 py-bsr-2">
                      {holding.market_value != null ? holding.market_value.toFixed(2) : "—"}
                    </td>
                    <td className="bsr-numeric px-bsr-2 py-bsr-2">
                      {holding.weight != null ? `${(holding.weight * 100).toFixed(1)}%` : "—"}
                    </td>
                    <td
                      className={`bsr-numeric px-bsr-2 py-bsr-2 ${
                        (holding.unrealized_pnl ?? 0) >= 0 ? "text-bsr-market-up" : "text-bsr-market-down"
                      }`}
                    >
                      {holding.unrealized_pnl != null ? holding.unrealized_pnl.toFixed(2) : "—"}
                    </td>
                    <td className="px-bsr-2 py-bsr-2">
                      {holding.recommendation ? (
                        <RecommendationBadge value={holding.recommendation as RecommendationValue} />
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <NewsAlertsSection portfolioId={analysis.portfolio_id} />

      <div className="grid grid-cols-1 gap-bsr-6 lg:grid-cols-2">
        <SectionCard title="التوزيع القطاعي">
          {sector_exposure.length === 0 ? (
            <EmptyState title="لا تتوفر بيانات قطاعات" />
          ) : (
            <ul className="flex flex-col gap-bsr-2">
              {sector_exposure.map((sector) => (
                <li key={sector.sector} className="flex items-center justify-between">
                  <span className="text-sm text-bsr-text-primary">{sector.sector_ar ?? sector.sector}</span>
                  <div className="flex flex-1 items-center gap-bsr-2 px-bsr-4">
                    <div className="h-2 flex-1 overflow-hidden rounded-bsr-full bg-bsr-navy-700">
                      <div
                        className="h-full rounded-bsr-full bg-bsr-gold-500"
                        style={{ width: `${Math.min(100, sector.weight * 100)}%` }}
                      />
                    </div>
                  </div>
                  <span className="bsr-numeric text-sm text-bsr-text-secondary">
                    {(sector.weight * 100).toFixed(1)}%
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-bsr-4 text-xs text-bsr-text-muted">
            النقد: {(allocation.cash_weight * 100).toFixed(1)}% من القيمة الإجمالية
          </p>
        </SectionCard>

        <SectionCard title="التنويع والتركز">
          <div className="flex flex-col gap-bsr-2 text-sm">
            <div className="flex justify-between">
              <span className="text-bsr-text-secondary">درجة التنويع</span>
              <span className="bsr-numeric text-bsr-text-primary">
                {diversification.score.toFixed(0)} / 100
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-bsr-text-secondary">عدد المراكز الفعّال</span>
              <span className="bsr-numeric text-bsr-text-primary">
                {diversification.effective_number_of_holdings.toFixed(1)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-bsr-text-secondary">أكبر مركز</span>
              <span className="bsr-numeric text-bsr-text-primary">
                {concentration.largest_position_symbol ?? "—"}
                {concentration.largest_position_weight != null
                  ? ` (${(concentration.largest_position_weight * 100).toFixed(1)}%)`
                  : ""}
              </span>
            </div>
            {concentration.is_concentrated ? (
              <p className="rounded-bsr-md bg-bsr-action-watch/15 px-bsr-3 py-bsr-2 text-bsr-action-watch">
                المحفظة مُركّزة بشكل ملحوظ في عدد محدود من المراكز.
              </p>
            ) : null}
            <p className="text-bsr-text-secondary">{diversification.narrative}</p>
          </div>
        </SectionCard>
      </div>

      <SectionCard title="ملف المخاطر">
        <div className="grid grid-cols-2 gap-bsr-3 md:grid-cols-4">
          <Stat label="درجة المخاطرة" value={risk_profile.risk_score.toFixed(0)} />
          <Stat
            label="التقلب السنوي المتوقع"
            value={
              risk_profile.expected_volatility_annualized_pct != null
                ? `${risk_profile.expected_volatility_annualized_pct.toFixed(1)}%`
                : "—"
            }
          />
          <Stat
            label="أقصى انخفاض متوقع"
            value={
              risk_profile.estimated_max_drawdown_pct != null
                ? `${risk_profile.estimated_max_drawdown_pct.toFixed(1)}%`
                : "—"
            }
          />
          <Stat label="بيتا المحفظة" value={risk_profile.portfolio_beta != null ? risk_profile.portfolio_beta.toFixed(2) : "غير متاح"} />
        </div>
        {risk_profile.portfolio_beta == null && risk_profile.beta_unavailable_reason ? (
          <p className="mt-bsr-3 text-xs text-bsr-text-muted">{risk_profile.beta_unavailable_reason}</p>
        ) : null}
        <p className="mt-bsr-4 text-sm text-bsr-text-secondary">{risk_profile.narrative}</p>
      </SectionCard>

      <SectionCard title="توصيات إعادة التوازن">
        {recommendations.rebalance_actions.length === 0 ? (
          <EmptyState title="لا توجد إجراءات إعادة توازن مقترحة حالياً" />
        ) : (
          <ul className="flex flex-col divide-y divide-bsr-border-subtle">
            {recommendations.rebalance_actions.map((action) => (
              <li key={action.symbol} className="flex flex-col gap-bsr-1 py-bsr-3">
                <div className="flex items-center justify-between">
                  <span className="bsr-numeric font-semibold text-bsr-text-primary">
                    {action.symbol}
                  </span>
                  <span className="rounded-bsr-full bg-bsr-surface-overlay px-bsr-3 py-1 text-xs text-bsr-text-primary">
                    {POSITION_ACTION_LABELS[action.action] ?? action.action}
                  </span>
                </div>
                <p className="text-sm text-bsr-text-secondary">{action.rationale}</p>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      {recommendations.new_buy_opportunities.length > 0 ? (
        <section>
          <div className="mb-bsr-4 flex items-center gap-bsr-2">
            <AiStar />
            <h2 className="text-base font-semibold text-bsr-text-primary">فرص شراء جديدة</h2>
          </div>
          <div className="grid grid-cols-1 gap-bsr-4 sm:grid-cols-2 lg:grid-cols-4">
            {recommendations.new_buy_opportunities.map((opportunity) => (
              <AiSignalCard
                key={opportunity.symbol}
                symbol={opportunity.symbol}
                sector={opportunity.sector_ar ?? opportunity.sector}
                recommendation={opportunity.recommendation as RecommendationValue}
                confidence={opportunity.confidence}
                href={`/stocks/${encodeURIComponent(opportunity.symbol)}`}
              />
            ))}
          </div>
        </section>
      ) : null}

      <div className="grid grid-cols-1 gap-bsr-6 lg:grid-cols-2">
        <SectionCard title="توصية السيولة النقدية">
          <div className="flex flex-col gap-bsr-2 text-sm">
            <div className="flex justify-between">
              <span className="text-bsr-text-secondary">النسبة النقدية الحالية</span>
              <span className="bsr-numeric text-bsr-text-primary">
                {(recommendations.cash_recommendation.current_cash_pct * 100).toFixed(1)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-bsr-text-secondary">النطاق المستهدف</span>
              <span className="bsr-numeric text-bsr-text-primary">
                {(recommendations.cash_recommendation.recommended_cash_pct_min * 100).toFixed(0)}% –{" "}
                {(recommendations.cash_recommendation.recommended_cash_pct_max * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-bsr-text-secondary">{recommendations.cash_recommendation.rationale}</p>
          </div>
        </SectionCard>

        <SectionCard title="توصيات التحسين">
          {recommendations.optimization_recommendations.length === 0 ? (
            <EmptyState title="لا توجد توصيات تحسين إضافية" />
          ) : (
            <ol className="flex flex-col gap-bsr-3">
              {recommendations.optimization_recommendations
                .slice()
                .sort((a, b) => a.priority - b.priority)
                .map((rec) => (
                  <li key={rec.title} className="flex flex-col gap-1">
                    <span className="text-sm font-medium text-bsr-text-primary">{rec.title}</span>
                    <span className="text-sm text-bsr-text-secondary">{rec.rationale}</span>
                  </li>
                ))}
            </ol>
          )}
        </SectionCard>
      </div>

      <SectionCard title="ملخص الصحة العام">
        <p className={`mb-bsr-2 text-sm font-semibold ${healthBandColorClass(health_score.band)}`}>
          {HEALTH_BAND_LABELS[health_score.band] ?? health_score.band}
        </p>
        <p className="mb-bsr-4 text-sm text-bsr-text-secondary">{health_score.narrative}</p>
        <div className="grid grid-cols-2 gap-bsr-2 sm:grid-cols-3">
          {Object.entries(health_score.components).map(([key, value]) => (
            <div key={key} className="flex items-center justify-between rounded-bsr-md bg-bsr-surface-overlay px-bsr-3 py-bsr-2 text-sm">
              <span className="text-bsr-text-secondary">{key}</span>
              <span className="bsr-numeric text-bsr-text-primary">{value.toFixed(0)}</span>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
