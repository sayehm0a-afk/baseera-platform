"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/patterns/EmptyState";
import { getMySubscription } from "@/lib/api/subscription";
import type { MySubscription } from "@/lib/api/subscription-types";

type SectionState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; subscription: MySubscription };

const PLAN_LABELS_AR: Record<string, string> = {
  TRIAL: "تجريبي",
  MONTHLY: "شهري",
  YEARLY: "سنوي",
  STAFF: "حساب فريق العمل",
};

const STATUS_LABELS_AR: Record<string, string> = {
  TRIALING: "فترة تجريبية",
  ACTIVE: "نشط",
  PAST_DUE: "متأخر السداد",
  CANCELED: "ملغى",
  EXPIRED: "منتهٍ",
};

// Both plans real Subscription rows can carry today (TRIAL/MONTHLY/
// YEARLY -- src.domain.models.SubscriptionPlan) grant identical full
// access while entitled; there is no feature-tiered plan in this
// codebase yet (every core route gates on the single
// require_active_subscription() check, not on which plan). This
// screen must not imply a tiering that does not exist.
const ENTITLED_STATUSES = new Set(["TRIALING", "ACTIVE", "CANCELED"]);

function fmtDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString("ar-SA", { calendar: "gregory" }) : "—";
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-bsr-border-subtle py-bsr-3 last:border-0">
      <span className="text-sm text-bsr-text-secondary">{label}</span>
      <span className="text-sm text-bsr-text-primary">{value}</span>
    </div>
  );
}

/** The user's own subscription state -- previously shown nowhere for a
 * regular user (only staff could see ANY subscription, via the
 * separate owner/subscriptions admin panel). Read-only: no
 * self-service upgrade/cancel flow exists yet, since no real payment
 * gateway is integrated (src/billing/provider.py is the seam for one)
 * -- this must never imply one is available. */
export function SubscriptionSection() {
  const [state, setState] = useState<SectionState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getMySubscription()
      .then((subscription) => {
        if (!cancelled) setState({ status: "ready", subscription });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return <p className="px-bsr-1 py-bsr-6 text-center text-sm text-bsr-text-secondary">جارٍ التحميل...</p>;
  }

  if (state.status === "error") {
    return (
      <EmptyState
        title="تعذّر تحميل بيانات الباقة"
        description="تأكد من اتصال الخادم وحاول مرة أخرى."
      />
    );
  }

  const { subscription } = state;
  const isEntitled = ENTITLED_STATUSES.has(subscription.status);

  return (
    <>
      <Row label="الباقة الحالية" value={PLAN_LABELS_AR[subscription.plan] ?? subscription.plan} />
      <Row label="الحالة" value={STATUS_LABELS_AR[subscription.status] ?? subscription.status} />
      {subscription.status === "TRIALING" && subscription.trial_ends_at ? (
        <Row label="تنتهي الفترة التجريبية في" value={fmtDate(subscription.trial_ends_at)} />
      ) : null}
      {subscription.status !== "TRIALING" && subscription.current_period_end ? (
        <Row
          label={subscription.cancel_at_period_end ? "ينتهي الوصول في" : "تتجدد الباقة في"}
          value={fmtDate(subscription.current_period_end)}
        />
      ) : null}
      {subscription.cancel_at_period_end ? (
        <div className="mt-bsr-3 rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-overlay p-bsr-3 text-sm text-bsr-text-secondary">
          تم إلغاء التجديد التلقائي — سيبقى الوصول متاحًا حتى نهاية الفترة الحالية أعلاه، ثم يتوقف.
        </div>
      ) : null}
      <div className="mt-bsr-3 rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-overlay p-bsr-3 text-sm leading-7 text-bsr-text-secondary">
        {isEntitled ? (
          <p>
            خلال الفترة التجريبية أو الاشتراك النشط، جميع ميزات بصيرة الأساسية (الرادار، البحث،
            تحليل الأسهم، قائمة المتابعة، سجل الأداء) متاحة بالكامل دون تقييد. لا توجد حاليًا باقة
            محدودة الميزات.
          </p>
        ) : (
          <p>
            انتهت صلاحية الباقة أو أُلغيت — الوصول إلى ميزات بصيرة الأساسية (الرادار، البحث،
            تحليل الأسهم) متوقف حتى تجديد الاشتراك.
          </p>
        )}
      </div>
    </>
  );
}
