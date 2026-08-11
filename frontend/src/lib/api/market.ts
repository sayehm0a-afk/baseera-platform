import { apiFetch } from "./client";
import type {
  AlertsResponse,
  MarketDataHealth,
  MarketScanProgress,
  MarketScanRun,
  MarketStatus,
  MarketSummary,
  OpportunitiesResponse,
  PersonalScanResponse,
  RankingsResponse,
  SectorsResponse,
  WatchlistsResponse,
} from "./types";

/** Every function here is a direct, unmodified call to an existing
 * `/api/v1/market/*` route (src/api/routes/market.py) -- no ranking,
 * scoring, or sentiment logic is re-derived on the frontend. */

export function getMarketStatus(): Promise<MarketStatus> {
  return apiFetch<MarketStatus>("/api/v1/market/status");
}

export function triggerScan(): Promise<MarketScanRun> {
  return apiFetch<MarketScanRun>("/api/v1/market/scan", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getScanRun(runId: number): Promise<MarketScanRun> {
  return apiFetch<MarketScanRun>(`/api/v1/market/scan/${runId}`);
}

export function getScanProgress(runId: number): Promise<MarketScanProgress> {
  return apiFetch<MarketScanProgress>(`/api/v1/market/scan/${runId}/progress`);
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

export function getOpportunities(runId?: number): Promise<OpportunitiesResponse> {
  const query = runId !== undefined ? `?run_id=${runId}` : "";
  return apiFetch<OpportunitiesResponse>(`/api/v1/market/opportunities${query}`);
}

/** "امسح السوق الآن" -- at most 5 unique, ranked opportunities read
 * from the latest completed scan; never triggers a new scan itself
 * (see src.market_intelligence.personal_scan for why). */
export function getPersonalTopOpportunities(): Promise<PersonalScanResponse> {
  return apiFetch<PersonalScanResponse>("/api/v1/market/personal/top-opportunities");
}

export function getWatchlists(
  category?: string,
  runId?: number
): Promise<WatchlistsResponse> {
  const search = new URLSearchParams();
  if (category) search.set("category", category);
  if (runId !== undefined) search.set("run_id", String(runId));
  const query = search.toString() ? `?${search.toString()}` : "";
  return apiFetch<WatchlistsResponse>(`/api/v1/market/watchlists${query}`);
}

// Not under /api/v1/market -- GET /health/market-data (main.py), the
// same top-level health-check family as /health/live and
// /health/ready, so it stays reachable even when the rest of the API
// is otherwise unavailable.
export function getMarketDataHealth(): Promise<MarketDataHealth> {
  return apiFetch<MarketDataHealth>("/health/market-data");
}
