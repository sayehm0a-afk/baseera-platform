import type { PersonalScanResponse } from "@/lib/api/types";

const STATE_COLOR: Record<PersonalScanResponse["freshness_state"], string> = {
  FRESH: "bg-bsr-market-up/15 text-bsr-market-up",
  AGING: "bg-bsr-gold-500/15 text-bsr-gold-500",
  STALE: "bg-bsr-market-down/15 text-bsr-market-down",
  NO_SCAN: "bg-bsr-text-muted/15 text-bsr-text-muted",
};

function formatAgeAr(hours: number): string {
  if (hours < 1) {
    const minutes = Math.max(1, Math.round(hours * 60));
    return `منذ ${minutes} دقيقة`;
  }
  const rounded = Math.round(hours);
  return `منذ ${rounded} ساعة`;
}

interface FreshnessBannerProps {
  result: Pick<
    PersonalScanResponse,
    "generated_at" | "data_age_hours" | "freshness_state" | "freshness_label_ar"
  >;
}

/** CONT Phase 6: the freshness/provenance disclosure every /today load
 * must show, regardless of whether any opportunity qualified --
 * `freshness_label_ar` and `freshness_state` are the backend's own
 * honest four-state read (see src.market_intelligence.personal_scan),
 * never recomputed or guessed here. Never claims data is fresher than
 * the backend actually says. */
export function FreshnessBanner({ result }: FreshnessBannerProps) {
  const generatedLabel =
    result.generated_at !== null
      ? new Date(result.generated_at).toLocaleString("ar-SA", {
          calendar: "gregory",
          dateStyle: "medium",
          timeStyle: "short",
        })
      : null;

  return (
    <div className="flex flex-wrap items-center justify-center gap-bsr-2 text-xs">
      <span
        className={`rounded-bsr-full px-bsr-3 py-1 font-semibold ${STATE_COLOR[result.freshness_state]}`}
      >
        {result.freshness_label_ar}
      </span>
      {generatedLabel ? (
        <span className="text-bsr-text-secondary">آخر مسح: {generatedLabel}</span>
      ) : null}
      {result.data_age_hours !== null ? (
        <span className="text-bsr-text-muted">({formatAgeAr(result.data_age_hours)})</span>
      ) : null}
    </div>
  );
}
