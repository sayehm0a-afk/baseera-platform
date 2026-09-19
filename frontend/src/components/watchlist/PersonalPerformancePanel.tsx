"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { getPersonalPerformance } from "@/lib/api/signals";
import type { PersonalPerformanceComparison } from "@/lib/api/signals-types";

type PanelState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; data: PersonalPerformanceComparison };

function formatWinRate(value: number | null): string {
  return value == null ? "--" : `${Math.round(value)}%`;
}

/** "أداؤك الشخصي مقابل أداء الخوارزمية" (product decision 2026-09-18):
 * the user's own resolved win rate among signals they explicitly
 * followed, next to the algorithm's overall resolved win rate --
 * both computed the exact same way (see
 * src.market_intelligence.followed_signals), so the comparison is
 * genuinely apples-to-apples, never two different metrics dressed up
 * as comparable. */
export function PersonalPerformancePanel() {
  const [state, setState] = useState<PanelState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getPersonalPerformance()
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data });
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
    return <EmptyState title="تعذّر تحميل مقارنة الأداء" description="تأكد من اتصال الخادم وحاول مرة أخرى." />;
  }

  const { data } = state;

  if (data.insufficient_data_message_ar) {
    return <EmptyState title="لا توجد بيانات كافية بعد" description={data.insufficient_data_message_ar} />;
  }

  return (
    <div className="grid grid-cols-2 gap-bsr-3">
      <div className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-overlay p-bsr-3">
        <p className="text-xs text-bsr-text-secondary">أداؤك الشخصي</p>
        <p className="bsr-numeric text-2xl font-bold text-bsr-teal-500">{formatWinRate(data.personal_win_rate_pct)}</p>
        <p className="text-xs text-bsr-text-secondary">
          من {data.personal_resolved_sample_size} إشارة محسومة تابعتها
        </p>
        {data.personal_small_sample_warning ? (
          <p className="mt-1 text-xs text-bsr-gold-500">عينة صغيرة -- تابع المزيد من الإشارات لنتيجة أدق.</p>
        ) : null}
      </div>
      <div className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-overlay p-bsr-3">
        <p className="text-xs text-bsr-text-secondary">أداء الخوارزمية عمومًا</p>
        <p className="bsr-numeric text-2xl font-bold text-bsr-gold-500">{formatWinRate(data.algorithm_win_rate_pct)}</p>
        <p className="text-xs text-bsr-text-secondary">
          من {data.algorithm_resolved_sample_size} إشارة محسومة على مستوى المنصة
        </p>
        {data.algorithm_small_sample_warning ? (
          <p className="mt-1 text-xs text-bsr-gold-500">
            عينة أولية -- العدد الحالي أقل من الحد الأدنى الإحصائي، والرقم قد يتغيّر بشكل ملموس مع تراكم المزيد من النتائج.
          </p>
        ) : null}
      </div>
    </div>
  );
}
