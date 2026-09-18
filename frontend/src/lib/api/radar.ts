import { apiFetch } from "./client";
import type {
  RadarHistoryDay,
  RadarHomeSummary,
  RadarOpportunityDetail,
  RadarOpportunitySummary,
  RadarScanNowResult,
} from "./radar-types";

/** Every function here calls one of the consumer-facing
 * /api/v1/radar/* routes (src/api/routes/radar.py). Every one except
 * `triggerRadarScanNow` is a read-only, zero-SAHMK-cost view over
 * already-persisted RadarOpportunity/DecisionV2Snapshot rows. Never
 * the staff-only /admin/market-intelligence/radar-v2/* routes. */

export function getRadarSummary(): Promise<RadarHomeSummary> {
  return apiFetch<RadarHomeSummary>("/api/v1/radar/summary");
}

export function getRadarOpportunities(params?: {
  classification?: string;
  limit?: number;
}): Promise<RadarOpportunitySummary[]> {
  const search = new URLSearchParams();
  if (params?.classification) search.set("classification", params.classification);
  if (params?.limit) search.set("limit", String(params.limit));
  const query = search.toString() ? `?${search.toString()}` : "";
  return apiFetch<RadarOpportunitySummary[]>(`/api/v1/radar/opportunities${query}`);
}

export function getRadarOpportunity(id: number): Promise<RadarOpportunityDetail> {
  return apiFetch<RadarOpportunityDetail>(`/api/v1/radar/opportunities/${id}`);
}

/** No dedicated by-symbol backend route exists (Radar V2's ranked list
 * is already small -- capped by RADAR_STAGE2_CANDIDATE_CAP -- so
 * fetching the full live list and finding the one matching row costs
 * nothing extra beyond the one request the list itself already makes).
 * Resolves to `null`, never throws, when this symbol has no live
 * (non-superseded) radar opportunity right now -- an honest "not
 * currently on the radar" state, not an error. */
export async function getRadarOpportunityBySymbol(
  symbol: string
): Promise<RadarOpportunitySummary | null> {
  const opportunities = await getRadarOpportunities({ limit: 200 });
  return opportunities.find((o) => o.symbol === symbol) ?? null;
}

/** Product decision 2026-09-18: browse a past day's real Smart Radar
 * picks. `date` must be "YYYY-MM-DD" (Tadawul-local). Read-only, zero
 * SAHMK cost -- see src/api/routes/radar.py's own docstring. */
export function getRadarHistoryDay(date: string): Promise<RadarHistoryDay> {
  return apiFetch<RadarHistoryDay>(`/api/v1/radar/history?date=${encodeURIComponent(date)}`);
}

/** On-demand consumer scan mandate (2026-09-11): claims one turn of
 * the same bounded, quota-gated, leader-locked Radar V2 cycle the
 * scheduler and staff routes already run, subject to a per-user
 * cooldown enforced server-side. NOT zero-SAHMK-cost -- see this
 * module's own docstring. */
export function triggerRadarScanNow(): Promise<RadarScanNowResult> {
  return apiFetch<RadarScanNowResult>("/api/v1/radar/scan-now", { method: "POST" });
}
