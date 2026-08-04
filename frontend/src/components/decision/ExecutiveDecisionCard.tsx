import { AiStar } from "@/components/ai/AiStar";
import { ConfidenceBar } from "@/components/ai/ConfidenceBar";
import { DecisionBadge } from "@/components/badges/DecisionBadge";
import type { DecisionV2 } from "@/lib/api/stocks-types";

const FRESHNESS_LABELS_AR: Record<DecisionV2["data_freshness_status"], string> = {
  LIVE: "بيانات حيّة",
  LAST_SESSION: "بيانات آخر جلسة مكتملة",
  STALE: "بيانات قديمة",
  UNKNOWN: "حداثة البيانات غير مؤكدة",
};

function fmt(value: number | null): string {
  return value == null ? "—" : value.toFixed(2);
}

function fmtPct(value: number | null): string {
  if (value == null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

/**
 * Phase 1 Decision Engine V2's executive-decision section for the
 * stock analysis page: the twelve explainability elements the spec
 * requires (what to do / why / entry / stop / targets / duration /
 * risk / invalidation / data source and freshness) rendered from the
 * structured DecisionV2 result -- no narrative text is generated
 * client-side, every sentence here is verbatim backend output. This
 * is the Phase 1 foundation only; the full multi-section Complete
 * Stock Intelligence Report is Phase 2, not yet built.
 */
export function ExecutiveDecisionCard({ decision }: { decision: DecisionV2 }) {
  const hasEntryZone = decision.entry_zone_low != null && decision.entry_zone_high != null;

  return (
    <div className="flex flex-col gap-bsr-4 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      {/* Decision + confidence */}
      <div className="flex flex-wrap items-start justify-between gap-bsr-2">
        <div className="flex flex-col gap-bsr-1">
          <span className="text-xs text-bsr-text-secondary">القرار التنفيذي لبصيرة</span>
          <DecisionBadge value={decision.decision} labelAr={decision.decision_label_ar} className="w-fit text-base" />
        </div>
        <div className="flex min-w-[10rem] flex-col gap-bsr-1">
          <div className="flex items-center justify-between text-xs text-bsr-teal-500">
            <span className="flex items-center gap-1">
              <AiStar size="sm" />
              درجة الثقة
            </span>
            <span className="bsr-numeric">{Math.round(decision.confidence_score)}%</span>
          </div>
          <ConfidenceBar confidence={decision.confidence_score} />
        </div>
      </div>

      <p className="text-[11px] leading-4 text-bsr-text-muted">{decision.confidence_disclaimer_ar}</p>

      {/* Freshness / market status */}
      <div className="flex flex-wrap items-center gap-bsr-2 text-xs text-bsr-text-secondary">
        <span className="rounded-bsr-full bg-bsr-surface-overlay px-bsr-2 py-bsr-0.5">
          {FRESHNESS_LABELS_AR[decision.data_freshness_status]}
        </span>
        <span className="rounded-bsr-full bg-bsr-surface-overlay px-bsr-2 py-bsr-0.5">{decision.market_status}</span>
        {decision.sector_ar ? (
          <span className="rounded-bsr-full bg-bsr-surface-overlay px-bsr-2 py-bsr-0.5">{decision.sector_ar}</span>
        ) : null}
      </div>

      {/* Entry / stop / targets */}
      {hasEntryZone || decision.stop_loss != null || decision.target_1 != null ? (
        <div className="grid grid-cols-2 gap-bsr-3 sm:grid-cols-4">
          <div>
            <p className="text-xs text-bsr-text-secondary">نطاق الدخول</p>
            <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
              {hasEntryZone ? `${fmt(decision.entry_zone_low)} – ${fmt(decision.entry_zone_high)}` : "—"}
            </p>
          </div>
          <div>
            <p className="text-xs text-bsr-text-secondary">وقف الخسارة</p>
            <p className="bsr-numeric text-sm font-semibold text-bsr-action-sell">{fmt(decision.stop_loss)}</p>
            {decision.downside_to_stop != null ? (
              <p className="bsr-numeric text-[11px] text-bsr-action-sell">{fmtPct(decision.downside_to_stop)}</p>
            ) : null}
          </div>
          <div>
            <p className="text-xs text-bsr-text-secondary">الهدف الأول</p>
            <p className="bsr-numeric text-sm font-semibold text-bsr-action-buy">{fmt(decision.target_1)}</p>
            {decision.expected_return_target_1 != null ? (
              <p className="bsr-numeric text-[11px] text-bsr-action-buy">
                {fmtPct(decision.expected_return_target_1)}
                {decision.risk_reward_target_1 != null ? ` · 1:${decision.risk_reward_target_1.toFixed(1)}` : ""}
              </p>
            ) : null}
          </div>
          <div>
            <p className="text-xs text-bsr-text-secondary">الهدف الثاني</p>
            <p className="bsr-numeric text-sm font-semibold text-bsr-action-buy">{fmt(decision.target_2)}</p>
            {decision.expected_return_target_2 != null ? (
              <p className="bsr-numeric text-[11px] text-bsr-action-buy">
                {fmtPct(decision.expected_return_target_2)}
                {decision.risk_reward_target_2 != null ? ` · 1:${decision.risk_reward_target_2.toFixed(1)}` : ""}
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* Duration / risk / quality */}
      <div className="grid grid-cols-2 gap-bsr-3 sm:grid-cols-3">
        <div>
          <p className="text-xs text-bsr-text-secondary">المدة المتوقعة</p>
          <p className="text-sm font-semibold text-bsr-text-primary">{decision.expected_holding_period_label_ar}</p>
        </div>
        <div>
          <p className="text-xs text-bsr-text-secondary">مستوى المخاطرة</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
            {Math.round(decision.risk_score)}/100
          </p>
        </div>
        <div>
          <p className="text-xs text-bsr-text-secondary">جودة الفرصة</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
            {Math.round(decision.opportunity_quality_score)}/100
          </p>
        </div>
      </div>

      {/* Reasons */}
      {decision.positive_reasons.length > 0 ? (
        <div className="flex flex-col gap-bsr-1">
          <p className="text-xs font-semibold text-bsr-action-buy">ما الذي يؤيد القرار</p>
          <ul className="flex flex-col gap-0.5 text-xs text-bsr-text-secondary">
            {decision.positive_reasons.map((reason, i) => (
              <li key={i}>• {reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {decision.negative_reasons.length > 0 ? (
        <div className="flex flex-col gap-bsr-1">
          <p className="text-xs font-semibold text-bsr-action-sell">ما الذي يضعف القرار</p>
          <ul className="flex flex-col gap-0.5 text-xs text-bsr-text-secondary">
            {decision.negative_reasons.map((reason, i) => (
              <li key={i}>• {reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {decision.warnings.length > 0 ? (
        <div className="flex flex-col gap-bsr-1 rounded-bsr-md bg-bsr-action-watch/10 p-bsr-2">
          <p className="text-xs font-semibold text-bsr-action-watch">تنبيهات</p>
          <ul className="flex flex-col gap-0.5 text-xs text-bsr-action-watch">
            {decision.warnings.map((warning, i) => (
              <li key={i}>• {warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {decision.invalidation_conditions.length > 0 ? (
        <div className="flex flex-col gap-bsr-1">
          <p className="text-xs font-semibold text-bsr-text-primary">متى يُلغى هذا القرار؟</p>
          <ul className="flex flex-col gap-0.5 text-xs text-bsr-text-secondary">
            {decision.invalidation_conditions.map((condition, i) => (
              <li key={i}>• {condition}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="text-xs text-bsr-text-secondary">{decision.recommendation_basis}</p>

      <p className="rounded-bsr-md bg-bsr-surface-overlay p-bsr-2 text-[11px] leading-4 text-bsr-text-muted">
        {decision.analysis_disclaimer_ar}
      </p>

      <div className="flex flex-wrap items-center gap-x-bsr-3 gap-y-1 text-[11px] text-bsr-text-muted">
        <span>المصدر: {decision.data_source}</span>
        <span>إصدار المحرك: {decision.analysis_version}</span>
        <span className="bsr-numeric">
          وقت القرار: {new Date(decision.decision_timestamp).toLocaleString("ar-SA")}
        </span>
      </div>
    </div>
  );
}
