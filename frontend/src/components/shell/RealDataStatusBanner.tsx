"use client";

import { useEffect, useState } from "react";
import { getMarketDataHealth } from "@/lib/api/market";
import type { MarketDataHealth } from "@/lib/api/types";

type BannerState =
  | { kind: "hidden" }
  | { kind: "real"; health: MarketDataHealth }
  | { kind: "unavailable"; health: MarketDataHealth | null };

/** Strict real-data mode's visible proof, shown on every authenticated
 * screen (mounted once in AppShell): GET /health/market-data is polled
 * on load, and whenever strict_real_data is true, this must show
 * either "REAL SAHMK DATA" or "REAL DATA UNAVAILABLE -- ANALYSIS
 * DISABLED" -- it must never render a normal, silent "everything is
 * fine" state while can_publish_recommendations is false. Deployments
 * with strict mode off (local dev/CI, which never claim to be
 * analyzing the real market in the first place) render nothing here,
 * unchanged from before this component existed. */
export function RealDataStatusBanner() {
  const [state, setState] = useState<BannerState>({ kind: "hidden" });

  useEffect(() => {
    let cancelled = false;
    getMarketDataHealth()
      .then((health) => {
        if (cancelled) return;
        if (!health.strict_real_data) {
          setState({ kind: "hidden" });
          return;
        }
        setState(
          health.can_publish_recommendations
            ? { kind: "real", health }
            : { kind: "unavailable", health }
        );
      })
      .catch(() => {
        if (!cancelled) setState({ kind: "unavailable", health: null });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.kind === "hidden") return null;

  const isReal = state.kind === "real";
  return (
    <div
      role="status"
      className={
        "flex items-center justify-center gap-bsr-2 px-bsr-4 py-bsr-1.5 text-xs font-semibold " +
        (isReal
          ? "bg-bsr-market-up/15 text-bsr-market-up"
          : "bg-bsr-market-down/15 text-bsr-market-down")
      }
    >
      <span className={"h-2 w-2 rounded-full " + (isReal ? "bg-bsr-market-up" : "bg-bsr-market-down")} />
      {isReal ? "REAL SAHMK DATA" : "REAL DATA UNAVAILABLE — ANALYSIS DISABLED"}
    </div>
  );
}
