"use client";

import { useCallback, useEffect, useState } from "react";
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
 * pushes that guard into its own wrapped fetcher, not into this hook.
 *
 * Also returns `reload`, a stable callback that re-runs the same
 * fetch for the current `key` -- a pure addition on top of the
 * existing `ResourceState<T>` shape (every status variant still
 * narrows exactly as before; `reload` is just an extra property
 * callers may ignore), for a caller that wants to offer a retry
 * action on an error/unavailable EmptyState. */
export function useResource<T>(
  key: string,
  fetcher: (key: string) => Promise<T>
): ResourceState<T> & { reload: () => void } {
  const [result, setResult] = useState<{ key: string } & ResourceState<T>>({
    key: "",
    status: "loading",
  });
  const [reloadToken, setReloadToken] = useState(0);

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
  }, [key, reloadToken]);

  const reload = useCallback(() => {
    // Forces the "key mismatch" branch below to loading immediately
    // (rather than keeping the stale error/data on screen until the
    // re-fetch resolves), and bumps reloadToken to re-run the effect
    // above even though `key` itself hasn't changed.
    setResult({ key: "", status: "loading" });
    setReloadToken((token) => token + 1);
  }, []);

  const state: ResourceState<T> = result.key === key ? result : { status: "loading" };
  return { ...state, reload };
}
