import Link from "next/link";
import { DecisionBadge } from "@/components/badges/DecisionBadge";
import type { StockDirectoryItem } from "@/lib/api/stocks-types";

function priceLabel(value: number | null): string {
  return value == null ? "--" : value.toFixed(2);
}

const ACTIONABLE_CLASSIFICATIONS = new Set(["STRONG_BUY_CANDIDATE", "BUY_CANDIDATE"]);

function changeLabel(item: StockDirectoryItem): { text: string; colorClass: string } {
  if (item.change_pct == null) {
    return { text: "--", colorClass: "text-bsr-text-secondary" };
  }
  const sign = item.change_pct > 0 ? "+" : "";
  const colorClass =
    item.change_pct > 0
      ? "text-bsr-market-up"
      : item.change_pct < 0
        ? "text-bsr-market-down"
        : "text-bsr-text-secondary";
  return { text: `${sign}${item.change_pct.toFixed(2)}%`, colorClass };
}

/** One row of the All-Stocks directory (RADAR-C Phase F) -- every
 * field comes straight from GET /api/v1/stocks/directory, which reads
 * only already-persisted PriceBar data (src.api.routes.stocks). No
 * price/change computation happens in the frontend. */
export function StockDirectoryRow({ item }: { item: StockDirectoryItem }) {
  const change = changeLabel(item);
  const hasDecision = item.latest_decision != null && item.latest_decision_label_ar != null;
  return (
    <Link
      href={`/stocks/${encodeURIComponent(item.symbol)}`}
      className="flex items-center justify-between gap-bsr-3 rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-raised px-bsr-4 py-bsr-3 transition-colors hover:border-bsr-gold-500/40"
    >
      <div className="flex min-w-0 flex-col gap-1">
        <span className="truncate text-sm font-semibold text-bsr-text-primary">
          {item.name_ar ?? item.name_en}
        </span>
        <span className="bsr-numeric text-xs text-bsr-text-secondary">
          {item.symbol}
          {item.sector_ar ? ` · ${item.sector_ar}` : ""}
        </span>
        {/* 2026-09-18: compact classification hint right in the list
         * row -- real data only (see StockDirectoryItemOut's own
         * docstring), omitted entirely rather than showing a
         * placeholder when this symbol has never been analyzed yet. */}
        {hasDecision ? (
          <DecisionBadge value={item.latest_decision!} labelAr={item.latest_decision_label_ar!} className="w-fit !px-bsr-2 !py-0.5 !text-xs" />
        ) : null}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-0.5">
        <span className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
          {priceLabel(item.current_price)}
        </span>
        <span className={`bsr-numeric text-xs font-semibold ${change.colorClass}`}>{change.text}</span>
        {hasDecision && item.latest_target_1 != null && ACTIONABLE_CLASSIFICATIONS.has(item.latest_decision!) ? (
          <span className="bsr-numeric text-xs text-bsr-market-up">هدف {priceLabel(item.latest_target_1)}</span>
        ) : null}
      </div>
    </Link>
  );
}
