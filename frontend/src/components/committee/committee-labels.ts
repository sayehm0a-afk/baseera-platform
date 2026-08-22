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

/** Pre-launch safety fix (2026-08-22, Priority 2): `agent_name` is a
 * fixed, hardcoded English string at each of the 8 call sites in
 * src.ai_evolution.committee.agents (e.g. "Technical Analysis Agent") --
 * unlike `role`/`stance` above it has no backend label_ar companion.
 * Same fixed-vocabulary frontend-label pattern as AGENT_ROLE_LABELS_AR;
 * an unrecognized name still renders under its raw text, never dropped. */
export const AGENT_NAME_LABELS_AR: Record<string, string> = {
  "Technical Analysis Agent": "وكيل التحليل الفني",
  "Fundamental Analysis Agent": "وكيل التحليل الأساسي",
  "News Intelligence Agent": "وكيل ذكاء الأخبار",
  "Market Sentiment Agent": "وكيل معنويات السوق",
  "Risk Management Agent": "وكيل إدارة المخاطر",
  "Liquidity & Volume Agent": "وكيل السيولة والحجم",
  "Macro Economy Agent": "وكيل الاقتصاد الكلي",
  "Portfolio Allocation Agent": "وكيل تخصيص المحفظة",
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
