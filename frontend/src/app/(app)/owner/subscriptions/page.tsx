"use client";

import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { OwnerNav } from "@/components/owner/OwnerNav";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { ApiError } from "@/lib/api/client";
import { listSubscriptions } from "@/lib/api/admin";
import type { AdminSubscription } from "@/lib/api/admin-types";

const PAGE_SIZE = 50;

const STATUS_LABELS_AR: Record<string, string> = {
  TRIALING: "فترة تجريبية",
  ACTIVE: "نشط",
  PAST_DUE: "متأخر السداد",
  CANCELED: "ملغى",
  EXPIRED: "منتهٍ",
};

function fmtDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString("ar-SA") : "—";
}

type PageState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; subscriptions: AdminSubscription[]; total: number; offset: number };

function SubscriptionsPageInner() {
  const [state, setState] = useState<PageState>({ status: "loading" });

  async function load(offset: number) {
    try {
      const result = await listSubscriptions(PAGE_SIZE, offset);
      setState({ status: "ready", subscriptions: result.subscriptions, total: result.total, offset });
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof ApiError ? error.message : "تعذّر تحميل قائمة الاشتراكات.",
      });
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function initialLoad() {
      try {
        const result = await listSubscriptions(PAGE_SIZE, 0);
        if (!cancelled) {
          setState({ status: "ready", subscriptions: result.subscriptions, total: result.total, offset: 0 });
        }
      } catch (error) {
        if (!cancelled) {
          setState({
            status: "error",
            message: error instanceof ApiError ? error.message : "تعذّر تحميل قائمة الاشتراكات.",
          });
        }
      }
    }
    initialLoad();
    return () => {
      cancelled = true;
    };
  }, []);

  function reload(offset: number) {
    setState({ status: "loading" });
    load(offset);
  }

  const disclosureBanner = (
    <div className="rounded-bsr-md border border-bsr-action-watch/40 bg-bsr-action-watch/10 p-bsr-3 text-xs text-bsr-text-secondary">
      لا توجد بوابة دفع فعلية مربوطة بالمنصة حالياً. تعرض هذه الصفحة حالة الاشتراكات الحقيقية المخزّنة في قاعدة
      البيانات (تجريبي/نشط/ملغى/منتهٍ) فقط، ولا تمثّل أي معاملات دفع فعلية.
    </div>
  );

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
        <EmptyState title="تعذّر تحميل قائمة الاشتراكات" description={state.message} />
      </div>
    );
  }

  const { subscriptions, total, offset } = state;

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-bsr-text-primary">الاشتراكات والباقات</h1>
        <span className="text-sm text-bsr-text-secondary">{total.toLocaleString("ar-SA")} اشتراك</span>
      </div>

      {disclosureBanner}

      {subscriptions.length === 0 ? (
        <EmptyState title="لا توجد اشتراكات" />
      ) : (
        <div className="overflow-x-auto rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-bsr-border-subtle text-right text-xs text-bsr-text-muted">
                <th className="p-bsr-3 font-medium">المستخدم</th>
                <th className="p-bsr-3 font-medium">الباقة</th>
                <th className="p-bsr-3 font-medium">الحالة</th>
                <th className="p-bsr-3 font-medium">نهاية التجربة</th>
                <th className="p-bsr-3 font-medium">بداية الفترة</th>
                <th className="p-bsr-3 font-medium">نهاية الفترة</th>
                <th className="p-bsr-3 font-medium">إلغاء عند الانتهاء</th>
              </tr>
            </thead>
            <tbody>
              {subscriptions.map((sub) => (
                <tr key={sub.id} className="border-b border-bsr-border-subtle last:border-0">
                  <td className="bsr-numeric p-bsr-3 text-bsr-text-primary">#{sub.user_id}</td>
                  <td className="p-bsr-3 text-bsr-text-secondary">{sub.plan}</td>
                  <td className="p-bsr-3 text-bsr-text-secondary">
                    {STATUS_LABELS_AR[sub.status] ?? sub.status}
                  </td>
                  <td className="bsr-numeric p-bsr-3 text-bsr-text-secondary">{fmtDate(sub.trial_ends_at)}</td>
                  <td className="bsr-numeric p-bsr-3 text-bsr-text-secondary">
                    {fmtDate(sub.current_period_start)}
                  </td>
                  <td className="bsr-numeric p-bsr-3 text-bsr-text-secondary">
                    {fmtDate(sub.current_period_end)}
                  </td>
                  <td className="p-bsr-3 text-bsr-text-secondary">{sub.cancel_at_period_end ? "نعم" : "لا"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center justify-between">
        <button
          type="button"
          disabled={offset === 0}
          onClick={() => reload(Math.max(0, offset - PAGE_SIZE))}
          className="rounded-bsr-md border border-bsr-border-subtle px-bsr-3 py-1.5 text-sm text-bsr-text-secondary disabled:opacity-40"
        >
          السابق
        </button>
        <span className="text-xs text-bsr-text-muted">
          {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} من {total}
        </span>
        <button
          type="button"
          disabled={offset + PAGE_SIZE >= total}
          onClick={() => reload(offset + PAGE_SIZE)}
          className="rounded-bsr-md border border-bsr-border-subtle px-bsr-3 py-1.5 text-sm text-bsr-text-secondary disabled:opacity-40"
        >
          التالي
        </button>
      </div>
    </div>
  );
}

export default function SubscriptionsPage() {
  return (
    <RequireStaff>
      <SubscriptionsPageInner />
    </RequireStaff>
  );
}
