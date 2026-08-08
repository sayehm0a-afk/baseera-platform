/** Matches src/api/schemas/recommendation_history.py exactly -- the
 * platform's real, append-only recommendation track record
 * (RecommendationSnapshot/RecommendationOutcome). Every field here is a
 * direct read of that data, never a recomputation. */

export interface RecommendationOutcome {
  evaluation_horizon_days: number;
  status: string;
  due_at: string;
  evaluated_at: string | null;
  price_at_evaluation: number | null;
  return_pct: number | null;
  hit_target: boolean | null;
  hit_stop: boolean | null;
  target_1_reached: boolean | null;
  target_1_reached_at: string | null;
  target_2_reached: boolean | null;
  target_2_reached_at: string | null;
  target_3_reached: boolean | null;
  target_3_reached_at: string | null;
  max_favorable_excursion_pct: number | null;
  max_adverse_excursion_pct: number | null;
  time_to_target_days: number | null;
}

export interface RecommendationHistoryItem {
  id: number;
  symbol: string;
  company_name_ar: string | null;
  sector: string | null;

  evaluated_at: string;
  recommendation: string;
  confidence_score: number;
  calibrated_confidence_score: number | null;

  market_price_at_evaluation: number | null;
  target_price: number | null;
  target_price_2: number | null;
  target_price_3: number | null;
  stop_loss: number | null;
  expected_return_pct: number | null;
  time_horizon: string | null;
  risk_level: string | null;
  position_size: string | null;
  expires_at: string | null;

  reasons: string[];
  engine_version: string;
  is_paper_trade: boolean | null;

  overall_status: "ACTIVE" | "COMPLETED" | "EXPIRED" | "NO_OUTCOMES_TRACKED";
  outcomes: RecommendationOutcome[];
}

export interface RecommendationHistoryList {
  generated_at: string;
  total: number;
  items: RecommendationHistoryItem[];
}

export interface RecommendationHistoryAuditItem extends RecommendationHistoryItem {
  contributor_breakdown: unknown[] | null;
  signals: unknown[] | null;
  total_score: number | null;
  calibration_version: string | null;
  run_id: number | null;
  source: string | null;
}

export interface RecommendationHistoryAuditList {
  generated_at: string;
  total: number;
  items: RecommendationHistoryAuditItem[];
}

export interface RecommendationHistoryStats {
  generated_at: string;
  evaluation_horizon_days: number;
  sample_size: number;
  terminal_sample_size: number;
  win_rate: number | null;
  average_return_pct: number | null;
  target_hit_rate: number | null;
  stop_hit_rate: number | null;
  status_counts: Record<string, number>;
  small_sample_warning: boolean;
}
