/** Mirrors src/api/schemas/backtesting.py. */

export interface BacktestCreateRequestBody {
  symbols: string[];
  start_date: string;
  end_date: string;
  data_provenance_mode?: "SYNTHETIC" | "LIVE";
  strategy?: string;
  evaluation_frequency_days?: number;
  holding_horizon_days?: number;
  target_price_horizon_days?: number;
}

export interface BacktestRun {
  id: number;
  idempotency_key: string;
  status: string;
  symbols: string[];
  strategy: string;
  data_provenance_mode: string;
  start_date: string;
  end_date: string;
  evaluation_frequency_days: number;
  holding_horizon_days: number;
  target_price_horizon_days: number;
  transaction_cost_bps: number;
  slippage_bps: number;
  confidence_threshold: number | null;
  recommendation_threshold: string | null;
  fundamental_reporting_lag_days: number;
  calibration_version: string | null;
  progress_current: number;
  progress_total: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  created_at: string;
}

export interface BacktestMetrics {
  id: number;
  status: string;
  data_provenance_mode: string;
  symbols: string[];
  metrics: Record<string, unknown> | null;
}

/** The literal strategy identifiers `src.backtesting.baselines.
 * DEFAULT_STRATEGIES` registers -- kept in lockstep with that dict's
 * keys rather than re-derived, since POST /api/v1/backtests rejects
 * anything else with `invalid_backtest_config`. */
export const STRATEGY_OPTIONS: { value: string; labelAr: string }[] = [
  { value: "ai_decision_engine", labelAr: "محرك القرار الذكي (معاير)" },
  { value: "uncalibrated_ai_decision_engine", labelAr: "محرك القرار الذكي (غير معاير)" },
  { value: "buy_and_hold", labelAr: "الشراء والاحتفاظ" },
  { value: "sma_crossover", labelAr: "تقاطع المتوسطات المتحركة" },
  { value: "rsi_only", labelAr: "مؤشر القوة النسبية فقط" },
  { value: "technical_only", labelAr: "التحليل الفني فقط" },
  { value: "fundamental_only", labelAr: "التحليل الأساسي فقط" },
];
