import Link from "next/link";
import type { StockDirectoryItem } from "@/lib/api/stocks-types";

function priceLabel(value: number | null): string {
  return value == null ? "--" : value.toFixed(2);
}

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
  return (
    <Link
      href={`/stocks/${encodeURIComponent(item.symbol)}`}
      className="flex items-center justify-between gap-bsr-3 rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-raised px-bsr-4 py-bsr-3 transition-colors hover:border-bsr-gold-500/40"
    >
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-sm font-semibold text-bsr-text-primary">
          {item.name_ar ?? item.name_en}
        </span>
        <span className="bsr-numeric text-xs text-bsr-text-secondary">
          {item.symbol}
          {item.sector_ar ? ` · ${item.sector_ar}` : ""}
        </span>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-0.5">
        <span className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
          {priceLabel(item.current_price)}
        </span>
        <span className={`bsr-numeric text-xs font-semibold ${change.colorClass}`}>{change.text}</span>
      </div>
    </Link>
  );
}
