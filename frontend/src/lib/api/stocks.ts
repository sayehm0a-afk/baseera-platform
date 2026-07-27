import { apiFetch } from "./client";
import type {
  AnalystReport,
  History,
  InvestmentDecision,
  Quote,
  Recommendation,
  Stock,
} from "./stocks-types";

/** Every function here is a direct, unmodified call to an existing
 * `/api/v1/stocks/*` route (src/api/routes/stocks.py) -- no technical/
 * fundamental/recommendation/decision logic is re-derived here. */

export function getStock(symbol: string): Promise<Stock> {
  return apiFetch<Stock>(`/api/v1/stocks/${encodeURIComponent(symbol)}`);
}

export function getQuote(symbol: string): Promise<Quote> {
  return apiFetch<Quote>(`/api/v1/stocks/${encodeURIComponent(symbol)}/quote`);
}

export function getHistory(
  symbol: string,
  params?: { timeframe?: string; limit?: number }
): Promise<History> {
  const search = new URLSearchParams();
  if (params?.timeframe) search.set("timeframe", params.timeframe);
  if (params?.limit) search.set("limit", String(params.limit));
  const query = search.toString() ? `?${search.toString()}` : "";
  return apiFetch<History>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/history${query}`
  );
}

export function getRecommendation(symbol: string): Promise<Recommendation> {
  return apiFetch<Recommendation>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/recommendation`
  );
}

export function getDecision(symbol: string): Promise<InvestmentDecision> {
  return apiFetch<InvestmentDecision>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/decision`
  );
}

export function getAnalystReport(symbol: string): Promise<AnalystReport> {
  return apiFetch<AnalystReport>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/analyst-report`
  );
}
