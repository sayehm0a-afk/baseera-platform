import type { AgentStanceValue } from "@/lib/api/stocks-types";

/** Arabic labels for the committee's role/stance vocabulary --
 * backend supplies the machine-readable identifier, frontend never
 * re-translates data, only labels its own fixed vocabulary (same
 * "backend supplies label_ar" rule DECISION_LABELS_AR already
 * follows). */
export const AGENT_ROLE_LABELS_AR: Record<string, string> = {
  technical: "التحليل الفني",
  fundamental: "التحليل الأساسي",
  news: "الأخبار",
  market_sentiment: "معنويات السوق",
  risk: "إدارة المخاطر",
  liquidity_volume: "السيولة والحجم",
  macro: "الاقتصاد الكلي",
  portfolio_allocation: "تخصيص المحفظة",
};

export const AGENT_STANCE_LABELS_AR: Record<AgentStanceValue, string> = {
  BULLISH: "متفائل",
  BEARISH: "متشائم",
  NEUTRAL: "محايد",
  UNAVAILABLE: "غير متوفر",
};

export const FINAL_DECISION_LABELS_AR: Record<string, string> = {
  BUY: "شراء",
  SELL: "بيع",
  HOLD: "احتفاظ",
};

export function stanceColorClass(stance: AgentStanceValue): string {
  switch (stance) {
    case "BULLISH":
      return "text-bsr-action-buy";
    case "BEARISH":
      return "text-bsr-action-sell";
    case "NEUTRAL":
      return "text-bsr-action-watch";
    default:
      return "text-bsr-text-tertiary";
  }
}
