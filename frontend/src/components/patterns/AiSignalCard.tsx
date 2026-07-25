import { AiStar } from "@/components/ai/AiStar";
import { ConfidenceBar } from "@/components/ai/ConfidenceBar";
import {
  RecommendationBadge,
  type RecommendationValue,
} from "@/components/badges/RecommendationBadge";

interface AiSignalCardProps {
  symbol: string;
  sector?: string | null;
  recommendation: RecommendationValue;
  confidence?: number | null;
  targetPrice?: number | null;
  expectedReturnPct?: number | null;
  href?: string;
}

/** The one shared "AI signal" card -- dashboard's signals-of-the-day,
 * Opportunities, and Scan's card view all reuse this rather than each
 * screen drawing its own (UI Spec Global Invariants §0). */
export function AiSignalCard({
  symbol,
  sector,
  recommendation,
  confidence,
  targetPrice,
  expectedReturnPct,
  href,
}: AiSignalCardProps) {
  const content = (
    <div className="flex flex-col gap-bsr-3 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-overlay p-bsr-4 transition-colors hover:border-bsr-gold-500/40">
      <div className="flex items-start justify-between">
        <div className="flex flex-col">
          <span className="bsr-numeric text-lg font-semibold text-bsr-text-primary">
            {symbol}
          </span>
          {sector ? (
            <span className="text-xs text-bsr-text-secondary">{sector}</span>
          ) : null}
        </div>
        <RecommendationBadge value={recommendation} />
      </div>

      {confidence != null ? (
        <div className="flex flex-col gap-bsr-1">
          <div className="flex items-center justify-between text-xs text-bsr-teal-500">
            <span className="flex items-center gap-1">
              <AiStar size="sm" />
              نسبة الثقة
            </span>
            <span className="bsr-numeric">{Math.round(confidence)}%</span>
          </div>
          <ConfidenceBar confidence={confidence} />
        </div>
      ) : null}

      {targetPrice != null || expectedReturnPct != null ? (
        <div className="flex items-center justify-between text-sm">
          {targetPrice != null ? (
            <span className="bsr-numeric text-bsr-text-secondary">
              الهدف: {targetPrice.toFixed(2)}
            </span>
          ) : (
            <span />
          )}
          {expectedReturnPct != null ? (
            <span
              className={`bsr-numeric ${expectedReturnPct >= 0 ? "text-bsr-market-up" : "text-bsr-market-down"}`}
            >
              {expectedReturnPct >= 0 ? "+" : ""}
              {expectedReturnPct.toFixed(1)}%
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );

  if (href) {
    return (
      <a href={href} className="block">
        {content}
      </a>
    );
  }
  return content;
}
