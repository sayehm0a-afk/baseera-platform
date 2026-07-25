import { AiStar } from "@/components/ai/AiStar";
import { ConfidenceBar } from "@/components/ai/ConfidenceBar";
import {
  RecommendationBadge,
  type RecommendationValue,
} from "@/components/badges/RecommendationBadge";
import { RISK_LEVEL_LABELS } from "@/lib/portfolio-labels";
import type { AnalystReport } from "@/lib/api/stocks-types";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6">
      <h2 className="mb-bsr-3 text-base font-semibold text-bsr-text-primary">{title}</h2>
      {children}
    </section>
  );
}

/**
 * Renders the full AnalystReportOut per the Explainability Contract
 * (DS §18.1): a reachable explanation for every recommendation, a
 * mandatory conflicting-evidence row that is never hidden -- even
 * when there is nothing to show it renders an explicit "no
 * conflicting evidence" state -- and a mandatory stop-loss row that
 * is always rendered, honestly showing "not set" rather than being
 * omitted when the backend returns null.
 */
export function AnalystReportView({ report }: { report: AnalystReport }) {
  return (
    <div className="flex flex-col gap-bsr-6">
      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6">
        <div className="mb-bsr-4 flex flex-wrap items-center justify-between gap-bsr-3">
          <div className="flex items-center gap-bsr-3">
            <span className="bsr-numeric text-2xl font-semibold text-bsr-text-primary">
              {report.symbol}
            </span>
            <RecommendationBadge value={report.recommendation as RecommendationValue} />
          </div>
          <span className="text-xs text-bsr-text-muted">
            {new Date(report.generated_at).toLocaleString("ar-SA")}
          </span>
        </div>

        <div className="mb-bsr-4 flex items-center gap-bsr-2">
          <AiStar />
          <span className="text-sm text-bsr-teal-500">نسبة ثقة بصيرة AI</span>
        </div>
        <ConfidenceBar confidence={report.confidence} />
        <p className="bsr-numeric mt-bsr-1 text-sm text-bsr-teal-500">
          {Math.round(report.confidence)}%
        </p>

        <div className="mt-bsr-4 grid grid-cols-2 gap-bsr-3 md:grid-cols-4">
          <div className="rounded-bsr-md bg-bsr-surface-overlay px-bsr-3 py-bsr-2">
            <p className="text-xs text-bsr-text-secondary">السعر المستهدف</p>
            <p className="bsr-numeric text-bsr-text-primary">
              {report.target_price != null ? report.target_price.toFixed(2) : "—"}
            </p>
          </div>
          <div className="rounded-bsr-md bg-bsr-action-sell/15 px-bsr-3 py-bsr-2">
            <p className="text-xs text-bsr-text-secondary">وقف الخسارة</p>
            <p className="bsr-numeric text-bsr-action-sell">
              {report.stop_loss != null ? report.stop_loss.toFixed(2) : "غير محدد"}
            </p>
          </div>
          <div className="rounded-bsr-md bg-bsr-surface-overlay px-bsr-3 py-bsr-2">
            <p className="text-xs text-bsr-text-secondary">الإطار الزمني</p>
            <p className="text-bsr-text-primary">{report.time_horizon}</p>
          </div>
          <div className="rounded-bsr-md bg-bsr-surface-overlay px-bsr-3 py-bsr-2">
            <p className="text-xs text-bsr-text-secondary">مستوى المخاطرة</p>
            <p className="text-bsr-text-primary">
              {RISK_LEVEL_LABELS[report.risk_level] ?? report.risk_level}
            </p>
          </div>
        </div>
      </section>

      <Section title="ملخص الاستثمار">
        <p className="text-sm leading-7 text-bsr-text-secondary">{report.investment_summary}</p>
      </Section>

      <div className="grid grid-cols-1 gap-bsr-6 lg:grid-cols-2">
        <Section title="التحليل الفني">
          <p className="text-sm leading-7 text-bsr-text-secondary">{report.technical_reasoning}</p>
        </Section>
        <Section title="التحليل الأساسي">
          <p className="text-sm leading-7 text-bsr-text-secondary">{report.fundamental_reasoning}</p>
        </Section>
      </div>

      <Section title="تفسير المخاطر">
        <p className="text-sm leading-7 text-bsr-text-secondary">{report.risk_explanation}</p>
      </Section>

      <div className="grid grid-cols-1 gap-bsr-6 lg:grid-cols-2">
        <Section title="عوامل داعمة">
          {report.bullish_factors.length === 0 ? (
            <p className="text-sm text-bsr-text-muted">لا توجد عوامل داعمة مسجّلة.</p>
          ) : (
            <ul className="flex flex-col gap-bsr-2">
              {report.bullish_factors.map((factor, index) => (
                <li key={index} className="flex gap-bsr-2 text-sm text-bsr-text-secondary">
                  <span className="text-bsr-market-up">+</span>
                  {factor}
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="الأدلة المتعارضة">
          {report.bearish_factors.length === 0 ? (
            <p className="text-sm text-bsr-text-muted">
              لا توجد أدلة متعارضة مسجّلة لهذه التوصية حالياً.
            </p>
          ) : (
            <ul className="flex flex-col gap-bsr-2">
              {report.bearish_factors.map((factor, index) => (
                <li key={index} className="flex gap-bsr-2 text-sm text-bsr-text-secondary">
                  <span className="text-bsr-market-down">−</span>
                  {factor}
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <div className="grid grid-cols-1 gap-bsr-6 lg:grid-cols-3">
        <Section title="تفسير نسبة الثقة">
          <p className="text-sm leading-7 text-bsr-text-secondary">{report.confidence_explanation}</p>
        </Section>
        <Section title="تفسير السعر المستهدف">
          <p className="text-sm leading-7 text-bsr-text-secondary">{report.target_price_explanation}</p>
        </Section>
        <Section title="تفسير وقف الخسارة">
          <p className="text-sm leading-7 text-bsr-text-secondary">{report.stop_loss_explanation}</p>
        </Section>
      </div>

      <Section title="تفسير الإطار الزمني">
        <p className="text-sm leading-7 text-bsr-text-secondary">{report.time_horizon_explanation}</p>
      </Section>

      <Section title="سيناريوهات بديلة">
        {report.alternative_scenarios.length === 0 ? (
          <p className="text-sm text-bsr-text-muted">لا توجد سيناريوهات بديلة مسجّلة.</p>
        ) : (
          <ul className="flex flex-col gap-bsr-2">
            {report.alternative_scenarios.map((scenario, index) => (
              <li key={index} className="text-sm text-bsr-text-secondary">
                • {scenario}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="الأساس المنطقي للتوصية النهائية">
        <p className="text-sm leading-7 text-bsr-text-secondary">
          {report.final_recommendation_rationale}
        </p>
      </Section>
    </div>
  );
}
