/** Mirrors src/api/schemas/stocks.py. */

export interface Stock {
  symbol: string;
  name_en: string;
  name_ar: string | null;
  sector: string | null;
  currency: string;
  is_active: boolean;
}

export interface Quote {
  symbol: string;
  // null when the only source available is a real-time price tick
  // and SAHMK has not yet finalized a daily OHLCV bar for the current
  // session -- see get_quote()'s docstring in routes/stocks.py.
  // `close` always carries a real price when this route succeeds at
  // all, live when available, otherwise the most recent settled
  // bar's close.
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
  timestamp: string;
  source: string;
  is_synthetic: boolean;
}

export interface HistoricalBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface History {
  symbol: string;
  timeframe: string;
  bars: HistoricalBar[];
}

/** `indicators`/`ratios` are typed loosely on purpose -- they mirror
 * src/api/schemas/stocks.py's `Dict[str, Any]`, since the indicator/
 * ratio registries (src/analysis/registry.py,
 * src/analysis/fundamental/registry.py) can grow without a schema
 * change on either side. Consumers must read defensively (typeof
 * checks), never assume a key exists. */
export interface MovingAveragePoint {
  timestamp: string;
  value: number;
}

export interface TechnicalAnalysis {
  symbol: string;
  timeframe: string;
  bars_used: number;
  as_of: string;
  indicators: Record<string, unknown>;
  /** Phase 2F: the real per-bar series behind sma_20/ema_20/vwap_20 --
   * `indicators` above only carries each one's single latest() value. */
  moving_averages: Record<string, MovingAveragePoint[]>;
}

export interface FundamentalAnalysis {
  symbol: string;
  period_type: string;
  fiscal_period_end: string | null;
  ratios: Record<string, unknown>;
  source: string;
  is_synthetic: boolean;
}

export interface Signal {
  name: string;
  description: string;
  direction: string;
  source: string;
  impact: number;
}

export interface ScoreContribution {
  source: string;
  score: number | null;
  weight: number;
  confidence: number;
  notes: string | null;
}

export interface Recommendation {
  symbol: string;
  recommendation: string;
  confidence: number;
  explanation: string;
  technical_score: number | null;
  fundamental_score: number | null;
  final_score: number;
  contributions: ScoreContribution[];
  signals: Signal[];
  generated_at: string;
}

export interface DecisionFactorBreakdown {
  category: string;
  points: number;
  weight: number;
  confidence: number;
  available: boolean;
  notes: string | null;
}

export interface InvestmentDecision {
  symbol: string;
  recommendation: string;
  confidence: number;
  final_score: number;
  target_price: number | null;
  stop_loss: number | null;
  time_horizon: string;
  expected_return_pct: number | null;
  risk_level: string;
  position_size: string;
  reasons: string[];
  breakdown: DecisionFactorBreakdown[];
  signals: Signal[];
  generated_at: string;
  entry_quality: string;
  entry_quality_notes: string[];
  risk_reward_ratio: number | null;
  stop_loss_basis: string;
  target_price_basis: string;
  confidence_calibration_notes: string[];
}

/** Mirrors src/analysis/decision_v2/types.py's `Decision` enum
 * exactly -- the Arabic-labeled action taxonomy, distinct from the
 * legacy `InvestmentDecision.recommendation` (STRONG_BUY/BUY/HOLD/
 * SELL/STRONG_SELL) band above. */
export type DecisionV2Value =
  | "STRONG_BUY_CANDIDATE"
  | "BUY_CANDIDATE"
  | "WAIT_FOR_ENTRY"
  | "WATCH"
  | "HOLD"
  | "REDUCE"
  | "EXIT"
  | "REJECT"
  | "INSUFFICIENT_DATA";

export interface SubScoresV2 {
  trend_score: number | null;
  momentum_score: number | null;
  volume_score: number | null;
  liquidity_score: number | null;
  volatility_score: number | null;
  risk_reward_score: number | null;
  market_context_score: number | null;
  data_quality_score: number;
}

export type GateStatus = "PASS" | "FAIL" | "NOT_EVALUATED";

export interface GateOutcome {
  name: string;
  status: GateStatus;
  passed: boolean;
  detail: string;
  blocking: boolean;
}

/** Mirrors DecisionV2Out (src/api/schemas/stocks.py) --
 * GET /api/v1/stocks/{symbol}/decision-v2. */
export interface DecisionV2 {
  symbol: string;
  company_name_ar: string | null;
  company_name_en: string;
  sector_ar: string | null;

  decision: DecisionV2Value;
  decision_label_ar: string;

  confidence_score: number;
  confidence_disclaimer_ar: string;
  opportunity_quality_score: number;
  risk_score: number;
  data_quality_score: number;
  data_freshness_status: "LIVE" | "LAST_SESSION" | "STALE" | "UNKNOWN";

  current_price: number | null;
  entry_zone_low: number | null;
  entry_zone_high: number | null;
  stop_loss: number | null;
  target_1: number | null;
  target_2: number | null;
  target_3: number | null;

  expected_return_target_1: number | null;
  expected_return_target_2: number | null;
  downside_to_stop: number | null;
  risk_reward_target_1: number | null;
  risk_reward_target_2: number | null;

