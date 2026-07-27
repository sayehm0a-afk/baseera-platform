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
export function RunScanButton() {
  const router = useRouter();
  const [status, setStatus] = useState<"idle" | "running" | "error">("idle");

  async function handleClick() {
    setStatus("running");
    try {
      const run = await triggerScan();
      for (let i = 0; i < MAX_POLLS; i++) {
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        const polled = await getScanRun(run.id);
        if (polled.status === "SUCCESS" || polled.status === "FAILED") {
          break;
        }
      }
      setStatus("idle");
      router.refresh();
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
        {status === "running" ? "جارٍ المسح..." : "تشغيل مسح السوق الآن"}
      </button>
      {status === "error" ? (
        <p className="text-sm text-bsr-market-down">
          تعذّر تشغيل المسح. تأكد من اتصال الخادم وحاول مرة أخرى.
        </p>
      ) : null}
    </div>
  );
}
