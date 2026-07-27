/** Arabic labels for the literal enum values
 * `src.domain.models.news_event.NewsCategory` / `SentimentLabel` and
 * `src.domain.models.portfolio_news_alert.PortfolioAlertType` define
 * (Phase 12) -- kept in lockstep with those values, not renamed or
 * re-derived. */

export const NEWS_CATEGORY_LABELS: Record<string, string> = {
  EARNINGS: "أرباح",
  DIVIDEND: "توزيعات أرباح",
  CONTRACT_AWARD: "ترسية عقد",
  EXPANSION: "توسع",
  ACQUISITION: "استحواذ",
  LAWSUIT: "قضية قانونية",
  REGULATORY_CHANGE: "تغيير تنظيمي",
  GOVERNMENT_POLICY: "سياسة حكومية",
  OIL: "النفط",
  INTEREST_RATES: "أسعار الفائدة",
  INFLATION: "التضخم",
  CURRENCY: "العملة",
  SUPPLY_CHAIN: "سلسلة الإمداد",
  PRODUCTION: "الإنتاج",
  GUIDANCE: "توجيهات الشركة",
  CREDIT_RATING: "التصنيف الائتماني",
  EXECUTIVE_CHANGE: "تغيير تنفيذي",
  BANKRUPTCY: "إفلاس",
  TRADING_SUSPENSION: "إيقاف تداول",
  OTHER: "أخرى",
};

export const SENTIMENT_LABEL_LABELS: Record<string, string> = {
  VERY_POSITIVE: "إيجابي جداً",
  POSITIVE: "إيجابي",
  NEUTRAL: "محايد",
  NEGATIVE: "سلبي",
  VERY_NEGATIVE: "سلبي جداً",
};

export function sentimentColorClass(label: string | null): string {
  if (label === "VERY_POSITIVE" || label === "POSITIVE") return "text-bsr-market-up";
  if (label === "VERY_NEGATIVE" || label === "NEGATIVE") return "text-bsr-market-down";
  if (label === "NEUTRAL") return "text-bsr-action-hold";
  return "text-bsr-text-muted";
}

export const PORTFOLIO_ALERT_TYPE_LABELS: Record<string, string> = {
  UPGRADE: "ترقية",
  DOWNGRADE: "تخفيض",
  HIGH_RISK: "مخاطرة عالية",
  MAJOR_OPPORTUNITY: "فرصة كبرى",
};

export function alertSeverityColorClass(severity: string): string {
  if (severity === "CRITICAL") return "bg-bsr-action-sell/15 text-bsr-action-sell";
  if (severity === "WARNING") return "bg-bsr-action-watch/15 text-bsr-action-watch";
  return "bg-bsr-action-hold/15 text-bsr-action-hold";
}
