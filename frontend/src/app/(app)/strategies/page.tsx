"use client";

import { useState } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { createBacktest, getBacktest, getBacktestMetrics } from "@/lib/api/backtests";
import { STRATEGY_OPTIONS } from "@/lib/api/backtests-types";
import type { BacktestRun } from "@/lib/api/backtests-types";
import { RUN_STATUS_LABELS } from "@/lib/market-intelligence-labels";
import {
  isFullBacktestReport,
  type FullBacktestReport,
} from "@/lib/api/backtest-metrics-types";

const POLL_INTERVAL_MS = 1500;
const MAX_POLLS = 60;

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function monthsAgoIso(months: number): string {
  const d = new Date();
  d.setMonth(d.getMonth() - months);
  return d.toISOString().slice(0, 10);
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-bsr-1 rounded-bsr-md bg-bsr-surface-overlay px-bsr-4 py-bsr-3">
      <span className="text-xs text-bsr-text-secondary">{label}</span>
      <span className="bsr-numeric text-lg font-semibold text-bsr-text-primary">{value}</span>
    </div>
  );
}

function pct(value: number | null): string {
  return value != null ? `${(value * 100).toFixed(1)}%` : "—";
}

function num(value: number | null, digits = 2): string {
  return value != null ? value.toFixed(digits) : "—";
}

export default function StrategiesPage() {
  const [symbols, setSymbols] = useState("2222, 1010, 1120");
  const [startDate, setStartDate] = useState(monthsAgoIso(6));
  const [endDate, setEndDate] = useState(todayIso());
  const [strategy, setStrategy] = useState(STRATEGY_OPTIONS[0].value);

  const [run, setRun] = useState<BacktestRun | null>(null);
  const [report, setReport] = useState<FullBacktestReport | null>(null);
  const [status, setStatus] = useState<"idle" | "running" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setReport(null);
    setStatus("running");

    const symbolList = symbols
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    if (symbolList.length === 0) {
      setError("أدخل رمز سهم واحد على الأقل.");
      setStatus("idle");
      return;
    }

    try {
      let current = await createBacktest({
        symbols: symbolList,
        start_date: startDate,
        end_date: endDate,
        strategy,
      });
      setRun(current);

      for (let i = 0; i < MAX_POLLS; i++) {
        if (current.status === "SUCCESS" || current.status === "FAILED") break;
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        current = await getBacktest(current.id);
        setRun(current);
      }

      if (current.status === "SUCCESS") {
        const metrics = await getBacktestMetrics(current.id);
        if (isFullBacktestReport(metrics.metrics)) {
          setReport(metrics.metrics);
        }
      } else if (current.status === "FAILED") {
        setError(current.error_message ?? "فشل تنفيذ اختبار الاستراتيجية.");
      }
      setStatus("idle");
    } catch {
      setError("تعذّر تشغيل اختبار الاستراتيجية. تحقق من المدخلات وحاول مرة أخرى.");
      setStatus("idle");
    }
  }

  return (
    <div className="flex flex-col gap-bsr-6">
      <div className="flex items-center gap-bsr-2">
        <AiStar size="lg" />
        <h1 className="text-lg font-semibold text-bsr-text-primary">الاستراتيجيات</h1>
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-bsr-4 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6"
      >
        <label className="flex flex-col gap-bsr-1">
          <span className="text-sm text-bsr-text-secondary">الرموز (مفصولة بفواصل)</span>
          <input
            value={symbols}
            onChange={(e) => setSymbols(e.target.value)}
            className="bsr-numeric rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
          />
        </label>

        <div className="grid grid-cols-1 gap-bsr-4 sm:grid-cols-3">
          <label className="flex flex-col gap-bsr-1">
            <span className="text-sm text-bsr-text-secondary">تاريخ البداية</span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="bsr-numeric rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-bsr-1">
            <span className="text-sm text-bsr-text-secondary">تاريخ النهاية</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="bsr-numeric rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-bsr-1">
            <span className="text-sm text-bsr-text-secondary">الاستراتيجية</span>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
            >
              {STRATEGY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.labelAr}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error ? <p className="text-sm text-bsr-market-down">{error}</p> : null}

        <button
          type="submit"
          disabled={status === "running"}
          className="self-start rounded-bsr-md bg-bsr-gold-500 px-bsr-5 py-bsr-2 font-semibold text-bsr-navy-950 hover:bg-bsr-gold-400 disabled:opacity-60"
        >
          {status === "running" ? "جارٍ اختبار الاستراتيجية..." : "اختبار الاستراتيجية"}
        </button>
      </form>

      {status === "running" && run ? (
        <div className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
          <p className="text-sm text-bsr-text-secondary">
            الحالة: {RUN_STATUS_LABELS[run.status] ?? run.status} ({run.progress_current} / {run.progress_total || "…"})
          </p>
          <LoadingScreen />
        </div>
      ) : null}

      {report ? (
        <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6">
          <h2 className="mb-bsr-4 text-base font-semibold text-bsr-text-primary">
            نتائج اختبار الاستراتيجية
          </h2>
          <div className="grid grid-cols-2 gap-bsr-3 sm:grid-cols-4">
            <MetricTile label="عدد التقييمات" value={String(report.overall.evaluation_count)} />
            <MetricTile label="دقة الاتجاه" value={pct(report.overall.direction_accuracy)} />
            <MetricTile label="معدل الفوز" value={pct(report.overall.win_rate)} />
            <MetricTile label="معامل الربح" value={num(report.overall.profit_factor)} />
            <MetricTile
              label="متوسط العائد المتوقع"
              value={report.overall.average_forward_return_pct != null ? `${report.overall.average_forward_return_pct.toFixed(2)}%` : "—"}
            />
            <MetricTile label="أقصى انخفاض" value={pct(report.overall.max_drawdown)} />
            <MetricTile label="نسبة شارب" value={num(report.overall.sharpe_ratio)} />
            <MetricTile label="نسبة سورتينو" value={num(report.overall.sortino_ratio)} />
          </div>
          <p className="mt-bsr-4 text-xs text-bsr-text-muted">
            تم تقييم {report.evaluated_count} حالة، منها {report.filtered_count} ضمن معايير
            التصفية{report.cancelled ? " -- تم إلغاء الاختبار قبل اكتماله." : "."}
          </p>
        </section>
      ) : null}

      {status === "idle" && !run ? (
        <EmptyState
          title="اختبر استراتيجية على بيانات تاريخية"
          description="حدد الرموز، الفترة الزمنية، والاستراتيجية، ثم شغّل اختبار أداء حقيقي عبر محرك الاختبار الخلفي."
        />
      ) : null}
    </div>
  );
}
