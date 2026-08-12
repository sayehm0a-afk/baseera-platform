import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PortfolioDetail } from "./PortfolioDetail";
import type { PortfolioAnalysis } from "@/lib/api/portfolio-types";

/** M7 gap closure: portfolio sector-display audit -- Arabic users must
 * never see a raw English sector name where the canonical sector_ar
 * value is available (src/domain/sector_labels.py). Covers the sector
 * exposure list and the new-buy-opportunity cards, the two portfolio
 * render sites that were still reading the raw `sector` field. */

vi.mock("@/lib/api/portfolio", () => ({
  getPortfolioNewsAlerts: vi.fn().mockResolvedValue({ alerts: [] }),
  refreshPortfolioNewsAlerts: vi.fn(),
}));

function buildAnalysis(overrides: Partial<PortfolioAnalysis> = {}): PortfolioAnalysis {
  return {
    portfolio_id: 1,
    name: "محفظتي",
    cash: 1000,
    total_value: 10000,
    generated_at: "2026-08-01T00:00:00Z",
    holdings: [],
    allocation: { entries: [], cash: 1000, cash_weight: 0.1, total_value: 10000 },
    sector_exposure: [
      {
        sector: "Real Estate Mgmt & Dev't",
        sector_ar: "إدارة وتطوير العقارات",
        market_value: 9000,
        weight: 0.9,
        holdings_count: 1,
        symbols: ["4300"],
      },
    ],
    concentration: {
      herfindahl_index: 1,
      sector_herfindahl_index: 1,
      largest_position_symbol: "4300",
      largest_position_weight: 0.9,
      top_3_weight: 0.9,
      is_concentrated: true,
      concentration_threshold: 0.5,
    },
    diversification: {
      score: 20,
      effective_number_of_holdings: 1,
      effective_number_of_sectors: 1,
      sector_count: 1,
      holdings_count: 1,
      narrative: "محفظة غير منوّعة.",
    },
    risk_profile: {
      risk_score: 50,
      risk_level: "MEDIUM",
      expected_volatility_annualized_pct: null,
      estimated_max_drawdown_pct: null,
      portfolio_beta: null,
      beta_unavailable_reason: null,
      correlation_matrix: null,
      excluded_from_volatility: [],
      narrative: "مستوى مخاطرة متوسط.",
    },
    recommendations: {
      rebalance_actions: [],
      new_buy_opportunities: [
        {
          symbol: "6004",
          sector: "Commercial & Professional Svc",
          sector_ar: "الخدمات التجارية والمهنية",
          recommendation: "BUY",
          confidence: 70,
          final_score: 80,
          rationale: "فرصة شراء واعدة.",
        },
      ],
      cash_recommendation: {
        current_cash: 1000,
        current_cash_pct: 0.1,
        recommended_cash_pct_min: 0.05,
        recommended_cash_pct_max: 0.15,
        recommended_cash_amount_min: 500,
        recommended_cash_amount_max: 1500,
        is_within_target_band: true,
        rationale: "النقد ضمن النطاق المستهدف.",
      },
      optimization_recommendations: [],
    },
    health_score: { score: 60, band: "FAIR", components: {}, narrative: "صحة مقبولة." },
    ...overrides,
  };
}

describe("PortfolioDetail sector display", () => {
  it("renders the canonical Arabic sector label in the sector-exposure list, not the raw English sector", () => {
    render(<PortfolioDetail analysis={buildAnalysis()} onEdit={() => {}} onReset={() => {}} />);

    expect(screen.getByText("إدارة وتطوير العقارات")).toBeInTheDocument();
    expect(screen.queryByText("Real Estate Mgmt & Dev't")).not.toBeInTheDocument();
  });

  it("passes the canonical Arabic sector label into the new-buy-opportunity card, not the raw English sector", () => {
    render(<PortfolioDetail analysis={buildAnalysis()} onEdit={() => {}} onReset={() => {}} />);

    expect(screen.getByText("الخدمات التجارية والمهنية")).toBeInTheDocument();
    expect(screen.queryByText("Commercial & Professional Svc")).not.toBeInTheDocument();
  });

  it("falls back to the raw sector when sector_ar is unavailable, rather than hiding the sector entirely", () => {
    const analysis = buildAnalysis({
      sector_exposure: [
        {
          sector: "Untranslated Sector",
          sector_ar: null,
          market_value: 9000,
          weight: 0.9,
          holdings_count: 1,
          symbols: ["4300"],
        },
      ],
    });
    render(<PortfolioDetail analysis={analysis} onEdit={() => {}} onReset={() => {}} />);

    expect(screen.getByText("Untranslated Sector")).toBeInTheDocument();
  });
});
