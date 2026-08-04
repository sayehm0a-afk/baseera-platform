"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { getRankings, getScanProgress } from "@/lib/api/market";
import type { MarketScanProgress } from "@/lib/api/types";

const POLL_INTERVAL_MS = 2000;

type PanelState =
  | { kind: "loading" }
  | { kind: "no_run" }
  | { kind: "no_progress_for_run" }
  | { kind: "progress"; data: MarketScanProgress };

/** Live scan progress -- real data from
 * GET /api/v1/market/scan/{run_id}/progress, which reads
 * MarketScanProgress (updated after every symbol by
 * ScanProgressTracker, not the once-at-the-end MarketScanRun
 * counters). Discovers the latest scan_run_id via a real rankings
 * call (the only response shape that currently exposes it), then
 * polls the progress route while the run is RUNNING. */
export function LiveScanPanel() {
  const [state, setState] = useState<PanelState>({ kind: "loading" });
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const rankings = await getRankings("TOP_BUY");
        const runId = rankings.scan_run_id;
        if (runId == null) {
          if (!cancelled) setState({ kind: "no_run" });
          return;
        }
        try {
          const progress = await getScanProgress(runId);
          if (cancelled) return;
          setState({ kind: "progress", data: progress });
          if (progress.status !== "RUNNING" && intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        } catch (error: unknown) {
          if (cancelled) return;
          if (error instanceof ApiError && error.code === "no_market_scan_data") {
            setState({ kind: "no_progress_for_run" });
          } else {
            throw error;
          }
        }
      } catch {
        if (!cancelled) setState({ kind: "no_run" });
      }
    }

    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  if (state.kind === "loading" || state.kind === "no_run") return null;

  if (state.kind === "no_progress_for_run") {
    return (
      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
        <p className="text-sm text-bsr-text-secondary">
          لا يوجد تتبع تقدّم حي لآخر مسح (رُصد قبل تفعيل هذه الميزة).
        </p>
      </section>
    );
  }

  const d = state.data;
  const isRunning = d.status === "RUNNING";

  return (
    <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <div className="mb-bsr-3 flex items-center justify-between">
        <h2 className="text-base font-semibold text-bsr-text-primary">
          {isRunning ? "المسح جارٍ الآن" : `المسح: ${d.status}`}
        </h2>
        <span className="bsr-numeric text-sm text-bsr-teal-500">
          {d.progress_pct}%
        </span>
      </div>

      <div className="mb-bsr-3 h-2 w-full overflow-hidden rounded-bsr-full bg-bsr-surface-base">
        <div
          className="h-full rounded-bsr-full bg-bsr-teal-500 transition-[width]"
          style={{ width: `${Math.min(100, Math.max(0, d.progress_pct))}%` }}
        />
      </div>

      {isRunning ? (
        <p className="mb-bsr-3 text-sm text-bsr-text-secondary">
          الرمز الحالي:{" "}
          <span className="bsr-numeric font-semibold text-bsr-text-primary">
            {d.current_symbol ?? "-"}
          </span>{" "}
          {d.current_symbol_name_en ? `(${d.current_symbol_name_en})` : ""}
        </p>
      ) : null}

      <dl className="grid grid-cols-2 gap-bsr-2 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-bsr-text-secondary">مكتمل</dt>
          <dd className="bsr-numeric font-semibold text-bsr-text-primary">
            {d.completed_count} / {d.eligible_discovered}
          </dd>
        </div>
        <div>
          <dt className="text-bsr-text-secondary">متبقٍ</dt>
          <dd className="bsr-numeric font-semibold text-bsr-text-primary">
            {d.remaining_count}
          </dd>
        </div>
        <div>
          <dt className="text-bsr-text-secondary">ناجح</dt>
          <dd className="bsr-numeric font-semibold text-bsr-market-up">
            {d.success_count}
          </dd>
        </div>
        <div>
          <dt className="text-bsr-text-secondary">فاشل</dt>
          <dd className="bsr-numeric font-semibold text-bsr-market-down">
            {d.failed_count}
          </dd>
        </div>
        <div>
          <dt className="text-bsr-text-secondary">منشور (شراء/بيع/حياد)</dt>
          <dd className="bsr-numeric font-semibold text-bsr-text-primary">
            {d.published_count}
          </dd>
        </div>
        <div>
          <dt className="text-bsr-text-secondary">مرفوض</dt>
          <dd className="bsr-numeric font-semibold text-bsr-text-primary">
            {d.rejected_count}
          </dd>
        </div>
        <div>
          <dt className="text-bsr-text-secondary">طلبات API</dt>
          <dd className="bsr-numeric font-semibold text-bsr-text-primary">
            {d.api_calls_total}
          </dd>
        </div>
        <div>
          <dt className="text-bsr-text-secondary">إعادة المحاولة</dt>
          <dd className="bsr-numeric font-semibold text-bsr-text-primary">
            {d.retries_total}
          </dd>
        </div>
      </dl>

      {d.latest_error ? (
        <p className="mt-bsr-3 text-sm text-bsr-market-down">
          آخر خطأ: {d.latest_error}
        </p>
      ) : null}
    </section>
  );
}
