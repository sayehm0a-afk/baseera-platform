/** Arabic labels for the 17 ranking categories and 9 watchlist
 * categories `src.market_intelligence.types.RankingCategory` /
 * `WatchlistCategory` define (Phase 7) -- kept in lockstep with those
 * literal enum values, not re-derived or renamed. */

export const RANKING_CATEGORY_LABELS: Record<string, string> = {
  TOP_BUY: "الأعلى شراءً",
  TOP_STRONG_BUY: "شراء قوي",
  TOP_LONG_TERM_INVESTMENT: "استثمار طويل الأجل",
  TOP_SWING_TRADE: "مضاربة قصيرة",
  TOP_DIVIDEND_STOCKS: "أسهم توزيعات",
  HIGHEST_CONFIDENCE: "الأعلى ثقة",
  HIGHEST_EXPECTED_RETURN: "الأعلى عائدًا متوقعًا",
  LOWEST_RISK: "الأقل مخاطرة",
  HIGHEST_RISK: "الأعلى مخاطرة",
  MOST_BULLISH: "الأكثر إيجابية",
  MOST_BEARISH: "الأكثر سلبية",
  MOST_IMPROVED_TODAY: "الأكثر تحسنًا اليوم",
  MOST_DETERIORATED_TODAY: "الأكثر تراجعًا اليوم",
  NEW_OPPORTUNITIES: "فرص جديدة",
  REMOVED_OPPORTUNITIES: "فرص أُزيلت",
  RECENTLY_UPGRADED: "تمت ترقيتها مؤخرًا",
  RECENTLY_DOWNGRADED: "تم تخفيضها مؤخرًا",
};

export const RANKING_CATEGORY_ORDER = Object.keys(RANKING_CATEGORY_LABELS);

export const WATCHLIST_CATEGORY_LABELS: Record<string, string> = {
  MOMENTUM: "الزخم",
  INVESTMENT: "الاستثمار",
  SWING: "المضاربة",
  HIGH_RISK: "مرتفعة المخاطر",
  DIVIDEND: "التوزيعات",
  RECOVERY: "التعافي",
  BREAKOUT_CANDIDATES: "مرشحة للاختراق",
  OVERSOLD_OPPORTUNITIES: "فرص تشبع بيعي",
  OVERBOUGHT_WARNINGS: "تحذيرات تشبع شرائي",
};

export const WATCHLIST_CATEGORY_ORDER = Object.keys(WATCHLIST_CATEGORY_LABELS);

/** Covers both `src.domain.models.market_scan_run.MarketScanStatus`
 * and `src.domain.models.backtest_run.BacktestRunStatus` -- identical
 * PENDING/RUNNING/SUCCESS/FAILED values (backtests additionally allow
 * CANCELLED). A run's raw status must never render in English on any
 * user-facing screen (Phase 1 Arabic UX requirement). */
export const RUN_STATUS_LABELS: Record<string, string> = {
  PENDING: "بانتظار البدء",
  RUNNING: "قيد التنفيذ",
  SUCCESS: "مكتمل",
  FAILED: "فشل",
  CANCELLED: "أُلغي",
};

/** Mirrors `src.domain.models.market_alert.AlertSeverity`. */
export const ALERT_SEVERITY_LABELS: Record<string, string> = {
  INFO: "معلومة",
  WARNING: "تنبيه",
  CRITICAL: "حرج",
};

/** `MarketScanProgress.status` (src/market_intelligence/scan_progress.py
 * -- a plain string, not a formal enum, set to "RUNNING"/"COMPLETED"/
 * "FAILED" by ScanProgressTracker/scan_job_runner.py). Distinct from
 * `MARKET_SCAN_STATUS_LABELS` above, which covers the separate
 * MarketScanRun.status enum (PENDING/RUNNING/SUCCESS/FAILED). */
export const SCAN_PROGRESS_STATUS_LABELS: Record<string, string> = {
  RUNNING: "قيد التنفيذ",
  COMPLETED: "مكتمل",
  FAILED: "فشل",
};
