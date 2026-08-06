import type { DecisionV2 } from "@/lib/api/stocks-types";

function fmt(value: number | null): string {
  return value == null ? "—" : value.toFixed(2);
}

function fmtDays(value: number | null): string {
  return value == null ? "—" : `${value} يوم`;
}

const SUB_SCORE_LABELS_AR: Record<string, string> = {
  trend_score: "الاتجاه",
  momentum_score: "الزخم",
  volume_score: "الحجم",
  liquidity_score: "السيولة",
  volatility_score: "التقلب",
  risk_reward_score: "العائد إلى المخاطرة",
  market_context_score: "سياق السوق",
  data_quality_score: "جودة البيانات",
};

const CONFIDENCE_BREAKDOWN_LABELS_AR: { key: keyof DecisionV2; label: string }[] = [
  { key: "technical_confidence", label: "الثقة الفنية" },
  { key: "momentum_confidence", label: "ثقة الزخم" },
  { key: "liquidity_confidence", label: "ثقة السيولة" },
  { key: "market_context_confidence", label: "ثقة سياق السوق" },
  { key: "data_quality_confidence", label: "ثقة جودة البيانات" },
];

/**
 * Phase 2E: the deep-dive transparency sections the immediate-answer
 * ExecutiveDecisionCard header deliberately keeps out of the way --
 * every field here is verbatim backend output already computed by
 * Decision Engine V2 (Phase 2A/2B/2C) but not yet surfaced anywhere on
 * the stock detail page. Additive only: this is a second panel
 * rendered alongside ExecutiveDecisionCard, not a redesign of it.
 */
