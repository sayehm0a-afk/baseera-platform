"use client";

import { useMemo, useState } from "react";
import { AnalystReportView } from "@/components/ai/AnalystReportView";
import { ConfidenceBar } from "@/components/ai/ConfidenceBar";
import { DecisionBadge } from "@/components/badges/DecisionBadge";
import { RecommendationBadge, type RecommendationValue } from "@/components/badges/RecommendationBadge";
import { PriceChart, type MovingAverageOverlay, type PriceLevel } from "@/components/charts/PriceChart";
import { CommitteePanel } from "@/components/committee/CommitteePanel";
import { BeginnerSummaryCard } from "@/components/decision/BeginnerSummaryCard";
import { DecisionTransparencyPanel } from "@/components/decision/DecisionTransparencyPanel";
import { ExecutiveDecisionCard } from "@/components/decision/ExecutiveDecisionCard";
import { CategoryTabs } from "@/components/patterns/CategoryTabs";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { RecommendationHistoryPanel } from "@/components/recommendation-history/RecommendationHistoryPanel";
import { AddToWatchlistButton } from "@/components/watchlist/AddToWatchlistButton";
import {
  getAnalystReport,
  getDecision,
  getDecisionV2,
  getFundamentalAnalysis,
  getHistory,
  getQuote,
  getStock,
  getTechnicalAnalysis,
} from "@/lib/api/stocks";
import { useResource } from "@/lib/hooks/useResource";
import { POSITION_SIZE_LABELS, RISK_LEVEL_LABELS, TIME_HORIZON_LABELS } from "@/lib/portfolio-labels";
import { formatIndicatorValue, formatRatioValue } from "@/lib/stock-detail-format";

const TABS = ["overview", "technical", "fundamental", "ai", "history"] as const;
type Tab = (typeof TABS)[number];

const TAB_LABELS: Record<Tab, string> = {
  overview: "نظرة عامة",
  technical: "التحليل الفني",
  fundamental: "التحليل الأساسي",
  ai: "توصية الذكاء الاصطناعي",
  history: "سجل التوصيات",
};

/** True indicator names -> Arabic display labels for the values
 * src/analysis/registry.py actually registers (verified against
 * IndicatorOutput.latest()'s real shape, not guessed) -- keys not
 * listed here still render, just under their raw registry name, so a
 * newly-registered indicator is never silently dropped. */
const INDICATOR_LABELS: Record<string, string> = {
  sma_20: "المتوسط المتحرك البسيط (20)",
  ema_20: "المتوسط المتحرك الأسي (20)",
  rsi_14: "مؤشر القوة النسبية (14)",
  adx_14: "مؤشر الاتجاه المتوسط (14)",
  atr_14: "المدى الحقيقي المتوسط (14)",
  macd: "MACD",
  bollinger: "نطاقات بولينجر",
  stochastic_14_3_3: "مذبذب ستوكاستيك",
  supertrend: "سوبرترند",
  obv: "حجم التداول المتوازن (OBV)",
  volume_sma_20: "متوسط حجم التداول (20)",
  vwap_20: "متوسط السعر المرجّح بالحجم (20)",
  support_resistance: "مستويات الدعم والمقاومة",
  fibonacci_retracement: "مستويات فيبوناتشي",
  volume_profile: "توزيع حجم التداول",
  candlestick_patterns: "أنماط الشموع اليابانية",
};

