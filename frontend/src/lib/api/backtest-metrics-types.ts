/** Shape of `BacktestRun.metrics` -- `src.backtesting.engine.
 * BacktestingEngine.run()` returns `full_report(filtered)` (see
 * src/backtesting/metrics.py `full_report`/`compute_all_metrics`).
 * Declared as a separate, narrower type from the open-ended
 * `Record<string, unknown>` the REST schema uses, since the backend
 * itself documents this exact shape in code, not just as free-form
 * JSON. */

export interface OverallMetrics {
  evaluation_count: number;
  direction_accuracy: number | null;
  target_price_hit_rate: number | null;
  stop_loss_hit_rate: number | null;
  average_forward_return_pct: number | null;
  median_forward_return_pct: number | null;
  win_rate: number | null;
  loss_rate: number | null;
  profit_factor: number | null;
  max_drawdown: number | null;
  volatility: number | null;
  downside_deviation: number | null;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  calibration_error: { overall_error: number; buckets: unknown[] } | null;
}

export interface FullBacktestReport {
  overall: OverallMetrics;
  evaluated_count: number;
  filtered_count: number;
  skipped: Record<string, number>;
  cancelled: boolean;
}

export function isFullBacktestReport(
  metrics: Record<string, unknown> | null
): metrics is Record<string, unknown> & FullBacktestReport {
  return !!metrics && typeof metrics === "object" && "overall" in metrics;
}
