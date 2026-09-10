"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { getScanRun, triggerScan } from "@/lib/api/market";

const POLL_INTERVAL_MS = 1500;
const MAX_POLLS = 40;

/** Triggers a real market scan (POST /api/v1/market/scan), polls the
 * run until it finishes, then refreshes the dashboard so it reads the
 * newly persisted summary -- no scan/ranking logic is duplicated here,
 * this only calls the existing backend job and waits for it. */
export function RunScanButton({ label }: { label?: string } = {}) {
  const router = useRouter();
  const [status, setStatus] = useState<"idle" | "running" | "error" | "failed" | "timeout">("idle");

  async function handleClick() {
    setStatus("running");
    try {
      const run = await triggerScan();
      for (let i = 0; i < MAX_POLLS; i++) {
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        const polled = await getScanRun(run.id);
        if (polled.status === "SUCCESS") {
          setStatus("idle");
          router.refresh();
          return;
        }
        if (polled.status === "FAILED") {
          setStatus("failed");
          return;
        }
      }
      setStatus("timeout");
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
      {status === "failed" ? (
        <p role="alert" className="text-sm text-bsr-market-down">
          لم ينجح المسح. لا توجد نتيجة جديدة مؤكدة من هذه المحاولة.
        </p>
      ) : null}
      {status === "timeout" ? (
        <p role="status" className="text-sm text-bsr-text-secondary">
          لم يصل تأكيد اكتمال المسح خلال دقيقة. قد يكون مستمرًا؛ راجع حالته قبل إعادة تشغيله.
        </p>
      ) : null}
      {status === "error" ? (
        <p className="text-sm text-bsr-market-down">
          تعذّر تشغيل المسح -- قد يكون هناك مسح آخر قيد التنفيذ بالفعل، أو تعذّر الاتصال بالخادم. حاول
          مرة أخرى بعد قليل.
        </p>
      ) : null}
    </div>
  );
}
