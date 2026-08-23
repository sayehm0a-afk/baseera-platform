/** Matches src/api/schemas/watchlist.py exactly -- the authenticated
 * user's own personal watchlist (distinct from WatchlistsResponse in
 * ./types.ts, which is the market-scan-derived TOP_BUY-style category
 * list, not a user's saved symbols). */

export interface WatchlistItem {
  symbol: string;
  added_at: string;

  company_name_ar: string | null;
  sector_ar: string | null;

  latest_decision: string | null;
  latest_decision_label_ar: string | null;
  latest_confidence_score: number | null;
  latest_current_price: number | null;
  latest_entry_zone_low: number | null;
  latest_entry_zone_high: number | null;
  latest_target_1: number | null;
  latest_target_2: number | null;
  latest_target_3: number | null;
  latest_stop_loss: number | null;
  latest_data_freshness_status: string | null;
  latest_decision_timestamp: string | null;
  // Production freshness fix (2026-08-23): whether `latest_decision`
  // itself (not the price it was computed from -- see
  // latest_data_freshness_status above) still belongs to the current/
  // most recently completed Tadawul session.
  latest_decision_freshness_status: string | null;
  latest_is_decision_fresh: boolean | null;

  radar_is_live_opportunity: boolean;
  radar_stage1_rank: number | null;
  radar_ranking_reason_ar: string | null;
}

export interface MyWatchlist {
  generated_at: string;
  items: WatchlistItem[];
}

/** Matches src.api.schemas.watchlist.WatchlistNewsAlertOut -- the
 * watchlist-side mirror of PortfolioNewsAlert in ./portfolio-types.ts
 * (RADAR-C Phase I). */
export interface WatchlistNewsAlert {
  id: number;
  watchlist_id: number;
  symbol: string;
  news_event_id: number;
  alert_type: string;
  severity: string;
  message: string;
  message_ar: string | null;
  generated_at: string;
  acknowledged_at: string | null;
}

export interface WatchlistNewsAlertList {
  alerts: WatchlistNewsAlert[];
}
