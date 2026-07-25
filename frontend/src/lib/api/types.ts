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

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    [key: string]: unknown;
  };
}
