import type { CommitteeConsensus } from "@/lib/api/stocks-types";
import {
  AGENT_ROLE_LABELS_AR,
  AGENT_STANCE_LABELS_AR,
  FINAL_DECISION_LABELS_AR,
  stanceColorClass,
} from "@/components/committee/committee-labels";

/**
 * AI Multi-Agent Investment Committee -- renders the real, persisted
 * consensus from one /decision-v2 response: every agent's opinion,
 * agreement/disagreement, the most optimistic/conservative agent, why
 * the consensus was reached, and why alternative opinions were
 * rejected. `null` (the committee could not run) renders nothing --
 * never a fabricated placeholder.
 */
export function CommitteePanel({ committee }: { committee: CommitteeConsensus | null }) {
  if (committee === null) return null;

  return (
    <div className="flex flex-col gap-bsr-4 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-bsr-text-primary">لجنة الاستثمار متعددة الوكلاء</h2>
        <span className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
          {FINAL_DECISION_LABELS_AR[committee.final_decision] ?? committee.final_decision} (
          {Math.round(committee.final_confidence)}%)
        </span>
      </div>

      {/* Agreement / disagreement summary */}
      <div className="grid grid-cols-2 gap-bsr-2 sm:grid-cols-4">
        <div>
          <p className="text-[11px] text-bsr-text-secondary">نسبة التوافق</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
            {Math.round(committee.agreement_pct)}%
          </p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">نسبة الاختلاف</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
            {Math.round(committee.disagreement_pct)}%
          </p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">درجة الاختلاف</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
            {committee.disagreement_score.toFixed(1)}
          </p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">عدد المشاركين</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">{committee.participant_count}</p>
        </div>
      </div>

      {/* Most optimistic / conservative */}
      {committee.most_optimistic_agent || committee.most_conservative_agent ? (
        <div className="grid grid-cols-1 gap-bsr-2 sm:grid-cols-2">
          {committee.most_optimistic_agent ? (
            <div>
              <p className="text-[11px] text-bsr-text-secondary">الأكثر تفاؤلاً</p>
              <p className="text-sm font-semibold text-bsr-action-buy">{committee.most_optimistic_agent}</p>
            </div>
          ) : null}
          {committee.most_conservative_agent ? (
            <div>
              <p className="text-[11px] text-bsr-text-secondary">الأكثر تحفظاً</p>
              <p className="text-sm font-semibold text-bsr-action-sell">{committee.most_conservative_agent}</p>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Why consensus was reached */}
      {committee.consensus_reasoning_ar ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-primary">لماذا تم التوصل إلى هذا القرار؟</p>
          <p className="mt-1 text-xs text-bsr-text-secondary">{committee.consensus_reasoning_ar}</p>
        </div>
      ) : null}

      {/* Agent opinion cards */}
      <div>
        <p className="mb-bsr-2 text-xs font-semibold text-bsr-text-primary">آراء الوكلاء الثمانية</p>
        <div className="grid grid-cols-1 gap-bsr-2 sm:grid-cols-2">
          {committee.opinions.map((opinion) => (
            <div
              key={opinion.agent_name}
              className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base p-bsr-2"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-bsr-text-primary">{opinion.agent_name}</span>
                <span className={`text-xs font-semibold ${stanceColorClass(opinion.stance)}`}>
                  {AGENT_STANCE_LABELS_AR[opinion.stance]}
                </span>
              </div>
              <p className="text-[11px] text-bsr-text-tertiary">
                {AGENT_ROLE_LABELS_AR[opinion.role] ?? opinion.role} · ثقة {Math.round(opinion.confidence)}%
              </p>
              <p className="mt-1 text-[11px] text-bsr-text-secondary">{opinion.reasoning}</p>
              {opinion.evidence.length > 0 ? (
                <ul className="mt-1 flex flex-col gap-0.5 text-[11px] text-bsr-text-secondary">
                  {opinion.evidence.map((item, i) => (
                    <li key={i}>• {item}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ))}
        </div>
      </div>

      {/* Why alternative opinions were rejected */}
      {committee.rejected_alternatives.length > 0 ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-primary">لماذا رُفضت الآراء البديلة؟</p>
          <ul className="mt-1 flex flex-col gap-1 text-[11px] text-bsr-text-secondary">
            {committee.rejected_alternatives.map((alt) => (
              <li key={alt.agent_name}>
                <span className="font-semibold text-bsr-text-primary">{alt.agent_name}</span>{" "}
                <span className={stanceColorClass(alt.stance)}>({AGENT_STANCE_LABELS_AR[alt.stance]})</span>:{" "}
                {alt.rejection_reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
