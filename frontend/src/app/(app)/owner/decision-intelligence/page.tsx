"use client";

import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { OwnerNav } from "@/components/owner/OwnerNav";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { ApiError } from "@/lib/api/client";
import { getDecisionIntelligence } from "@/lib/api/admin";
import type { DecisionIntelligence } from "@/lib/api/admin-types";

type PageState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: DecisionIntelligence };

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">{title}</h2>
      {children}
    </section>
  );
}

function CountRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between border-b border-bsr-border-subtle py-bsr-2 last:border-0">
      <span className="text-sm text-bsr-text-secondary">{label}</span>
      <span className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
        {value.toLocaleString("ar-SA")}
      </span>
    </div>
  );
}

function DecisionIntelligencePageInner() {
  const [state, setState] = useState<PageState>({ status: "loading" });

  useEffect(() => {
    getDecisionIntelligence(72)
      .then((data) => setState({ status: "ready", data }))
      .catch((error) =>
        setState({
          status: "error",
          message: error instanceof ApiError ? error.message : "تعذّر تحميل إحصاءات محرك القرار.",
        })
      );
  }, []);

  if (state.status === "loading") {
    return (
      <div className="flex flex-col gap-bsr-4">
        <OwnerNav />
        <LoadingScreen />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="flex flex-col gap-bsr-4">
        <OwnerNav />
        <EmptyState title="تعذّر تحميل إحصاءات محرك القرار" description={state.message} />
      </div>
    );
  }

  const { data } = state;

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <h1 className="text-lg font-semibold text-bsr-text-primary">ذكاء القرار الاستثماري</h1>
      <p className="text-sm text-bsr-text-secondary">
        إحصاءات حقيقية عن آخر قرار لكل سهم خلال {data.window_hours} ساعة الماضية — إجمالي الأسهم المقيَّمة:{" "}
        {data.total_symbols_evaluated.toLocaleString("ar-SA")}.
      </p>

      {data.total_symbols_evaluated === 0 ? (
        <EmptyState
          title="لا توجد قرارات ضمن هذه النافذة الزمنية"
          description="لم يُسجَّل أي تحليل من محرك القرار V2 خلال الفترة المحددة."
        />
      ) : (
        <>
          <Card title="توزيع القرارات">
            {data.decision_distribution.map((row) => (
              <CountRow key={row.decision} label={row.decision} value={row.count} />
            ))}
          </Card>

          <Card title="توزيع درجة الثقة">
            {data.confidence_buckets.map((row) => (
              <CountRow key={row.bucket_label} label={row.bucket_label} value={row.count} />
            ))}
          </Card>

          <Card title="توزيع مستوى المخاطر">
            {data.risk_distribution.map((row) => (
              <CountRow key={row.risk_level ?? "غير محدد"} label={row.risk_level ?? "غير محدد"} value={row.count} />
            ))}
          </Card>

          <Card title="أفضل الفرص (حسب الثقة، وليس أبجدياً)">
            {data.top_opportunities.length === 0 ? (
              <p className="text-sm text-bsr-text-muted">لا توجد فرص شراء حالياً.</p>
            ) : (
              <div className="flex flex-col gap-bsr-1">
                {data.top_opportunities.map((row) => (
                  <div
                    key={row.symbol}
                    className="flex items-center justify-between border-b border-bsr-border-subtle py-bsr-2 last:border-0"
                  >
                    <div>
                      <span className="font-semibold text-bsr-text-primary">{row.symbol}</span>{" "}
                      <span className="text-sm text-bsr-text-secondary">{row.company_name_ar ?? ""}</span>
                      <span className="ms-bsr-2 text-xs text-bsr-text-muted">{row.decision_label_ar}</span>
                    </div>
                    <span className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
                      {row.confidence_score.toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="الفرص المرفوضة وأسبابها الفعلية">
            {data.rejected_opportunities.length === 0 ? (
              <p className="text-sm text-bsr-text-muted">لا توجد فرص مرفوضة حالياً.</p>
            ) : (
              <div className="flex flex-col gap-bsr-1">
                {data.rejected_opportunities.map((row) => (
                  <div key={row.symbol} className="border-b border-bsr-border-subtle py-bsr-2 last:border-0">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-bsr-text-primary">{row.symbol}</span>
                      <span className="text-xs text-bsr-text-muted">{row.decision}</span>
                    </div>
                    <p className="text-sm text-bsr-text-secondary">
                      {row.failed_gate_names.length > 0
                        ? row.failed_gate_names.join("، ")
                        : "لا يوجد شرط فاشل محدد."}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="أكثر أسباب الرفض تكراراً">
            {data.rejection_reason_counts.length === 0 ? (
              <p className="text-sm text-bsr-text-muted">لا توجد فرص مرفوضة حالياً.</p>
            ) : (
              data.rejection_reason_counts.map((row) => (
                <CountRow key={row.gate_name} label={row.gate_name} value={row.fail_count} />
              ))
            )}
          </Card>

          <Card title="ترتيب القطاعات (حسب متوسط الثقة)">
            {data.sector_ranking.map((row) => (
              <div
                key={row.sector_ar ?? "غير محدد"}
                className="flex flex-wrap items-center justify-between gap-bsr-1 border-b border-bsr-border-subtle py-bsr-2 last:border-0"
              >
                <span className="text-sm text-bsr-text-secondary">{row.sector_ar ?? "غير محدد"}</span>
                <div className="flex items-center gap-bsr-2">
                  <span className="text-xs text-bsr-text-muted">
                    {row.symbols_evaluated.toLocaleString("ar-SA")} سهم · {row.buy_candidate_count} فرصة شراء
                  </span>
                  <span className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
                    {row.average_confidence !== null ? `${row.average_confidence.toFixed(1)}%` : "—"}
                  </span>
                </div>
              </div>
            ))}
          </Card>
        </>
      )}
    </div>
  );
}

export default function DecisionIntelligencePage() {
  return (
    <RequireStaff>
      <DecisionIntelligencePageInner />
    </RequireStaff>
  );
}
