"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";

export type ResourceState<T> =
  | { status: "loading" }
  | { status: "not_found" }
  | { status: "insufficient_data" }
  | { status: "unavailable" }
  | { status: "error" }
  | { status: "ready"; data: T };

/** Single-object counterpart to useCategoryFetch.ts's array-shaped
 * pattern -- fetches one resource keyed by `key` (e.g. a stock
 * symbol), classifying failures by the backend's stable `error.code`
 * (src/api/exceptions.py) instead of collapsing everything into one
 * generic "error" state, so a caller can render "this symbol doesn't
 * exist" differently from "not enough history yet" or "the data
 * provider is temporarily unavailable." Re-fetches whenever `key`
 * changes; a stale in-flight request for a superseded key is ignored,
 * never applied. Always fetches (mirrors useCategoryFetch.ts's own
 * convention) -- a caller that must skip fetching under some condition
 * pushes that guard into its own wrapped fetcher, not into this hook. */
export function useResource<T>(
  key: string,
  fetcher: (key: string) => Promise<T>
): ResourceState<T> {
  const [result, setResult] = useState<{ key: string } & ResourceState<T>>({
    key: "",
    status: "loading",
  });

  useEffect(() => {
    let cancelled = false;

    fetcher(key)
      .then((data) => {
        if (cancelled) return;
        setResult({ key, status: "ready", data });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError) {
          if (error.code === "stock_not_found") {
            setResult({ key, status: "not_found" });
            return;
          }
          if (error.code === "insufficient_data") {
            setResult({ key, status: "insufficient_data" });
            return;
          }
          if (error.code === "provider_unavailable") {
            setResult({ key, status: "unavailable" });
            return;
          }
        }
        setResult({ key, status: "error" });
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return result.key === key ? result : { status: "loading" };
}
