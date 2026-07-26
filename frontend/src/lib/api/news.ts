import { apiFetch } from "./client";
import type { NewsFeed } from "./news-types";

/** Every function here is a direct, unmodified call to an existing
 * `/api/v1/news/*` route (src/api/routes/news.py) -- no entity/
 * classification/sentiment/impact logic is re-derived on the
 * frontend; every value shown is exactly what the News Intelligence
 * Engine persisted. `POST /news/refresh` and `GET /news/sources` are
 * staff-only ops routes (src/auth/rbac.py's `require_staff_role`) and
 * are intentionally not called from the customer-facing frontend. */

export function getMarketNews(limit?: number): Promise<NewsFeed> {
  const query = limit != null ? `?limit=${limit}` : "";
  return apiFetch<NewsFeed>(`/api/v1/news/market${query}`);
}

export function getSymbolNews(symbol: string, limit?: number): Promise<NewsFeed> {
  const query = limit != null ? `?limit=${limit}` : "";
  return apiFetch<NewsFeed>(
    `/api/v1/news/${encodeURIComponent(symbol)}${query}`
  );
}
