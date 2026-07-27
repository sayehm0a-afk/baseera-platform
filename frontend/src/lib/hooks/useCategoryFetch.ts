"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";

export type CategoryFetchState<T> =
  | { status: "loading" }
  | { status: "unavailable" }
  | { status: "error" }
  | { status: "ready"; entries: T[] };

/** Shared "load one category's worth of data, refetch on category
 * change" pattern for Scan/Watchlist -- keeps the previous result
 * tagged with the category it belongs to instead of calling setState
 * synchronously inside the effect body (React Compiler's
 * react-hooks/set-state-in-effect rule), and renders "loading"
 * whenever the tag doesn't match the currently selected category. */
export function useCategoryFetch<T>(
  category: string,
  fetcher: (category: string) => Promise<T[]>
): CategoryFetchState<T> {
  const [result, setResult] = useState<{ category: string } & CategoryFetchState<T>>({
    category: "",
    status: "loading",
  });

  useEffect(() => {
    let cancelled = false;

    fetcher(category)
      .then((entries) => {
        if (cancelled) return;
        setResult({ category, status: "ready", entries });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError && error.code === "no_market_scan_data") {
          setResult({ category, status: "unavailable" });
        } else {
          setResult({ category, status: "error" });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [category, fetcher]);

  return result.category === category ? result : { status: "loading" };
}
