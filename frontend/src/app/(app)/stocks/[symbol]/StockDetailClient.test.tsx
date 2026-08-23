import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StockDetailClient } from "./StockDetailClient";
import type { DecisionV2 } from "@/lib/api/stocks-types";

/** Regression: the M7 production UX audit found that when the market
 * data provider is unavailable (e.g. SAHMK daily quota exhausted),
 * the executive decision panel silently rendered nothing at all, and
 * the legacy overview panel showed "insufficient historical data" --
 * a misleading message, since the real cause was a live-data outage,
 * not a lack of history. Both panels now render an honest, distinct
 * "provider unavailable" message instead. */

vi.mock("@/lib/api/stocks", () => ({
  getStock: vi.fn(),
  getQuote: vi.fn(),
  getHistory: vi.fn(),
  getTechnicalAnalysis: vi.fn(),
  getDecision: vi.fn(),
  getDecisionV2: vi.fn(),
  getFundamentalAnalysis: vi.fn(),
  getAnalystReport: vi.fn(),
}));

vi.mock("@/lib/api/radar", () => ({
  getRadarOpportunityBySymbol: vi.fn(),
}));

import { ApiError } from "@/lib/api/client";
import { getRadarOpportunityBySymbol } from "@/lib/api/radar";
import {
  getAnalystReport,
  getDecision,
  getDecisionV2,
  getFundamentalAnalysis,
  getHistory,
  getQuote,
  getStock,
  getTechnicalAnalysis,
} from "@/lib/api/stocks";

function providerUnavailable() {
  return Promise.reject(new ApiError(503, "provider_unavailable", "provider down"));
}

function insufficientData() {
  return Promise.reject(new ApiError(422, "insufficient_data", "not enough data"));
}

function buildDecisionV2(overrides: Partial<DecisionV2> = {}): DecisionV2 {
  return {
    symbol: "2222",
    company_name_ar: "أرامكو السعودية",
    company_name_en: "Saudi Aramco",
    sector_ar: "الطاقة",
    decision: "BUY_CANDIDATE",
    decision_label_ar: "مرشح للشراء",
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
    decision_freshness_status: "LIVE",
    is_decision_fresh: true,
    invalidation_conditions: [],
    positive_reasons: ["اتجاه صاعد مؤكد بحجم تداول قوي"],
    negative_reasons: [],
    warnings: [],
    recommendation_basis: "بناءً على تقاطع إيجابي للمتوسطات المتحركة.",
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
    time_horizon_rationale_ar: "زخم واضح -- الأنسب متابعة الفرصة على مدى أسبوع تداول تقريبًا.",
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
    accumulation_assessment_ar: "إشارات تجميع محتملة.",
    volume_confirms_decision: true,
    abnormal_volume: false,
    technical_evidence: { rsi_14: 58.2 },
    trend_direction_ar: "صاعد",
    trend_strength_label_ar: "معتدل",
    decision_summary_ar: "شراء -- بثقة 66٪.",
    why_now_ar: "اتجاه صاعد مدعوم بحجم تداول قوي.",
    why_not_stronger_ar: "",
    why_not_buy_reasons: [],
    fundamental_summary: {},
    fundamental_summary_ar: "",
    news_impact: "NO_RELEVANT_NEWS",
    news_impact_summary_ar: "لا توجد أخبار محلَّلة حديثة ذات صلة بهذا السهم.",
    committee: null,
    entry_confirmation_conditions_ar: [],
    watch_next_session_ar: [],
    market_risk_state: "NEUTRAL",
    market_risk_label_ar: "محايد",
    market_risk_basis_ar: "نسبة الإشارات الإيجابية 50%.",
    market_risk_entry_permitted: true,
    market_risk_is_live: true,
    market_breadth_buy_count: 10,
    market_breadth_sell_count: 10,
    market_breadth_symbols_scanned: 40,
    market_breadth_average_confidence: 62,
    ...overrides,
  };
}

