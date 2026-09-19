"use client";

import { useState } from "react";
import { getScanRun, triggerScan } from "@/lib/api/market";

const POLL_INTERVAL_MS = 1500;
const MAX_POLLS = 40;

/** Triggers a real market scan (POST /api/v1/market/scan), polls the
 * run until it finishes, then calls `onScanComplete` so the caller
 * re-reads the newly persisted summary -- no scan/ranking logic is
 * duplicated here, this only calls the existing backend job and waits
 * for it.
 *
 * `onScanComplete` replaces a previous `router.refresh()` call here:
 * every real consumer of this button (dashboard, scan, opportunities,
 * reports) is a "use client" page that fetches its data through a
 * hook's own useEffect/state, not a Server Component, so
 * `router.refresh()` -- which only re-renders Server Components --
 * was a silent no-op. The caller now passes its own hook's `reload`
 * instead. */
export function RunScanButton({
  label,
  onScanComplete,
}: { label?: string; onScanComplete?: () => void } = {}) {
  const [status, setStatus] = useState<"idle" | "running" | "error" | "timeout">("idle");

  async function handleClick() {
    setStatus("running");
    try {
      const run = await triggerScan();
      let finished = false;
      for (let i = 0; i < MAX_POLLS; i++) {
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        const polled = await getScanRun(run.id);
        if (polled.status === "SUCCESS" || polled.status === "FAILED") {
          finished = true;
          break;
        }
      }
      if (!finished) {
        // The scan is still PENDING/RUNNING server-side after MAX_POLLS --
        // reporting success here would be false: the caller would reload
        // into the same stale/empty data with no indication anything
        // timed out. Surface it distinctly instead of silently going idle.
        setStatus("timeout");
        return;
      }
      setStatus("idle");
      onScanComplete?.();
    } catch {
      setStatus("error");
    }
  }

  return (
    <div className="flex flex-col items-center gap-bsr-2">
      <button
        type="button"
        onClick={handleClick}
        disabled={status === "running"}
        className="rounded-bsr-md bg-bsr-gold-500 px-bsr-4 py-bsr-2 font-semibold text-bsr-navy-950 transition-colors hover:bg-bsr-gold-400 disabled:opacity-60"
      >
        {status === "running" ? "جارٍ المسح..." : (label ?? "تشغيل مسح السوق الآن")}
      </button>
      <div aria-live="polite" className="contents">
        {status === "error" ? (
          <p className="text-sm text-bsr-market-down">
            تعذّر تشغيل المسح -- قد يكون هناك مسح آخر قيد التنفيذ بالفعل، أو تعذّر الاتصال بالخادم. حاول
            مرة أخرى بعد قليل.
          </p>
        ) : null}
        {status === "timeout" ? (
          <p className="text-sm text-bsr-text-secondary">
            المسح ما زال قيد التنفيذ في الخادم -- يستغرق وقتًا أطول من المعتاد. يمكنك الانتظار قليلاً ثم
            تحديث الصفحة لعرض النتائج عند اكتمالها.
          </p>
        ) : null}
      </div>
    </div>
  );
}
