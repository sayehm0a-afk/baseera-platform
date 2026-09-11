"use client";

import { useCallback, useEffect, useState } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { RadarOpportunityCard } from "@/components/radar/RadarOpportunityCard";
import { getRadarSummary, triggerRadarScanNow } from "@/lib/api/radar";
import type { RadarHomeSummary } from "@/lib/api/radar-types";
import { formatArabicDateTime, formatRelativeAgeAr, isEntryMissed } from "@/lib/format/freshness";

// On-demand consumer scan mandate (2026-09-11): honest Arabic text for
// every real stop_reason POST /scan-now can return (both the shared
// run_one_bounded_background_cycle's own reasons, and this route's own
// cooldown_active/redis_unavailable) -- never a generic failure string
// hiding which real safety gate declined the scan.
const SCAN_NOW_STOP_REASON_AR: Record<string, string> = {
  cooldown_active: "يمكنك طلب فحص فوري جديد بعد قليل -- كل مستخدم له فترة انتظار محدودة بين الطلبات.",
  redis_unavailable: "تعذّر التحقق من فترة الانتظار حاليًا. حاول مرة أخرى بعد قليل.",
  upstream_confirmed_exhausted: "استُنفد رصيد بيانات السوق الحي لليوم. سيُستأنف الفحص غدًا تلقائيًا.",
  background_quota_low: "رصيد بيانات السوق الحي منخفض حاليًا، فتم تأجيل هذا الفحص لحماية الفحوصات المجدولة.",
  database_unhealthy: "تعذّر الاتصال بقاعدة البيانات مؤقتًا. حاول مرة أخرى بعد قليل.",
  redis_unhealthy: "تعذّر الاتصال بخدمة التخزين المؤقت. حاول مرة أخرى بعد قليل.",
  sahmk_not_live: "مزوّد بيانات السوق الحي غير متصل حاليًا. حاول مرة أخرى بعد قليل.",
  scan_in_progress: "هناك فحص آخر قيد التنفيذ حاليًا. حاول مرة أخرى بعد قليل.",
  not_leader: "خادم آخر يتولى الفحص حاليًا. حاول مرة أخرى بعد قليل.",
  no_candidates: "لم يجد الفحص المحلي أي مرشح جديد يستحق التحقق الحي في هذه اللحظة.",
  universe_complete: "لا توجد رموز جديدة تحتاج فحصًا حيًا في هذه اللحظة.",
};

function scanNowMessageAr(stopReason: string | null, retryAfterSeconds: number | null): string {
  if (!stopReason) return "";
  const base = SCAN_NOW_STOP_REASON_AR[stopReason] ?? "تعذّر تنفيذ الفحص الفوري لسبب غير متوقع. حاول مرة أخرى لاحقًا.";
  if (stopReason === "cooldown_active" && retryAfterSeconds != null && retryAfterSeconds > 0) {
    const minutes = Math.ceil(retryAfterSeconds / 60);
    return `يمكنك طلب فحص فوري جديد بعد ${minutes} ${minutes === 1 ? "دقيقة" : "دقائق"} تقريبًا.`;
  }
  return base;
}

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
  const validated = Math.min(summary.stage1_candidate_count, summary.stage2_candidate_cap);
  return (
    <div className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 space-y-1">
      <p className="text-xs text-bsr-text-secondary">
        فحص الرادار{" "}
        <span className="bsr-numeric font-semibold text-bsr-text-primary">{summary.stage1_universe_size}</span> سهمًا في السوق
        السعودي
        {summary.stage1_evaluated_count != null && summary.stage1_evaluated_count !== summary.stage1_universe_size ? (
          <>
            {" "}
            (<span className="bsr-numeric font-semibold text-bsr-text-primary">{summary.stage1_evaluated_count}</span> منها قابل
            للتحليل حاليًا)
          </>
        ) : null}
        {" "}محليًا بدون تكلفة، ورشّح منها{" "}
        <span className="bsr-numeric font-semibold text-bsr-text-primary">{summary.stage1_candidate_count}</span> مرشحًا، ثم تحقّق
        حيًا من أفضل{" "}
        <span className="bsr-numeric font-semibold text-bsr-text-primary">{validated}</span> لحماية رصيد الاستعلامات الحية.
      </p>
      {summary.final_opportunities_count != null ? (
        <p className="text-xs text-bsr-text-secondary">
          نتج عن هذا الفحص{" "}
          <span className="bsr-numeric font-semibold text-bsr-text-primary">{summary.final_opportunities_count}</span> فرصة
          جديدة/محدّثة.
        </p>
      ) : null}
    </div>
  );
}

