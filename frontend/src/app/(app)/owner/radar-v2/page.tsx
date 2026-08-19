"use client";

import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { DecisionBadge } from "@/components/badges/DecisionBadge";
import { FRESHNESS_LABELS_AR } from "@/components/radar/RadarOpportunityCard";
import { OwnerNav } from "@/components/owner/OwnerNav";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import {
  getAdminRadarV2Performance,
  getAdminRadarV2SahmkConsumption,
  getAdminRadarV2Summary,
  listAdminRadarV2Opportunities,
} from "@/lib/api/admin";
import type {
  AdminRadarV2Performance,
  AdminRadarV2SahmkConsumption,
  AdminRadarV2Summary,
} from "@/lib/api/admin-types";
import { ApiError } from "@/lib/api/client";
import type { RadarOpportunitySummary } from "@/lib/api/radar-types";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">{title}</h2>
      {children}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-[11px] text-bsr-text-secondary">{label}</p>
      <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">{value}</p>
    </div>
  );
}

function fmtPct(pct: number | null): string {
  return pct !== null ? `${pct.toFixed(1)}%` : "—";
}

function fmtDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("ar-SA") : "—";
}

type PageState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      summary: AdminRadarV2Summary;
      performance: AdminRadarV2Performance;
      sahmk: AdminRadarV2SahmkConsumption;
      opportunities: RadarOpportunitySummary[];
    };

/** Basirah Radar V2 mandate (Phase E-H, 2026-08-17): the staff
 * observability view for Radar V2 -- reads the exact same staff-gated
 * diagnostics routes already exercised by the backend test suite
 * (summary/performance/sahmk-consumption/opportunities), never a new
 * query or a duplicated metric. Every rate below is null (never 0%)
 * until real forward-market data has actually resolved outcomes -- see
 * RadarV2PerformanceOut's own contract. */
