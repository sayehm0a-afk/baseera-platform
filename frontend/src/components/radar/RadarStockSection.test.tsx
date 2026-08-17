import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RadarStockSection } from "./RadarStockSection";
import type { RadarOpportunityDetail, RadarOpportunitySummary } from "@/lib/api/radar-types";

vi.mock("@/lib/api/radar", () => ({
  getRadarOpportunity: vi.fn(),
}));

import { getRadarOpportunity } from "@/lib/api/radar";

function buildSummary(overrides: Partial<RadarOpportunitySummary> = {}): RadarOpportunitySummary {
  return {
    id: 7,
    symbol: "2222",
    company_name_ar: "أرامكو السعودية",
    company_name_en: "Saudi Aramco",
    classification: "BUY_CANDIDATE",
    classification_label_ar: "شراء",
    confidence_score: 70,
    confidence_disclaimer_ar: "درجة الثقة تقيس قوة واتساق الأدلة المتاحة، وليست احتمال ربح مضمون.",
    price_at_signal: 30.5,
    entry_zone_low: 30.0,
    entry_zone_high: 30.6,
    stop_loss: 29.0,
    target_1: 32.0,
    target_2: null,
    target_3: null,
    expected_return_target_1: 4.9,
    risk_reward_target_1: 1.8,
    risk_level: "MEDIUM",
    risk_level_label_ar: "متوسطة",
    data_freshness_status: "LIVE",
    stage1_rank: 3,
    stage1_ranking_score: 70.0,
    ranking_reason_ar: "زخم شرائي قوي",
    emitted_at: "2026-08-17T09:00:00Z",
    decision_v2_snapshot_id: 100,
    ...overrides,
  };
}

function buildDetail(): RadarOpportunityDetail {
  return {
    ...buildSummary(),
    stage1_component_scores: { trend: 80, momentum: 75, volume: 60, liquidity: 70, volatility: 65, risk_reward: 55 },
    stage1_signals: [{ name: "trending", detail_ar: "اتجاه صاعد قوي" }],
    stage1_risk_reward_ratio: 1.8,
    expected_holding_period_min_days: 5,
    expected_holding_period_max_days: 15,
    expected_holding_period_label_ar: "من 5 إلى 15 يوم تداول",
    positive_reasons: ["اختراق حقيقي للمقاومة"],
    negative_reasons: [],
    warnings: ["السيولة أقل من المتوسط"],
    recommendation_basis: null,
    liquidity_quality_ar: null,
    relative_volume: null,
    accumulation_assessment_ar: null,
    decision_timestamp: "2026-08-17T09:00:00Z",
    market_status: "OPEN",
    outcome_status: null,
    outcome_return_pct: null,
    outcome_evaluated_at: null,
  };
}

describe("RadarStockSection", () => {
  it("renders nothing for a symbol with no live radar opportunity -- never a fabricated empty box", () => {
    const { container } = render(<RadarStockSection opportunity={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the real summary fields for a live radar opportunity", () => {
    render(<RadarStockSection opportunity={buildSummary()} />);

    expect(screen.getByText("الرادار الذكي")).toBeInTheDocument();
    expect(screen.getByText("الترتيب #3")).toBeInTheDocument();
    expect(screen.getByText("شراء")).toBeInTheDocument();
    expect(screen.getByText("زخم شرائي قوي")).toBeInTheDocument();
  });

  it("lazily loads and renders the full detail evidence on demand", async () => {
    vi.mocked(getRadarOpportunity).mockResolvedValue(buildDetail());

    render(<RadarStockSection opportunity={buildSummary()} />);
    fireEvent.click(screen.getByRole("button", { name: "عرض تفاصيل الأدلة الفنية" }));

    await waitFor(() => expect(screen.getByText("اختراق حقيقي للمقاومة")).toBeInTheDocument());
    expect(screen.getByText("السيولة أقل من المتوسط")).toBeInTheDocument();
    expect(screen.getByText("اتجاه صاعد قوي")).toBeInTheDocument();
    expect(getRadarOpportunity).toHaveBeenCalledWith(7);
  });
});
