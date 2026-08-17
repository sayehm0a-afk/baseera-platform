import { apiFetch } from "./client";
import type {
  AnalystReport,
  DecisionV2,
  FundamentalAnalysis,
  History,
  InvestmentDecision,
  Quote,
  Recommendation,
  Stock,
  StockDirectory,
  StockSearch,
  TechnicalAnalysis,
} from "./stocks-types";

/** Every function here is a direct, unmodified call to an existing
 * `/api/v1/stocks/*` route (src/api/routes/stocks.py) -- no technical/
 * fundamental/recommendation/decision logic is re-derived here. */

export function getStock(symbol: string): Promise<Stock> {
  return apiFetch<Stock>(`/api/v1/stocks/${encodeURIComponent(symbol)}`);
}

/** Search the registered symbol universe by Tadawul symbol, Arabic
 * company name, or English company name (GET /api/v1/stocks/search). */
export function searchStocks(query: string, limit = 20): Promise<StockSearch> {
  const search = new URLSearchParams({ q: query, limit: String(limit) });
  return apiFetch<StockSearch>(`/api/v1/stocks/search?${search.toString()}`);
}

/** All-Stocks directory (Phase F): every active symbol with its
 * current price + daily change %, computed entirely from already-
 * persisted data (GET /api/v1/stocks/directory) -- never a live
 * SAHMK call. */
export function getStockDirectory(params?: {
  q?: string;
  sector?: string;
  limit?: number;
  offset?: number;
}): Promise<StockDirectory> {
  const search = new URLSearchParams();
  if (params?.q) search.set("q", params.q);
  if (params?.sector) search.set("sector", params.sector);
  if (params?.limit != null) search.set("limit", String(params.limit));
  if (params?.offset != null) search.set("offset", String(params.offset));
  const query = search.toString() ? `?${search.toString()}` : "";
  return apiFetch<StockDirectory>(`/api/v1/stocks/directory${query}`);
}

export function getQuote(symbol: string): Promise<Quote> {
  return apiFetch<Quote>(`/api/v1/stocks/${encodeURIComponent(symbol)}/quote`);
}

/** `start`/`end` are the route's real query params (ISO-8601
 * datetimes) -- both optional; omitting both returns all ingested
 * history, which is what the stock-detail chart wants by default. */
export function getHistory(
  symbol: string,
  params?: { start?: string; end?: string }
): Promise<History> {
  const search = new URLSearchParams();
  if (params?.start) search.set("start", params.start);
  if (params?.end) search.set("end", params.end);
  const query = search.toString() ? `?${search.toString()}` : "";
  return apiFetch<History>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/history${query}`
  );
}

export function getTechnicalAnalysis(symbol: string): Promise<TechnicalAnalysis> {
  return apiFetch<TechnicalAnalysis>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/technical`
  );
}

export function getFundamentalAnalysis(symbol: string): Promise<FundamentalAnalysis> {
  return apiFetch<FundamentalAnalysis>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/fundamentals`
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

/** Decision Engine V2 (Phase 1): the Arabic-labeled, gate-checked
 * executive decision -- entry zone, up to 3 targets, holding period,
 * eight sub-scores, and the full gate list. See
 * src/analysis/decision_v2/ and this route's own docstring. */
export function getDecisionV2(symbol: string): Promise<DecisionV2> {
  return apiFetch<DecisionV2>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/decision-v2`
  );
}

export function getAnalystReport(symbol: string): Promise<AnalystReport> {
  return apiFetch<AnalystReport>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/analyst-report`
  );
}