describe("StockDetailClient", () => {
  it("shows an honest 'provider unavailable' message on both the executive decision panel and the legacy overview panel, instead of blank content or a misleading 'insufficient data' message", async () => {
    vi.mocked(getStock).mockResolvedValue({
      symbol: "6004",
      name_en: "Catrion",
      name_ar: "كاتريون",
      sector: "Commercial & Professional Svc",
      sector_ar: "الخدمات التجارية والمهنية",
      currency: "SAR",
      is_active: true,
    });
    vi.mocked(getQuote).mockImplementation(providerUnavailable);
    vi.mocked(getDecisionV2).mockImplementation(providerUnavailable);
    vi.mocked(getDecision).mockImplementation(providerUnavailable);
    vi.mocked(getHistory).mockImplementation(providerUnavailable);
    vi.mocked(getTechnicalAnalysis).mockImplementation(providerUnavailable);
    vi.mocked(getFundamentalAnalysis).mockImplementation(providerUnavailable);
    vi.mocked(getAnalystReport).mockImplementation(providerUnavailable);
    vi.mocked(getRadarOpportunityBySymbol).mockResolvedValue(null);

    render(<StockDetailClient symbol="6004" />);

    expect(await screen.findByText("تعذّر تحميل قرار الذكاء الاصطناعي")).toBeInTheDocument();
    expect(await screen.findByText("تعذّر تحميل التوصية الآلية")).toBeInTheDocument();

    // The old, misleading "insufficient data" copy must not appear when
    // the real cause is a provider outage.
    expect(screen.queryByText("البيانات غير كافية لإصدار قرار")).not.toBeInTheDocument();
    expect(
      screen.queryByText("غالباً بسبب نقص بيانات تاريخية كافية لتشغيل محرك القرار.")
    ).not.toBeInTheDocument();

    // Both messages explain the real cause: the market data provider,
    // not the stock's own history, is unavailable.
    expect(screen.getAllByText(/مزود بيانات السوق غير متاح حالياً/).length).toBeGreaterThanOrEqual(2);
  });

  it("still shows the real 'insufficient data' message when the decision engine genuinely lacks enough data for the symbol", async () => {
    vi.mocked(getStock).mockResolvedValue({
      symbol: "9999",
      name_en: "New Listing",
      name_ar: "إدراج جديد",
      sector: null,
      sector_ar: null,
      currency: "SAR",
      is_active: true,
    });
    vi.mocked(getQuote).mockImplementation(providerUnavailable);
    vi.mocked(getDecisionV2).mockRejectedValue(new ApiError(422, "insufficient_data", "not enough data"));
    vi.mocked(getDecision).mockRejectedValue(new ApiError(422, "insufficient_data", "not enough data"));
    vi.mocked(getHistory).mockImplementation(providerUnavailable);
    vi.mocked(getTechnicalAnalysis).mockImplementation(providerUnavailable);
    vi.mocked(getFundamentalAnalysis).mockImplementation(providerUnavailable);
    vi.mocked(getAnalystReport).mockImplementation(providerUnavailable);
    vi.mocked(getRadarOpportunityBySymbol).mockResolvedValue(null);

    render(<StockDetailClient symbol="9999" />);

    expect(await screen.findByText("البيانات غير كافية لإصدار قرار")).toBeInTheDocument();
    expect(
      await screen.findByText("غالباً بسبب نقص بيانات تاريخية كافية لتشغيل محرك القرار.")
    ).toBeInTheDocument();
  });

  it("RADAR-C Phase G: renders the chart right after the executive decision and keeps the advanced transparency panel collapsed until the user expands it", async () => {
    vi.mocked(getStock).mockResolvedValue({
      symbol: "2222",
      name_en: "Saudi Aramco",
      name_ar: "أرامكو السعودية",
      sector: "Energy",
      sector_ar: "الطاقة",
      currency: "SAR",
      is_active: true,
    });
    vi.mocked(getQuote).mockImplementation(providerUnavailable);
    vi.mocked(getDecisionV2).mockResolvedValue(buildDecisionV2());
    vi.mocked(getDecision).mockImplementation(insufficientData);
    vi.mocked(getHistory).mockResolvedValue({ symbol: "2222", timeframe: "ONE_DAY", bars: [] });
    vi.mocked(getTechnicalAnalysis).mockImplementation(insufficientData);
    vi.mocked(getFundamentalAnalysis).mockImplementation(insufficientData);
    vi.mocked(getAnalystReport).mockImplementation(insufficientData);
    vi.mocked(getRadarOpportunityBySymbol).mockResolvedValue(null);

    render(<StockDetailClient symbol="2222" />);

    // The executive decision (decision/confidence/entry/targets/why)
    // renders first, and the real chart -- here an honest empty state
    // since no bars were persisted -- comes right after it.
    const decisionSummary = await screen.findByText("شراء -- بثقة 66٪.");
    const chartEmptyState = await screen.findByText("لا تتوفر بيانات تاريخية بعد لهذا السهم");
    expect(
      decisionSummary.compareDocumentPosition(chartEmptyState) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();

    // The advanced transparency panel (full gate list, sub-scores) is
    // collapsed by default -- its content is not in the document yet.
    expect(screen.queryByText("صاعد — معتدل")).not.toBeInTheDocument();
    expect(screen.getByText("التحليل الكامل والشفافية")).toBeInTheDocument();

    fireEvent.click(screen.getByText("التحليل الكامل والشفافية"));

    expect(await screen.findByText("صاعد — معتدل")).toBeInTheDocument();
  });
});
