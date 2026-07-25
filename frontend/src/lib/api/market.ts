import { apiFetch } from "./client";
import type {
  AlertsResponse,
  MarketScanRun,
  MarketSummary,
  RankingsResponse,
  SectorsResponse,
} from "./types";

/** Every function here is a direct, unmodified call to an existing
 * `/api/v1/market/*` route (src/api/routes/market.py) -- no ranking,
 * scoring, or sentiment logic is re-derived on the frontend. */

export function triggerScan(): Promise<MarketScanRun> {
  return apiFetch<MarketScanRun>("/api/v1/market/scan", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getScanRun(runId: number): Promise<MarketScanRun> {
  return apiFetch<MarketScanRun>(`/api/v1/market/scan/${runId}`);
}

export function getMarketSummary(runId?: number): Promise<MarketSummary> {
  const query = runId !== undefined ? `?run_id=${runId}` : "";
  return apiFetch<MarketSummary>(`/api/v1/market/summary${query}`);
}

export function getSectors(runId?: number): Promise<SectorsResponse> {
  const query = runId !== undefined ? `?run_id=${runId}` : "";
  return apiFetch<SectorsResponse>(`/api/v1/market/sectors${query}`);
}

export function getAlerts(params?: {
  severity?: string;
  alertType?: string;
  limit?: number;
}): Promise<AlertsResponse> {
  const search = new URLSearchParams();
  if (params?.severity) search.set("severity", params.severity);
  if (params?.alertType) search.set("alert_type", params.alertType);
  if (params?.limit) search.set("limit", String(params.limit));
  const query = search.toString() ? `?${search.toString()}` : "";
  return apiFetch<AlertsResponse>(`/api/v1/market/alerts${query}`);
}

export function getRankings(
  category?: string,
  runId?: number
): Promise<RankingsResponse> {
  const search = new URLSearchParams();
  if (category) search.set("category", category);
  if (runId !== undefined) search.set("run_id", String(runId));
  const query = search.toString() ? `?${search.toString()}` : "";
  return apiFetch<RankingsResponse>(`/api/v1/market/rankings${query}`);
}
