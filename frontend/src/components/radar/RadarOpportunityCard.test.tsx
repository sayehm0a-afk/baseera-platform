import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RadarOpportunityCard } from "./RadarOpportunityCard";
import type { RadarOpportunitySummary } from "@/lib/api/radar-types";

function buildOpportunity(overrides: Partial<RadarOpportunitySummary> = {}): RadarOpportunitySummary {
  return {
    id: 42,
    symbol: "2222",
    company_name_ar: "أرامكو السعودية",
    company_name_en: "Saudi Aramco",
    classification: "BUY_CANDIDATE",
    classification_label_ar: "شراء",
    confidence_score: 78.4,
    confidence_disclaimer_ar: "درجة الثقة تقيس قوة واتساق الأدلة المتاحة، وليست احتمال ربح مضمون.",
    basirah_score: 81.2,
    price_at_signal: 30.5,
    entry_zone_low: 30.0,
    entry_zone_high: 30.6,
    stop_loss: 29.0,
    target_1: 32.0,
    target_2: 33.0,
    target_3: 34.0,
    expected_return_target_1: 4.9,
    risk_reward_target_1: 1.8,
    risk_level: "MEDIUM",
    risk_level_label_ar: "متوسطة",
    data_freshness_status: "LIVE",
    stage1_rank: 1,
    stage1_ranking_score: 88.5,
    ranking_reason_ar: "اختراق مستوى المقاومة بحجم تداول مرتفع",
    emitted_at: "2026-08-17T09:00:00Z",
    decision_v2_snapshot_id: 100,
    ...overrides,
  };
}

describe("RadarOpportunityCard", () => {
  it("renders the real fields from a RadarOpportunitySummary, never fabricated", () => {
    render(<RadarOpportunityCard opportunity={buildOpportunity()} />);

    expect(screen.getByText("أرامكو السعودية")).toBeInTheDocument();
    expect(screen.getByText("2222")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("شراء")).toBeInTheDocument();
    expect(screen.getByText("78%")).toBeInTheDocument();
    expect(screen.getByText("81/100")).toBeInTheDocument();
    expect(screen.getByText("متوسطة")).toBeInTheDocument();
    expect(screen.getByText("اختراق مستوى المقاومة بحجم تداول مرتفع")).toBeInTheDocument();
    expect(
      screen.getByText("درجة الثقة تقيس قوة واتساق الأدلة المتاحة، وليست احتمال ربح مضمون.")
    ).toBeInTheDocument();
  });

  it("shows a placeholder rather than fabricating a missing price", () => {
    render(<RadarOpportunityCard opportunity={buildOpportunity({ target_2: null, target_3: null })} />);

    const dashes = screen.getAllByText("--");
    expect(dashes.length).toBeGreaterThanOrEqual(2);
  });

  it("shows a placeholder rather than fabricating a missing Basirah Score", () => {
    render(<RadarOpportunityCard opportunity={buildOpportunity({ basirah_score: null })} />);

    expect(screen.getAllByText("--").length).toBeGreaterThanOrEqual(1);
  });

  it("omits the ranking-reason section when the backend supplied none", () => {
    render(<RadarOpportunityCard opportunity={buildOpportunity({ ranking_reason_ar: null })} />);

    expect(screen.queryByText("لماذا الآن؟")).not.toBeInTheDocument();
  });

  it("labels stale data honestly rather than presenting it as live", () => {
    render(<RadarOpportunityCard opportunity={buildOpportunity({ data_freshness_status: "STALE" })} />);

    expect(screen.getByText("بيانات قديمة")).toBeInTheDocument();
  });
});
