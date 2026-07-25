"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NavIcon } from "./NavIcon";
import { MOBILE_TAB_ITEMS } from "./nav-items";

/** The one shared bottom tab bar every authenticated screen reuses on
 * mobile (UI Spec Global Invariants §0). */
export function MobileTabBar() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="التنقل الرئيسي"
      className="flex shrink-0 items-stretch justify-around border-t border-bsr-border-subtle bg-bsr-surface-base pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      {MOBILE_TAB_ITEMS.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.key}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`flex flex-1 flex-col items-center gap-1 py-bsr-2 text-xs ${
              active ? "text-bsr-gold-500" : "text-bsr-text-secondary"
            }`}
          >
            <NavIcon name={item.key} />
            <span>{item.labelAr}</span>
          </Link>
        );
      })}
    </nav>
  );
}
