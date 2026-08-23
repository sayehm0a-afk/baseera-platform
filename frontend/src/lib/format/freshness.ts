/** Pre-launch safety fix (2026-08-22, Priority 1 -- Recommendation
 * Freshness): shared presentation-only helpers for showing a real
 * recommendation's age/timestamp in Arabic, and for classifying it as
 * still-actionable vs no-longer-actionable for display purposes only.
 *
 * Nothing here recomputes or overrides a Decision Engine value -- it only
 * formats `emitted_at`/`decision_timestamp` (already-real timestamps) and
 * reads the already-computed `entry_status`/`data_freshness_status`
 * fields to decide how to *label* a card, never to change what the
 * backend classified it as. */

/** Every BASIRAH trading timestamp must render on the Gregorian calendar
 * -- the CLDR default calendar for the "ar-SA" locale is Hijri, and iOS
 * Safari is known to honor that default while Chromium often silently
 * overrides it. Always pass `calendar: "gregory"` explicitly rather than
 * relying on a browser-specific default. */
const AR_SA_GREGORIAN = "ar-SA-u-ca-gregory";

export function formatArabicDateTime(iso: string | null | undefined): string {
  if (!iso) return "--";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString(AR_SA_GREGORIAN, {
    calendar: "gregory",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

const MINUTE_MS = 60 * 1000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

/** A short Arabic relative-age phrase ("قبل 5 دقائق" / "قبل 3 ساعات" /
 * "قبل يومين"). Never claims a value is "now" unless it genuinely is
 * within the last minute. */
export function formatRelativeAgeAr(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "غير معروف";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "غير معروف";
  const diffMs = now.getTime() - date.getTime();
  if (diffMs < 0) return "الآن";

  const minutes = Math.floor(diffMs / MINUTE_MS);
  if (minutes < 1) return "قبل أقل من دقيقة";
  if (minutes < 60) return `قبل ${minutes} ${minutes === 1 ? "دقيقة" : "دقائق"}`;

  const hours = Math.floor(diffMs / HOUR_MS);
  if (hours < 24) return `قبل ${hours} ${hours === 1 ? "ساعة" : "ساعات"}`;

  const days = Math.floor(diffMs / DAY_MS);
  if (days === 1) return "قبل يوم واحد";
  if (days === 2) return "قبل يومين";
  if (days < 11) return `قبل ${days} أيام`;
  return `قبل ${days} يومًا`;
}

/** Age-in-days used purely to bucket a recommendation for display
 * (current session / previous session / stale) -- not a re-evaluation
 * and not a change to `data_freshness_status`, which continues to mean
 * "sourced from real data at signal time" exactly as the Decision
 * Engine computes it. */
export function ageInDays(iso: string | null | undefined, now: Date = new Date()): number | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return (now.getTime() - date.getTime()) / DAY_MS;
}

export type DataFreshnessStatus = "LIVE" | "LAST_SESSION" | "STALE" | "UNKNOWN";

export const FRESHNESS_LABELS_AR: Record<DataFreshnessStatus, string> = {
  LIVE: "بيانات حيّة",
  LAST_SESSION: "بيانات آخر جلسة مكتملة",
  STALE: "بيانات قديمة",
  UNKNOWN: "حداثة البيانات غير مؤكدة",
};

export function freshnessLabelAr(status: string | null | undefined): string {
  if (status && status in FRESHNESS_LABELS_AR) {
    return FRESHNESS_LABELS_AR[status as DataFreshnessStatus];
  }
  return FRESHNESS_LABELS_AR.UNKNOWN;
}

/** Production freshness fix (2026-08-23): a separate Arabic label set
 * for DECISION freshness (`decision_freshness_status` /
 * `latest_decision_freshness_status` / `guidance_freshness_status`),
 * deliberately worded differently from `FRESHNESS_LABELS_AR` above --
 * that set describes PRICE/quote data staleness ("بيانات قديمة"),
 * this one describes a stale ANALYSIS/decision that needs
 * re-evaluation ("تحليل قديم"). Never call `freshnessLabelAr` on a
 * *_freshness_status field or vice versa -- LIVE PRICE != LIVE
 * DECISION, and mixing the two label sets would silently reintroduce
 * that exact confusion in the UI. */
export const DECISION_FRESHNESS_LABELS_AR: Record<DataFreshnessStatus, string> = {
  LIVE: "قرار حالي لهذه الجلسة",
  LAST_SESSION: "قرار آخر جلسة مكتملة",
  STALE: "تحليل قديم — يحتاج إعادة تقييم",
  UNKNOWN: "حداثة القرار غير مؤكدة",
};

export function decisionFreshnessLabelAr(status: string | null | undefined): string {
  if (status && status in DECISION_FRESHNESS_LABELS_AR) {
    return DECISION_FRESHNESS_LABELS_AR[status as DataFreshnessStatus];
  }
  return DECISION_FRESHNESS_LABELS_AR.UNKNOWN;
}

/** `entry_status === "MISSED_ENTRY"` is a real, already-computed
 * Decision Engine V2 value (src.analysis.decision_v2.trade_classification.
 * classify_entry_status) meaning the price has already moved past the
 * recommended entry zone. Used here only to decide whether a card may
 * still present itself as a current actionable opportunity -- the
 * decision/classification itself is untouched. */
export function isEntryMissed(entryStatus: string | null | undefined): boolean {
  return entryStatus === "MISSED_ENTRY";
}
