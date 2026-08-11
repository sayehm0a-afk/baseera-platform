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
    market_status: "OPEN",
    market_status_label_ar: "التداول المستمر",
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
    gates: [{ name: "DATA_FRESHNESS", status: "PASS", passed: true, detail: "بيانات حديثة", blocking: true }],
    is_real_data: true,
    quote_timestamp: "2026-08-04T11:55:00Z",
    technical_confidence: 80,
    momentum_confidence: 70,
    liquidity_confidence: 90,
    market_context_confidence: 60,
    data_quality_confidence: 90,
    trade_type: "WEEKLY_SWING",
    trade_type_label_ar: "مضاربة أسبوعية",
    time_horizon_rationale_ar: "زخم غير حاسم حاليًا -- الأنسب متابعة الفرصة على مدى أسبوع تداول تقريبًا.",
    best_entry_price: 26.8,
    accumulation_zone_low: 26.5,
    accumulation_zone_high: 26.93,
    entry_quality: "GOOD",
    entry_quality_label_ar: "جيدة",
    entry_status: "NEAR_ENTRY",
    entry_status_label_ar: "قريب من الدخول",
    invalidation_price: 26.46,
    risk_level: "MEDIUM",
    risk_level_label_ar: "متوسطة",
    estimated_days_target_1: 5,
    estimated_days_target_2: 9,
    estimated_days_target_3: null,
    nearest_support: 26.4,
    major_support: 25.8,
    nearest_resistance: 27.9,
    major_resistance: 28.5,
    breakout_level: 27.9,
    breakdown_level: 26.4,
    support_resistance_evidence_ar: "مستويات مكتشفة عبر تحليل القمم والقيعان السعرية.",
    current_volume: 1_800_000,
    average_volume: 1_500_000,
    relative_volume: 1.2,
    liquidity_quality_ar: "سيولة جيدة",
    accumulation_score: 65,
    accumulation_assessment_ar: "إشارات تجميع محتملة بناءً على اتجاه التدفق النقدي التراكمي (OBV).",
    volume_confirms_decision: true,
    abnormal_volume: false,
    technical_evidence: { rsi_14: 58.2, adx_14: 24.1 },
    trend_direction_ar: "صاعد",
    trend_strength_label_ar: "معتدل",
    decision_summary_ar: "مراقبة -- بثقة 66٪، مصنّف كـ«مضاربة أسبوعية».",
    why_now_ar: "السهم يستحق المتابعة لكن الأدلة الحالية غير كافية لاتخاذ قرار دخول.",
    why_not_stronger_ar: "لم يتحقق قرار أقوى بسبب: نسبة العائد إلى المخاطرة غير كافية.",
    why_not_buy_reasons: [],
    fundamental_summary: {},
    fundamental_summary_ar: "",
    committee: null,
    entry_confirmation_conditions_ar: ["اختراق حقيقي لمستوى 27.90 مدعوم بحجم تداول أعلى من المتوسط يعزز الفرضية."],
    watch_next_session_ar: ["رد فعل السعر عند مستوى المقاومة القريب (27.90)."],
    market_risk_state: "NEUTRAL",
    market_risk_label_ar: "محايد",
    market_risk_basis_ar: "نسبة الإشارات الإيجابية 50% (10 شراء مقابل 10 بيع) من أصل 40 سهمًا تم فحصها في آخر عملية مسح.",
    market_risk_entry_permitted: true,
    market_risk_is_live: true,
    market_breadth_buy_count: 10,
    market_breadth_sell_count: 10,
    market_breadth_symbols_scanned: 40,
    market_breadth_average_confidence: 62,
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

  it("renders the Arabic data-source trust signal, never the raw internal provider identifier, plus the engine version and decision timestamp", () => {
    render(<ExecutiveDecisionCard decision={buildDecision({ data_source: "SAHMK_REAL", analysis_version: "2.0.0" })} />);
    expect(screen.getByText(/بيانات حقيقية من السوق/)).toBeInTheDocument();
    expect(screen.queryByText(/SAHMK_REAL/)).not.toBeInTheDocument();
    expect(screen.getByText(/2\.0\.0/)).toBeInTheDocument();
  });

  it("falls back to the raw data_source value for an unrecognized future source, rather than hiding it", () => {
    render(<ExecutiveDecisionCard decision={buildDecision({ data_source: "SOME_NEW_PROVIDER" })} />);
    expect(screen.getByText(/SOME_NEW_PROVIDER/)).toBeInTheDocument();
  });

  it("renders the Arabic market-status label, never the raw English enum value", () => {
    render(<ExecutiveDecisionCard decision={buildDecision({ market_status: "OPEN", market_status_label_ar: "التداول المستمر" })} />);
    expect(screen.getByText("التداول المستمر")).toBeInTheDocument();
    expect(screen.queryByText("OPEN")).not.toBeInTheDocument();
  });

  it("renders the Phase 2A beginner-friendly summary and why-now sentence", () => {
    render(
      <ExecutiveDecisionCard
        decision={buildDecision({
          decision_summary_ar: "شراء -- بثقة 80٪.",
          why_now_ar: "اتجاه صاعد قوي مدعوم بحجم تداول مرتفع.",
        })}
      />
    );
    expect(screen.getByText("شراء -- بثقة 80٪.")).toBeInTheDocument();
    expect(screen.getByText("اتجاه صاعد قوي مدعوم بحجم تداول مرتفع.")).toBeInTheDocument();
  });

  it("renders the trade type and entry status labels", () => {
    render(
      <ExecutiveDecisionCard
        decision={buildDecision({ trade_type_label_ar: "مضاربة أسبوعية", entry_status_label_ar: "قريب من الدخول" })}
      />
    );
    expect(screen.getByText("مضاربة أسبوعية")).toBeInTheDocument();
    expect(screen.getByText("قريب من الدخول")).toBeInTheDocument();
  });

  it("renders the nearest support and resistance levels when available", () => {
    render(<ExecutiveDecisionCard decision={buildDecision({ nearest_support: 26.4, nearest_resistance: 27.9 })} />);
    expect(screen.getByText("26.40")).toBeInTheDocument();
    expect(screen.getByText("27.90")).toBeInTheDocument();
  });

  it("omits the support/resistance section entirely when neither level is available", () => {
    render(
      <ExecutiveDecisionCard decision={buildDecision({ nearest_support: null, nearest_resistance: null })} />
    );
    expect(screen.queryByText("أقرب دعم")).not.toBeInTheDocument();
    expect(screen.queryByText("أقرب مقاومة")).not.toBeInTheDocument();
  });

  it("renders the Phase 2C market risk state and its evidence basis", () => {
    render(
      <ExecutiveDecisionCard
        decision={buildDecision({
          market_risk_label_ar: "دخول انتقائي",
          market_risk_basis_ar: "نسبة الإشارات الإيجابية 60% (24 شراء مقابل 16 بيع) من أصل 40 سهمًا.",
        })}
      />
    );
    expect(screen.getByText("دخول انتقائي")).toBeInTheDocument();
    expect(
      screen.getByText("نسبة الإشارات الإيجابية 60% (24 شراء مقابل 16 بيع) من أصل 40 سهمًا.")
    ).toBeInTheDocument();
  });

  it("labels a last-session market risk read as such, not as live", () => {
    render(
      <ExecutiveDecisionCard
        decision={buildDecision({
          market_risk_label_ar: "السوق مغلق",
          market_risk_is_live: false,
        })}
      />
    );
    expect(screen.getByText("السوق مغلق (آخر جلسة)")).toBeInTheDocument();
  });

  it("does not append the last-session note when the market risk read is live", () => {
    render(
      <ExecutiveDecisionCard
        decision={buildDecision({ market_risk_label_ar: "دخول قوي", market_risk_is_live: true })}
      />
    );
    expect(screen.getByText("دخول قوي")).toBeInTheDocument();
    expect(screen.queryByText(/آخر جلسة/)).not.toBeInTheDocument();
  });
});