  expected_holding_period_min_days: number | null;
  expected_holding_period_max_days: number | null;
  expected_holding_period_label_ar: string;
  horizon_type: string;

  market_status: string;
  decision_timestamp: string;

  invalidation_conditions: string[];
  positive_reasons: string[];
  negative_reasons: string[];
  warnings: string[];
  recommendation_basis: string;
  analysis_disclaimer_ar: string;

  analysis_version: string;
  data_source: string;
  scan_run_id: number | null;

  sub_scores: SubScoresV2;
  gates: GateOutcome[];

  /** Phase 2A canonical extensions -- see DecisionResult's own
   * docstring (src/analysis/decision_v2/types.py) for how each field
   * is derived. */
  is_real_data: boolean;
  quote_timestamp: string | null;

  technical_confidence: number | null;
  momentum_confidence: number | null;
  liquidity_confidence: number | null;
  market_context_confidence: number | null;
  data_quality_confidence: number | null;

  trade_type:
    | "SCALP"
    | "INTRADAY"
    | "SHORT_SWING_2_5_DAYS"
    | "WEEKLY_SWING"
    | "SWING_TRADE"
    | "MONTHLY_INVESTMENT"
    | "MEDIUM_TERM_INVESTMENT"
    | "LONG_TERM_INVESTMENT"
    | null;
  trade_type_label_ar: string;
  time_horizon_rationale_ar: string;

  best_entry_price: number | null;
  accumulation_zone_low: number | null;
  accumulation_zone_high: number | null;
  entry_quality: "POOR" | "FAIR" | "GOOD" | "EXCELLENT";
  entry_quality_label_ar: string;
  entry_status:
    | "READY_NOW"
    | "NEAR_ENTRY"
    | "WAIT_FOR_PULLBACK"
    | "MISSED_ENTRY"
    | "CONDITIONAL_ON_BREAKOUT"
    | "NOT_SUITABLE";
  entry_status_label_ar: string;

  invalidation_price: number | null;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "VERY_HIGH";
  risk_level_label_ar: string;

  estimated_days_target_1: number | null;
  estimated_days_target_2: number | null;
  estimated_days_target_3: number | null;

  nearest_support: number | null;
  major_support: number | null;
  nearest_resistance: number | null;
  major_resistance: number | null;
  breakout_level: number | null;
  breakdown_level: number | null;
  support_resistance_evidence_ar: string;

  current_volume: number | null;
  average_volume: number | null;
  relative_volume: number | null;
  liquidity_quality_ar: string;
  accumulation_score: number | null;
  accumulation_assessment_ar: string;
  volume_confirms_decision: boolean | null;
  abnormal_volume: boolean;

  /** Every registered technical indicator's latest value, keyed by
   * name -- the same loosely-typed shape TechnicalAnalysisOut.indicators
   * already uses; consumers must read defensively. */
  technical_evidence: Record<string, unknown>;
  trend_direction_ar: string;
  trend_strength_label_ar: string;

  decision_summary_ar: string;
  why_now_ar: string;
  why_not_stronger_ar: string;
  /** Distinct from why_not_stronger_ar: a general "why isn't this a
   * buy at all" list, empty for STRONG_BUY_CANDIDATE/BUY_CANDIDATE. */
  why_not_buy_reasons: string[];
  entry_confirmation_conditions_ar: string[];
  watch_next_session_ar: string[];

  /** Phase 2C: Market Risk and Exit Warning Engine -- a market-wide
   * (not per-symbol) risk read, distinct from `market_status` above. */
  market_risk_state: string;
  market_risk_label_ar: string;
  market_risk_basis_ar: string;
  market_risk_entry_permitted: boolean;
  market_risk_is_live: boolean;
  market_breadth_buy_count: number | null;
  market_breadth_sell_count: number | null;
  market_breadth_symbols_scanned: number | null;
  market_breadth_average_confidence: number | null;

  /** Section 12: real M2.3 fundamental ratios (revenue/profit growth,
   * margins, ROE, debt-to-equity, valuation multiples, dividend
   * yield) -- values are null when a ratio could not be computed from
   * real reported financials, never fabricated. */
  fundamental_summary: Record<string, number | null>;
  fundamental_summary_ar: string;
}

export interface StockSearchResult {
  symbol: string;
  name_en: string;
  name_ar: string | null;
  sector: string | null;
}

export interface StockSearch {
  query: string;
  results: StockSearchResult[];
}

export interface AnalystReport {
  symbol: string;
  recommendation: string;
  confidence: number;
  final_score: number;
  target_price: number | null;
  stop_loss: number | null;
  time_horizon: string;
  expected_return_pct: number | null;
  risk_level: string;
  position_size: string;
  investment_summary: string;
  technical_reasoning: string;
  fundamental_reasoning: string;
  risk_explanation: string;
  bullish_factors: string[];
  bearish_factors: string[];
  confidence_explanation: string;
  target_price_explanation: string;
  stop_loss_explanation: string;
  time_horizon_explanation: string;
  alternative_scenarios: string[];
  final_recommendation_rationale: string;
  generated_at: string;
  engine_version: string;
  entry_quality: string;
  entry_quality_notes: string[];
  risk_reward_ratio: number | null;
  stop_loss_basis: string;
  target_price_basis: string;
  confidence_calibration_notes: string[];
}
