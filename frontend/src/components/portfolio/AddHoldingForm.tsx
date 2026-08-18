"use client";

import { useEffect, useRef, useState } from "react";
import { searchStocks } from "@/lib/api/stocks";
import type { StockSearchResult } from "@/lib/api/stocks-types";

/** RADAR-C Phase H: add one real, persisted holding (POST
 * /api/v1/portfolio/{id}/holdings) -- symbol/quantity/average cost
 * only, the minimum the mandate requires. Symbol suggestions reuse
 * the same GET /api/v1/stocks/search the global TopBar search already
 * calls; picking a suggestion or typing a raw symbol both work, so an
 * unlisted-yet symbol is never a dead end. */
export function AddHoldingForm({
  onAdd,
}: {
  onAdd: (symbol: string, quantity: number, averageCost: number | undefined) => Promise<void>;
}) {
  const [symbol, setSymbol] = useState("");
  const [quantity, setQuantity] = useState("");
  const [averageCost, setAverageCost] = useState("");
  const [suggestions, setSuggestions] = useState<StockSearchResult[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const trimmed = symbol.trim();
    let cancelled = false;
    const timer = setTimeout(() => {
      if (trimmed.length < 1) {
        setSuggestions([]);
        return;
      }
      searchStocks(trimmed, 6)
        .then((res) => {
          if (!cancelled) setSuggestions(res.results);
        })
        .catch(() => {
          if (!cancelled) setSuggestions([]);
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [symbol]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const trimmedSymbol = symbol.trim();
    const parsedQuantity = Number(quantity);
    if (!trimmedSymbol || !quantity.trim() || !(parsedQuantity > 0)) {
      setError("أدخل رمز السهم وكمية أكبر من صفر.");
      return;
    }

    setSubmitting(true);
    try {
      await onAdd(
        trimmedSymbol,
        parsedQuantity,
        averageCost.trim() ? Number(averageCost) : undefined
      );
      setSymbol("");
      setQuantity("");
      setAverageCost("");
      setSuggestions([]);
    } catch {
      setError("تعذّرت إضافة السهم. تحقق من الرمز وحاول مرة أخرى.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-bsr-2 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4"
    >
      <span className="text-sm font-semibold text-bsr-text-primary">إضافة سهم إلى المحفظة</span>
      <div className="grid grid-cols-1 gap-bsr-2 sm:grid-cols-[1.2fr_1fr_1fr_auto]">
        <div ref={containerRef} className="relative">
          <input
            placeholder="رمز السهم أو اسم الشركة"
            value={symbol}
            onChange={(e) => {
              setSymbol(e.target.value);
              setShowSuggestions(true);
            }}
            onFocus={() => setShowSuggestions(true)}
            className="w-full rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
          />
          {showSuggestions && suggestions.length > 0 ? (
            <ul className="absolute z-10 mt-1 w-full max-h-56 overflow-y-auto rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-raised shadow-lg">
              {suggestions.map((result) => (
                <li key={result.symbol}>
                  <button
                    type="button"
                    onClick={() => {
                      setSymbol(result.symbol);
                      setShowSuggestions(false);
                    }}
                    className="flex w-full items-center justify-between gap-bsr-2 px-bsr-3 py-bsr-2 text-start text-sm hover:bg-bsr-surface-overlay"
                  >
                    <span className="truncate text-bsr-text-primary">{result.name_ar ?? result.name_en}</span>
                    <span className="bsr-numeric shrink-0 text-bsr-text-secondary">{result.symbol}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <input
          type="number"
          min={0}
          step="1"
          placeholder="الكمية"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          className="bsr-numeric rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
        />
        <input
          type="number"
          min={0}
          step="0.01"
          placeholder="متوسط سعر الشراء"
          value={averageCost}
          onChange={(e) => setAverageCost(e.target.value)}
          className="bsr-numeric rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={submitting}
          className="rounded-bsr-md bg-bsr-gold-500 px-bsr-4 py-bsr-2 font-semibold text-bsr-navy-950 hover:bg-bsr-gold-400 disabled:opacity-60"
        >
          {submitting ? "جارٍ الإضافة..." : "إضافة"}
        </button>
      </div>
      {error ? <p className="text-sm text-bsr-market-down">{error}</p> : null}
    </form>
  );
}
