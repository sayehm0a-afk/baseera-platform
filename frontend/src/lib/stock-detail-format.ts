/** Formatting for the free-form `indicators`/`ratios` maps
 * src/api/schemas/stocks.py's TechnicalAnalysisOut/FundamentalAnalysisOut
 * return -- values are either a plain number (most indicators/ratios)
 * or a plain object of sub-values (MACD/Bollinger/Stochastic/
 * SuperTrend, per src/analysis/types.py's IndicatorOutput.latest()).
 * Extracted from StockDetailClient so the formatting logic itself is
 * unit-testable without mounting the chart (lightweight-charts needs a
 * real <canvas> context jsdom doesn't implement). */

export function formatIndicatorValue(value: unknown): string {
  if (typeof value === "number") return value.toFixed(2);
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `${k}: ${typeof v === "number" ? v.toFixed(2) : String(v)}`)
      .join("  ·  ");
  }
  return String(value ?? "—");
}

// Ratio keys src/analysis/fundamental/ratios/{profitability,growth,valuation}.py
// return as a raw fraction (e.g. 0.174 for a real 17.4% ROE) -- every other
// ratio key (current_ratio, debt_to_equity, price_to_earnings, market_cap,
// ...) is a genuine multiple/currency value, never a percentage, and must
// never be scaled here.
const PERCENTAGE_RATIO_KEYS = new Set([
  "net_profit_margin",
  "gross_profit_margin",
  "return_on_equity",
  "return_on_assets",
  "dividend_yield",
  "revenue_growth",
  "net_income_growth",
  "eps_growth",
]);

export function formatRatioValue(name: string, value: unknown): string {
  if (typeof value !== "number") return String(value ?? "—");
  if (PERCENTAGE_RATIO_KEYS.has(name)) return `${(value * 100).toFixed(2)}%`;
  return value.toFixed(2);
}
