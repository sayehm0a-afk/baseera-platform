import { apiFetch } from "./client";
import type {
  BacktestCreateRequestBody,
  BacktestMetrics,
  BacktestRun,
} from "./backtests-types";

/** Every function here is a direct, unmodified call to an existing
 * `/api/v1/backtests/*` route (src/api/routes/backtests.py) -- no
 * strategy/metrics logic is re-derived here. */

export function createBacktest(
  body: BacktestCreateRequestBody
): Promise<BacktestRun> {
  return apiFetch<BacktestRun>("/api/v1/backtests", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getBacktest(runId: number): Promise<BacktestRun> {
  return apiFetch<BacktestRun>(`/api/v1/backtests/${runId}`);
}

export function getBacktestMetrics(runId: number): Promise<BacktestMetrics> {
  return apiFetch<BacktestMetrics>(`/api/v1/backtests/${runId}/metrics`);
}

export function cancelBacktest(runId: number): Promise<BacktestRun> {
  return apiFetch<BacktestRun>(`/api/v1/backtests/${runId}/cancel`, {
    method: "POST",
  });
}