type ScanNowState =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "done"; executed: boolean; messageAr: string };

export default function RadarPage() {
  const { data, reload } = useRadarData();
  const [scanNow, setScanNow] = useState<ScanNowState>({ phase: "idle" });

  const handleScanNow = useCallback(async () => {
    setScanNow({ phase: "loading" });
    try {
      const result = await triggerRadarScanNow();
      if (result.executed) {
        setScanNow({
          phase: "done",
          executed: true,
          messageAr:
            result.opportunities_emitted_count > 0
              ? `اكتمل الفحص الفوري -- تم رصد ${result.opportunities_emitted_count} فرصة جديدة/محدّثة.`
              : "اكتمل الفحص الفوري -- لم تُرصد فرص جديدة تستوفي معايير الجودة هذه المرة.",
        });
        reload();
      } else {
        setScanNow({
          phase: "done",
          executed: false,
          messageAr: scanNowMessageAr(result.stop_reason, result.retry_after_seconds),
        });
      }
    } catch {
      setScanNow({
        phase: "done",
        executed: false,
        messageAr: "تعذّر تنفيذ الفحص الفوري. حاول مرة أخرى لاحقًا.",
      });
    }
  }, [reload]);

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
        <div className="flex flex-wrap items-center justify-center gap-bsr-3">
          <button
            type="button"
            onClick={reload}
            disabled={data.status === "loading"}
            className="rounded-bsr-md bg-bsr-gold-500 px-bsr-6 py-bsr-2 font-semibold text-bsr-navy-950 transition-colors hover:bg-bsr-gold-400 disabled:opacity-60"
          >
            {data.status === "loading" ? "جارٍ التحديث..." : "تحديث العرض"}
          </button>
          <button
            type="button"
            onClick={handleScanNow}
            disabled={scanNow.phase === "loading"}
            className="rounded-bsr-md border border-bsr-gold-500 px-bsr-6 py-bsr-2 font-semibold text-bsr-gold-500 transition-colors hover:bg-bsr-gold-500/10 disabled:opacity-60"
          >
            {scanNow.phase === "loading" ? "جارٍ الفحص الفوري..." : "فحص فوري"}
          </button>
        </div>
        {/* Honesty fix: "تحديث العرض" (not "تحديث الرادار") because this
         * button only re-reads the same already-persisted scan results
         * (fetchRadarData/getRadarSummary above) -- it never triggers a
         * new market scan. Without this line, a user could reasonably
         * expect a fresh scan on every press, which would be false: new
         * opportunities only ever appear on the scheduler's own
         * schedule (see "آخر تحديث للرادار" timestamp below), or on
         * demand via "فحص فوري" (subject to a per-user cooldown -- see
         * POST /api/v1/radar/scan-now). */}
        <p className="mt-bsr-2 text-xs text-bsr-text-muted">
          بصيرة يفحص السوق تلقائيًا على فترات مجدولة — زر &quot;تحديث العرض&quot; يُطابق آخر فحص مكتمل فقط، وزر &quot;فحص فوري&quot; يطلب فحصًا حيًا جديدًا الآن (محدود بفترة انتظار لكل مستخدم).
        </p>
        {scanNow.phase === "done" ? (
          <p
            role="status"
            className={`mt-bsr-2 text-sm ${scanNow.executed ? "text-bsr-market-up" : "text-bsr-text-secondary"}`}
          >
            {scanNow.messageAr}
          </p>
        ) : null}
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

      {data.status === "ready" ? (
        <p className="text-center text-xs text-bsr-text-secondary">
          آخر تحديث للرادار: <span className="bsr-numeric">{formatArabicDateTime(data.summary.generated_at)}</span> (
          {formatRelativeAgeAr(data.summary.generated_at)})
          {data.summary.most_recent_emitted_at ? (
            <>
              {" "}
              · أحدث إشارة: <span className="bsr-numeric">{formatRelativeAgeAr(data.summary.most_recent_emitted_at)}</span>
            </>
          ) : null}
        </p>
      ) : null}

      {data.status === "ready" ? <MarketRiskBanner summary={data.summary} /> : null}
      {data.status === "ready" ? <ScanFunnelBanner summary={data.summary} /> : null}

      {data.status === "ready" && data.summary.live_opportunity_count === 0 ? (
        <EmptyState
          title="لا توجد فرص مرصودة حاليًا"
          description="لم يرصد الرادار الذكي أي فرصة حقيقية تستوفي معايير الجودة في آخر مسح للسوق."
        />
      ) : null}

      {data.status === "ready" && data.summary.live_opportunity_count > 0
        ? (() => {
            // Production truthfulness fix (2026-08-23): a Decision V2
            // signal that has gone STALE (is_decision_fresh === false)
            // must never render as a current actionable opportunity here,
            // even when entry_status still reads READY_NOW because price
            // hasn't yet moved out of the recommended zone -- LIVE PRICE
            // != LIVE DECISION (see src/lib/format/freshness.ts). Real
            // production case that motivated this: symbol 6060, signaled
            // 2026-08-20 (3 days stale), still showed "شراء" inside "الفرص
            // الحية" because only entry_status was checked. Stale-but-not-
            // missed-entry opportunities get their own clearly-labeled
            // section instead of being silently dropped or silently shown
            // as current.
            const currentOpportunities = data.summary.top_opportunities.filter(
              (o) => !isEntryMissed(o.entry_status) && o.is_decision_fresh
            );
            const staleOpportunities = data.summary.top_opportunities.filter(
              (o) => !isEntryMissed(o.entry_status) && !o.is_decision_fresh
            );
            const missedEntryOpportunities = data.summary.top_opportunities.filter((o) => isEntryMissed(o.entry_status));
            return (
              <>
                <section className="flex flex-col gap-bsr-4">
                  <div className="flex items-center justify-between">
                    <h2 className="text-base font-semibold text-bsr-text-primary">
                      الفرص الحية ({currentOpportunities.length})
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
                  {currentOpportunities.length === 0 ? (
                    <EmptyState
                      title="لا توجد فرصة دخول حالية"
                      description="جميع الفرص المرصودة تجاوز سعرها نطاق الدخول الموصى به، أو أصبح تحليلها قديمًا. انظر أدناه للفرص السابقة."
                    />
                  ) : (
                    <div className="grid grid-cols-1 gap-bsr-4 md:grid-cols-2">
                      {currentOpportunities.map((opportunity) => (
                        <RadarOpportunityCard key={opportunity.id} opportunity={opportunity} />
                      ))}
                    </div>
                  )}
                </section>

                {staleOpportunities.length > 0 ? (
                  <section className="flex flex-col gap-bsr-4">
                    <h2 className="text-base font-semibold text-bsr-text-secondary">
                      تحليل قديم — يحتاج إعادة تقييم ({staleOpportunities.length})
                    </h2>
                    <p className="text-xs text-bsr-text-secondary">
                      معروضة للاطلاع فقط -- تحليل هذه الفرص لم يعد يمثّل الجلسة الحالية.
                    </p>
                    <div className="grid grid-cols-1 gap-bsr-4 md:grid-cols-2">
                      {staleOpportunities.map((opportunity) => (
                        <RadarOpportunityCard key={opportunity.id} opportunity={opportunity} />
                      ))}
                    </div>
                  </section>
                ) : null}

                {missedEntryOpportunities.length > 0 ? (
                  <section className="flex flex-col gap-bsr-4">
                    <h2 className="text-base font-semibold text-bsr-text-secondary">
                      فرص فاتت نقطة الدخول ({missedEntryOpportunities.length})
                    </h2>
                    <p className="text-xs text-bsr-text-secondary">
                      معروضة للاطلاع فقط -- لم تعد فرص دخول حالية.
                    </p>
                    <div className="grid grid-cols-1 gap-bsr-4 md:grid-cols-2">
                      {missedEntryOpportunities.map((opportunity) => (
                        <RadarOpportunityCard key={opportunity.id} opportunity={opportunity} />
                      ))}
                    </div>
                  </section>
                ) : null}
              </>
            );
          })()
        : null}
    </div>
  );
}
