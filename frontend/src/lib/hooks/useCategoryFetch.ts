"use client";

import { useCallback, useEffect, useState } from "react";
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
 * whenever the tag doesn't match the currently selected category.
 *
 * Also returns `reload`, a stable callback that re-runs the same
 * fetch for the current `category` -- a pure addition on top of the
 * existing `CategoryFetchState<T>` shape (every status variant still
 * narrows exactly as before; `reload` is just an extra property
 * callers may ignore), for a caller that wants to offer a retry
 * action on an error EmptyState. */
export function useCategoryFetch<T>(
  category: string,
  fetcher: (category: string) => Promise<T[]>
): CategoryFetchState<T> & { reload: () => void } {
  const [result, setResult] = useState<{ category: string } & CategoryFetchState<T>>({
    category: "",
    status: "loading",
  });
  const [reloadToken, setReloadToken] = useState(0);

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
  }, [category, fetcher, reloadToken]);

  const reload = useCallback(() => {
    // Forces the "category mismatch" branch below to loading
    // immediately (rather than keeping the stale error/entries on
    // screen until the re-fetch resolves), and bumps reloadToken to
    // re-run the effect above even though `category` hasn't changed.
    setResult({ category: "", status: "loading" });
    setReloadToken((token) => token + 1);
  }, []);

  const state: CategoryFetchState<T> = result.category === category ? result : { status: "loading" };
  return { ...state, reload };
}
