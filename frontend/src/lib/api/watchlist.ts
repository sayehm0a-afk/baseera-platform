import { apiFetch } from "./client";
import type { MyWatchlist, WatchlistItem, WatchlistNewsAlertList } from "./watchlist-types";

/** Every function here is a direct, unmodified call to an existing
 * /api/v1/watchlist/* route (src/api/routes/watchlist.py) -- the
 * authenticated user's own saved symbols, never the market-scan-
 * derived category lists getWatchlists() in ./market.ts returns. */

export function getMyWatchlist(): Promise<MyWatchlist> {
  return apiFetch<MyWatchlist>("/api/v1/watchlist");
}

export function addToWatchlist(symbol: string): Promise<WatchlistItem> {
  return apiFetch<WatchlistItem>("/api/v1/watchlist/items", {
    method: "POST",
    body: JSON.stringify({ symbol }),
  });
}

export function removeFromWatchlist(symbol: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/api/v1/watchlist/items/${symbol}`, {
    method: "DELETE",
  });
}

/** Already-persisted alerts (RADAR-C Phase I) -- see
 * refreshWatchlistNewsAlerts() to re-evaluate watched symbols against
 * the latest analyzed news. */
export function getWatchlistNewsAlerts(): Promise<WatchlistNewsAlertList> {
  return apiFetch<WatchlistNewsAlertList>("/api/v1/watchlist/news-alerts");
}

export function refreshWatchlistNewsAlerts(): Promise<WatchlistNewsAlertList> {
  return apiFetch<WatchlistNewsAlertList>("/api/v1/watchlist/news-alerts/refresh", {
    method: "POST",
  });
}
