import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DecisionTransparencyPanel } from "./DecisionTransparencyPanel";
import type { DecisionV2 } from "@/lib/api/stocks-types";

/** Phase 2E: coverage for the deep-dive transparency panel -- every
 * field here is verbatim backend output already computed by Decision
 * Engine V2 (Phase 2A/2B/2C) but not rendered by ExecutiveDecisionCard
 * itself; these tests lock down that none of it is silently dropped. */

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
    target_3: 28.9,
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
    gates: [
      { name: "data_freshness", status: "PASS", passed: true, detail: "بيانات حديثة", blocking: true },
      {
        name: "risk_reward_minimum",
        status: "FAIL",
        passed: false,
        detail: "العائد إلى المخاطرة غير كافٍ",
        blocking: true,
      },
      {
        name: "stale_recommendation",
        status: "NOT_EVALUATED",
        passed: true,
        detail: "فحص التكرار غير مطبّق بعد",
        blocking: false,
      },
    ],
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
    estimated_days_target_3: 14,
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

describe("DecisionTransparencyPanel", () => {
  it("renders why the decision was not stronger", () => {
    render(<DecisionTransparencyPanel decision={buildDecision()} />);
    expect(screen.getByText("لم يتحقق قرار أقوى بسبب: نسبة العائد إلى المخاطرة غير كافية.")).toBeInTheDocument();
  });

  it("renders entry confirmation conditions and watch-next-session items", () => {
    render(<DecisionTransparencyPanel decision={buildDecision()} />);
    expect(
      screen.getByText("اختراق حقيقي لمستوى 27.90 مدعوم بحجم تداول أعلى من المتوسط يعزز الفرضية.", { exact: false })
    ).toBeInTheDocument();
    expect(screen.getByText("رد فعل السعر عند مستوى المقاومة القريب (27.90).", { exact: false })).toBeInTheDocument();
  });

  it("renders trend direction and strength", () => {
    render(<DecisionTransparencyPanel decision={buildDecision()} />);
    expect(screen.getByText("صاعد — معتدل")).toBeInTheDocument();
  });

  it("renders the six-part confidence breakdown alongside the overall score", () => {
    render(<DecisionTransparencyPanel decision={buildDecision({ confidence_score: 66 })} />);
    expect(screen.getByText("66%")).toBeInTheDocument();
    expect(screen.getByText("الثقة الفنية")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
  });

  it("renders all eight sub-scores", () => {
    render(<DecisionTransparencyPanel decision={buildDecision()} />);
    expect(screen.getByText("الاتجاه")).toBeInTheDocument();
    expect(screen.getByText("80/100")).toBeInTheDocument();
    expect(screen.getByText("جودة البيانات")).toBeInTheDocument();
  });

  it("renders the third target and per-target estimated days when available", () => {
    render(<DecisionTransparencyPanel decision={buildDecision()} />);
    expect(screen.getByText("28.90")).toBeInTheDocument();
    expect(screen.getByText("14 يوم")).toBeInTheDocument();
  });

  it("omits the extended-targets section entirely when neither field is available", () => {
    render(<DecisionTransparencyPanel decision={buildDecision({ target_3: null, estimated_days_target_3: null })} />);
    expect(screen.queryByText("الهدف الثالث والمدى الزمني الكامل")).not.toBeInTheDocument();
  });

  it("renders major support/resistance and breakout/breakdown levels", () => {
    render(<DecisionTransparencyPanel decision={buildDecision()} />);
    expect(screen.getByText("25.80")).toBeInTheDocument();
    expect(screen.getByText("28.50")).toBeInTheDocument();
  });

  it("renders volume detail including whether volume confirms the decision", () => {
    render(<DecisionTransparencyPanel decision={buildDecision()} />);
    expect(screen.getByText("1.20×")).toBeInTheDocument();
    expect(screen.getByText("يدعم القرار")).toBeInTheDocument();
  });

  it("flags abnormal volume when present", () => {
    render(<DecisionTransparencyPanel decision={buildDecision({ abnormal_volume: true })} />);
    expect(screen.getByText("حجم تداول غير معتاد اليوم.")).toBeInTheDocument();
  });

  it("renders every publication gate with its real Arabic detail text", () => {
    render(<DecisionTransparencyPanel decision={buildDecision()} />);
    expect(screen.getByText("بوابات النشر (3)")).toBeInTheDocument();
    expect(screen.getByText("بيانات حديثة")).toBeInTheDocument();
    expect(screen.getByText("العائد إلى المخاطرة غير كافٍ")).toBeInTheDocument();
  });

  it("marks a NOT_EVALUATED gate with a neutral indicator, never a pass checkmark", () => {
    render(<DecisionTransparencyPanel decision={buildDecision()} />);
    const notEvaluatedRow = screen.getByText("فحص التكرار غير مطبّق بعد").closest("li");
    expect(notEvaluatedRow).not.toBeNull();
    expect(notEvaluatedRow).toHaveTextContent("○");
    expect(notEvaluatedRow).not.toHaveTextContent("✓");
  });

  it("omits the publication-gates section entirely when there are no gates", () => {
    render(<DecisionTransparencyPanel decision={buildDecision({ gates: [] })} />);
    expect(screen.queryByText(/بوابات النشر/)).not.toBeInTheDocument();
  });

  it("renders a dash for every sub-score when all are null, without crashing", () => {
    render(
      <DecisionTransparencyPanel
        decision={buildDecision({
          sub_scores: {
            trend_score: null,
            momentum_score: null,
            volume_score: null,
            liquidity_score: null,
            volatility_score: null,
            risk_reward_score: null,
            market_context_score: null,
            data_quality_score: 0,
          },
        })}
      />
    );
    expect(screen.getByText("الاتجاه")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(7);
  });

  it("degrades sensibly for a REJECT decision with no opportunity at all", () => {
    /** 'no opportunity' is a valid, real result -- every list-backed
     * section (confirmation conditions, watch-next-session) must be
     * omitted rather than rendered empty, and the panel must not
     * crash when why_not_stronger_ar explains a hard rejection. */
    render(
      <DecisionTransparencyPanel
        decision={buildDecision({
          decision: "REJECT",
          decision_label_ar: "مرفوض",
          entry_status: "NOT_SUITABLE",
          entry_status_label_ar: "غير مناسب",
          why_not_stronger_ar: "تم الرفض بسبب فشل بوابة نشر إلزامية: عدم كفاية بيانات السيولة.",
          entry_confirmation_conditions_ar: [],
          watch_next_session_ar: [],
          invalidation_conditions: [],
        })}
      />
    );
    expect(
      screen.getByText("تم الرفض بسبب فشل بوابة نشر إلزامية: عدم كفاية بيانات السيولة.")
    ).toBeInTheDocument();
    expect(screen.queryByText("شروط تأكيد الدخول")).not.toBeInTheDocument();
    expect(screen.queryByText("ما يجب مراقبته في الجلسة القادمة")).not.toBeInTheDocument();
  });
});
