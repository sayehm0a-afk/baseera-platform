import type { DecisionV2Value } from "./stocks-types";

/** Matches src/api/schemas/market_intelligence.py's
 * RadarOpportunitySummaryOut exactly -- one row in the ranked Smart
 * Radar list, only the currently-live (non-superseded) opportunity per
 * symbol. `classification` is the same Decision V2 taxonomy as
 * stocks-types.ts's `DecisionV2Value` -- reuse DecisionBadge, never a
 * new color/label mapping. */
export interface RadarOpportunitySummary {
  id: number;
  symbol: string;
  company_name_ar: string | null;
  company_name_en: string;

  classification: DecisionV2Value;
  classification_label_ar: string;
  confidence_score: number;
  confidence_disclaimer_ar: string;

  // Phase 5: the platform's single unified 0-100 opportunity-quality
  // composite, distinct from confidence_score (evidence strength).
  basirah_score: number | null;

  price_at_signal: number | null;
  entry_zone_low: number | null;
  entry_zone_high: number | null;
  stop_loss: number | null;
  target_1: number | null;
  target_2: number | null;
  target_3: number | null;
  expected_return_target_1: number | null;
  risk_reward_target_1: number | null;

  risk_level: string | null;
  risk_level_label_ar: string | null;
  data_freshness_status: "LIVE" | "LAST_SESSION" | "STALE" | "UNKNOWN";

  stage1_rank: number | null;
  stage1_ranking_score: number | null;
  ranking_reason_ar: string | null;

  emitted_at: string;
  decision_v2_snapshot_id: number;
}

export interface RadarStage1ComponentScores {
  trend: number | null;
  momentum: number | null;
  volume: number | null;
  liquidity: number | null;
  volatility: number | null;
  risk_reward: number | null;
}

export interface RadarStage1Signal {
  name: string;
  detail_ar: string;
}

/** Matches RadarOpportunityDetailOut -- extends the summary with
 * Stage 1's full evidence breakdown and the linked decision's
 * reasoning/risk flags. */
export interface RadarOpportunityDetail extends RadarOpportunitySummary {
  stage1_component_scores: RadarStage1ComponentScores;
  stage1_signals: RadarStage1Signal[];
  stage1_risk_reward_ratio: number | null;

  expected_holding_period_min_days: number | null;
  expected_holding_period_max_days: number | null;
  expected_holding_period_label_ar: string | null;

  positive_reasons: string[];
  negative_reasons: string[];
  warnings: string[];
  recommendation_basis: string | null;

  liquidity_quality_ar: string | null;
  relative_volume: number | null;
  accumulation_assessment_ar: string | null;

  // Phase 4 (Advanced Technical Engine exposure): already computed by
  // Decision Engine V2 for every Stage 2 candidate, just not previously
  // surfaced through the Radar API. No "intraday" fields (VWAP/opening
  // range/HOD-LOD) exist -- the platform has no intraday OHLCV data.
  trend_direction_ar: string | null;
  trend_strength_label_ar: string | null;
  nearest_support: number | null;
  major_support: number | null;
  nearest_resistance: number | null;
  major_resistance: number | null;
  breakout_level: number | null;
  breakdown_level: number | null;
  support_resistance_evidence_ar: string | null;
  current_volume: number | null;
  average_volume: number | null;
  accumulation_score: number | null;
  entry_quality_label_ar: string | null;
  entry_status_label_ar: string | null;
  why_now_ar: string | null;
  why_not_stronger_ar: string | null;
  why_not_buy_reasons: string[];

  // Phase 5: per-opportunity market-risk read, sector, and any
  // conditions that would invalidate this decision.
  market_risk_state: string | null;
  market_risk_label_ar: string | null;
  sector_ar: string | null;
  invalidation_conditions: string[];

  decision_timestamp: string;
  market_status: string;

  outcome_status: string | null;
  outcome_return_pct: number | null;
  outcome_evaluated_at: string | null;
}

/** Matches RadarHomeSummaryOut (src/api/schemas/radar.py) -- the
 * single-call Smart Radar home payload. */
export interface RadarHomeSummary {
  generated_at: string;

  live_opportunity_count: number;
  live_by_classification: Record<string, number>;
  average_confidence: number | null;
  most_recent_emitted_at: string | null;

  market_status: string;
  market_status_label_ar: string;

  market_risk_state: string;
  market_risk_label_ar: string;
  market_risk_basis_ar: string;
  entry_permitted: boolean;
  market_risk_is_live: boolean;

  top_opportunities: RadarOpportunitySummary[];

  // Radar V2's real, dynamic scan funnel from the most recent completed
  // cycle: full local universe -> analyzable (had enough price history)
  // -> Stage 1 candidates -> Stage 2 live-validated -> final opportunities
  // emitted. Null only when no Radar V2 cycle has completed yet -- never
  // fabricated as 0.
  stage1_universe_size: number | null;
  stage1_evaluated_count: number | null;
  stage1_candidate_count: number | null;
  stage2_candidate_cap: number;
  stage2_validated_count: number | null;
  final_opportunities_count: number | null;
  last_full_scan_at: string | null;
}
