"use client";

import { useState } from "react";
import type { ReactNode } from "react";

/** Collapsed-by-default wrapper for advanced/deep-dive content (RADAR-C
 * Phase G: "simple outside, sophisticated inside") -- the essential
 * decision (price/entry/targets/stop/why) stays always visible outside
 * this component; only supplementary depth (full gate list, sub-score
 * breakdown, committee debate) lives behind the toggle. */
export function ExpandableSection({
  title,
  subtitle,
  defaultOpen = false,
  children,
}: {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-bsr-3 p-bsr-4 text-start"
      >
        <span className="flex flex-col gap-0.5">
          <span className="text-sm font-semibold text-bsr-text-primary">{title}</span>
          {subtitle ? <span className="text-xs text-bsr-text-secondary">{subtitle}</span> : null}
        </span>
        <span className="shrink-0 text-xs text-bsr-text-secondary">{open ? "إخفاء ▲" : "عرض التفاصيل ▼"}</span>
      </button>
      {open ? <div className="flex flex-col gap-bsr-4 border-t border-bsr-border-subtle p-bsr-4">{children}</div> : null}
    </div>
  );
}
