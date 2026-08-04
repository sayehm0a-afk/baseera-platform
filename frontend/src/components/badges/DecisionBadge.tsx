import type { DecisionV2Value } from "@/lib/api/stocks-types";

/**
 * Decision Engine V2's action badge -- the 9-state Arabic taxonomy
 * (src.analysis.decision_v2.types.Decision), distinct from the legacy
 * 6-state RecommendationBadge. Reuses the same semantic color tokens
 * (buy/hold/watch/sell) so the two badges read consistently side by
 * side, but maps a strictly larger state space onto them:
 * STRONG_BUY_CANDIDATE/BUY_CANDIDATE -> buy, WAIT_FOR_ENTRY/WATCH ->
 * watch, HOLD -> hold, REDUCE/EXIT/REJECT -> sell,
 * INSUFFICIENT_DATA -> muted/neutral (never colored as if it were a
 * real signal -- there is no signal here, only missing data).
 */
const COLOR_CLASSES: Record<DecisionV2Value, string> = {
  STRONG_BUY_CANDIDATE: "bg-bsr-action-buy/15 text-bsr-action-buy",
  BUY_CANDIDATE: "bg-bsr-action-buy/15 text-bsr-action-buy",
  WAIT_FOR_ENTRY: "bg-bsr-action-watch/15 text-bsr-action-watch",
  WATCH: "bg-bsr-action-watch/15 text-bsr-action-watch",
  HOLD: "bg-bsr-action-hold/15 text-bsr-action-hold",
  REDUCE: "bg-bsr-action-sell/15 text-bsr-action-sell",
  EXIT: "bg-bsr-action-sell/15 text-bsr-action-sell",
  REJECT: "bg-bsr-action-sell/15 text-bsr-action-sell",
  INSUFFICIENT_DATA: "bg-bsr-text-muted/15 text-bsr-text-muted",
};

interface DecisionBadgeProps {
  value: DecisionV2Value;
  labelAr: string;
  className?: string;
}

/** `labelAr` is always the backend's own `decision_label_ar` -- this
 * component never re-translates the decision itself, only colors it,
 * so the displayed Arabic text and the gate-checked decision it
 * describes can never drift apart. */
export function DecisionBadge({ value, labelAr, className }: DecisionBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-bsr-full px-bsr-3 py-bsr-1 text-sm font-semibold ${COLOR_CLASSES[value] ?? COLOR_CLASSES.INSUFFICIENT_DATA} ${className ?? ""}`}
    >
      {labelAr}
    </span>
  );
}
