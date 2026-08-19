"use client";

import { useState } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { ConfidenceBar } from "@/components/ai/ConfidenceBar";
import { DecisionBadge } from "@/components/badges/DecisionBadge";
import { getRadarOpportunity } from "@/lib/api/radar";
import type { RadarOpportunityDetail, RadarOpportunitySummary } from "@/lib/api/radar-types";

interface RadarStockSectionProps {
  opportunity: RadarOpportunitySummary | null;
}

type DetailState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; detail: RadarOpportunityDetail };

/** Stock-detail's "Radar V2" panel -- shown only when this symbol has
 * a real, live (non-superseded) RadarOpportunity right now (see
 * StockDetailClient's use of getRadarOpportunityBySymbol). Mirrors
 * CommitteePanel's own convention of returning null rather than
 * rendering an empty-state box when there is nothing real to show --
 * a symbol not currently on the radar is not itself noteworthy. */
export function RadarStockSection({ opportunity }: RadarStockSectionProps) {
  const [detail, setDetail] = useState<DetailState>({ status: "idle" });

  if (opportunity == null) {
    return null;
  }

  const o = opportunity;

  function loadDetail() {
    if (detail.status === "loading" || detail.status === "ready") return;
    setDetail({ status: "loading" });
    getRadarOpportunity(o.id)
      .then((d) => setDetail({ status: "ready", detail: d }))
      .catch(() => setDetail({ status: "error" }));
  }

  return (
    <div className="flex flex-col gap-bsr-3 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-bsr-2">
          <AiStar />
          <h2 className="text-base font-semibold text-bsr-text-primary">الرادار الذكي</h2>
          {o.stage1_rank != null ? (
            <span className="bsr-numeric text-xs text-bsr-text-secondary">الترتيب #{o.stage1_rank}</span>
          ) : null}
        </div>
        <DecisionBadge value={o.classification} labelAr={o.classification_label_ar} />
      </div>

      <div className="flex items-center gap-bsr-3">
        <span className="text-xs text-bsr-text-secondary">الثقة</span>
        <div className="flex-1">
          <ConfidenceBar confidence={o.confidence_score} />
        </div>
        <span className="bsr-numeric text-sm font-semibold text-bsr-teal-500">
          {Math.round(o.confidence_score)}%
        </span>
      </div>

      {o.ranking_reason_ar ? (
        <div>
          <p className="text-xs text-bsr-text-secondary">لماذا رصد الرادار هذا السهم؟</p>
          <p className="text-sm text-bsr-text-primary">{o.ranking_reason_ar}</p>
        </div>
      ) : null}

      <p className="text-xs text-bsr-text-muted">{o.confidence_disclaimer_ar}</p>

      {detail.status === "idle" ? (
        <button
          type="button"
          onClick={loadDetail}
          className="self-start rounded-bsr-md border border-bsr-border-subtle px-bsr-3 py-bsr-2 text-xs font-semibold text-bsr-text-primary transition-colors hover:border-bsr-gold-500/40"
        >
          عرض تفاصيل الأدلة الفنية
        </button>
      ) : null}

      {detail.status === "loading" ? (
        <p className="text-xs text-bsr-text-secondary">جارٍ تحميل التفاصيل...</p>
      ) : null}

      {detail.status === "error" ? (
        <p className="text-xs text-bsr-market-down">تعذّر تحميل تفاصيل الرادار.</p>
      ) : null}

      {detail.status === "ready" ? (
        <div className="flex flex-col gap-bsr-2 border-t border-bsr-border-subtle pt-bsr-3">
          {detail.detail.why_now_ar ? (
            <div>
              <p className="text-xs text-bsr-text-secondary">لماذا الآن؟</p>
              <p className="text-sm text-bsr-text-primary">{detail.detail.why_now_ar}</p>
            </div>
          ) : null}
          {detail.detail.entry_quality_label_ar || detail.detail.entry_status_label_ar ? (
            <div className="flex flex-wrap gap-bsr-3 text-sm">
              {detail.detail.entry_quality_label_ar ? (
                <span className="text-bsr-text-secondary">
                  جودة الدخول: <span className="font-semibold text-bsr-text-primary">{detail.detail.entry_quality_label_ar}</span>
                </span>
              ) : null}
              {detail.detail.entry_status_label_ar ? (
                <span className="text-bsr-text-secondary">
                  حالة الدخول: <span className="font-semibold text-bsr-text-primary">{detail.detail.entry_status_label_ar}</span>
                </span>
              ) : null}
            </div>
          ) : null}
          {detail.detail.trend_direction_ar || detail.detail.trend_strength_label_ar ? (
            <p className="text-sm text-bsr-text-secondary">
              الاتجاه:{" "}
              <span className="font-semibold text-bsr-text-primary">
                {[detail.detail.trend_direction_ar, detail.detail.trend_strength_label_ar].filter(Boolean).join(" -- ")}
              </span>
            </p>
          ) : null}
          {detail.detail.support_resistance_evidence_ar ? (
            <p className="text-sm text-bsr-text-primary">{detail.detail.support_resistance_evidence_ar}</p>
          ) : null}
          {detail.detail.sector_ar ? (
            <p className="text-xs text-bsr-text-secondary">
              القطاع: <span className="font-semibold text-bsr-text-primary">{detail.detail.sector_ar}</span>
            </p>
          ) : null}
          {detail.detail.why_not_stronger_ar ? (
            <div>
              <p className="text-xs text-bsr-text-secondary">لماذا ليست إشارة أقوى؟</p>
              <p className="text-sm text-bsr-text-primary">{detail.detail.why_not_stronger_ar}</p>
            </div>
          ) : null}
          {detail.detail.invalidation_conditions.length > 0 ? (
            <div>
              <p className="text-xs text-bsr-text-secondary">شروط إلغاء الإشارة</p>
              <ul className="list-inside list-disc text-sm text-bsr-market-down">
                {detail.detail.invalidation_conditions.map((condition) => (
                  <li key={condition}>{condition}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {detail.detail.positive_reasons.length > 0 ? (
            <div>
              <p className="text-xs text-bsr-text-secondary">نقاط القوة</p>
              <ul className="list-inside list-disc text-sm text-bsr-text-primary">
                {detail.detail.positive_reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {detail.detail.warnings.length > 0 ? (
            <div>
              <p className="text-xs text-bsr-text-secondary">تحذيرات</p>
              <ul className="list-inside list-disc text-sm text-bsr-market-down">
                {detail.detail.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {detail.detail.stage1_signals.length > 0 ? (
            <div>
              <p className="text-xs text-bsr-text-secondary">الإشارات الفنية المرصودة</p>
              <ul className="list-inside list-disc text-sm text-bsr-text-primary">
                {detail.detail.stage1_signals.map((signal) => (
                  <li key={signal.name}>{signal.detail_ar}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {detail.detail.expected_holding_period_label_ar ? (
            <p className="text-sm text-bsr-text-secondary">
              المدة المتوقعة للصفقة:{" "}
              <span className="font-semibold text-bsr-text-primary">
                {detail.detail.expected_holding_period_label_ar}
              </span>
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
