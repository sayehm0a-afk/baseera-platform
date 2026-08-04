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

export function formatRatioValue(value: unknown): string {
  if (typeof value === "number") return value.toFixed(2);
  return String(value ?? "—");
}
