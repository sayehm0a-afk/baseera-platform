export type ChartRange = "1W" | "1M" | "3M" | "6M" | "1Y" | "ALL";

export const CHART_RANGE_LABELS_AR: Record<ChartRange, string> = {
  "1W": "أسبوع",
  "1M": "شهر",
  "3M": "3 أشهر",
  "6M": "6 أشهر",
  "1Y": "سنة",
  ALL: "الكل",
};

// Daily-bar lookback windows -- never an "اليوم" (today) tab here: this
// codebase's price history is daily OHLCV (src.domain.models.price_bar),
// and a single day of daily bars would show one candle, misleadingly
// implying intraday granularity Basirah does not actually have. "ALL"
// is handled separately (no cutoff) since it means "everything the
// backend already returned", not a fixed window.
const RANGE_DAYS: Record<Exclude<ChartRange, "ALL">, number> = {
  "1W": 7,
  "1M": 30,
  "3M": 90,
  "6M": 182,
  "1Y": 365,
};

export function rangeCutoffDate(range: ChartRange, latest: Date): Date | null {
  if (range === "ALL") return null;
  const cutoff = new Date(latest);
  cutoff.setDate(cutoff.getDate() - RANGE_DAYS[range]);
  return cutoff;
}

interface ChartRangeTabsProps {
  value: ChartRange;
  onChange: (range: ChartRange) => void;
  options?: ChartRange[];
}

const DEFAULT_OPTIONS: ChartRange[] = ["1W", "1M", "3M", "6M", "1Y", "ALL"];

/** The same time-range switcher pattern already common in trading
 * apps -- filters the real, already-fetched bars client-side (see
 * StockDetailClient's use of rangeCutoffDate), never a separate
 * fetch per range. */
export function ChartRangeTabs({ value, onChange, options = DEFAULT_OPTIONS }: ChartRangeTabsProps) {
  return (
    <div className="flex flex-wrap gap-bsr-1" role="tablist" aria-label="المدى الزمني للرسم البياني">
      {options.map((range) => (
        <button
          key={range}
          type="button"
          role="tab"
          aria-selected={value === range}
          onClick={() => onChange(range)}
          className={`rounded-bsr-full px-bsr-3 py-1 text-xs font-semibold transition-colors ${
            value === range
              ? "bg-bsr-gold-500 text-bsr-navy-950"
              : "bg-bsr-surface-overlay text-bsr-text-secondary hover:text-bsr-text-primary"
          }`}
        >
          {CHART_RANGE_LABELS_AR[range]}
        </button>
      ))}
    </div>
  );
}
