"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { NotificationBell } from "@/components/shell/NotificationBell";
import { searchStocks } from "@/lib/api/stocks";
import type { StockSearchResult } from "@/lib/api/stocks-types";

/** The one shared top app bar every authenticated screen reuses
 * (UI Spec Global Invariants §0).
 *
 * Search calls GET /api/v1/stocks/search (symbol / Arabic name /
 * English name, case-insensitive substring match against the real
 * registered symbol universe -- src/api/routes/stocks.py) and shows a
 * live results dropdown; picking a result or submitting the form both
 * navigate to /stocks/{symbol}. Typing a raw symbol with no matches
 * still navigates directly on submit, so a symbol not yet returned by
 * search (e.g. right after ingestion) is never a dead end.
 */
export function TopBar() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const trimmed = query.trim();
    let cancelled = false;
    const timer = setTimeout(() => {
      if (cancelled) return;
      if (trimmed.length < 1) {
        setResults([]);
        return;
      }
      searchStocks(trimmed, 8)
        .then((res) => {
          if (!cancelled) setResults(res.results);
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function goToSymbol(symbol: string) {
    const trimmed = symbol.trim();
    if (!trimmed) return;
    setOpen(false);
    setQuery("");
    setResults([]);
    router.push(`/stocks/${encodeURIComponent(trimmed)}`);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (results.length > 0) {
      goToSymbol(results[0].symbol);
    } else {
      goToSymbol(query);
    }
  }

  return (
    <header className="flex h-16 shrink-0 items-center gap-bsr-4 border-b border-bsr-border-subtle bg-bsr-surface-base px-bsr-4 md:px-bsr-6">
      <div className="flex items-center gap-bsr-2">
        <AiStar size="lg" label="بصيرة" />
        <span className="text-lg font-semibold text-bsr-white">بصيرة</span>
        <span className="text-lg font-semibold text-bsr-teal-500">AI</span>
      </div>

      <form onSubmit={handleSubmit} className="hidden flex-1 items-center md:flex">
        <div ref={containerRef} className="relative w-full max-w-md">
          <label>
            <span className="sr-only">ابحث برمز السهم أو اسم الشركة</span>
            <input
              type="search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setOpen(true);
              }}
              onFocus={() => setOpen(true)}
              placeholder="ابحث برمز السهم أو اسم الشركة (مثال: 2222 أو أرامكو)..."
              className="w-full rounded-bsr-full border border-bsr-border-subtle bg-bsr-surface-raised px-bsr-4 py-bsr-2 text-sm text-bsr-text-primary placeholder:text-bsr-text-muted focus:border-bsr-gold-500 focus:outline-none"
            />
          </label>

          {open && results.length > 0 ? (
            <ul className="absolute end-0 start-0 top-full z-20 mt-bsr-1 max-h-80 overflow-y-auto rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised py-bsr-1 shadow-lg">
              {results.map((result) => (
                <li key={result.symbol}>
                  <button
                    type="button"
                    onClick={() => goToSymbol(result.symbol)}
                    className="flex w-full items-center justify-between gap-bsr-3 px-bsr-4 py-bsr-2 text-start hover:bg-bsr-surface-overlay"
                  >
                    <span className="flex flex-col">
                      <span className="text-sm text-bsr-text-primary">
                        {result.name_ar ?? result.name_en}
                      </span>
                      {result.sector_ar ?? result.sector ? (
                        <span className="text-xs text-bsr-text-secondary">{result.sector_ar ?? result.sector}</span>
                      ) : null}
                    </span>
                    <span className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
                      {result.symbol}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </form>

      <div className="ms-auto flex items-center gap-bsr-3">
        <NotificationBell />
        {/* RADAR-C/E: primary nav no longer carries a Settings item
         * (nav-items.ts) -- account/settings remain reachable here,
         * de-emphasized next to the four investment surfaces rather
         * than competing with them in SideNav/MobileTabBar. */}
        <Link
          href="/settings"
          aria-label="الإعدادات والملف الشخصي"
          className="flex h-9 w-9 items-center justify-center rounded-bsr-full bg-bsr-surface-raised text-sm font-semibold text-bsr-text-primary"
        >
          م
        </Link>
      </div>
    </header>
  );
}
