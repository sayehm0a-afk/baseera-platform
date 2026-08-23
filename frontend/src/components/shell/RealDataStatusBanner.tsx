"use client";

import { useEffect, useState } from "react";
import { getMarketDataHealth, getMarketStatus } from "@/lib/api/market";
import type { MarketDataHealth, MarketStatus } from "@/lib/api/types";

type BannerState =
  | { kind: "hidden" }
  | { kind: "unavailable" }
  | { kind: "unknown" }
  | { kind: "status"; marketStatus: MarketStatus | null };

const STATUS_DOT_CLASS: Record<string, string> = {
  OPEN: "bg-bsr-market-up",
  PRE_MARKET: "bg-bsr-text-muted",
  PRE_OPEN_AUCTION: "bg-bsr-action-watch",
  CLOSING_AUCTION: "bg-bsr-action-watch",
  CLOSING_PRICE_TRADING: "bg-bsr-action-watch",
  POST_CLOSE: "bg-bsr-text-muted",
  WEEKEND: "bg-bsr-text-muted",
  CLOSED: "bg-bsr-text-muted",
  UNKNOWN: "bg-bsr-text-muted",
  PROVIDER_UNREACHABLE: "bg-bsr-market-down",
};

const STATUS_TEXT_CLASS: Record<string, string> = {
  OPEN: "text-bsr-market-up",
  PRE_MARKET: "text-bsr-text-secondary",
  PRE_OPEN_AUCTION: "text-bsr-action-watch",
  CLOSING_AUCTION: "text-bsr-action-watch",
  CLOSING_PRICE_TRADING: "text-bsr-action-watch",
  POST_CLOSE: "text-bsr-text-secondary",
  WEEKEND: "text-bsr-text-secondary",
  CLOSED: "text-bsr-text-secondary",
  UNKNOWN: "text-bsr-text-secondary",
  PROVIDER_UNREACHABLE: "text-bsr-market-down",
};

/** Statuses where prices on screen belong to a completed session, not
 * a live tick -- the banner should always say which session that is. */
const NON_LIVE_STATUSES = new Set([
  "PRE_MARKET", "PRE_OPEN_AUCTION", "POST_CLOSE", "WEEKEND", "CLOSED", "UNKNOWN",
]);

/** Strict real-data mode's visible proof, shown on every authenticated
 * screen (mounted once in AppShell): GET /health/market-data is polled
 * on load, and whenever strict_real_data is true, this renders either
 * a real-data-unavailable notice or the current Tadawul market status
 * -- it must never render nothing while can_publish_recommendations is
 * false. Deployments with strict mode off (local dev/CI, which never
 * claim to be analyzing the real market in the first place) render
 * nothing here, unchanged from before this component existed.
 *
 * Also folds in GET /api/v1/market/status so a closed market never
 * reads as "data unavailable" -- it reads as "السوق مغلق" plus which
 * completed session the currently-displayed prices belong to (Section
 * 2 of the practical-testing release: closed must never look broken).
 */
export function RealDataStatusBanner() {
  const [state, setState] = useState<BannerState>({ kind: "hidden" });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      let health: MarketDataHealth;
      try {
        health = await getMarketDataHealth();
      } catch {
        if (!cancelled) setState({ kind: "unavailable" });
        return;
      }
      if (cancelled) return;

      if (!health.strict_real_data) {
        setState({ kind: "hidden" });
        return;
      }

      if (!health.can_publish_recommendations) {
        // Production truthfulness fix (2026-08-23): only render the
        // "تعذر الحصول على بيانات حقيقية" failure message for a
        // genuinely observed failure. `provider_state ===
        // "UNKNOWN_NO_RECENT_CHECK"` means no worker has made a real
        // provider-selection call recently enough for the shared health
        // snapshot to still be fresh -- confirmed in production even
        // moments after a fully successful SAHMK ingestion run (see
        // src/market_data/provider_factory.py's own module docstring).
        // `can_publish_recommendations` itself is unchanged -- still
        // fail-closed -- only the banner's wording is now honest about
        // which of the two situations is real.
        if (!cancelled) {
          setState(health.provider_state === "UNKNOWN_NO_RECENT_CHECK" ? { kind: "unknown" } : { kind: "unavailable" });
        }
        return;
      }

      try {
        const marketStatus = await getMarketStatus();
        if (!cancelled) setState({ kind: "status", marketStatus });
      } catch {
        if (!cancelled) setState({ kind: "status", marketStatus: null });
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.kind === "hidden") return null;

  if (state.kind === "unavailable") {
    return (
      <div
        role="status"
        className="flex items-center justify-center gap-bsr-2 bg-bsr-market-down/15 px-bsr-4 py-bsr-1.5 text-xs font-semibold text-bsr-market-down"
      >
        <span className="h-2 w-2 rounded-full bg-bsr-market-down" />
        تعذر الحصول على بيانات حقيقية من مزود البيانات — التحليل متوقف مؤقتًا لحين استعادة الاتصال
      </div>
    );
  }

  if (state.kind === "unknown") {
    return (
      <div
        role="status"
        className="flex items-center justify-center gap-bsr-2 bg-bsr-surface-overlay px-bsr-4 py-bsr-1.5 text-xs font-semibold text-bsr-text-secondary"
      >
        <span className="h-2 w-2 rounded-full bg-bsr-text-muted" />
        لم يتم التحقق من الاتصال بمزود البيانات مؤخرًا — لا يوجد دليل على وجود عطل حاليًا
      </div>
    );
  }

  const ms = state.marketStatus;
  const status = ms?.status ?? "CLOSED";
  const dotClass = STATUS_DOT_CLASS[status] ?? STATUS_DOT_CLASS.CLOSED;
  const textClass = STATUS_TEXT_CLASS[status] ?? STATUS_TEXT_CLASS.CLOSED;
  const showLastSession = ms && NON_LIVE_STATUSES.has(status) && ms.last_completed_session_date;

  return (
    <div
      role="status"
      className={`flex flex-wrap items-center justify-center gap-bsr-2 bg-bsr-surface-overlay px-bsr-4 py-bsr-1.5 text-xs font-semibold ${textClass}`}
    >
      <span className={`h-2 w-2 rounded-full ${dotClass}`} />
      <span>{ms?.label_ar ?? "السوق مغلق"}</span>
      {showLastSession ? (
        <span className="bsr-numeric font-normal text-bsr-text-secondary">
          — آخر جلسة تداول مكتملة: {ms!.last_completed_session_date}
        </span>
      ) : null}
      <span className="font-normal text-bsr-text-muted">بيانات حقيقية من سهمك (SAHMK)</span>
    </div>
  );
}
