import { AiStar } from "@/components/ai/AiStar";
import { ConfidenceBar } from "@/components/ai/ConfidenceBar";
import {
  RecommendationBadge,
  type RecommendationValue,
} from "@/components/badges/RecommendationBadge";
import { RISK_LEVEL_LABELS, TIME_HORIZON_LABELS } from "@/lib/portfolio-labels";

interface AiSignalCardProps {
  symbol: string;
  sector?: string | null;
  recommendation: RecommendationValue;
  confidence?: number | null;
  currentPrice?: number | null;
  targetPrice?: number | null;
  stopLoss?: number | null;
  riskRewardRatio?: number | null;
  timeHorizon?: string | null;
  riskLevel?: string | null;
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
  currentPrice,
  targetPrice,
  stopLoss,
  riskRewardRatio,
  timeHorizon,
  riskLevel,
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

      {currentPrice != null || stopLoss != null ? (
        <div className="grid grid-cols-2 gap-bsr-2 text-xs">
          {currentPrice != null ? (
            <div>
              <span className="text-bsr-text-muted">السعر المرجعي: </span>
              <span className="bsr-numeric text-bsr-text-secondary">{currentPrice.toFixed(2)}</span>
            </div>
          ) : null}
          {stopLoss != null ? (
            <div>
              <span className="text-bsr-text-muted">وقف الخسارة: </span>
              <span className="bsr-numeric text-bsr-action-sell">{stopLoss.toFixed(2)}</span>
            </div>
          ) : null}
        </div>
      ) : null}

      {riskRewardRatio != null || timeHorizon != null || riskLevel != null ? (
        <div className="flex flex-wrap items-center gap-x-bsr-3 gap-y-1 text-xs text-bsr-text-muted">
          {riskRewardRatio != null ? (
            <span>
              العائد/المخاطرة: <span className="bsr-numeric text-bsr-text-secondary">1:{riskRewardRatio.toFixed(1)}</span>
            </span>
          ) : null}
          {timeHorizon != null ? (
            <span>المدة: {TIME_HORIZON_LABELS[timeHorizon] ?? timeHorizon}</span>
          ) : null}
          {riskLevel != null ? (
            <span>المخاطرة: {RISK_LEVEL_LABELS[riskLevel] ?? riskLevel}</span>
          ) : null}
        </div>
      ) : null}

      <p className="text-xs leading-4 text-bsr-text-muted">
        درجة الجودة تعكس قوة الأدلة المتاحة وقت التحليل، ولا تضمن تحقيق الربح.
      </p>

      {href ? (
        <div className="flex items-center gap-bsr-2 pt-bsr-1">
          <a
            href={href}
            className="flex-1 rounded-bsr-md bg-bsr-gold-500 px-bsr-3 py-bsr-1.5 text-center text-xs font-semibold text-bsr-navy-950 hover:bg-bsr-gold-400"
          >
            عرض التحليل الكامل
          </a>
          <a
            href={`${href}#chart`}
            className="flex-1 rounded-bsr-md border border-bsr-border-subtle px-bsr-3 py-bsr-1.5 text-center text-xs font-semibold text-bsr-text-secondary hover:bg-bsr-surface-overlay"
          >
            فتح الشارت
          </a>
        </div>
      ) : null}
    </div>
  );

  return content;
}
