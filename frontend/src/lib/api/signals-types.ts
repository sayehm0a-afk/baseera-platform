/** Matches src/api/schemas/signals.py exactly -- a user's "متابعة هذه
 * الإشارة" (follow this signal) commitments and the honest personal-
 * vs-algorithm win-rate comparison (product decision 2026-09-18). */

export interface FollowedSignal {
  id: number;
  decision_v2_snapshot_id: number;
  symbol: string;
  company_name_ar: string | null;
  followed_at: string;

  decision: string;
  decision_label_ar: string;
  entry_zone_low: number | null;
  entry_zone_high: number | null;
  stop_loss: number | null;
  target_1: number | null;
  target_2: number | null;
  target_3: number | null;

  // Real, already-tracked outcome for this exact snapshot -- null
  // only when no DecisionV2Outcome row exists yet.
  outcome_status: string | null;
  outcome_status_label_ar: string | null;
  outcome_return_pct: number | null;
}

export interface FollowedSignalList {
  generated_at: string;
  items: FollowedSignal[];
}

export interface PersonalPerformanceComparison {
  generated_at: string;

  personal_resolved_sample_size: number;
  personal_win_rate_pct: number | null;
  personal_small_sample_warning: boolean;

  algorithm_resolved_sample_size: number;
  algorithm_win_rate_pct: number | null;

  insufficient_data_message_ar: string | null;
}
