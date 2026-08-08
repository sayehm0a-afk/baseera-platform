"use client";

import { useCallback, useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { OwnerNav } from "@/components/owner/OwnerNav";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { ApiError } from "@/lib/api/client";
import { getMarketCoverage, triggerFullDiscovery } from "@/lib/api/admin";
import type { MarketCoverage } from "@/lib/api/admin-types";

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

function MarketCoveragePageInner() {
  const [coverage, setCoverage] = useState<MarketCoverage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [triggerMessage, setTriggerMessage] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  // `loading` already defaults to true via useState above, so this
  // effect never needs a synchronous setState call of its own
  // (react-hooks/set-state-in-effect forbids that) -- every setState
  // here happens strictly inside a promise callback. `reloadToken` lets
  // handleTrigger request a refresh without calling setState in an
  // effect body either.
  useEffect(() => {
    getMarketCoverage()
      .then((data) => setCoverage(data))
      .catch((err) => setError(err instanceof ApiError ? err.message : "تعذّر تحميل بيانات تغطية السوق."))
      .finally(() => setLoading(false));
  }, [reloadToken]);

  const load = useCallback(() => setReloadToken((t) => t + 1), []);

  function handleTrigger() {
    setTriggering(true);
    setTriggerMessage(null);
    triggerFullDiscovery()
      .then((result) => {
        setTriggerMessage(result.message);
        load();
      })
      .catch((err) => setTriggerMessage(err instanceof ApiError ? err.message : "تعذّر بدء عملية الاكتشاف الكاملة."))
      .finally(() => setTriggering(false));
  }

  if (loading && coverage === null) {
    return (
      <div className="flex flex-col gap-bsr-4">
        <OwnerNav />
        <LoadingScreen />
      </div>
    );
  }
  if (error || coverage === null) {
    return (
      <div className="flex flex-col gap-bsr-4">
        <OwnerNav />
        <EmptyState title="تعذّر تحميل بيانات تغطية السوق" description={error ?? undefined} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-bsr-text-primary">تغطية السوق السعودي</h1>
        <button
          type="button"
          onClick={handleTrigger}
          disabled={triggering}
          className="rounded-bsr-md bg-bsr-gold-500 px-bsr-3 py-1.5 text-xs font-semibold text-bsr-navy-950 disabled:opacity-50"
        >
          {triggering ? "جارٍ البدء..." : "بدء اكتشاف كامل للسوق"}
        </button>
      </div>
      {triggerMessage ? <p className="text-xs text-bsr-text-secondary">{triggerMessage}</p> : null}

      <Card title="الأسهم المتتبَّعة">
        <div className="grid grid-cols-2 gap-bsr-3 sm:grid-cols-4">
          <Stat label="إجمالي الأسهم" value={coverage.total_stocks} />
          <Stat label="نشطة" value={coverage.active_stocks} />
          <Stat label="غير نشطة" value={coverage.inactive_stocks} />
          <Stat label="نسبة التغطية" value={fmtPct(coverage.coverage_pct)} />
          <Stat label="لديها بيانات سعرية" value={coverage.stocks_with_price_history} />
          <Stat label="بدون بيانات سعرية" value={coverage.stocks_without_price_history} />
          <Stat label="السوق الرئيسية" value={coverage.main_market_stocks} />
          <Stat label="نمو" value={coverage.nomu_market_stocks} />
        </div>
      </Card>

      <Card title="البيانات المالية والتوزيعات">
        <div className="grid grid-cols-2 gap-bsr-3 sm:grid-cols-4">
          <Stat label="لديها بيانات مالية" value={coverage.stocks_with_fundamentals} />
          <Stat label="بدون بيانات مالية" value={coverage.stocks_without_fundamentals} />
          <Stat label="لديها توزيعات" value={coverage.stocks_with_dividends} />
          <Stat label="بدون توزيعات" value={coverage.stocks_without_dividends} />
        </div>
      </Card>

      <Card title="آخر مسح للسوق">
        {coverage.latest_scan_run ? (
          <div className="grid grid-cols-2 gap-bsr-3 sm:grid-cols-4">
            <Stat label="الحالة" value={coverage.latest_scan_run.status} />
            <Stat label="طُلب" value={coverage.latest_scan_run.symbols_requested} />
            <Stat label="نجح" value={coverage.latest_scan_run.symbols_succeeded} />
            <Stat label="فشل" value={coverage.latest_scan_run.symbols_failed} />
            <Stat label="دخلت محرك القرار" value={coverage.latest_scan_symbols_entering_decision_engine} />
            <Stat label="توصيات صدرت" value={coverage.latest_scan_recommendations_generated} />
            <Stat label="بدأ" value={fmtDate(coverage.latest_scan_run.started_at)} />
            <Stat label="انتهى" value={fmtDate(coverage.latest_scan_run.finished_at)} />
          </div>
        ) : (
          <p className="text-sm text-bsr-text-muted">لم يُشغَّل أي مسح للسوق بعد.</p>
        )}
      </Card>

      <Card title="آخر مهام الاستيعاب (Ingestion)">
        <p className="mb-bsr-2 text-[11px] text-bsr-text-secondary">
          الاكتشاف التلقائي: {coverage.ingestion_auto_discover_enabled ? "مفعّل" : "معطّل"} · الرموز المهيّأة:{" "}
          {coverage.ingestion_configured_seed_symbols}
        </p>
        <div className="flex flex-col gap-bsr-1">
          {coverage.latest_ingestion_runs.map((run) => (
            <div
              key={run.job_name}
              className="flex items-center justify-between rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base p-bsr-2"
            >
              <span className="text-xs font-semibold text-bsr-text-primary">{run.job_name}</span>
              <span className="bsr-numeric text-[11px] text-bsr-text-secondary">
                {run.status ?? "لم يُشغَّل بعد"} · نجح {run.symbols_succeeded} · فشل {run.symbols_failed}
              </span>
            </div>
          ))}
        </div>
      </Card>

      <Card title="التغطية حسب القطاع">
        <div className="flex flex-col gap-bsr-1">
          {coverage.sector_coverage.map((sector) => (
            <div key={sector.sector ?? "unknown"} className="flex items-center justify-between text-xs">
              <span className="text-bsr-text-secondary">{sector.sector ?? "غير مصنّف"}</span>
              <span className="bsr-numeric text-bsr-text-primary">
                {sector.active_stocks}/{sector.total_stocks} ({fmtPct(sector.coverage_pct)})
              </span>
            </div>
          ))}
        </div>
      </Card>

      <Card title="مسار خط الأنابيب (Pipeline Funnel)">
        <div className="flex flex-col gap-bsr-1">
          {coverage.pipeline_funnel.map((stage) => (
            <div key={stage.stage} className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base p-bsr-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-bsr-text-primary">{stage.stage}</span>
                <span className="bsr-numeric text-bsr-text-secondary">
                  {stage.output_count}/{stage.relative_to} (−{stage.dropped})
                </span>
              </div>
              <p className="mt-1 text-[11px] text-bsr-text-tertiary">{stage.reason}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card title="تناسق قاعدة البيانات">
        <div className="grid grid-cols-2 gap-bsr-3 sm:grid-cols-3">
          <Stat label="نشطة بلا instrument_bucket" value={coverage.db_consistency.active_stocks_missing_instrument_bucket} />
          <Stat label="نشطة بلا قطاع" value={coverage.db_consistency.active_stocks_missing_sector} />
          <Stat label="نشطة بلا سوق" value={coverage.db_consistency.active_stocks_missing_exchange} />
          <Stat label="غير نشطة بلا سبب استبعاد" value={coverage.db_consistency.inactive_stocks_missing_exclusion_reason} />
        </div>
      </Card>

      <p className="text-[11px] text-bsr-text-tertiary">آخر تحديث: {fmtDate(coverage.generated_at)}</p>
    </div>
  );
}

export default function MarketCoveragePage() {
  return (
    <RequireStaff>
      <MarketCoveragePageInner />
    </RequireStaff>
  );
}
