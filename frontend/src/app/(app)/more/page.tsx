import Link from "next/link";
import { NavIcon } from "@/components/shell/NavIcon";
import { MOBILE_TAB_ITEMS, PRIMARY_NAV_ITEMS } from "@/components/shell/nav-items";

/** The mobile bottom tab bar's "المزيد" destination -- lists every
 * primary nav item that doesn't already have its own tab (see
 * MOBILE_TAB_ITEMS in nav-items.ts), so nothing in the desktop side
 * nav becomes unreachable on a mobile viewport. */
export default function MorePage() {
  const items = PRIMARY_NAV_ITEMS.filter(
    (item) => !MOBILE_TAB_ITEMS.some((tab) => tab.key === item.key)
  );

  return (
    <div className="flex flex-col gap-bsr-4">
      <h1 className="text-lg font-semibold text-bsr-text-primary">المزيد</h1>
      <div className="flex flex-col gap-bsr-2">
        {items.map((item) => (
          <Link
            key={item.key}
            href={item.href}
            className="flex items-center gap-bsr-3 rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-raised px-bsr-4 py-bsr-3 text-bsr-text-primary transition-colors hover:border-bsr-gold-500/40"
          >
            <NavIcon name={item.key} className="text-bsr-text-secondary" />
            <span className="text-sm font-medium">{item.labelAr}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
