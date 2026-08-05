import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BeginnerSummaryCard } from "./BeginnerSummaryCard";
import type { DecisionV2 } from "@/lib/api/stocks-types";

/** Phase 2G: coverage for the beginner-facing 8-question summary --
 * every field here is verbatim backend output already computed by
 * Decision Engine V2; these tests lock down that each of the 8
 * questions is answered from a real field and that an empty list
 * omits its section rather than rendering an empty heading. */

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
    gates: [{ name: "data_freshness", passed: true, detail: "بيانات حديثة", blocking: true }],
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

describe("BeginnerSummaryCard", () => {
  it("answers 'what should I do' with the real decision label and summary", () => {
    render(<BeginnerSummaryCard decision={buildDecision({ decision_label_ar: "مراقبة" })} />);
    expect(screen.getByText("مراقبة")).toBeInTheDocument();
    expect(screen.getByText("مراقبة -- بثقة 66٪، مصنّف كـ«مضاربة أسبوعية».")).toBeInTheDocument();
  });

  it("answers 'why' with why_now_ar", () => {
    render(<BeginnerSummaryCard decision={buildDecision()} />);
    expect(screen.getByText("السهم يستحق المتابعة لكن الأدلة الحالية غير كافية لاتخاذ قرار دخول.")).toBeInTheDocument();
  });

  it("answers 'when to enter' with the real entry status label", () => {
    render(<BeginnerSummaryCard decision={buildDecision({ entry_status_label_ar: "قريب من الدخول" })} />);
    expect(screen.getByText("قريب من الدخول")).toBeInTheDocument();
  });

  it("answers 'how much risk' with the real risk level label", () => {
    render(<BeginnerSummaryCard decision={buildDecision({ risk_level_label_ar: "متوسطة" })} />);
    expect(screen.getByText("متوسطة")).toBeInTheDocument();
  });

  it("combines negative reasons and warnings under 'what could go wrong'", () => {
    render(<BeginnerSummaryCard decision={buildDecision()} />);
    expect(screen.getByText("تقييم مرتفع نسبياً للقطاع", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("البيانات قريبة من نهاية صلاحيتها", { exact: false })).toBeInTheDocument();
  });

  it("omits the 'what could go wrong' section when there are no reasons or warnings", () => {
    render(<BeginnerSummaryCard decision={buildDecision({ negative_reasons: [], warnings: [] })} />);
    expect(screen.queryByText("ما الذي قد يحدث بشكل خاطئ؟")).not.toBeInTheDocument();
  });

  it("answers 'how long to hold' with the real holding period label", () => {
    render(<BeginnerSummaryCard decision={buildDecision({ expected_holding_period_label_ar: "من 5 إلى 15 يوم تداول" })} />);
    expect(screen.getByText("من 5 إلى 15 يوم تداول")).toBeInTheDocument();
  });

  it("answers 'what confirms I'm right' with entry confirmation conditions", () => {
    render(<BeginnerSummaryCard decision={buildDecision()} />);
    expect(
      screen.getByText("اختراق حقيقي لمستوى 27.90 مدعوم بحجم تداول أعلى من المتوسط يعزز الفرضية.", { exact: false })
    ).toBeInTheDocument();
  });

  it("answers 'what would change my mind' with invalidation conditions", () => {
    render(<BeginnerSummaryCard decision={buildDecision()} />);
    expect(screen.getByText("إغلاق دون وقف الخسارة", { exact: false })).toBeInTheDocument();
  });

  it("always renders the analysis disclaimer", () => {
    render(<BeginnerSummaryCard decision={buildDecision()} />);
    expect(screen.getByText("هذا التحليل لا يُعد توصية استثمارية مضمونة ولا يضمن تحقيق ربح.")).toBeInTheDocument();
  });

  it("degrades sensibly for a REJECT decision with no real opportunity", () => {
    /** 'no opportunity' is a valid, real result for a beginner to see
     * too -- confirmation/invalidation sections must disappear rather
     * than render empty, and 'what could go wrong' becomes the
     * dominant answer instead of crashing or showing stale content. */
    render(
      <BeginnerSummaryCard
        decision={buildDecision({
          decision: "REJECT",
          decision_label_ar: "مرفوض",
          decision_summary_ar: "مرفوض -- لا توجد فرصة حقيقية حاليًا وفق بوابات النشر.",
          entry_status: "NOT_SUITABLE",
          entry_status_label_ar: "غير مناسب",
          entry_confirmation_conditions_ar: [],
          invalidation_conditions: [],
          negative_reasons: ["فشل بوابة العائد إلى المخاطرة."],
          warnings: [],
        })}
      />
    );
    expect(screen.getByText("مرفوض")).toBeInTheDocument();
    expect(screen.getByText("غير مناسب")).toBeInTheDocument();
    expect(screen.getByText("فشل بوابة العائد إلى المخاطرة.", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("ما الذي يؤكد صحة القرار؟")).not.toBeInTheDocument();
    expect(screen.queryByText("ما الذي يلغي هذا القرار؟")).not.toBeInTheDocument();
  });
});
