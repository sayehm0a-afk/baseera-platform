"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { getFollowedSignals } from "@/lib/api/signals";
import type { FollowedSignal } from "@/lib/api/signals-types";
import { formatArabicDateTime, formatRelativeAgeAr } from "@/lib/format/freshness";

type PanelState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; items: FollowedSignal[] };

const RESOLVED_WIN_STATUSES = new Set(["TARGET_1_HIT", "TARGET_2_HIT", "TARGET_3_HIT"]);
const RESOLVED_LOSS_STATUSES = new Set(["STOP_LOSS_HIT"]);

function outcomeColorClass(status: string | null): string {
  if (status != null && RESOLVED_WIN_STATUSES.has(status)) return "text-bsr-market-up";
  if (status != null && RESOLVED_LOSS_STATUSES.has(status)) return "text-bsr-market-down";
  return "text-bsr-text-secondary";
}

/** Every signal this user explicitly tapped "متابعة هذه الإشارة" on
 * (see RadarOpportunityCard), with its real, already-tracked outcome
 * -- never recomputed here (see
 * src.market_intelligence.followed_signals.list_followed_signals). */
export function FollowedSignalsPanel() {
  const [state, setState] = useState<PanelState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getFollowedSignals()
      .then((result) => {
        if (!cancelled) setState({ status: "ready", items: result.items });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return <LoadingScreen />;
  }

  if (state.status === "error") {
    return <EmptyState title="تعذّر تحميل الإشارات المتابَعة" description="تأكد من اتصال الخادم وحاول مرة أخرى." />;
  }

  if (state.items.length === 0) {
    return (
      <EmptyState
        title="لا تتابع أي إشارة بعد"
        description={'اضغط "متابعة هذه الإشارة" على أي توصية شراء في الرادار الذكي لتتبع نتيجتها الحقيقية هنا.'}
      />
    );
  }

  return (
    <ul className="flex flex-col divide-y divide-bsr-border-subtle">
      {state.items.map((item) => (
        <li key={item.id} className="flex flex-col gap-bsr-1 px-bsr-4 py-bsr-3">
          <div className="flex items-center justify-between gap-bsr-3">
            <Link href={`/stocks/${item.symbol}`} className="flex flex-col">
              <span className="bsr-numeric font-semibold text-bsr-text-primary">{item.symbol}</span>
              {item.company_name_ar ? (
                <span className="text-sm text-bsr-text-secondary">{item.company_name_ar}</span>
              ) : null}
            </Link>
            <span className={`text-sm font-semibold ${outcomeColorClass(item.outcome_status)}`}>
              {item.outcome_status_label_ar ?? "قيد المتابعة"}
            </span>
          </div>
          <p className="text-xs text-bsr-text-secondary">
            تابعت هذه الإشارة: <span className="bsr-numeric">{formatArabicDateTime(item.followed_at)}</span> (
            {formatRelativeAgeAr(item.followed_at)})
          </p>
          {item.outcome_return_pct != null ? (
            <p className={`bsr-numeric text-sm font-semibold ${outcomeColorClass(item.outcome_status)}`}>
              العائد المحقق: {item.outcome_return_pct > 0 ? "+" : ""}
              {item.outcome_return_pct.toFixed(2)}%
            </p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
