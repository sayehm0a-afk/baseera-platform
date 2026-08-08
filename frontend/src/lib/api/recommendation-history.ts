import { apiFetch } from "./client";
import type {
  RecommendationHistoryAuditList,
  RecommendationHistoryList,
  RecommendationHistoryStats,
} from "./recommendation-history-types";

/** Every function here is a direct, unmodified call to an existing
 * /api/v1/recommendations/* or /api/v1/admin/recommendation-history
 * route -- no client-side recomputation of any statistic. */

export function getRecommendationHistory(params?: {
  symbol?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<RecommendationHistoryList> {
  const query = new URLSearchParams();
  if (params?.symbol) query.set("symbol", params.symbol);
  if (params?.status) query.set("status", params.status);
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  if (params?.offset !== undefined) query.set("offset", String(params.offset));
  const qs = query.toString();
  return apiFetch<RecommendationHistoryList>(
    `/api/v1/recommendations/history${qs ? `?${qs}` : ""}`
  );
}

export function getRecommendationHistoryStats(
  evaluationHorizonDays: number
): Promise<RecommendationHistoryStats> {
  return apiFetch<RecommendationHistoryStats>(
    `/api/v1/recommendations/history/stats?evaluation_horizon_days=${evaluationHorizonDays}`
  );
}

export function getAdminRecommendationHistory(params?: {
  symbol?: string;
  limit?: number;
  offset?: number;
}): Promise<RecommendationHistoryAuditList> {
  const query = new URLSearchParams();
  if (params?.symbol) query.set("symbol", params.symbol);
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  if (params?.offset !== undefined) query.set("offset", String(params.offset));
  const qs = query.toString();
  return apiFetch<RecommendationHistoryAuditList>(
    `/api/v1/admin/recommendation-history${qs ? `?${qs}` : ""}`
  );
}
