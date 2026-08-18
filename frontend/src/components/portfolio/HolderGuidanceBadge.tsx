import type { HolderGuidanceValue } from "@/lib/api/portfolio-types";

/** RADAR-C Phase H: the "I already own this -- what now" badge --
 * distinct from DecisionBadge (a fresh "should I buy" read). Reuses
 * the same semantic color tokens so the two badges read consistently
 * side by side: HOLD -> hold, WATCH -> watch, REDUCE/EXIT -> sell. */
const COLOR_CLASSES: Record<HolderGuidanceValue, string> = {
  HOLD: "bg-bsr-action-hold/15 text-bsr-action-hold",
  WATCH: "bg-bsr-action-watch/15 text-bsr-action-watch",
  REDUCE: "bg-bsr-action-sell/15 text-bsr-action-sell",
  EXIT: "bg-bsr-action-sell/15 text-bsr-action-sell",
};

export function HolderGuidanceBadge({
  value,
  labelAr,
  className,
}: {
  value: HolderGuidanceValue;
  labelAr: string;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-bsr-full px-bsr-3 py-bsr-1 text-xs font-semibold ${COLOR_CLASSES[value]} ${className ?? ""}`}
    >
      {labelAr}
    </span>
  );
}
