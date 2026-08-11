import {
  RecommendationBadge,
  type RecommendationValue,
} from "@/components/badges/RecommendationBadge";
import { AiStar } from "@/components/ai/AiStar";

interface InstrumentRowProps {
  symbol: string;
  nameAr?: string | null;
  sector?: string | null;
  price?: number | null;
  changePct?: number | null;
  /** Set to "target" when `price` is an AI-projected target rather
   * than a live quote -- never presented as a current price. */
  priceKind?: "quote" | "target";
  stopLoss?: number | null;
  recommendation?: RecommendationValue | null;
  confidence?: number | null;
  /** Set when the underlying quote came from a synthetic/dev provider
   * -- surfaced honestly rather than presented as a live price
   * (matches the backend's own source/is_synthetic labeling). */
  isSynthetic?: boolean;
  href?: string;
}

/** The one shared instrument row every screen (watchlist, scan
 * results, sector breakdown, rankings) reuses -- UI Spec Global
 * Invariants §0: a screen implementing its own instrument row is
 * defective by definition. */
export function InstrumentRow({
  symbol,
  nameAr,
  sector,
  price,
  changePct,
  priceKind = "quote",
  stopLoss,
  recommendation,
  confidence,
  isSynthetic,
  href,
}: InstrumentRowProps) {
  const isUp = (changePct ?? 0) >= 0;

  const content = (
    <div className="flex items-center justify-between gap-bsr-4 rounded-bsr-md px-bsr-4 py-bsr-3 transition-colors hover:bg-bsr-surface-overlay">
      <div className="flex min-w-0 flex-col">
        <div className="flex items-center gap-bsr-2">
          <span className="bsr-numeric font-semibold text-bsr-text-primary">
            {symbol}
          </span>
          {isSynthetic ? (
            <span className="rounded-bsr-sm bg-bsr-navy-700 px-bsr-2 py-0.5 text-xs text-bsr-text-muted">
              بيانات تجريبية
            </span>
          ) : null}
        </div>
        {(nameAr ?? sector) ? (
          <span className="truncate text-sm text-bsr-text-secondary">
            {nameAr ?? sector}
          </span>
        ) : null}
      </div>

      <div className="flex items-center gap-bsr-4">
        {confidence != null ? (
          <div className="flex items-center gap-bsr-1 text-sm text-bsr-teal-500">
            <AiStar size="sm" />
            <span className="bsr-numeric">{Math.round(confidence)}%</span>
          </div>
        ) : null}

        {price != null ? (
          <div className="flex flex-col items-end">
            {priceKind === "target" ? (
              <span className="text-xs text-bsr-text-muted">الهدف</span>
            ) : null}
            <span className="bsr-numeric font-semibold text-bsr-text-primary">
              {price.toFixed(2)}
            </span>
            {changePct != null ? (
              <span
                className={`bsr-numeric text-sm ${isUp ? "text-bsr-market-up" : "text-bsr-market-down"}`}
              >
                {isUp ? "+" : ""}
                {changePct.toFixed(2)}%
              </span>
            ) : null}
            {stopLoss != null ? (
              <span className="bsr-numeric text-xs text-bsr-action-sell">
                وقف: {stopLoss.toFixed(2)}
              </span>
            ) : null}
          </div>
        ) : null}

        {recommendation ? (
          <RecommendationBadge value={recommendation} />
        ) : null}
      </div>
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