export function StockDetailClient({ symbol }: { symbol: string }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [beginnerMode, setBeginnerMode] = useState(false);

  const stock = useResource(symbol, getStock);
  const quote = useResource(symbol, getQuote);
  const history = useResource(symbol, (s) => getHistory(s));
  const technical = useResource(symbol, getTechnicalAnalysis);
  const decision = useResource(symbol, getDecision);
  const decisionV2 = useResource(symbol, getDecisionV2);
  const fundamentals = useResource(symbol, getFundamentalAnalysis);
  const analystReport = useResource(symbol, getAnalystReport);

  const priceLevels = useMemo<PriceLevel[]>(() => {
    const levels: PriceLevel[] = [];

    // Decision V2's entry zone/stop/targets take priority -- they're
    // the gate-checked, publication-safe numbers; the legacy /decision
    // single-point target/stop below is only a fallback when V2 has no
    // decision yet (e.g. insufficient data for the newer engine).
    if (decisionV2.status === "ready") {
      const d = decisionV2.data;
      if (d.entry_zone_low != null) levels.push({ price: d.entry_zone_low, label: "أسفل نطاق الدخول", color: "#3E8ED0" });
      if (d.entry_zone_high != null) levels.push({ price: d.entry_zone_high, label: "أعلى نطاق الدخول", color: "#3E8ED0" });
      if (d.stop_loss != null) levels.push({ price: d.stop_loss, label: "وقف الخسارة", color: "#E5484D" });
      if (d.target_1 != null) levels.push({ price: d.target_1, label: "الهدف الأول", color: "#1FA97A" });
      if (d.target_2 != null) levels.push({ price: d.target_2, label: "الهدف الثاني", color: "#1FA97A" });
      if (d.target_3 != null) levels.push({ price: d.target_3, label: "الهدف الثالث", color: "#1FA97A" });
      // Phase 2F: breakout/breakdown/invalidation are already computed
      // by Decision Engine V2 (Phase 2A) but were never drawn on the
      // chart -- real levels, not derived here.
      if (d.breakout_level != null) {
        levels.push({ price: d.breakout_level, label: "مستوى الاختراق", color: "#8B5CF6" });
      }
      if (d.breakdown_level != null) {
        levels.push({ price: d.breakdown_level, label: "مستوى الانكسار", color: "#8B5CF6" });
      }
      if (d.invalidation_price != null && d.invalidation_price !== d.stop_loss) {
        levels.push({ price: d.invalidation_price, label: "سعر إلغاء القرار", color: "#B98900" });
      }
    } else if (decision.status === "ready") {
      if (decision.data.target_price != null) {
        levels.push({ price: decision.data.target_price, label: "الهدف", color: "#1FA97A" });
      }
      if (decision.data.stop_loss != null) {
        levels.push({ price: decision.data.stop_loss, label: "وقف الخسارة", color: "#E5484D" });
      }
    }

    if (quote.status === "ready") {
      levels.push({ price: quote.data.close, label: "السعر المرجعي", color: "#C9A24B" });
    }

    // Support/resistance -- real indicator output from
    // src.analysis.indicators.support_resistance, already returned by
    // GET /technical under indicators.support_resistance; only the two
    // levels nearest the current price are drawn to keep the chart
    // legible. Never fabricated here -- absent entirely when the
    // indicator wasn't computed (e.g. insufficient history).
    if (technical.status === "ready" && quote.status === "ready") {
      const sr = technical.data.indicators["support_resistance"] as
        | { support?: number[]; resistance?: number[] }
        | undefined;
      const price = quote.data.close;
      const nearestBelow = (sr?.support ?? [])
        .filter((p) => p < price)
        .sort((a, b) => b - a)
        .slice(0, 2);
      const nearestAbove = (sr?.resistance ?? [])
        .filter((p) => p > price)
        .sort((a, b) => a - b)
        .slice(0, 2);
      nearestBelow.forEach((p, i) =>
        levels.push({ price: p, label: i === 0 ? "دعم" : "دعم إضافي", color: "#3E8ED0" })
      );
      nearestAbove.forEach((p, i) =>
        levels.push({ price: p, label: i === 0 ? "مقاومة" : "مقاومة إضافية", color: "#B98900" })
      );
    }

    return levels;
  }, [decision, decisionV2, quote, technical]);

  // Phase 2F: real per-bar moving-average overlays (GET /technical's
  // `moving_averages`) -- absent entirely when the indicator wasn't
  // computed, never interpolated or fabricated here.
  const movingAverages = useMemo<MovingAverageOverlay[]>(() => {
    if (technical.status !== "ready") return [];
    const overlays: { name: string; label: string; color: string }[] = [
      { name: "sma_20", label: "المتوسط المتحرك البسيط (20)", color: "#3E8ED0" },
      { name: "ema_20", label: "المتوسط المتحرك الأسي (20)", color: "#C9A24B" },
      { name: "vwap_20", label: "متوسط السعر المرجّح بالحجم (20)", color: "#8B5CF6" },
    ];
    return overlays
      .map(({ name, label, color }) => ({
        name,
        label,
        color,
        points: technical.data.moving_averages[name] ?? [],
      }))
      .filter((overlay) => overlay.points.length > 0);
  }, [technical]);

  if (stock.status === "loading" || quote.status === "loading") {
    return <LoadingScreen />;
  }

  if (stock.status === "not_found") {
    return (
      <EmptyState
        title="لم يتم العثور على هذا الرمز"
        description={`لا يوجد سهم مسجّل بالرمز "${symbol}". تحقق من الرمز وحاول مرة أخرى.`}
      />
    );
  }

  if (stock.status === "error" || stock.status === "unavailable") {
    return (
      <EmptyState
        title="تعذّر تحميل بيانات السهم"
        description="حدث خطأ أثناء الاتصال بالخادم. حاول مرة أخرى بعد قليل."
      />
    );
  }

  if (stock.status !== "ready") {
    return <LoadingScreen />;
  }

  const stockData = stock.data;
  const displayName = stockData.name_ar ?? stockData.name_en;
  const sectorAr =
    (decisionV2.status === "ready" ? decisionV2.data.sector_ar : null) ?? stockData.sector_ar;
  const decisionRec =
    decision.status === "ready" ? (decision.data.recommendation as RecommendationValue) : null;

  return (
    <div className="flex flex-col gap-bsr-4">
      {/* Header */}
      <div className="flex flex-col gap-bsr-2 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
        <div className="flex flex-wrap items-start justify-between gap-bsr-2">
          <div>
            <h1 className="text-lg font-semibold text-bsr-text-primary">{displayName}</h1>
            <p className="bsr-numeric text-sm text-bsr-text-secondary">
              {stockData.symbol}
              {sectorAr ? ` · ${sectorAr}` : stockData.sector ? ` · ${stockData.sector}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-bsr-3">
            {decisionV2.status === "ready" ? (
              <DecisionBadge value={decisionV2.data.decision} labelAr={decisionV2.data.decision_label_ar} />
            ) : decisionRec ? (
              <RecommendationBadge value={decisionRec} />
            ) : null}
            <AddToWatchlistButton symbol={symbol} />
          </div>
        </div>

        {quote.status === "ready" ? (
          <div className="flex flex-wrap items-baseline gap-bsr-3">
            <span className="bsr-numeric text-2xl font-bold text-bsr-text-primary">
              {quote.data.close.toFixed(2)}
            </span>
            <span className="text-sm text-bsr-text-secondary">{stockData.currency}</span>
            {quote.data.is_synthetic ? (
              <span className="rounded-bsr-full bg-bsr-action-watch/15 px-bsr-3 py-bsr-1 text-xs text-bsr-action-watch">
                بيانات تجريبية (غير حقيقية) -- المصدر: {quote.data.source}
              </span>
            ) : (
              <span className="text-xs text-bsr-text-secondary">المصدر: {quote.data.source}</span>
            )}
            <span className="bsr-numeric text-xs text-bsr-text-secondary">
              آخر تحديث: {new Date(quote.data.timestamp).toLocaleString("ar-SA")}
            </span>
          </div>
        ) : quote.status === "unavailable" ? (
          <p className="text-sm text-bsr-text-secondary">
            تعذّر تحميل آخر سعر متداول -- مزود بيانات السوق غير متاح حالياً.
          </p>
        ) : (
          <p className="text-sm text-bsr-text-secondary">تعذّر تحميل آخر سعر متداول.</p>
        )}
      </div>

      {/* Executive decision (Decision Engine V2, Phase 1 foundation) --
          plus the Phase 2E deep-dive transparency panel underneath it,
          for every field DecisionV2 already computes that the
          immediate-answer card above deliberately keeps out of the way.
          Phase 2G adds an opt-in beginner-mode summary alongside these,
          never replacing them. */}
      {decisionV2.status === "ready" ? (
        <>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => setBeginnerMode((prev) => !prev)}
              className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-raised px-bsr-3 py-1 text-xs font-semibold text-bsr-text-secondary"
            >
              {beginnerMode ? "إخفاء العرض المبسّط" : "عرض مبسّط (للمبتدئين)"}
            </button>
          </div>
          {beginnerMode ? <BeginnerSummaryCard decision={decisionV2.data} /> : null}
          <ExecutiveDecisionCard decision={decisionV2.data} />
          <DecisionTransparencyPanel decision={decisionV2.data} />
          <CommitteePanel committee={decisionV2.data.committee} />
        </>
      ) : decisionV2.status === "loading" ? (
        <LoadingScreen />
      ) : decisionV2.status === "insufficient_data" ? (
        <EmptyState
          title="البيانات غير كافية لإصدار قرار"
          description="لا تتوفر بيانات فنية أو مالية كافية لهذا السهم بعد لتشغيل محرك القرار الإصدار الثاني."
        />
      ) : decisionV2.status === "unavailable" ? (
        <EmptyState
          title="تعذّر تحميل قرار الذكاء الاصطناعي"
          description="مزود بيانات السوق غير متاح حالياً، ويتوقف محرك القرار عن إصدار توصيات جديدة إلى حين استعادة الاتصال به. هذا لا يعني عدم كفاية البيانات التاريخية لهذا السهم."
        />
      ) : (
        <EmptyState
          title="تعذّر تحميل قرار الذكاء الاصطناعي"
          description="حدث خطأ أثناء الاتصال بالخادم. حاول مرة أخرى بعد قليل."
        />
      )}

      {/* Chart */}
      <div id="chart" className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-3">
        {history.status === "loading" ? <LoadingScreen /> : null}
        {history.status === "insufficient_data" || history.status === "not_found" ? (
          <EmptyState
            title="لا تتوفر بيانات تاريخية كافية"
            description="لم يتم تجميع بيانات أسعار كافية لعرض الرسم البياني لهذا السهم بعد."
          />
        ) : null}
        {history.status === "unavailable" || history.status === "error" ? (
          <EmptyState title="تعذّر تحميل الرسم البياني" description="حاول مرة أخرى بعد قليل." />
        ) : null}
        {history.status === "ready" ? (
          history.data.bars.length === 0 ? (
            <EmptyState title="لا تتوفر بيانات تاريخية بعد لهذا السهم" />
          ) : (
            <PriceChart bars={history.data.bars} levels={priceLevels} movingAverages={movingAverages} />
          )
        ) : null}
      </div>

      <CategoryTabs categories={[...TABS]} labels={TAB_LABELS} active={tab} onChange={(t) => setTab(t as Tab)} />

      {tab === "overview" ? (
        decision.status === "ready" ? (
          <div className="flex flex-col gap-bsr-2">
          <p className="text-xs text-bsr-text-muted">تفاصيل إضافية من محرك القرار الأساسي (حجم المركز المقترح).</p>
          <div className="grid grid-cols-2 gap-bsr-3 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 sm:grid-cols-4">
            <div>
              <p className="text-xs text-bsr-text-secondary">الثقة</p>
              <p className="bsr-numeric text-base font-semibold text-bsr-text-primary">
                {Math.round(decision.data.confidence)}%
              </p>
              <ConfidenceBar confidence={decision.data.confidence} className="mt-bsr-1" />
            </div>
            <div>
              <p className="text-xs text-bsr-text-secondary">الأفق الزمني</p>
              <p className="text-base font-semibold text-bsr-text-primary">
                {TIME_HORIZON_LABELS[decision.data.time_horizon] ?? decision.data.time_horizon}
              </p>
            </div>
            <div>
              <p className="text-xs text-bsr-text-secondary">مستوى المخاطرة</p>
              <p className="text-base font-semibold text-bsr-text-primary">
                {RISK_LEVEL_LABELS[decision.data.risk_level] ?? decision.data.risk_level}
              </p>
            </div>
            <div>
              <p className="text-xs text-bsr-text-secondary">حجم المركز المقترح</p>
              <p className="text-base font-semibold text-bsr-text-primary">
                {POSITION_SIZE_LABELS[decision.data.position_size] ?? decision.data.position_size}
              </p>
            </div>
          </div>
          </div>
        ) : decision.status === "loading" ? (
          <LoadingScreen />
        ) : decision.status === "insufficient_data" ? (
          <EmptyState
            title="لا تتوفر توصية آلية لهذا السهم بعد"
            description="غالباً بسبب نقص بيانات تاريخية كافية لتشغيل محرك القرار."
          />
        ) : decision.status === "unavailable" ? (
          <EmptyState
            title="تعذّر تحميل التوصية الآلية"
            description="مزود بيانات السوق غير متاح حالياً. حاول مرة أخرى بعد استعادة الاتصال."
          />
        ) : (
          <EmptyState
            title="تعذّر تحميل التوصية الآلية"
            description="حدث خطأ أثناء الاتصال بالخادم. حاول مرة أخرى بعد قليل."
          />
        )
      ) : null}

      {tab === "technical" ? (
        technical.status === "ready" ? (
          <div className="grid grid-cols-1 gap-bsr-2 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 sm:grid-cols-2">
            {Object.entries(technical.data.indicators).map(([name, value]) => (
              <div key={name} className="flex items-center justify-between border-b border-bsr-border-subtle py-bsr-2 last:border-0">
                <span className="text-sm text-bsr-text-secondary">{INDICATOR_LABELS[name] ?? name}</span>
                <span className="bsr-numeric text-sm font-medium text-bsr-text-primary">
                  {formatIndicatorValue(value)}
                </span>
              </div>
            ))}
          </div>
        ) : technical.status === "loading" ? (
          <LoadingScreen />
        ) : technical.status === "insufficient_data" ? (
          <EmptyState title="لا تتوفر مؤشرات فنية كافية لهذا السهم بعد" />
        ) : technical.status === "unavailable" ? (
          <EmptyState
            title="تعذّر تحميل المؤشرات الفنية"
            description="مزود بيانات السوق غير متاح حالياً. حاول مرة أخرى بعد استعادة الاتصال."
          />
        ) : (
          <EmptyState
            title="تعذّر تحميل المؤشرات الفنية"
            description="حدث خطأ أثناء الاتصال بالخادم. حاول مرة أخرى بعد قليل."
          />
        )
      ) : null}

      {tab === "fundamental" ? (
        fundamentals.status === "ready" ? (
          <div className="flex flex-col gap-bsr-3">
            {fundamentals.data.is_synthetic ? (
              <p className="rounded-bsr-md bg-bsr-action-watch/15 px-bsr-3 py-bsr-2 text-xs text-bsr-action-watch">
                بيانات مالية تجريبية (غير حقيقية) -- المصدر: {fundamentals.data.source}
              </p>
            ) : null}
            <div className="grid grid-cols-1 gap-bsr-2 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 sm:grid-cols-2">
              {Object.entries(fundamentals.data.ratios).map(([name, value]) => (
                <div key={name} className="flex items-center justify-between border-b border-bsr-border-subtle py-bsr-2 last:border-0">
                  <span className="text-sm text-bsr-text-secondary">{name}</span>
                  <span className="bsr-numeric text-sm font-medium text-bsr-text-primary">
                    {formatRatioValue(value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : fundamentals.status === "loading" ? (
          <LoadingScreen />
        ) : fundamentals.status === "insufficient_data" ? (
          <EmptyState title="لا تتوفر بيانات مالية كافية لهذا السهم بعد" />
        ) : fundamentals.status === "unavailable" ? (
          <EmptyState
            title="تعذّر تحميل البيانات المالية"
            description="مزود بيانات السوق غير متاح حالياً. حاول مرة أخرى بعد استعادة الاتصال."
          />
        ) : (
          <EmptyState
            title="تعذّر تحميل البيانات المالية"
            description="حدث خطأ أثناء الاتصال بالخادم. حاول مرة أخرى بعد قليل."
          />
        )
      ) : null}

      {tab === "ai" ? (
        analystReport.status === "ready" ? (
          <AnalystReportView report={analystReport.data} />
        ) : analystReport.status === "loading" ? (
          <LoadingScreen />
        ) : analystReport.status === "insufficient_data" ? (
          <EmptyState title="لا يتوفر تقرير الذكاء الاصطناعي الكامل لهذا السهم بعد" />
        ) : analystReport.status === "unavailable" ? (
          <EmptyState
            title="تعذّر تحميل تقرير الذكاء الاصطناعي"
            description="مزود بيانات السوق غير متاح حالياً. حاول مرة أخرى بعد استعادة الاتصال."
          />
        ) : (
          <EmptyState
            title="تعذّر تحميل تقرير الذكاء الاصطناعي"
            description="حدث خطأ أثناء الاتصال بالخادم. حاول مرة أخرى بعد قليل."
          />
        )
      ) : null}

      {tab === "history" ? <RecommendationHistoryPanel symbol={symbol} /> : null}
    </div>
  );
}
