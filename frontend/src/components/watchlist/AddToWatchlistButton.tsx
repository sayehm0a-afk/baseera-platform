"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api/client";
import { addToWatchlist } from "@/lib/api/watchlist";

type ButtonState = "idle" | "saving" | "added" | "already_added" | "error";

interface AddToWatchlistButtonProps {
  symbol: string;
}

/** POST /api/v1/watchlist/items for the current stock page's symbol.
 * A 409 (already saved) is treated as a success state, not an error --
 * the user's intent ("keep this in my watchlist") is already true. */
export function AddToWatchlistButton({ symbol }: AddToWatchlistButtonProps) {
  const [state, setState] = useState<ButtonState>("idle");

  async function handleClick() {
    setState("saving");
    try {
      await addToWatchlist(symbol);
      setState("added");
    } catch (error) {
      if (error instanceof ApiError && error.code === "watchlist_item_already_exists") {
        setState("already_added");
      } else {
        setState("error");
      }
    }
  }

  const isSaved = state === "added" || state === "already_added";

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={handleClick}
        disabled={state === "saving" || isSaved}
        className={`rounded-bsr-md border px-bsr-3 py-1 text-xs font-semibold transition-colors ${
          isSaved
            ? "border-bsr-teal-500 bg-bsr-teal-500/10 text-bsr-teal-500"
            : "border-bsr-border-subtle bg-bsr-surface-raised text-bsr-text-secondary"
        }`}
      >
        {state === "saving"
          ? "جارٍ الإضافة..."
          : isSaved
            ? "أُضيف إلى قائمة المتابعة"
            : "أضف إلى قائمة المتابعة"}
      </button>
      {state === "error" ? (
        <span className="text-xs text-bsr-action-sell">تعذّرت الإضافة إلى قائمة المتابعة.</span>
      ) : null}
    </div>
  );
}
