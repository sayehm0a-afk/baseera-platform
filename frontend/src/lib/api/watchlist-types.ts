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

  radar_is_live_opportunity: boolean;
  radar_stage1_rank: number | null;
  radar_ranking_reason_ar: string | null;
}

export interface MyWatchlist {
  generated_at: string;
  items: WatchlistItem[];
}
