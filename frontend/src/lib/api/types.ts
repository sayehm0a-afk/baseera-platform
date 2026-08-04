/**
 * Mirrors src/api/schemas/market_intelligence.py exactly -- field names
 * and optionality kept in lockstep with the Pydantic models so this file
 * is the single place a backend schema change surfaces as a type error.
 */

export interface ChangeEvent {
  symbol: string;
  change_type: string;
  previous_value: string | null;
  new_value: string | null;
  delta: number | null;
  detected_at: string;
}

export interface MarketSummary {
  scan_run_id: number | null;
  generated_at: string;
  symbols_scanned: number;
  bull_bear_ratio: number | null;
  average_confidence: number | null;
  average_recommendation_score: number | null;
  buy_signal_count: number;
  sell_signal_count: number;
  strongest_sectors: string[];
  weakest_sectors: string[];
  most_important_changes: ChangeEvent[];
}

export interface SectorSummary {
  sector: string;
  symbol_count: number;
  average_confidence: number | null;
  average_final_score: number | null;
  average_expected_return_pct: number | null;
  average_technical_score: number | null;
  average_fundamental_score: number | null;
  buy_count: number;
  sell_count: number;
  hold_count: number;
  breadth: number;
  momentum: number | null;
}

export interface SectorsResponse {
  scan_run_id: number | null;
  sectors: SectorSummary[];
}

export interface Alert {
  alert_type: string;
  severity: string;
  symbol: string | null;
  sector: string | null;
  message: string;
  generated_at: string;
}

export interface AlertsResponse {
  total: number;
  limit: number;
  offset: number;
  alerts: Alert[];
}

export interface RankingEntry {
  symbol: string;
  sector: string | null;
  recommendation: string | null;
  confidence: number | null;
  final_score: number | null;
  target_price: number | null;
  expected_return_pct: number | null;
  risk_level: string | null;
  rank_value: number | null;
  current_price: number | null;
  stop_loss: number | null;
  risk_reward_ratio: number | null;
  time_horizon: string | null;
}

export interface RankingList {
  category: string;
  entries: RankingEntry[];
  generated_at: string;
}

export interface RankingsResponse {
  scan_run_id: number | null;
  rankings: RankingList[];
}

export interface WatchlistEntry {
  symbol: string;
  sector: string | null;
  recommendation: string | null;
  confidence: number | null;
  reason: string;
}

export interface WatchlistResult {
  category: string;
  entries: WatchlistEntry[];
  generated_at: string;
}

export interface WatchlistsResponse {
  scan_run_id: number | null;
  watchlists: WatchlistResult[];
}

export interface MarketScanRun {
  id: number;
  status: string;
  symbols_requested: number;
  symbols_succeeded: number;
  symbols_skipped: number;
  symbols_failed: number;
  error_summary: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  created_at: string;
}

/** Live per-symbol progress for one scan run, from
 * GET /api/v1/market/scan/{runId}/progress -- distinct from
 * MarketScanRun above, which only updates once, at the very end. */
export interface MarketScanProgress {
  run_id: number;
  status: string;
  eligible_discovered: number;
  completed_count: number;
  remaining_count: number;
  progress_pct: number;
  success_count: number;
  failed_count: number;
  skipped_count: number;
  insufficient_data_count: number;
  published_count: number;
  rejected_count: number;
  watch_only_count: number;
  not_evaluated_count: number;
  current_symbol: string | null;
  current_symbol_name_en: string | null;
  current_symbol_name_ar: string | null;
  last_completed_symbol: string | null;
  api_calls_total: number;
  retries_total: number;
  latest_error: string | null;
  latest_warning: string | null;
  started_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
}

export interface MarketDataHealth {
  configured_provider: string;
  strict_real_data: boolean;
  synthetic_allowed: boolean;
  sahmk_key_present: boolean;
  current_provider_kind: string | null;
  last_connectivity_status: string | null;
  last_connectivity_at: string | null;
  last_real_data_at: string | null;
  last_scan_source: string | null;
  can_publish_recommendations: boolean;
}

/** Mirrors MarketStatusOut (src/api/schemas/market_intelligence.py).
 * `status` is one of OPEN/PRE_OPEN_AUCTION/CLOSING_AUCTION/CLOSED/
 * PROVIDER_UNREACHABLE. */
export interface MarketStatus {
  status: string;
  label_ar: string;
  is_trading_day: boolean;
  server_time_riyadh: string;
  seconds_until_next_open: number;
  seconds_until_close: number | null;
  last_completed_session_date: string | null;
  provider_connected: boolean;
  holiday_calendar_disclosed_gap: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    [key: string]: unknown;
  };
}
