export interface NavItem {
  key: string;
  labelAr: string;
  href: string;
}

/** Partial reversal of the single-screen mandate (2026-09-28, same
 * day, direct owner instruction after reviewing a competitor app):
 * a radar-only app shows a completely empty screen on any day with
 * zero confirmed recommendations -- which, given real external SAHMK
 * quota scarcity, is common. The owner's own reference screenshots
 * showed a competitor that never shows an empty screen because
 * Portfolio and Market are always populated with real holdings/prices
 * regardless of whether a signal fired that day. Restoring those two
 * surfaces alongside Radar so the app always has real content to show.
 *
 * Watchlist and everything else from the earlier RADAR-C/E four-item
 * nav still exists as a real route with real, untouched backend data
 * behind it -- only Radar/Stocks/Portfolio are back in primary nav.
 */
export const PRIMARY_NAV_ITEMS: NavItem[] = [
  { key: "radar", labelAr: "التوصيات المؤكدة", href: "/radar" },
  { key: "stocks", labelAr: "السوق", href: "/stocks" },
  { key: "portfolio", labelAr: "محفظتي", href: "/portfolio" },
];

/** The mobile bottom tab bar mirrors the three primary surfaces. */
export const MOBILE_TAB_ITEMS: NavItem[] = PRIMARY_NAV_ITEMS;
