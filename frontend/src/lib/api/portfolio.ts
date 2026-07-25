import { apiFetch } from "./client";
import type {
  Allocation,
  Diversification,
  HealthScore,
  PortfolioAnalysis,
  PortfolioAnalyzeRequestBody,
  PortfolioRecommendations,
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
