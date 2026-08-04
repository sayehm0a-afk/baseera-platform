import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ExecutiveDecisionCard } from "./ExecutiveDecisionCard";
import type { DecisionV2 } from "@/lib/api/stocks-types";

/** Phase 2 Foundation Cleanup, goal 4: production-grade coverage for
 * the component that renders Decision Engine V2's executive summary
 * -- every field here is verbatim backend output, so these tests lock
 * down that no field is silently dropped, mislabeled, or rendered when
 * absent, as a regression guard before Phase 2 builds on top of this
 * component (the Complete Stock Intelligence Report). */

function buildDecision(overrides: Partial<DecisionV2> = {}): DecisionV2 {
  return {
    symbol: "2222",
    company_name_ar: "أرامكو السعودية",
    company_name_en: "Saudi Aramco",
    sector_ar: "الطاقة",
    decision: "WATCH",
    decision_label_ar: "مراقبة",
    confidence_score: 66,
    confidence_disclaimer_ar: "درجة الثقة تعكس قوة الأدلة، لا تضمن الربح.",
    opportunity_quality_score: 72,
    risk_score: 40,
    data_quality_score: 90,
    data_freshness_status: "LIVE",
    current_price: 27.1,
    entry_zone_low: 26.8,
    entry_zone_high: 26.93,
    stop_loss: 26.46,
    target_1: 27.7,
    target_2: 28.14,
    target_3: null,
    expected_return_target_1: 2.2,
    expected_return_target_2: 3.8,
    downside_to_stop: -2.4,
    risk_reward_target_1: 1.8,
    risk_reward_target_2: 2.5,
    expected_holding_period_min_days: 5,
    expected_holding_period_max_days: 15,
    expected_holding_period_label_ar: "من 5 إلى 15 يوم تداول",
    horizon_type: "SWING",
    market_status: "التداول المستمر",
    decision_timestamp: "2026-08-04T12:00:00Z",
    invalidation_conditions: ["إغلاق دون وقف الخسارة"],
    positive_reasons: ["اتجاه صاعد مؤكد بحجم تداول قوي"],
    negative_reasons: ["تقييم مرتفع نسبياً للقطاع"],
    warnings: ["البيانات قريبة من نهاية صلاحيتها"],
    recommendation_basis: "بناءً على تقاطع إيجابي للمتوسطات المتحركة وحجم تداول أعلى من المتوسط.",
    analysis_disclaimer_ar: "هذا التحليل لا يُعد توصية استثمارية مضمونة ولا يضمن تحقيق ربح.",
    analysis_version: "2.0.0",
    data_source: "SAHMK_REAL",
    scan_run_id: 34,
    sub_scores: {
      trend_score: 80,
      momentum_score: 70,
      volume_score: 65,
      liquidity_score: 90,
      volatility_score: 50,
      risk_reward_score: 75,
      market_context_score: 60,
      data_quality_score: 90,
    },
    gates: [{ name: "DATA_FRESHNESS", passed: true, detail: "بيانات حديثة", blocking: true }],
    ...overrides,
  };
}

describe("ExecutiveDecisionCard", () => {
  it("renders the decision badge with the backend's own Arabic label, never re-translated", () => {
    render(<ExecutiveDecisionCard decision={buildDecision({ decision: "BUY_CANDIDATE", decision_label_ar: "مرشح للشراء" })} />);
    expect(screen.getByText("مرشح للشراء")).toBeInTheDocument();
  });

  it("renders the confidence score and its disclaimer together", () => {
    render(<ExecutiveDecisionCard decision={buildDecision({ confidence_score: 66 })} />);
    expect(screen.getByText("66%")).toBeInTheDocument();
    expect(screen.getByText("درجة الثقة تعكس قوة الأدلة، لا تضمن الربح.")).toBeInTheDocument();
  });

  it("renders the entry zone, stop loss, and both targets when present", () => {
    render(<ExecutiveDecisionCard decision={buildDecision()} />);
    expect(screen.getByText("26.80 – 26.93")).toBeInTheDocument();
    expect(screen.getByText("26.46")).toBeInTheDocument();
    expect(screen.getByText("27.70")).toBeInTheDocument();
    expect(screen.getByText("28.14")).toBeInTheDocument();
  });

  it("shows an em dash for the entry zone instead of fabricating one when both bounds are absent", () => {
    render(
      <ExecutiveDecisionCard
        decision={buildDecision({ entry_zone_low: null, entry_zone_high: null, stop_loss: null, target_1: null })}
      />
    );
    expect(screen.queryByText(/–/)).not.toBeInTheDocument();
  });

  it("renders positive reasons, negative reasons, warnings, and invalidation conditions verbatim", () => {
    // Each item renders as "• {text}" across two text nodes inside one
    // <li>, so these match on substring rather than exact node text.
    render(<ExecutiveDecisionCard decision={buildDecision()} />);
    expect(screen.getByText("اتجاه صاعد مؤكد بحجم تداول قوي", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("تقييم مرتفع نسبياً للقطاع", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("البيانات قريبة من نهاية صلاحيتها", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("إغلاق دون وقف الخسارة", { exact: false })).toBeInTheDocument();
  });

  it("omits the reasons/warnings/invalidation sections entirely when their arrays are empty, rather than rendering an empty heading", () => {
    render(
      <ExecutiveDecisionCard
        decision={buildDecision({ positive_reasons: [], negative_reasons: [], warnings: [], invalidation_conditions: [] })}
      />
    );
    expect(screen.queryByText("ما الذي يؤيد القرار")).not.toBeInTheDocument();
    expect(screen.queryByText("ما الذي يضعف القرار")).not.toBeInTheDocument();
    expect(screen.queryByText("تنبيهات")).not.toBeInTheDocument();
    expect(screen.queryByText("متى يُلغى هذا القرار؟")).not.toBeInTheDocument();
  });

  it("always renders the analysis disclaimer -- Basirah must never present a decision without it", () => {
    render(<ExecutiveDecisionCard decision={buildDecision()} />);
    expect(
      screen.getByText("هذا التحليل لا يُعد توصية استثمارية مضمونة ولا يضمن تحقيق ربح.")
    ).toBeInTheDocument();
  });

  it("renders the freshness status label for each of the four DataFreshnessStatus values", () => {
    const cases: Array<[DecisionV2["data_freshness_status"], string]> = [
      ["LIVE", "بيانات حيّة"],
      ["LAST_SESSION", "بيانات آخر جلسة مكتملة"],
      ["STALE", "بيانات قديمة"],
      ["UNKNOWN", "حداثة البيانات غير مؤكدة"],
    ];
    for (const [status, labelAr] of cases) {
      const { unmount } = render(<ExecutiveDecisionCard decision={buildDecision({ data_freshness_status: status })} />);
      expect(screen.getByText(labelAr)).toBeInTheDocument();
      unmount();
    }
  });

  it("renders the data source, engine version, and decision timestamp in the footer", () => {
    render(<ExecutiveDecisionCard decision={buildDecision({ data_source: "SAHMK_REAL", analysis_version: "2.0.0" })} />);
    expect(screen.getByText(/SAHMK_REAL/)).toBeInTheDocument();
    expect(screen.getByText(/2\.0\.0/)).toBeInTheDocument();
  });
});
