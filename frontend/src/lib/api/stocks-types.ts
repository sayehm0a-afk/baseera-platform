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
