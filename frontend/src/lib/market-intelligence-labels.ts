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
