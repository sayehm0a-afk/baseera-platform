export interface NavItem {
  key: string;
  labelAr: string;
  href: string;
}

/** RADAR-C/E ("BASIRAH RADAR-C + SIMPLIFICATION MANDATE"): the
 * consumer product converges on four primary surfaces -- Smart Radar
 * (now the de facto home: market state + best opportunities, see
 * /radar's own page), the full Saudi stock directory, the user's own
 * portfolio, and their watchlist ("المتابعة" -- carries the existing
 * real-money-relevant Radar-state badges from src.api.routes.watchlist,
 * see RADAR-G). Stock Detail is reached by selecting a stock (TopBar
 * search or any card), not via a fifth nav slot.
 *
 * Every previously-listed item that is NOT one of these four
 * (dashboard/today/scan/opportunities/ai/news/reports/strategies/
 * settings) still exists as a real route with real, untouched backend
 * data behind it -- only removed from primary/mobile navigation, per
 * the mandate's explicit "do not delete useful capability merely
 * because it disappears from navigation." Settings remains reachable
 * via the profile control in TopBar rather than competing here with
 * the four investment surfaces above.
 */
export const PRIMARY_NAV_ITEMS: NavItem[] = [
  { key: "radar", labelAr: "الرادار الذكي", href: "/radar" },
  { key: "stocks", labelAr: "جميع الأسهم", href: "/stocks" },
  { key: "portfolio", labelAr: "محفظتي", href: "/portfolio" },
  { key: "watchlist", labelAr: "المتابعة", href: "/watchlist" },
];

/** The mobile bottom tab bar mirrors the four primary surfaces
 * exactly -- with only four destinations there is no overflow to
 * relegate to a "more" tab (see the now-removed /more page, which
 * existed solely to index the overflow from the previous 10-item
 * nav). */
export const MOBILE_TAB_ITEMS: NavItem[] = PRIMARY_NAV_ITEMS;
