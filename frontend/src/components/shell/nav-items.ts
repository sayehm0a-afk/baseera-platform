export interface NavItem {
  key: string;
  labelAr: string;
  href: string;
}

/** The 10-item primary navigation, taken directly from the approved
 * dashboard mockups (desktop side nav) -- order and labels are not
 * invented. Two additive items follow it: "أفضل الفرص الآن" (/today),
 * the personal day-trading-analyst entry point -- at most 5 unique,
 * ranked opportunities in one screen, see src.market_intelligence.
 * personal_scan -- and "الرادار الذكي" (/radar), the Basirah Radar V2
 * consumer surface (src.market_intelligence.radar_v2 /
 * src.api.routes.radar): the full ranked, forward-tested opportunity
 * list rather than a top-5 personal snapshot. Neither is part of the
 * original mockup set; both are placed immediately after "الرئيسية"
 * so they are the first things a trader reaches, without removing or
 * reordering any approved item. */
export const PRIMARY_NAV_ITEMS: NavItem[] = [
  { key: "home", labelAr: "الرئيسية", href: "/dashboard" },
  { key: "today", labelAr: "أفضل الفرص الآن", href: "/today" },
  { key: "radar", labelAr: "الرادار الذكي", href: "/radar" },
  { key: "scan", labelAr: "المسح", href: "/scan" },
  { key: "watchlist", labelAr: "المراقبة", href: "/watchlist" },
  { key: "opportunities", labelAr: "الفرص", href: "/opportunities" },
  { key: "portfolio", labelAr: "المحفظة", href: "/portfolio" },
  { key: "ai", labelAr: "الذكاء الاصطناعي", href: "/ai" },
  { key: "news", labelAr: "الأخبار", href: "/news" },
  { key: "reports", labelAr: "التقارير", href: "/reports" },
  { key: "strategies", labelAr: "الاستراتيجيات", href: "/strategies" },
  { key: "settings", labelAr: "الإعدادات", href: "/settings" },
];

/** The 5-item mobile bottom tab bar from the approved mobile mockups. */
export const MOBILE_TAB_ITEMS: NavItem[] = [
  { key: "home", labelAr: "الرئيسية", href: "/dashboard" },
  { key: "scan", labelAr: "المسح", href: "/scan" },
  { key: "watchlist", labelAr: "المراقبة", href: "/watchlist" },
  { key: "news", labelAr: "الأخبار", href: "/news" },
  { key: "more", labelAr: "المزيد", href: "/more" },
];