function RadarV2PageInner() {
  const [state, setState] = useState<PageState>({ status: "loading" });

  useEffect(() => {
    Promise.all([
      getAdminRadarV2Summary(),
      getAdminRadarV2Performance(),
      getAdminRadarV2SahmkConsumption(),
      listAdminRadarV2Opportunities(50),
    ])
      .then(([summary, performance, sahmk, opportunities]) =>
        setState({ status: "ready", summary, performance, sahmk, opportunities })
      )
      .catch((err) =>
        setState({
          status: "error",
          message: err instanceof ApiError ? err.message : "تعذّر تحميل بيانات الرادار الذكي.",
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
        <EmptyState title="تعذّر تحميل بيانات الرادار الذكي" description={state.message} />
      </div>
    );
  }

  const { summary, performance, sahmk, opportunities } = state;

  // Derived client-side, never a second hardcoded Arabic mapping: every
  // classification key already carries its own Arabic label on each
  // opportunity row, so this is only a lookup over already-fetched data.
  const classificationLabels: Record<string, string> = {};
  for (const o of opportunities) {
    classificationLabels[o.classification] = o.classification_label_ar;
  }

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <h1 className="text-lg font-semibold text-bsr-text-primary">مراقبة الرادار الذكي (Radar V2)</h1>

      <Card title="الحالة الحالية">
        <div className="grid grid-cols-2 gap-bsr-3 sm:grid-cols-4">
          <Stat label="الفرص الحية" value={summary.live_opportunity_count} />
          <Stat label="متوسط الثقة" value={summary.average_confidence != null ? fmtPct(summary.average_confidence) : "—"} />
          <Stat label="سقف مرشحي المرحلة الثانية" value={summary.stage2_candidate_cap} />
          <Stat label="آخر عملية مسح" value={summary.most_recent_scan_run_id ?? "—"} />
        </div>
        {Object.keys(summary.live_by_classification).length > 0 ? (
          <div className="mt-bsr-3 flex flex-wrap gap-bsr-2">
            {Object.entries(summary.live_by_classification).map(([classification, count]) => (
              <span key={classification} className="rounded-bsr-full bg-bsr-surface-overlay px-bsr-3 py-1 text-xs text-bsr-text-primary">
                {classificationLabels[classification] ?? classification}: <span className="bsr-numeric font-semibold">{count}</span>
              </span>
            ))}
          </div>
        ) : null}
        <p className="mt-bsr-2 text-[11px] text-bsr-text-tertiary">آخر تحديث: {fmtDate(summary.generated_at)}</p>
      </Card>

      <Card title="أداء الرادار الحقيقي (تتبّع الأداء الفعلي)">
        <div className="grid grid-cols-2 gap-bsr-3 sm:grid-cols-4">
          <Stat label="إجمالي الفرص المُصدرة" value={performance.total_opportunities_emitted} />
          <Stat label="نتائج تحت المتابعة" value={performance.pending_count} />
          <Stat label="نتائج محسومة" value={performance.resolved_count} />
          <Stat label="بلغت الهدف" value={performance.target_hit_count} />
          <Stat label="بلغت وقف الخسارة" value={performance.stop_loss_hit_count} />
          <Stat label="نسبة بلوغ الهدف" value={fmtPct(performance.target_hit_rate)} />
          <Stat label="نسبة بلوغ وقف الخسارة" value={fmtPct(performance.stop_loss_hit_rate)} />
          <Stat label="متوسط العائد" value={performance.average_return_pct != null ? fmtPct(performance.average_return_pct) : "—"} />
        </div>
        {performance.resolved_count === 0 ? (
          <p className="mt-bsr-2 text-xs text-bsr-text-secondary">
            لا توجد بعد نتائج سوقية حقيقية محسومة لقياس الأداء الفعلي -- هذا وضع طبيعي في المراحل المبكرة، وليس معدل صفر.
          </p>
        ) : null}
      </Card>

      <Card title="استهلاك SAHMK الخاص بالرادار الذكي">
        {sahmk.rate_limiter_by_operation || sahmk.cache_by_operation ? (
          <div className="flex flex-col gap-bsr-3">
            {sahmk.rate_limiter_by_operation ? (
              <div>
                <p className="mb-1 text-[11px] font-semibold text-bsr-text-secondary">حد المعدل حسب العملية</p>
                <div className="flex flex-col gap-1">
                  {Object.entries(sahmk.rate_limiter_by_operation).map(([op, val]) => (
                    <div key={op} className="flex items-start justify-between gap-bsr-2 text-[11px]">
                      <span className="text-bsr-text-secondary">{op}</span>
                      <span className="bsr-numeric text-bsr-text-primary" dir="ltr">
                        {JSON.stringify(val)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {sahmk.cache_by_operation ? (
              <div>
                <p className="mb-1 text-[11px] font-semibold text-bsr-text-secondary">التخزين المؤقت حسب العملية</p>
                <div className="flex flex-col gap-1">
                  {Object.entries(sahmk.cache_by_operation).map(([op, val]) => (
                    <div key={op} className="flex items-start justify-between gap-bsr-2 text-[11px]">
                      <span className="text-bsr-text-secondary">{op}</span>
                      <span className="bsr-numeric text-bsr-text-primary" dir="ltr">
                        {JSON.stringify(val)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="text-xs text-bsr-text-secondary">لا توجد بيانات استهلاك مسجّلة بعد لعملية الرادار الذكي.</p>
        )}
      </Card>

      <Card title={`الفرص الحية حاليًا (${opportunities.length})`}>
        {opportunities.length === 0 ? (
          <p className="text-xs text-bsr-text-secondary">لا توجد فرصة حية حاليًا -- لم يُصدر الرادار أي فرصة بعد في هذا المسح.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right text-sm">
              <thead>
                <tr className="text-[11px] text-bsr-text-secondary">
                  <th className="p-1">الترتيب</th>
                  <th className="p-1">الرمز</th>
                  <th className="p-1">التصنيف</th>
                  <th className="p-1">الثقة</th>
                  <th className="p-1">حداثة البيانات</th>
                </tr>
              </thead>
              <tbody>
                {opportunities.map((o) => (
                  <tr key={o.id} className="border-t border-bsr-border-subtle">
                    <td className="bsr-numeric p-1">{o.stage1_rank ?? "—"}</td>
                    <td className="bsr-numeric p-1">{o.symbol}</td>
                    <td className="p-1">
                      <DecisionBadge value={o.classification} labelAr={o.classification_label_ar} />
                    </td>
                    <td className="bsr-numeric p-1">{Math.round(o.confidence_score)}%</td>
                    <td className="p-1">{FRESHNESS_LABELS_AR[o.data_freshness_status]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

export default function RadarV2Page() {
  return (
    <RequireStaff>
      <RadarV2PageInner />
    </RequireStaff>
  );
}
