"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** Phase 3E: shared sub-navigation for the owner/admin section --
 * lets the new admin screens (users/sessions/feature flags/
 * announcements/audit log/analytics/AI usage) live as real pages
 * instead of dead ends with no way back to the rest of the admin
 * surface. */
const LINKS: { href: string; label: string }[] = [
  { href: "/owner", label: "لوحة الحالة" },
  { href: "/owner/live-test", label: "اختبار السوق المباشر" },
  { href: "/owner/users", label: "المستخدمون" },
  { href: "/owner/sessions", label: "الجلسات" },
  { href: "/owner/announcements", label: "الإعلانات" },
  { href: "/owner/feature-flags", label: "مفاتيح الميزات" },
  { href: "/owner/audit-log", label: "سجل التدقيق" },
  { href: "/owner/analytics", label: "التحليلات" },
  { href: "/owner/ai-usage", label: "استخدام الذكاء الاصطناعي" },
  { href: "/owner/decision-intelligence", label: "ذكاء القرار" },
  { href: "/owner/investment-committee", label: "لجنة الاستثمار" },
  { href: "/owner/recommendation-history", label: "سجل التوصيات" },
  { href: "/owner/market-coverage", label: "تغطية السوق" },
  { href: "/owner/subscriptions", label: "الاشتراكات" },
];

export function OwnerNav() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-wrap gap-bsr-2 border-b border-bsr-border-subtle pb-bsr-3">
      {LINKS.map((link) => {
        const active = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`rounded-bsr-md px-bsr-3 py-1.5 text-sm ${
              active
                ? "bg-bsr-gold-500 font-semibold text-bsr-navy-950"
                : "text-bsr-text-secondary hover:bg-bsr-surface-overlay"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
