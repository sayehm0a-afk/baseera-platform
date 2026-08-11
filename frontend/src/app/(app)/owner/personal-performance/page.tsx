"use client";

import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { OwnerNav } from "@/components/owner/OwnerNav";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { ApiError } from "@/lib/api/client";
import { getPersonalPerformanceDashboard } from "@/lib/api/admin";
import type { GroupPerformance, PersonalPerformanceDashboard } from "@/lib/api/admin-types";

type PageState =
  | { status: "loading" }
  | { status: "forbidden" }
  | { status: "error"; message: string }
  | { status: "ready"; data: PersonalPerformanceDashboard };

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

function PercentRow({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex items-center justify-between border-b border-bsr-border-subtle py-bsr-2 last:border-0">
      <span className="text-sm text-bsr-text-secondary">{label}</span>
      <span className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
        {value !== null ? `${value.toFixed(1)}%` : "بيانات غير كافية"}
      </span>
    </div>
  );
}

function GroupList({ groups }: { groups: GroupPerformance[] }) {
  if (groups.length === 0) {
    return <p className="text-sm text-bsr-text-muted">بيانات غير كافية لعرض هذا المقياس</p>;
  }
  return (
    <div className="flex flex-col gap-bsr-1">
      {groups.map((g) => (
        <div
          key={g.group}
          className="flex flex-wrap items-center justify-between gap-bsr-1 border-b border-bsr-border-subtle py-bsr-2 last:border-0"
        >
          <span className="text-sm text-bsr-text-secondary">{g.group}</span>
          <div className="flex items-center gap-bsr-2">
            <span className="text-xs text-bsr-text-muted">{g.sample_size.toLocaleString("ar-SA")} حالة</span>
            <span className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
              {g.win_rate !== null ? `${g.win_rate.toFixed(1)}%` : "—"}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function PersonalPerformancePageInner() {
  const [state, setState] = useState<PageState>({ status: "loading" });

  useEffect(() => {
    getPersonalPerformanceDashboard(7)
      .then((data) => setState({ status: "ready", data }))
      .catch((error) => {
        if (error instanceof ApiError && error.status === 403) {
          setState({ status: "forbidden" });
          return;
        }
        setState({
          status: "error",
          message: error instanceof ApiError ? error.message : "تعذّر تحميل لوحة أداء الفرص اليومية.",
        });
      });
  }, []);

  if (state.status === "loading") {
    return (
      <div className="flex flex-col gap-bsr-4">
        <OwnerNav />
        <LoadingScreen />
      </div>
    );
  }
  if (state.status === "forbidden") {
    return (
      <div className="flex flex-col gap-bsr-4">
        <OwnerNav />
        <EmptyState
          title="هذه الصفحة مخصصة للمالك فقط"
          description="لوحة أداء الفرص اليومية متاحة فقط لحساب المالك (OWNER)."
        />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="flex flex-col gap-bsr-4">
        <OwnerNav />
        <EmptyState title="تعذّر تحميل لوحة أداء الفرص اليومية" description={state.message} />
      </div>
    );
  }

  const { data } = state;

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <h1 className="text-lg font-semibold text-bsr-text-primary">أداء الفرص اليومية</h1>
      <p className="text-sm text-bsr-text-secondary">
        إحصاءات حقيقية عن قرارات ونتائج &quot;امسح السوق الآن&quot; — أفق التقييم: {data.evaluation_horizon_days} يوم.
        إجمالي القرارات المُصدرة: {data.total_decisions_issued.toLocaleString("ar-SA")}.
      </p>
      {data.small_sample_warning ? (
        <p className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-overlay px-bsr-3 py-bsr-2 text-xs text-bsr-text-muted">
          عينة النتائج المكتملة صغيرة حالياً — هذه الأرقام لا تمثّل سجلاً موثوقاً بعد.
        </p>
      ) : null}

      {data.total_decisions_issued === 0 && data.outcome_sample_size === 0 ? (
        <EmptyState
          title="بيانات غير كافية لعرض هذه اللوحة"
          description={data.insufficient_data_message_ar ?? "لا توجد بيانات مسح أو نتائج بعد."}
        />
      ) : (
        <>
          <Card title="توزيع القرارات (امسح السوق الآن)">
            {Object.keys(data.decision_distribution).length === 0 ? (
              <p className="text-sm text-bsr-text-muted">بيانات غير كافية لعرض هذا المقياس</p>
            ) : (
              Object.entries(data.decision_distribution).map(([decision, count]) => (
                <CountRow key={decision} label={decision} value={count} />
              ))
            )}
          </Card>

          <Card title="توزيع حالة الدخول">
            {Object.keys(data.entry_status_distribution).length === 0 ? (
              <p className="text-sm text-bsr-text-muted">بيانات غير كافية لعرض هذا المقياس</p>
            ) : (
              Object.entries(data.entry_status_distribution).map(([status, count]) => (
                <CountRow key={status} label={status} value={count} />
              ))
            )}
          </Card>

          <Card title="توزيع حالة مخاطر السوق">
            {Object.keys(data.market_risk_state_distribution).length === 0 ? (
              <p className="text-sm text-bsr-text-muted">بيانات غير كافية لعرض هذا المقياس</p>
            ) : (
              Object.entries(data.market_risk_state_distribution).map(([state_, count]) => (
                <CountRow key={state_} label={state_} value={count} />
              ))
            )}
          </Card>

          <Card title="معدلات إصابة الأهداف ووقف الخسارة">
            <PercentRow label="الهدف الأول" value={data.target_1_hit_rate} />
            <PercentRow label="الهدف الثاني" value={data.target_2_hit_rate} />
            <PercentRow label="الهدف الثالث" value={data.target_3_hit_rate} />
            <PercentRow label="وقف الخسارة" value={data.stop_loss_hit_rate} />
          </Card>

          <Card title="النتائج الفعلية">
            <CountRow label="العينة الإجمالية" value={data.outcome_sample_size} />
            <CountRow label="النتائج المكتملة" value={data.terminal_outcome_sample_size} />
            <CountRow label="منتهية الصلاحية" value={data.expired_count} />
            <CountRow label="قيد الانتظار" value={data.unresolved_count} />
            <div className="flex items-center justify-between border-b border-bsr-border-subtle py-bsr-2 last:border-0">
              <span className="text-sm text-bsr-text-secondary">متوسط العائد المحقق</span>
              <span className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
                {data.average_realized_return_pct !== null
                  ? `${data.average_realized_return_pct.toFixed(2)}%`
                  : "بيانات غير كافية"}
              </span>
            </div>
            <div className="flex items-center justify-between py-bsr-2">
              <span className="text-sm text-bsr-text-secondary">متوسط المدة الفعلية لبلوغ الهدف</span>
              <span className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
                {data.average_time_to_target_days !== null
                  ? `${data.average_time_to_target_days.toFixed(1)} يوم`
                  : "بيانات غير كافية"}
              </span>
            </div>
          </Card>

          <Card title="أقوى القطاعات أداءً">
            <GroupList groups={data.strongest_groups} />
          </Card>

          <Card title="أضعف القطاعات أداءً">
            <GroupList groups={data.weakest_groups} />
          </Card>

          <Card title="معايرة الثقة حسب حالة مخاطر السوق">
            <p className="text-sm text-bsr-text-muted">{data.market_risk_state_calibration_unavailable_ar}</p>
          </Card>
        </>
      )}
    </div>
  );
}

export default function PersonalPerformancePage() {
  return (
    <RequireStaff>
      <PersonalPerformancePageInner />
    </RequireStaff>
  );
}
