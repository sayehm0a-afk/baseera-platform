export interface NavItem {
  key: string;
  labelAr: string;
  href: string;
}

/** Single-screen focus mandate (2026-09-28, direct owner instruction
 * after a real, difficult week: "focus on ONE screen -- issuing
 * confirmed recommendations -- we don't need stock analysis or any
 * other interface"). The app's one primary destination is now the
 * Smart Radar / confirmed-recommendations screen itself.
 *
 * Every previously-listed surface (stock directory, portfolio,
 * watchlist, and everything from the earlier RADAR-C/E ten-item nav)
 * still exists as a real route with real, untouched backend data
 * behind it -- only removed from primary/mobile navigation, matching
 * this codebase's own established convention: "do not delete useful
 * capability merely because it disappears from navigation." A stock
 * is still reachable by search (TopBar) or by tapping a recommendation
 * card; portfolio/watchlist remain reachable via direct URL for anyone
 * who still wants them, just no longer competing for primary attention.
 */
export const PRIMARY_NAV_ITEMS: NavItem[] = [
  { key: "radar", labelAr: "التوصيات المؤكدة", href: "/radar" },
];

/** The mobile bottom tab bar mirrors the single primary surface. */
export const MOBILE_TAB_ITEMS: NavItem[] = PRIMARY_NAV_ITEMS;
