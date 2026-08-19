"use client";

import { useCallback, useEffect, useState } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { RadarOpportunityCard } from "@/components/radar/RadarOpportunityCard";
import { getRadarSummary } from "@/lib/api/radar";
import type { RadarHomeSummary } from "@/lib/api/radar-types";

type RadarData =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; summary: RadarHomeSummary };

// Client Component for the same reason every other authenticated
// screen in this app is one (apiFetch depends on the browser's
// httpOnly session cookie). GET /api/v1/radar/summary reads only
// already-persisted RadarOpportunity/DecisionV2Snapshot rows -- this
// page never triggers a market scan and spends zero SAHMK quota.
async function fetchRadarData(): Promise<RadarData> {
  try {
    const summary = await getRadarSummary();
    return { status: "ready", summary };
  } catch {
    return { status: "error" };
  }
}

function useRadarData() {
  const [data, setData] = useState<RadarData>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchRadarData().then((result) => {
      if (!cancelled) setData(result);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const reload = useCallback(() => {
    setData({ status: "loading" });
    fetchRadarData().then(setData);
  }, []);

  return { data, reload };
}

/** Market-wide entry-risk read (classify_market_risk) -- reuses the
 * existing up/down semantic tokens (never a new color system): green
 * when new entries are permitted, red when they are blocked. The
 * Arabic label/basis text always comes verbatim from the backend. */
function MarketRiskBanner({ summary }: { summary: RadarHomeSummary }) {
  const colorClass = summary.entry_permitted ? "text-bsr-market-up" : "text-bsr-market-down";
  return (
    <div className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-bsr-text-secondary">حالة السوق: {summary.market_status_label_ar}</span>
        <span className={`text-sm font-semibold ${colorClass}`}>{summary.market_risk_label_ar}</span>
      </div>
      <p className="mt-bsr-2 text-xs text-bsr-text-secondary">{summary.market_risk_basis_ar}</p>
      {!summary.market_risk_is_live ? (
        <p className="mt-bsr-1 text-xs text-bsr-text-muted">هذا التقييم مبني على آخر جلسة تداول مكتملة، وليس بيانات حية.</p>
      ) : null}
    </div>
  );
}

/** The real Radar V2 scan funnel -- Stage 1 scans the full local Saudi
 * market universe at zero SAHMK cost and ranks candidates; Stage 2
 * live-validates only the top-ranked ones, capped to protect paid
 * SAHMK quota. Shown so "الفرص الحية" never reads as "only N stocks
 * were checked" when the radar actually scanned far more. Renders
 * nothing until a real Radar V2 cycle has completed at least once --
 * never a fabricated count. */
function ScanFunnelBanner({ summary }: { summary: RadarHomeSummary }) {
  if (summary.stage1_universe_size == null || summary.stage1_candidate_count == null) {
    return null;
  }
  return (
    <div className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <p className="text-xs text-bsr-text-secondary">
        فحص الرادار{" "}
        <span className="bsr-numeric font-semibold text-bsr-text-primary">{summary.stage1_universe_size}</span> سهمًا في السوق
        السعودي محليًا (بدون تكلفة)، ورشّح منها{" "}
        <span className="bsr-numeric font-semibold text-bsr-text-primary">{summary.stage1_candidate_count}</span> مرشحًا، ثم تحقّق
        حيًا من أفضل{" "}
        <span className="bsr-numeric font-semibold text-bsr-text-primary">
          {Math.min(summary.stage1_candidate_count, summary.stage2_candidate_cap)}
        </span>{" "}
        منها لحماية رصيد الاستعلامات الحية.
      </p>
    </div>
  );
}

export default function RadarPage() {
  const { data, reload } = useRadarData();

  return (
    <div className="flex flex-col gap-bsr-6">
      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 text-center md:p-bsr-6">
        <div className="mb-bsr-2 flex items-center justify-center gap-bsr-2">
          <AiStar />
          <h1 className="text-lg font-semibold text-bsr-text-primary">الرادار الذكي</h1>
        </div>
        <p className="mb-bsr-4 text-sm text-bsr-text-secondary">
          الفرص التي رصدها بصيرة حاليًا في السوق السعودي، مرتبة بحسب قوة الأدلة الفنية
        </p>
        <button
          type="button"
          onClick={reload}
          disabled={data.status === "loading"}
          className="rounded-bsr-md bg-bsr-gold-500 px-bsr-6 py-bsr-2 font-semibold text-bsr-navy-950 transition-colors hover:bg-bsr-gold-400 disabled:opacity-60"
        >
          {data.status === "loading" ? "جارٍ التحديث..." : "تحديث الرادار"}
        </button>
      </section>

      {data.status === "loading" ? <LoadingScreen /> : null}

      {data.status === "error" ? (
        <EmptyState
          title="تعذّر تحميل الرادار الذكي"
          description="تأكد من اتصال الخادم وحاول مرة أخرى."
          action={
            <button
              type="button"
              onClick={reload}
              className="rounded-bsr-md border border-bsr-border-subtle px-bsr-4 py-bsr-2 text-sm font-semibold text-bsr-text-primary"
            >
              إعادة المحاولة
            </button>
          }
        />
      ) : null}

      {data.status === "ready" ? <MarketRiskBanner summary={data.summary} /> : null}
      {data.status === "ready" ? <ScanFunnelBanner summary={data.summary} /> : null}

      {data.status === "ready" && data.summary.live_opportunity_count === 0 ? (
        <EmptyState
          title="لا توجد فرص مرصودة حاليًا"
          description="لم يرصد الرادار الذكي أي فرصة حقيقية تستوفي معايير الجودة في آخر مسح للسوق."
        />
      ) : null}

      {data.status === "ready" && data.summary.live_opportunity_count > 0 ? (
        <section className="flex flex-col gap-bsr-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-bsr-text-primary">
              الفرص الحية ({data.summary.live_opportunity_count})
            </h2>
            {data.summary.average_confidence != null ? (
              <span className="text-sm text-bsr-text-secondary">
                متوسط الثقة:{" "}
                <span className="bsr-numeric font-semibold text-bsr-teal-500">
                  {Math.round(data.summary.average_confidence)}%
                </span>
              </span>
            ) : null}
          </div>
          <div className="grid grid-cols-1 gap-bsr-4 md:grid-cols-2">
            {data.summary.top_opportunities.map((opportunity) => (
              <RadarOpportunityCard key={opportunity.id} opportunity={opportunity} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