export function DecisionTransparencyPanel({ decision }: { decision: DecisionV2 }) {
  const hasExtendedTargets = decision.target_3 != null || decision.estimated_days_target_3 != null;
  const hasExtendedLevels =
    decision.major_support != null ||
    decision.major_resistance != null ||
    decision.breakout_level != null ||
    decision.breakdown_level != null;
  const hasVolumeDetail =
    decision.current_volume != null || decision.average_volume != null || decision.relative_volume != null;
  const confidenceBreakdown = CONFIDENCE_BREAKDOWN_LABELS_AR.filter(
    ({ key }) => decision[key] != null
  );

  return (
    <div className="flex flex-col gap-bsr-4 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <h2 className="text-sm font-semibold text-bsr-text-primary">التحليل الكامل والشفافية</h2>

      {/* 1: why not stronger */}
      {decision.why_not_stronger_ar ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-primary">لماذا لم يكن القرار أقوى؟</p>
          <p className="mt-1 text-xs text-bsr-text-secondary">{decision.why_not_stronger_ar}</p>
        </div>
      ) : null}

      {/* 2: entry confirmation conditions */}
      {decision.entry_confirmation_conditions_ar.length > 0 ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-primary">شروط تأكيد الدخول</p>
          <ul className="mt-1 flex flex-col gap-0.5 text-xs text-bsr-text-secondary">
            {decision.entry_confirmation_conditions_ar.map((condition, i) => (
              <li key={i}>• {condition}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* 3: watch next session */}
      {decision.watch_next_session_ar.length > 0 ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-primary">ما يجب مراقبته في الجلسة القادمة</p>
          <ul className="mt-1 flex flex-col gap-0.5 text-xs text-bsr-text-secondary">
            {decision.watch_next_session_ar.map((item, i) => (
              <li key={i}>• {item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* 4: trend direction and strength */}
      <div>
        <p className="text-xs font-semibold text-bsr-text-primary">الاتجاه وقوته</p>
        <p className="mt-1 text-xs text-bsr-text-secondary">
          {decision.trend_direction_ar} — {decision.trend_strength_label_ar}
        </p>
      </div>

      {/* 5: 6-part confidence breakdown */}
      {confidenceBreakdown.length > 0 ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-primary">تفصيل درجة الثقة</p>
          <div className="mt-1 grid grid-cols-2 gap-bsr-2 sm:grid-cols-3">
            <div>
              <p className="text-[11px] text-bsr-text-secondary">الثقة الإجمالية</p>
              <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
                {Math.round(decision.confidence_score)}%
              </p>
            </div>
            {confidenceBreakdown.map(({ key, label }) => (
              <div key={key}>
                <p className="text-[11px] text-bsr-text-secondary">{label}</p>
                <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
                  {Math.round(decision[key] as number)}%
                </p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* 6: eight sub-scores */}
      <div>
        <p className="text-xs font-semibold text-bsr-text-primary">العناصر الفرعية الثمانية للتحليل</p>
        <div className="mt-1 grid grid-cols-2 gap-bsr-2 sm:grid-cols-4">
          {Object.entries(decision.sub_scores).map(([key, value]) => (
            <div key={key}>
              <p className="text-[11px] text-bsr-text-secondary">{SUB_SCORE_LABELS_AR[key] ?? key}</p>
              <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
                {value == null ? "—" : `${Math.round(value)}/100`}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* 7: extended targets */}
      {hasExtendedTargets ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-primary">الهدف الثالث والمدى الزمني الكامل</p>
          <div className="mt-1 grid grid-cols-2 gap-bsr-2 sm:grid-cols-3">
            <div>
              <p className="text-[11px] text-bsr-text-secondary">الهدف الثالث</p>
              <p className="bsr-numeric text-sm font-semibold text-bsr-action-buy">{fmt(decision.target_3)}</p>
            </div>
            <div>
              <p className="text-[11px] text-bsr-text-secondary">مدة الهدف الأول</p>
              <p className="bsr-numeric text-sm text-bsr-text-primary">{fmtDays(decision.estimated_days_target_1)}</p>
            </div>
            <div>
              <p className="text-[11px] text-bsr-text-secondary">مدة الهدف الثاني</p>
              <p className="bsr-numeric text-sm text-bsr-text-primary">{fmtDays(decision.estimated_days_target_2)}</p>
            </div>
            <div>
              <p className="text-[11px] text-bsr-text-secondary">مدة الهدف الثالث</p>
              <p className="bsr-numeric text-sm text-bsr-text-primary">{fmtDays(decision.estimated_days_target_3)}</p>
            </div>
          </div>
        </div>
      ) : null}

      {/* 8: extended support/resistance levels */}
      {hasExtendedLevels ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-primary">مستويات إضافية للدعم والمقاومة</p>
          <div className="mt-1 grid grid-cols-2 gap-bsr-2 sm:grid-cols-4">
            <div>
              <p className="text-[11px] text-bsr-text-secondary">دعم رئيسي</p>
              <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">{fmt(decision.major_support)}</p>
            </div>
            <div>
              <p className="text-[11px] text-bsr-text-secondary">مقاومة رئيسية</p>
              <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">{fmt(decision.major_resistance)}</p>
            </div>
            <div>
              <p className="text-[11px] text-bsr-text-secondary">مستوى الاختراق</p>
              <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">{fmt(decision.breakout_level)}</p>
            </div>
            <div>
              <p className="text-[11px] text-bsr-text-secondary">مستوى الانكسار</p>
              <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">{fmt(decision.breakdown_level)}</p>
            </div>
          </div>
          {decision.support_resistance_evidence_ar ? (
            <p className="mt-1 text-[11px] text-bsr-text-secondary">{decision.support_resistance_evidence_ar}</p>
          ) : null}
        </div>
      ) : null}

      {/* 9: volume detail */}
      {hasVolumeDetail ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-primary">تفاصيل الحجم والسيولة</p>
          <div className="mt-1 grid grid-cols-2 gap-bsr-2 sm:grid-cols-4">
            <div>
              <p className="text-[11px] text-bsr-text-secondary">الحجم الحالي</p>
              <p className="bsr-numeric text-sm text-bsr-text-primary">
                {decision.current_volume == null ? "—" : Math.round(decision.current_volume).toLocaleString("ar-SA")}
              </p>
            </div>
            <div>
              <p className="text-[11px] text-bsr-text-secondary">متوسط الحجم</p>
              <p className="bsr-numeric text-sm text-bsr-text-primary">
                {decision.average_volume == null ? "—" : Math.round(decision.average_volume).toLocaleString("ar-SA")}
              </p>
            </div>
            <div>
              <p className="text-[11px] text-bsr-text-secondary">الحجم النسبي</p>
              <p className="bsr-numeric text-sm text-bsr-text-primary">
                {decision.relative_volume == null ? "—" : `${decision.relative_volume.toFixed(2)}×`}
              </p>
            </div>
            <div>
              <p className="text-[11px] text-bsr-text-secondary">تأكيد الحجم للقرار</p>
              <p className="text-sm text-bsr-text-primary">
                {decision.volume_confirms_decision == null
                  ? "غير محدد"
                  : decision.volume_confirms_decision
                    ? "يدعم القرار"
                    : "لا يدعم القرار"}
              </p>
            </div>
          </div>
          {decision.abnormal_volume ? (
            <p className="mt-1 text-[11px] text-bsr-action-watch">حجم تداول غير معتاد اليوم.</p>
          ) : null}
        </div>
      ) : null}

      {/* 10: publication gates */}
      {decision.gates.length > 0 ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-primary">
            بوابات النشر ({decision.gates.length})
          </p>
          <ul className="mt-1 flex flex-col gap-0.5 text-[11px]">
            {decision.gates.map((gate) => (
              <li
                key={gate.name}
                className={`flex items-start justify-between gap-bsr-2 ${
                  gate.status === "FAIL"
                    ? "text-bsr-action-sell"
                    : gate.status === "NOT_EVALUATED"
                      ? "text-bsr-text-tertiary"
                      : "text-bsr-text-secondary"
                }`}
              >
                <span>{gate.detail}</span>
                <span className="shrink-0">
                  {gate.status === "PASS" ? "✓" : gate.status === "NOT_EVALUATED" ? "○" : gate.blocking ? "✗" : "⚠"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
