import { SENTIMENT_LABEL_LABELS, sentimentColorClass } from "@/lib/news-labels";

/** News sentiment badge -- Very Positive/Positive/Neutral/Negative/Very
 * Negative, the 5 `src.domain.models.news_event.SentimentLabel` values
 * (Phase 12). Reuses the same market up/down/hold palette
 * `RecommendationBadge` and `healthBandColorClass` already use for
 * directional meaning, rather than inventing a new one. */
export function SentimentBadge({
  label,
  className,
}: {
  label: string;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-bsr-full bg-bsr-surface-overlay px-bsr-3 py-bsr-1 text-xs font-medium ${sentimentColorClass(label)} ${className ?? ""}`}
    >
      {SENTIMENT_LABEL_LABELS[label] ?? label}
    </span>
  );
}
