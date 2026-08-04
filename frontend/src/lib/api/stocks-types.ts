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
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
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
export interface TechnicalAnalysis {
  symbol: string;
  timeframe: string;
  bars_used: number;
  as_of: string;
  indicators: Record<string, unknown>;
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

export interface GateOutcome {
  name: string;
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
