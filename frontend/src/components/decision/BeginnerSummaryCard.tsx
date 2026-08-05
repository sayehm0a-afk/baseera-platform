import { DecisionBadge } from "@/components/badges/DecisionBadge";
import type { DecisionV2 } from "@/lib/api/stocks-types";

/**
 * Phase 2G: Beginner Experience -- answers the same 8 questions a
 * less-experienced user actually asks about a decision, in short plain
 * Arabic sentences. Computes nothing new: every value here is a field
 * Decision Engine V2 already produces (Phase 2A/2B), just re-selected
 * and re-ordered around the question a beginner would ask rather than
 * the engine's own internal structure. Opt-in and additive -- renders
 * alongside ExecutiveDecisionCard, never replaces it.
 */
export function BeginnerSummaryCard({ decision }: { decision: DecisionV2 }) {
  const risksToWatch = [...decision.negative_reasons, ...decision.warnings];

  return (
    <div className="flex flex-col gap-bsr-4 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <h2 className="text-sm font-semibold text-bsr-text-primary">ملخص مبسّط للمبتدئين</h2>

      {/* 1: what should I do */}
      <div>
        <p className="text-xs font-semibold text-bsr-text-secondary">ماذا يجب أن أفعل؟</p>
        <div className="mt-1 flex items-center gap-bsr-2">
          <DecisionBadge value={decision.decision} labelAr={decision.decision_label_ar} className="text-sm" />
        </div>
        {decision.decision_summary_ar ? (
          <p className="mt-1 text-xs text-bsr-text-secondary">{decision.decision_summary_ar}</p>
        ) : null}
      </div>

      {/* 2: why */}
      {decision.why_now_ar ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-secondary">لماذا؟</p>
          <p className="mt-1 text-xs text-bsr-text-primary">{decision.why_now_ar}</p>
        </div>
      ) : null}

      {/* 3: when to enter */}
      <div>
        <p className="text-xs font-semibold text-bsr-text-secondary">متى أدخل؟</p>
        <p className="mt-1 text-xs text-bsr-text-primary">{decision.entry_status_label_ar}</p>
      </div>

      {/* 4: how much risk */}
      <div>
        <p className="text-xs font-semibold text-bsr-text-secondary">ما مستوى المخاطرة؟</p>
        <p className="mt-1 text-xs text-bsr-text-primary">{decision.risk_level_label_ar}</p>
      </div>

      {/* 5: what could go wrong */}
      {risksToWatch.length > 0 ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-secondary">ما الذي قد يحدث بشكل خاطئ؟</p>
          <ul className="mt-1 flex flex-col gap-0.5 text-xs text-bsr-action-sell">
            {risksToWatch.map((reason, i) => (
              <li key={i}>• {reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* 6: how long to hold */}
      {decision.expected_holding_period_label_ar ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-secondary">كم المدة المتوقعة للاحتفاظ؟</p>
          <p className="mt-1 text-xs text-bsr-text-primary">{decision.expected_holding_period_label_ar}</p>
        </div>
      ) : null}

      {/* 7: what confirms I'm right */}
      {decision.entry_confirmation_conditions_ar.length > 0 ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-secondary">ما الذي يؤكد صحة القرار؟</p>
          <ul className="mt-1 flex flex-col gap-0.5 text-xs text-bsr-action-buy">
            {decision.entry_confirmation_conditions_ar.map((condition, i) => (
              <li key={i}>• {condition}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* 8: what would change my mind */}
      {decision.invalidation_conditions.length > 0 ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-secondary">ما الذي يلغي هذا القرار؟</p>
          <ul className="mt-1 flex flex-col gap-0.5 text-xs text-bsr-text-primary">
            {decision.invalidation_conditions.map((condition, i) => (
              <li key={i}>• {condition}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="rounded-bsr-md bg-bsr-surface-overlay p-bsr-2 text-[11px] leading-4 text-bsr-text-muted">
        {decision.analysis_disclaimer_ar}
      </p>
    </div>
  );
}
