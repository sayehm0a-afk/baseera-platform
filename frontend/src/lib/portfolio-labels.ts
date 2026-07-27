/** Arabic labels for the literal enum values
 * `src.portfolio_intelligence.types` defines -- kept in lockstep with
 * those values, not renamed or re-derived. */

export const POSITION_ACTION_LABELS: Record<string, string> = {
  INCREASE: "زيادة",
  REDUCE: "تخفيض",
  EXIT: "خروج",
  HOLD: "احتفاظ",
  NEW_BUY: "شراء جديد",
};

export const HEALTH_BAND_LABELS: Record<string, string> = {
  EXCELLENT: "ممتازة",
  GOOD: "جيدة",
  FAIR: "متوسطة",
  POOR: "ضعيفة",
  CRITICAL: "حرجة",
};

export function healthBandColorClass(band: string): string {
  if (band === "EXCELLENT" || band === "GOOD") return "text-bsr-market-up";
  if (band === "FAIR") return "text-bsr-action-watch";
  return "text-bsr-market-down";
}

export const RISK_LEVEL_LABELS: Record<string, string> = {
  LOW: "منخفضة",
  MEDIUM: "متوسطة",
  HIGH: "مرتفعة",
  VERY_HIGH: "مرتفعة جداً",
};
