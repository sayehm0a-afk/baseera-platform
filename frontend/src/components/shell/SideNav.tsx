"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NavIcon } from "./NavIcon";
import { PRIMARY_NAV_ITEMS } from "./nav-items";

/** The one shared side navigation every authenticated screen reuses
 * (UI Spec Global Invariants §0). Desktop/tablet only -- mobile uses
 * MobileTabBar instead. */
export function SideNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="التنقل الرئيسي"
      className="hidden w-56 shrink-0 flex-col gap-bsr-1 border-e border-bsr-border-subtle bg-bsr-surface-base p-bsr-3 md:flex"
    >
      {PRIMARY_NAV_ITEMS.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.key}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`flex items-center gap-bsr-3 rounded-bsr-md px-bsr-3 py-bsr-2 text-sm transition-colors ${
              active
                ? "bg-bsr-surface-raised text-bsr-gold-500"
                : "text-bsr-text-secondary hover:bg-bsr-surface-raised hover:text-bsr-text-primary"
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
