"use client";

import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { OwnerNav } from "@/components/owner/OwnerNav";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { ApiError } from "@/lib/api/client";
import { getAIUsageSummary } from "@/lib/api/admin";
import type { AIUsageSummary } from "@/lib/api/admin-types";

type PageState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: AIUsageSummary };

function StatusRow({ label, value, colorClass }: { label: string; value: string; colorClass?: string }) {
  return (
    <div className="flex items-center justify-between border-b border-bsr-border-subtle py-bsr-2 last:border-0">
      <span className="text-sm text-bsr-text-secondary">{label}</span>
      <span className={`bsr-numeric text-sm font-semibold ${colorClass ?? "text-bsr-text-primary"}`}>{value}</span>
    </div>
  );
}

function AiUsagePageInner() {
  const [state, setState] = useState<PageState>({ status: "loading" });

  useEffect(() => {
    getAIUsageSummary()
      .then((data) => setState({ status: "ready", data }))
      .catch((error) =>
        setState({
          status: "error",
          message: error instanceof ApiError ? error.message : "تعذّر تحميل بيانات استخدام الذكاء الاصطناعي.",
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
        <EmptyState title="تعذّر تحميل بيانات الاستخدام" description={state.message} />
      </div>
    );
  }

  const { data } = state;
  const featureEntries = Object.entries(data.by_feature);

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <h1 className="text-lg font-semibold text-bsr-text-primary">استخدام الذكاء الاصطناعي والتكلفة</h1>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
        <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">ملخص عام</h2>
        <StatusRow label="إجمالي الطلبات" value={data.total_requests.toLocaleString("ar-SA")} />
        <StatusRow
          label="طلبات ناجحة"
          value={data.success_count.toLocaleString("ar-SA")}
          colorClass="text-bsr-market-up"
        />
        <StatusRow
          label="طلبات فاشلة"
          value={data.failed_count.toLocaleString("ar-SA")}
          colorClass="text-bsr-market-down"
        />
        <StatusRow
          label="طلبات منتهية المهلة"
          value={data.timeout_count.toLocaleString("ar-SA")}
          colorClass="text-bsr-action-watch"
        />
        <StatusRow label="إجمالي الرموز (Tokens)" value={data.total_tokens.toLocaleString("ar-SA")} />
        <StatusRow
          label="التكلفة التقديرية (دولار أمريكي)"
          value={`$${data.estimated_cost_usd.toFixed(2)}`}
        />
      </section>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
        <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">الاستخدام حسب الميزة</h2>
        {featureEntries.length === 0 ? (
          <p className="text-sm text-bsr-text-muted">لا توجد بيانات.</p>
        ) : (
          featureEntries.map(([feature, count]) => (
            <StatusRow key={feature} label={feature} value={count.toLocaleString("ar-SA")} />
          ))
        )}
      </section>
    </div>
  );
}

export default function AiUsagePage() {
  return (
    <RequireStaff>
      <AiUsagePageInner />
    </RequireStaff>
  );
}
