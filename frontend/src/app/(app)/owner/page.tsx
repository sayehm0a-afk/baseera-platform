"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { OwnerNav } from "@/components/owner/OwnerNav";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { getDashboardSummary, getSystemHealth } from "@/lib/api/admin";
import type { AdminDashboardSummary, SystemHealth } from "@/lib/api/admin-types";
import { RUN_STATUS_LABELS } from "@/lib/market-intelligence-labels";

type PageState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; summary: AdminDashboardSummary; health: SystemHealth };

const HEALTH_LABELS: Record<string, string> = {
  healthy: "سليم",
  unhealthy: "غير سليم",
  degraded: "متدهور",
};

function healthColor(value: string | null | undefined): string {
  if (value === "healthy") return "text-bsr-market-up";
  if (value == null) return "text-bsr-text-muted";
  return "text-bsr-market-down";
}

function StatusRow({ label, value, colorClass }: { label: string; value: string; colorClass?: string }) {
  return (
    <div className="flex items-center justify-between border-b border-bsr-border-subtle py-bsr-2 last:border-0">
      <span className="text-sm text-bsr-text-secondary">{label}</span>
      <span className={`bsr-numeric text-sm font-semibold ${colorClass ?? "text-bsr-text-primary"}`}>
        {value}
      </span>
    </div>
  );
}

