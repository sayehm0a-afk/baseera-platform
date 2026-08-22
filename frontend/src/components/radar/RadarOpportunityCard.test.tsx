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
    entry_status: "READY_NOW",
    entry_status_label_ar: "مناسب الآن",
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

  it("always shows a real Arabic timestamp for when the signal was emitted", () => {
    render(<RadarOpportunityCard opportunity={buildOpportunity({ emitted_at: "2026-08-17T09:00:00Z" })} />);

    expect(screen.getByText(/صدرت الإشارة:/)).toBeInTheDocument();
  });

  it("shows a missed-entry warning and does not present a multi-day-old missed opportunity as currently actionable", () => {
    const fourDaysAgo = new Date(Date.now() - 4 * 24 * 60 * 60 * 1000).toISOString();
    render(
      <RadarOpportunityCard
        opportunity={buildOpportunity({
          emitted_at: fourDaysAgo,
          entry_status: "MISSED_ENTRY",
          entry_status_label_ar: "فاتت نقطة الدخول",
        })}
      />
    );

    expect(screen.getByText(/فاتت نقطة الدخول/)).toBeInTheDocument();
    expect(screen.getByText(/لم تعد فرصة دخول حالية/)).toBeInTheDocument();
  });

  it("does not show the missed-entry warning for a currently actionable opportunity", () => {
    render(<RadarOpportunityCard opportunity={buildOpportunity({ entry_status: "READY_NOW" })} />);

    expect(screen.queryByText(/لم تعد فرصة دخول حالية/)).not.toBeInTheDocument();
  });
});
