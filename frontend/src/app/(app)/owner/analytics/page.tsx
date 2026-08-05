"use client";

import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { OwnerNav } from "@/components/owner/OwnerNav";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { ApiError } from "@/lib/api/client";
import { getAnalytics } from "@/lib/api/admin";
import type { Analytics } from "@/lib/api/admin-types";

type PageState = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: Analytics };

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-bsr-border-subtle py-bsr-2 last:border-0">
      <span className="text-sm text-bsr-text-secondary">{label}</span>
      <span className="bsr-numeric text-sm font-semibold text-bsr-text-primary">{value}</span>
    </div>
  );
}

function BreakdownSection({ title, breakdown }: { title: string; breakdown: Record<string, number> }) {
  const entries = Object.entries(breakdown);
  return (
    <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">{title}</h2>
      {entries.length === 0 ? (
        <p className="text-sm text-bsr-text-muted">لا توجد بيانات.</p>
      ) : (
        entries.map(([key, value]) => <StatusRow key={key} label={key} value={value.toLocaleString("ar-SA")} />)
      )}
    </section>
  );
}

function AnalyticsPageInner() {
  const [state, setState] = useState<PageState>({ status: "loading" });

  useEffect(() => {
    getAnalytics()
      .then((data) => setState({ status: "ready", data }))
      .catch((error) =>
        setState({
          status: "error",
          message: error instanceof ApiError ? error.message : "تعذّر تحميل بيانات التحليلات.",
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
        <EmptyState title="تعذّر تحميل بيانات التحليلات" description={state.message} />
      </div>
    );
  }

  const { data } = state;

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <h1 className="text-lg font-semibold text-bsr-text-primary">التحليلات</h1>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
        <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">نظرة عامة</h2>
        <StatusRow label="إجمالي المستخدمين" value={data.total_users.toLocaleString("ar-SA")} />
        <StatusRow label="إجمالي المحافظ" value={data.total_portfolios.toLocaleString("ar-SA")} />
        <StatusRow label="إجمالي عمليات الاختبار الخلفي" value={data.total_backtest_runs.toLocaleString("ar-SA")} />
      </section>

      <BreakdownSection title="المستخدمون حسب الدور الإداري" breakdown={data.users_by_staff_role} />
      <BreakdownSection title="الاشتراكات حسب الحالة" breakdown={data.subscriptions_by_status} />
      <BreakdownSection title="الاشتراكات حسب الخطة" breakdown={data.subscriptions_by_plan} />
    </div>
  );
}

export default function AnalyticsPage() {
  return (
    <RequireStaff>
      <AnalyticsPageInner />
    </RequireStaff>
  );
}