function OwnerStatusPageInner() {
  const [state, setState] = useState<PageState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    Promise.all([getDashboardSummary(), getSystemHealth()])
      .then(([summary, health]) => {
        if (!cancelled) setState({ status: "ready", summary, health });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
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
        <EmptyState
          title="تعذّر تحميل حالة النظام"
          description="هذه الصفحة مخصّصة لملاك المنصة فقط، وتتطلب اتصالاً سليماً بالخادم."
        />
      </div>
    );
  }

  const { summary, health } = state;
  const frontendCommit = process.env.NEXT_PUBLIC_DEPLOYMENT_COMMIT ?? null;

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-bsr-text-primary">لوحة حالة الإنتاج (المالك)</h1>
        <Link
          href="/owner/live-test"
          className="rounded-bsr-md bg-bsr-gold-500 px-bsr-4 py-bsr-2 text-sm font-semibold text-bsr-navy-950 hover:bg-bsr-gold-400"
        >
          اختبار السوق المباشر
        </Link>
      </div>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
        <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">صحة الخدمات</h2>
        <StatusRow
          label="الحالة العامة"
          value={HEALTH_LABELS[health.status] ?? health.status}
          colorClass={healthColor(health.status)}
        />
        <StatusRow
          label="تطبيق البيانات الحقيقية الصارم (STRICT_REAL_DATA)"
          value={summary.strict_real_data_enforced ? "مُفعّل" : "غير مُفعّل"}
          colorClass={summary.strict_real_data_enforced ? "text-bsr-market-up" : "text-bsr-market-down"}
        />
        <StatusRow label="حالة السوق الآن" value={summary.market_status_label_ar} />
        <StatusRow label="إصدار محرك القرار" value={summary.decision_engine_version} />
        <StatusRow
          label="قاعدة البيانات"
          value={HEALTH_LABELS[summary.database_health] ?? summary.database_health}
          colorClass={healthColor(summary.database_health)}
        />
        <StatusRow
          label="Redis"
          value={HEALTH_LABELS[summary.redis_health] ?? summary.redis_health}
          colorClass={healthColor(summary.redis_health)}
        />
        <StatusRow
          label="مزود بيانات السوق (SAHMK)"
          value={summary.market_data_provider ?? "غير متوفر"}
        />
        <StatusRow
          label="اتصال مزود البيانات"
          value={
            summary.market_data_health
              ? HEALTH_LABELS[summary.market_data_health] ?? summary.market_data_health
              : "غير معروف"
          }
          colorClass={healthColor(summary.market_data_health)}
        />
      </section>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
        <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">آخر مسح للسوق</h2>
        {summary.last_scan_id == null ? (
          <p className="text-sm text-bsr-text-muted">لم يُنفَّذ أي مسح بعد.</p>
        ) : (
          <>
            <StatusRow label="رقم المسح" value={String(summary.last_scan_id)} />
            <StatusRow label="الحالة" value={summary.last_scan_status ? (RUN_STATUS_LABELS[summary.last_scan_status] ?? summary.last_scan_status) : "—"} />
            <StatusRow
              label="بدأ في"
              value={summary.last_scan_started_at ? new Date(summary.last_scan_started_at).toLocaleString("ar-SA") : "—"}
            />
            <StatusRow
              label="انتهى في"
              value={summary.last_scan_finished_at ? new Date(summary.last_scan_finished_at).toLocaleString("ar-SA") : "لا يزال قيد التنفيذ"}
            />
            <StatusRow label="الرموز المطلوبة" value={String(summary.last_scan_symbols_requested ?? "—")} />
            <StatusRow label="الرموز الناجحة" value={String(summary.last_scan_symbols_succeeded ?? "—")} />
            <StatusRow label="الرموز الفاشلة" value={String(summary.last_scan_symbols_failed ?? "—")} />
            <StatusRow label="فرص مقبولة (منشورة)" value={String(summary.last_scan_published_count ?? "—")} />
            <StatusRow label="فرص للمراقبة فقط" value={String(summary.last_scan_watch_only_count ?? "—")} />
            <StatusRow label="فرص مرفوضة" value={String(summary.last_scan_rejected_count ?? "—")} />
            <StatusRow label="بيانات غير كافية" value={String(summary.last_scan_insufficient_data_count ?? "—")} />
            {summary.last_scan_latest_error ? (
              <div className="border-b border-bsr-border-subtle py-bsr-2 last:border-0">
                <p className="text-sm text-bsr-text-secondary">آخر خطأ</p>
                <p className="text-sm text-bsr-market-down">{summary.last_scan_latest_error}</p>
              </div>
            ) : null}
          </>
        )}
        <StatusRow
          label="قفل تنفيذ المسح"
          value={summary.scan_lock_active ? "مقفل (مسح قيد التنفيذ)" : "متاح"}
          colorClass={summary.scan_lock_active ? "text-bsr-action-watch" : "text-bsr-market-up"}
        />
        <StatusRow
          label="مجدول المسح الدوري"
          value={summary.market_intelligence_scheduler_running ? "يعمل" : "متوقف"}
          colorClass={summary.market_intelligence_scheduler_running ? "text-bsr-market-up" : "text-bsr-text-muted"}
        />
        <StatusRow
          label="مجدول استيراد البيانات"
          value={summary.ingestion_scheduler_running ? "يعمل" : "متوقف"}
          colorClass={summary.ingestion_scheduler_running ? "text-bsr-market-up" : "text-bsr-text-muted"}
        />
        <StatusRow
          label="مهام استيراد مؤجَّلة (حصة SAHMK)"
          value={
            summary.ingestion_deferred_job_count > 0
              ? `${summary.ingestion_deferred_job_count} من 4`
              : "لا يوجد"
          }
          colorClass={summary.ingestion_deferred_job_count > 0 ? "text-bsr-action-watch" : "text-bsr-market-up"}
        />
        {summary.ingestion_deferred_job_count > 0 && summary.ingestion_next_retry_at ? (
          <StatusRow
            label="إعادة المحاولة التالية"
            value={new Date(summary.ingestion_next_retry_at).toLocaleString("ar-SA")}
          />
        ) : null}
      </section>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
        <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">النشر</h2>
        <StatusRow label="بيئة التشغيل" value={summary.environment} />
        <StatusRow label="إصدار الخادم" value={summary.app_version} />
        <StatusRow label="مرجع نشر الخادم (Commit)" value={summary.deployment_commit ?? "غير معروف"} />
        <StatusRow label="مرجع نشر الواجهة (Commit)" value={frontendCommit ?? "غير معروف"} />
      </section>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
        <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">المستخدمون</h2>
        <StatusRow label="مستخدمون جدد (24 ساعة)" value={String(summary.new_users_last_24h)} />
        <StatusRow label="مستخدمون جدد (7 أيام)" value={String(summary.new_users_last_7d)} />
        <StatusRow label="تسجيلات دخول (24 ساعة)" value={String(summary.logins_last_24h)} />
        <StatusRow label="حسابات مقفلة" value={String(summary.locked_accounts)} />
      </section>
    </div>
  );
}

export default function OwnerStatusPage() {
  return (
    <RequireStaff>
      <OwnerStatusPageInner />
    </RequireStaff>
  );
}
