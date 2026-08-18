import { apiFetch } from "./client";
import type {
  Allocation,
  Diversification,
  HealthScore,
  HoldingCreateInput,
  HoldingUpdateInput,
  MessageResponse,
  PortfolioAnalysis,
  PortfolioAnalyzeRequestBody,
  PortfolioCreateInput,
  PortfolioHoldingDetail,
  PortfolioHoldings,
  PortfolioList,
  PortfolioNewsAlertList,
  PortfolioRecommendations,
  PortfolioSummary,
  RebalancePlan,
  RiskProfile,
} from "./portfolio-types";

/** Every function here is a direct, unmodified call to an existing
 * `/api/v1/portfolio/*` route (src/api/routes/portfolio.py) -- no
 * allocation/risk/rebalance/scoring logic is re-derived here. */

export function analyzePortfolio(
  body: PortfolioAnalyzeRequestBody
): Promise<PortfolioAnalysis> {
  return apiFetch<PortfolioAnalysis>("/api/v1/portfolio/analyze", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getPortfolio(portfolioId: number): Promise<PortfolioAnalysis> {
  return apiFetch<PortfolioAnalysis>(`/api/v1/portfolio/${portfolioId}`);
}

export function getPortfolioRecommendations(
  portfolioId: number
): Promise<PortfolioRecommendations> {
  return apiFetch<PortfolioRecommendations>(
    `/api/v1/portfolio/${portfolioId}/recommendations`
  );
}

export function getPortfolioRisk(portfolioId: number): Promise<RiskProfile> {
  return apiFetch<RiskProfile>(`/api/v1/portfolio/${portfolioId}/risk`);
}

export function getPortfolioAllocation(
  portfolioId: number
): Promise<Allocation> {
  return apiFetch<Allocation>(`/api/v1/portfolio/${portfolioId}/allocation`);
}

export function getPortfolioDiversification(
  portfolioId: number
): Promise<Diversification> {
  return apiFetch<Diversification>(
    `/api/v1/portfolio/${portfolioId}/diversification`
  );
}

export function getPortfolioRebalance(
  portfolioId: number
): Promise<RebalancePlan> {
  return apiFetch<RebalancePlan>(`/api/v1/portfolio/${portfolioId}/rebalance`);
}

export function getPortfolioHealth(portfolioId: number): Promise<HealthScore> {
  return apiFetch<HealthScore>(`/api/v1/portfolio/${portfolioId}/health`);
}

/** Already-persisted alerts (Phase 12) -- see `refreshPortfolioNewsAlerts`
 * to re-evaluate held positions against the latest analyzed news. */
export function getPortfolioNewsAlerts(
  portfolioId: number
): Promise<PortfolioNewsAlertList> {
  return apiFetch<PortfolioNewsAlertList>(
    `/api/v1/portfolio/${portfolioId}/news-alerts`
  );
}

export function refreshPortfolioNewsAlerts(
  portfolioId: number
): Promise<PortfolioNewsAlertList> {
  return apiFetch<PortfolioNewsAlertList>(
    `/api/v1/portfolio/${portfolioId}/news-alerts/refresh`,
    { method: "POST" }
  );
}

/** RADAR-C Phase H: real per-holding CRUD + DB-only P&L + Decision V2
 * holder guidance -- distinct from analyzePortfolio() above, which
 * requires a live market-data provider call. Every function here maps
 * 1:1 onto the lighter, always-DB-only routes added alongside the
 * existing POST /analyze surface. */

export function listMyPortfolios(): Promise<PortfolioList> {
  return apiFetch<PortfolioList>("/api/v1/portfolio");
}

export function createPortfolio(
  body: PortfolioCreateInput
): Promise<PortfolioSummary> {
  return apiFetch<PortfolioSummary>("/api/v1/portfolio", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deletePortfolio(
  portfolioId: number
): Promise<MessageResponse> {
  return apiFetch<MessageResponse>(`/api/v1/portfolio/${portfolioId}`, {
    method: "DELETE",
  });
}

export function getPortfolioHoldings(
  portfolioId: number
): Promise<PortfolioHoldings> {
  return apiFetch<PortfolioHoldings>(
    `/api/v1/portfolio/${portfolioId}/holdings`
  );
}

export function addPortfolioHolding(
  portfolioId: number,
  body: HoldingCreateInput
): Promise<PortfolioHoldingDetail> {
  return apiFetch<PortfolioHoldingDetail>(
    `/api/v1/portfolio/${portfolioId}/holdings`,
    { method: "POST", body: JSON.stringify(body) }
  );
}

export function updatePortfolioHolding(
  portfolioId: number,
  holdingId: number,
  body: HoldingUpdateInput
): Promise<PortfolioHoldingDetail> {
  return apiFetch<PortfolioHoldingDetail>(
    `/api/v1/portfolio/${portfolioId}/holdings/${holdingId}`,
    { method: "PATCH", body: JSON.stringify(body) }
  );
}

export function deletePortfolioHolding(
  portfolioId: number,
  holdingId: number
): Promise<MessageResponse> {
  return apiFetch<MessageResponse>(
    `/api/v1/portfolio/${portfolioId}/holdings/${holdingId}`,
    { method: "DELETE" }
  );
}
