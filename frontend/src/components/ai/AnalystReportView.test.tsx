import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnalystReportView } from "./AnalystReportView";
import type { AnalystReport } from "@/lib/api/stocks-types";

/** Decision Engine V2 rollout: the /ai screen's full analyst report
 * must prefer the gate-checked V2 badge over the legacy
 * RecommendationBadge whenever both decision and decision_label_ar
 * are present, exactly as the stock detail page already does. */

function buildReport(overrides: Partial<AnalystReport> = {}): AnalystReport {
  return {
    symbol: "2222",
    recommendation: "BUY",
    confidence: 70,
    final_score: 80,
    target_price: 35,
    stop_loss: 28,
    time_horizon: "MEDIUM_TERM",
    expected_return_pct: 5,
    risk_level: "MEDIUM",
    position_size: "MEDIUM",
    investment_summary: "ملخص الاستثمار.",
    technical_reasoning: "التحليل الفني.",
    fundamental_reasoning: "التحليل الأساسي.",
    risk_explanation: "تفسير المخاطر.",
    bullish_factors: [],
    bearish_factors: [],
    confidence_explanation: "تفسير الثقة.",
    target_price_explanation: "تفسير السعر المستهدف.",
    stop_loss_explanation: "تفسير وقف الخسارة.",
    time_horizon_explanation: "تفسير الإطار الزمني.",
    alternative_scenarios: [],
    final_recommendation_rationale: "الأساس المنطقي.",
    generated_at: "2026-08-01T00:00:00Z",
    engine_version: "v1",
    entry_quality: "GOOD",
    entry_quality_notes: [],
    risk_reward_ratio: 2,
    stop_loss_basis: "atr",
    target_price_basis: "atr",
    confidence_calibration_notes: [],
    ...overrides,
  };
}

describe("AnalystReportView Decision Engine V2 precedence", () => {
  it("renders the Decision Engine V2 badge instead of the legacy recommendation badge when both decision and decision_label_ar are present", () => {
    render(
      <AnalystReportView
        report={buildReport({ decision: "BUY_CANDIDATE", decision_label_ar: "مرشح للشراء" })}
      />
    );
    expect(screen.getByText("مرشح للشراء")).toBeInTheDocument();
    expect(screen.queryByText("شراء")).not.toBeInTheDocument();
  });

  it("falls back to the legacy recommendation badge when V2 decision data is absent", () => {
    render(<AnalystReportView report={buildReport()} />);
    expect(screen.getByText("شراء")).toBeInTheDocument();
    expect(screen.queryByText("مرشح للشراء")).not.toBeInTheDocument();
  });
});
