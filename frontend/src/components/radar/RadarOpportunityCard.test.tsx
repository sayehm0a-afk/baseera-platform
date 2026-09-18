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
    decision_freshness_status: "LIVE" as const,
    is_decision_fresh: true,
    decision_v2_snapshot_id: 100,
    sector_ar: "الطاقة",
    historical_reliability_level: "HIGH",
    historical_reliability_label_ar: "موثوقية تاريخية عالية لهذا القطاع",
    historical_reliability_win_rate_pct: 74.1,
    historical_reliability_sample_size: 88,
    recent_negative_outcome_status: null,
    recent_negative_outcome_label_ar: null,
    recent_negative_outcome_at: null,
    recent_negative_outcome_return_pct: null,
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

  it("omits a missing second/third target entirely rather than fabricating or showing a bare placeholder (2026-09-18: large, focused trade-parameters block)", () => {
    render(<RadarOpportunityCard opportunity={buildOpportunity({ target_2: null, target_3: null })} />);

    expect(screen.queryByText("الهدف الثاني")).not.toBeInTheDocument();
    expect(screen.queryByText("الهدف الثالث")).not.toBeInTheDocument();
    expect(screen.getByText("الهدف الأول")).toBeInTheDocument();
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

  it("labels a stale decision honestly (تحليل قديم), distinct from and never using the price-freshness label -- production regression: symbol 6060 (3-day-old BUY, live price, stale decision)", () => {
    render(
      <RadarOpportunityCard
        opportunity={buildOpportunity({
          symbol: "6060",
          data_freshness_status: "LIVE",
          entry_status: "READY_NOW",
          decision_freshness_status: "STALE",
          is_decision_fresh: false,
        })}
      />
    );

    // Price freshness ("بيانات حيّة") and decision freshness ("تحليل
    // قديم") must both be visible and never conflated into one label.
    expect(screen.getByText("بيانات حيّة")).toBeInTheDocument();
    expect(screen.getByText("تحليل قديم — يحتاج إعادة تقييم")).toBeInTheDocument();
  });

  it("does not show the decision-freshness warning for a fresh decision", () => {
    render(<RadarOpportunityCard opportunity={buildOpportunity({ is_decision_fresh: true })} />);

    expect(screen.queryByText(/تحليل قديم/)).not.toBeInTheDocument();
  });

  it("shows the real per-sector reliability disclosure with its win rate and sample size, independent of confidence_score", () => {
    render(<RadarOpportunityCard opportunity={buildOpportunity()} />);
    expect(screen.getByText(/موثوقية تاريخية عالية لهذا القطاع/)).toBeInTheDocument();
    expect(screen.getByText(/74% نسبة ربح فعلية على 88 توصية سابقة/)).toBeInTheDocument();
  });

  it("flags a historically weak sector with the market-down color, and omits the win-rate parenthetical when data is insufficient", () => {
    render(
      <RadarOpportunityCard
        opportunity={buildOpportunity({
          historical_reliability_level: "INSUFFICIENT_DATA",
          historical_reliability_label_ar: "بيانات غير كافية لتقييم موثوقية هذا القطاع بعد",
          historical_reliability_win_rate_pct: null,
          historical_reliability_sample_size: 4,
        })}
      />
    );
    const badge = screen.getByText("بيانات غير كافية لتقييم موثوقية هذا القطاع بعد");
    expect(badge.className).not.toContain("bsr-market-down");
    expect(screen.queryByText(/نسبة ربح فعلية/)).not.toBeInTheDocument();
  });

  it("does not show a recent-failure warning when the backend reports none", () => {
    render(<RadarOpportunityCard opportunity={buildOpportunity()} />);
    expect(screen.queryByText(/آخر إشارة لهذا السهم/)).not.toBeInTheDocument();
  });

  it("shows a prominent warning when this exact symbol's own recent signal already failed -- production regression: symbol 1830, re-quoted as a fresh BUY_CANDIDATE hours after its own stop-loss was breached", () => {
    render(
      <RadarOpportunityCard
        opportunity={buildOpportunity({
          recent_negative_outcome_status: "STOP_LOSS_HIT",
          recent_negative_outcome_label_ar: "آخر إشارة لهذا السهم اخترقت وقف الخسارة",
          recent_negative_outcome_at: "2026-09-15T15:00:00Z",
          recent_negative_outcome_return_pct: -2.3,
        })}
      />
    );
    expect(screen.getByText(/آخر إشارة لهذا السهم اخترقت وقف الخسارة/)).toBeInTheDocument();
  });
});
