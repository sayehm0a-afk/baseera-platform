/**
 * Recommendation action badge -- BUY/SELL/WATCH/HOLD, per the Phase 9
 * decision: a dedicated semantic palette distinct from both market
 * up/down colors and AI teal. AI teal must never color this badge.
 *
 * `STRONG_BUY`/`BUY` and `SELL`/`STRONG_SELL` are the literal values
 * `src.analysis.recommendation.types.Recommendation` returns from the
 * backend; `WATCH` has no backend enum member and is only ever passed
 * explicitly by a caller that has its own reason to show it (e.g. a
 * watchlist category), never inferred here.
 */
export type RecommendationValue =
  | "STRONG_BUY"
  | "BUY"
  | "HOLD"
  | "WATCH"
  | "SELL"
  | "STRONG_SELL";

const LABELS: Record<RecommendationValue, string> = {
  STRONG_BUY: "شراء قوي",
  BUY: "شراء",
  HOLD: "احتفاظ",
  WATCH: "مراقبة",
  SELL: "بيع",
  STRONG_SELL: "بيع قوي",
};

const COLOR_CLASSES: Record<RecommendationValue, string> = {
  STRONG_BUY: "bg-bsr-action-buy/15 text-bsr-action-buy",
  BUY: "bg-bsr-action-buy/15 text-bsr-action-buy",
  HOLD: "bg-bsr-action-hold/15 text-bsr-action-hold",
  WATCH: "bg-bsr-action-watch/15 text-bsr-action-watch",
  SELL: "bg-bsr-action-sell/15 text-bsr-action-sell",
  STRONG_SELL: "bg-bsr-action-sell/15 text-bsr-action-sell",
};

interface RecommendationBadgeProps {
  value: RecommendationValue;
  className?: string;
}

export function RecommendationBadge({
  value,
  className,
}: RecommendationBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-bsr-full px-bsr-3 py-bsr-1 text-sm font-medium ${COLOR_CLASSES[value]} ${className ?? ""}`}
    >
      {LABELS[value]}
    </span>
  );
}
